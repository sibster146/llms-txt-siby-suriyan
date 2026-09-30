from typing import Any

KIMI_K3_MODEL_ID = "us.moonshotai.kimi-k3"


class BedrockClientError(Exception):
    """Raised when Bedrock generation fails or returns no usable JSON or text."""


class BedrockClient:
    """Small wrapper around Amazon Bedrock Converse."""

    def __init__(self, client: Any, model_id: str = KIMI_K3_MODEL_ID) -> None:
        """Store an injected Bedrock Runtime client and the model to invoke.

        Args:
            client: A boto3-compatible client exposing the Converse API.
            model_id: Bedrock model or inference profile ID; defaults to Kimi K3.

        No network request is made during initialization.
        """
        self.client = client
        self.model_id = model_id

    def generate_text(
        self,
        *,
        system_prompt: str,
        prompt: str,
        max_tokens: int,
    ) -> str:
        """Generate text through Converse without structured-output validation.

        Args:
            system_prompt: Instructions provided in the system message.
            prompt: User message containing the generation request and source data.
            max_tokens: Maximum output token count requested from Bedrock.

        Returns:
            All string-valued text blocks concatenated in response order without
            added separators. Whitespace and Markdown fences are preserved;
            non-text blocks are ignored.

        Raises:
            BedrockClientError: If the Converse request fails or the concatenated
                text is empty.

        Temperature is set to zero except for Kimi K3. This method does not check
        llms.txt formatting or whether generation stopped at the token limit.
        """
        inference_config: dict[str, Any] = {"maxTokens": max_tokens}
        try:
            response = self.client.converse(
                modelId=self.model_id,
                system=[{"text": system_prompt}],
                messages=[{"role": "user", "content": [{"text": prompt}]}],
                inferenceConfig=inference_config,
            )
        except Exception as error:
            raise BedrockClientError(f"Bedrock generation failed: {error}") from error

        content = response.get("output", {}).get("message", {}).get("content", [])
        text = "".join(
            block["text"]
            for block in content
            if isinstance(block, dict) and isinstance(block.get("text"), str)
        )
        if not text:
            raise BedrockClientError("Bedrock did not return text content")
        return text
