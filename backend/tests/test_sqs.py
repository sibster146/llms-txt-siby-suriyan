import json
from typing import Any

import pytest

from app.clients.sqs import SQSClient, SQSClientError


class FakeSqsBotoClient:
    def __init__(self, response: dict[str, Any] | None = None) -> None:
        self.response = response or {"MessageId": "message-123"}
        self.calls: list[dict[str, str]] = []

    def send_message(self, **kwargs: str) -> dict[str, Any]:
        self.calls.append(kwargs)
        return self.response


def test_send_json_serializes_message_and_returns_message_id() -> None:
    boto_client = FakeSqsBotoClient()
    client = SQSClient(boto_client, "https://sqs.example/crawl")

    message_id = client.send_json({"action": "crawl_url", "payload": {"depth": 0}})

    assert message_id == "message-123"
    assert boto_client.calls == [
        {
            "QueueUrl": "https://sqs.example/crawl",
            "MessageBody": json.dumps(
                {"action": "crawl_url", "payload": {"depth": 0}},
                separators=(",", ":"),
            ),
        }
    ]


def test_send_json_rejects_response_without_message_id() -> None:
    client = SQSClient(FakeSqsBotoClient({"ResponseMetadata": {}}), "queue-url")

    with pytest.raises(SQSClientError) as error:
        client.send_json({"action": "crawl_url"})

    assert error.value.code == "SQS_INVALID_RESPONSE"
