import importlib.util
import json
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

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
    monkeypatch.setenv("LLM_TXT_DLQ_ARN", "arn:generator-dlq")
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


@pytest.mark.parametrize("environment", ["dev", "prod"])
@pytest.mark.parametrize("failure", [None, "Bedrock request failed", "database", "malformed"])
def test_dlq_finalizes_without_regeneration_or_republishing(monkeypatch, environment, failure):
    path = (
        Path(__file__).parents[2]
        / "deployables"
        / environment
        / "lambdas/llms_txt_generator/handler.py"
    )
    spec = importlib.util.spec_from_file_location(f"generator_{environment}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv("LLM_TXT_DLQ_ARN", "arn:generator-dlq")
    table, generate, queues = Mock(), Mock(), Mock()
    monkeypatch.setattr(module, "_crawl_runs_table", lambda: table)
    monkeypatch.setattr(module, "_generator_service", generate)
    monkeypatch.setattr(module, "_retry_queues", queues)
    event = _event()
    record = event["Records"][0]
    record["eventSourceARN"] = "arn:generator-dlq"
    if failure == "database":
        table.mark_generation_failed.side_effect = RuntimeError("DynamoDB unavailable")
    elif failure == "malformed":
        record["body"] = json.dumps({"original_body": "not json"})
    elif failure:
        message = json.loads(record["body"])
        record["body"] = json.dumps({**message, "failure_reason": failure})
    result = module.lambda_handler(event, None)
    expected = [{"itemIdentifier": "message-1"}] if failure in {"database", "malformed"} else []
    assert result == {"batchItemFailures": expected}
    generate.assert_not_called()
    queues.assert_not_called()
    if failure != "malformed":
        args = table.mark_generation_failed.call_args.kwargs
        assert args["site_id"] == "site-1"
        assert args["crawl_run_id"] == "crawl-1"
        if failure == "Bedrock request failed":
            assert args["error_message"] == failure
        else:
            assert "timeout" in args["error_message"]
