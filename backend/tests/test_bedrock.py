from typing import Any

import pytest

from app.clients.bedrock import AMAZON_NOVA_PRO_MODEL_ID, BedrockClient, BedrockClientError


class FakeBedrockRuntime:
    def __init__(self, response: dict[str, Any] | None = None) -> None:
        self.response = response or {}
        self.calls: list[dict[str, Any]] = []

    def converse(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return self.response


def test_bedrock_client_returns_constrained_tool_input() -> None:
    runtime = FakeBedrockRuntime(
        {
            "output": {
                "message": {
                    "content": [
                        {
                            "toolUse": {
                                "name": "create_llms_txt_plan",
                                "input": {"site_name": "Example"},
                            }
                        }
                    ]
                }
            }
        }
    )
    client = BedrockClient(runtime, "amazon.nova-pro-v1:0")

    result = client.generate_json(
        system_prompt="System",
        prompt="Prompt",
        schema={"type": "object"},
        max_tokens=100,
    )

    assert result == {"site_name": "Example"}
    assert runtime.calls[0]["modelId"] == "amazon.nova-pro-v1:0"
    assert runtime.calls[0]["inferenceConfig"]["temperature"] == 0
    assert runtime.calls[0]["toolConfig"]["toolChoice"] == {
        "tool": {"name": "create_llms_txt_plan"}
    }


def test_bedrock_client_defaults_to_amazon_nova_pro() -> None:
    client = BedrockClient(FakeBedrockRuntime())

    assert client.model_id == AMAZON_NOVA_PRO_MODEL_ID


def test_bedrock_client_rejects_a_response_without_structured_output() -> None:
    client = BedrockClient(FakeBedrockRuntime({"output": {"message": {"content": []}}}), "model")

    with pytest.raises(BedrockClientError):
        client.generate_json(
            system_prompt="System",
            prompt="Prompt",
            schema={"type": "object"},
            max_tokens=100,
        )
