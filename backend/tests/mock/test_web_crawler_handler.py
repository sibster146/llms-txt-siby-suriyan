import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize("environment", ["dev", "prod"])
def test_crawl_handler_routes_dlq_and_returns_only_failed_records(monkeypatch, environment) -> None:
    path = (
        Path(__file__).parents[3] / "deployables" / environment / "lambdas/web_crawler/handler.py"
    )
    spec = importlib.util.spec_from_file_location(f"crawler_{environment}", path)
    handler = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(handler)
    monkeypatch.setenv("CRAWL_DLQ_ARN", "arn:dlq")
    calls = []

    def dead_letter(message):
        if message.get("fail"):
            raise RuntimeError("DynamoDB unavailable")
        calls.append(("dlq", message))

    service = SimpleNamespace(
        process_dead_letter=dead_letter,
        process_message=lambda message: calls.append(("crawl", message)),
    )
    monkeypatch.setattr(handler, "_web_crawler_service", lambda: service)
    result = handler.lambda_handler(
        {
            "Records": [
                {
                    "messageId": "normal",
                    "body": "{}",
                    "eventSourceARN": "arn:crawl",
                    "attributes": {"ApproximateReceiveCount": "2"},
                },
                {"messageId": "dead", "body": "{}", "eventSourceARN": "arn:dlq"},
                {
                    "messageId": "retry",
                    "body": json.dumps({"fail": True}),
                    "eventSourceARN": "arn:dlq",
                },
            ]
        },
        None,
    )
    assert calls == [("crawl", {}), ("dlq", {})]
    assert result == {"batchItemFailures": [{"itemIdentifier": "retry"}]}
