from typing import Any

import pytest

from app.clients.bedrock import KIMI_K3_MODEL_ID, BedrockClient, BedrockClientError


class FakeBedrockRuntime:
    def __init__(self, response: dict[str, Any] | None = None) -> None:
        self.response = response or {}
        self.calls: list[dict[str, Any]] = []

    def converse(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return self.response


def test_bedrock_client_defaults_to_kimi_k3() -> None:
    client = BedrockClient(FakeBedrockRuntime())

    assert client.model_id == KIMI_K3_MODEL_ID



def test_bedrock_client_returns_model_text_unchanged() -> None:
    runtime = FakeBedrockRuntime(
        {
            "output": {
                "message": {
                    "content": [
                        {"reasoningContent": {"reasoningText": {"text": "thinking"}}},
                        {"text": "```markdown\n# Example\n```\n"},
                    ]
                }
            }
        }
    )
    client = BedrockClient(runtime)

    result = client.generate_text(
        system_prompt="System",
        prompt="Prompt",
        max_tokens=100,
    )

    assert result == "```markdown\n# Example\n```\n"
    assert runtime.calls[0]["inferenceConfig"] == {"maxTokens": 100}
    assert "toolConfig" not in runtime.calls[0]


def test_bedrock_client_rejects_a_response_without_text() -> None:
    client = BedrockClient(
        FakeBedrockRuntime(
            {
                "output": {
                    "message": {
                        "content": [
                            {"reasoningContent": {"reasoningText": {"text": "thinking"}}}
                        ]
                    }
                }
            }
        )
    )

    with pytest.raises(BedrockClientError, match="did not return text content"):
        client.generate_text(
            system_prompt="System",
            prompt="Prompt",
            max_tokens=100,
        )
