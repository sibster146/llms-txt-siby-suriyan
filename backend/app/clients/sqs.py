import json
from typing import Any


class SQSClientError(Exception):
    """Raised when an SQS operation fails."""

    def __init__(self, message: str, code: str = "SQS_CLIENT_ERROR") -> None:
        super().__init__(message)
        self.code = code


class SQSClient:
    """Application wrapper around one SQS queue."""

    def __init__(self, client: Any, queue_url: str) -> None:
        self.client = client
        self.queue_url = queue_url

    def send_json(self, message: dict[str, Any], *, delay_seconds: int | None = None) -> str:
        request: dict[str, Any] = {
            "QueueUrl": self.queue_url,
            "MessageBody": json.dumps(message, separators=(",", ":")),
        }
        if delay_seconds is not None:
            if not 0 <= delay_seconds <= 900:
                raise ValueError("delay_seconds must be between 0 and 900")
            request["DelaySeconds"] = delay_seconds

        try:
            response = self.client.send_message(**request)
        except Exception as error:
            raise SQSClientError(
                f"Failed to send SQS message: {error}",
                code="SQS_SEND_MESSAGE_FAILED",
            ) from error

        message_id = response.get("MessageId")
        if not isinstance(message_id, str) or not message_id:
            raise SQSClientError(
                "SQS did not return a message ID.",
                code="SQS_INVALID_RESPONSE",
            )
        return message_id
