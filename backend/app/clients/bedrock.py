import json
from typing import Any

AMAZON_NOVA_PRO_MODEL_ID = "amazon.nova-pro-v1:0"


class BedrockClientError(Exception):
    """Raised when Amazon Bedrock cannot return a usable structured response."""


class BedrockClient:
    """Small wrapper around Bedrock Converse with constrained tool output."""

    def __init__(self, client: Any, model_id: str = AMAZON_NOVA_PRO_MODEL_ID) -> None:
        self.client = client
        self.model_id = model_id

    def generate_json(
        self,
        *,
        system_prompt: str,
        prompt: str,
        schema: dict[str, Any],
        max_tokens: int,
    ) -> dict[str, Any]:
        tool_name = "create_llms_txt_plan"
        try:
            response = self.client.converse(
                modelId=self.model_id,
                system=[{"text": system_prompt}],
                messages=[{"role": "user", "content": [{"text": prompt}]}],
                inferenceConfig={"maxTokens": max_tokens, "temperature": 0},
                toolConfig={
                    "tools": [
                        {
                            "toolSpec": {
                                "name": tool_name,
                                "description": "Return the curated llms.txt plan.",
                                "inputSchema": {"json": schema},
                            }
                        }
                    ],
                    "toolChoice": {"tool": {"name": tool_name}},
                },
            )
        except Exception as error:
            raise BedrockClientError(f"Bedrock generation failed: {error}") from error

        content = response.get("output", {}).get("message", {}).get("content", [])
        for block in content:
            tool_use = block.get("toolUse") if isinstance(block, dict) else None
            if isinstance(tool_use, dict) and tool_use.get("name") == tool_name:
                result = tool_use.get("input")
                if isinstance(result, dict):
                    return result

        for block in content:
            text = block.get("text") if isinstance(block, dict) else None
            if not isinstance(text, str):
                continue
            try:
                result = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(result, dict):
                return result

        raise BedrockClientError("Bedrock did not return the requested structured plan")
