import importlib.util
import json
from pathlib import Path
from typing import Any

HANDLER_PATH = (
    Path(__file__).parents[2]
    / "deployables"
    / "dev"
    / "lambdas"
    / "llms_txt_generator"
    / "handler.py"
)
SPEC = importlib.util.spec_from_file_location("llms_txt_generator_handler", HANDLER_PATH)
assert SPEC is not None and SPEC.loader is not None
handler = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(handler)


class FakeQueue:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.messages: list[tuple[dict[str, Any], int | None]] = []

    def send_json(
        self,
        message: dict[str, Any],
        *,
        delay_seconds: int | None = None,
    ) -> str:
        if self.fail:
            raise RuntimeError("queue unavailable")
        self.messages.append((message, delay_seconds))
        return "message-id"


def _event(*, attempt: int | None = None) -> dict[str, Any]:
    message: dict[str, Any] = {
        "action": "generate_llms_txt",
        "payload": {"site_id": "site-1", "crawl_run_id": "crawl-1"},
    }
    if attempt is not None:
        message["retry_attempt"] = attempt
    return {
        "Records": [
            {
                "messageId": "message-1",
                "body": json.dumps(message),
            }
        ]
    }


def _configure(monkeypatch: Any, retry: FakeQueue, dlq: FakeQueue) -> None:
    monkeypatch.setenv("GENERATOR_MAX_ATTEMPTS", "4")
    monkeypatch.setenv("GENERATOR_RETRY_DELAY_SECONDS", "30")
    monkeypatch.setattr(handler, "_retry_queues", lambda: (retry, dlq))
    monkeypatch.setattr(
        handler,
        "_process_record",
        lambda _: (_ for _ in ()).throw(RuntimeError("generation failed")),
    )


def test_failed_generation_schedules_a_delayed_retry(monkeypatch: Any) -> None:
    retry = FakeQueue()
    dlq = FakeQueue()
    _configure(monkeypatch, retry, dlq)

    result = handler.lambda_handler(_event(), None)

    assert result == {"batchItemFailures": []}
    assert retry.messages[0][0]["retry_attempt"] == 2
    assert retry.messages[0][1] == 30
    assert dlq.messages == []


def test_fourth_failed_attempt_is_sent_to_the_dlq(monkeypatch: Any) -> None:
    retry = FakeQueue()
    dlq = FakeQueue()
    _configure(monkeypatch, retry, dlq)

    result = handler.lambda_handler(_event(attempt=4), None)

    assert result == {"batchItemFailures": []}
    assert retry.messages == []
    assert dlq.messages[0][0]["retry_attempt"] == 4
    assert dlq.messages[0][0]["failure_reason"] == "generation failed"


def test_original_message_is_retried_if_scheduling_fails(monkeypatch: Any) -> None:
    retry = FakeQueue(fail=True)
    _configure(monkeypatch, retry, FakeQueue())

    result = handler.lambda_handler(_event(), None)

    assert result == {"batchItemFailures": [{"itemIdentifier": "message-1"}]}


def test_leased_message_uses_native_sqs_retry_without_scheduling_a_copy(
    monkeypatch: Any,
) -> None:
    retry = FakeQueue()
    dlq = FakeQueue()
    monkeypatch.setattr(handler, "_retry_queues", lambda: (retry, dlq))
    monkeypatch.setattr(
        handler,
        "_process_record",
        lambda _: (_ for _ in ()).throw(handler.GenerationLeaseUnavailableError("already leased")),
    )

    result = handler.lambda_handler(_event(), None)

    assert result == {"batchItemFailures": [{"itemIdentifier": "message-1"}]}
    assert retry.messages == []
    assert dlq.messages == []
