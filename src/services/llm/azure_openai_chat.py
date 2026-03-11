
"""Azure OpenAI LLM provider for chat completions."""
from __future__ import annotations
from openai import AzureOpenAI, RateLimitError
from src.services.llm.base import LLMProvider
from src.utils.retry import make_retry_decorator
from src.utils.logging import get_logger
from src.utils.exceptions import LLMError

logger = get_logger("pipeline.llm.azure_openai")


class AzureOpenAILLMProvider(LLMProvider):
    """Chat completion via Azure OpenAI (o-series and later models).

    Args:
        api_key: Azure OpenAI API key.
        endpoint: Azure OpenAI endpoint URL.
        deployment: Deployment name (e.g., "o4-mini").
        api_version: API version string.
        model: Model name for logging.
        max_completion_tokens: Maximum tokens in the response.
        max_attempts: Retry attempts on rate limit.
        backoff_factor: Exponential backoff multiplier.
        min_wait: Minimum retry wait seconds.
        max_wait: Maximum retry wait seconds.
    """

    def __init__(self, api_key: str, endpoint: str, deployment: str,
                 api_version: str, model: str = "o4-mini",
                 max_completion_tokens: int = 4096,
                 max_attempts: int = 3, backoff_factor: float = 1.5,
                 min_wait: float = 30, max_wait: float = 120,
                 **kwargs):
        self._deployment = deployment
        self._model = model
        self._max_completion_tokens = max_completion_tokens

        self._client = AzureOpenAI(
            api_key=api_key,
            azure_endpoint=endpoint,
            api_version=api_version,
        )

        self._retry = make_retry_decorator(
            max_attempts=max_attempts,
            backoff_factor=backoff_factor,
            min_wait=min_wait,
            max_wait=max_wait,
            retry_on=(RateLimitError,),
        )

    def chat(self, system_message: str, user_message: str,
             response_format: dict | None = None) -> dict:
        """Send a chat completion request to Azure OpenAI.

        Args:
            system_message: System prompt.
            user_message: User prompt.
            response_format: e.g., {"type": "json_object"} to force JSON output.

        Returns:
            Dict with 'content' (str) and 'usage' (dict with token counts).
        """
        @self._retry
        def _call():
            kwargs = {
                "model": self._deployment,
                "messages": [
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": user_message},
                ],
                "max_completion_tokens": self._max_completion_tokens,
            }
            if response_format:
                kwargs["response_format"] = response_format

            try:
                response = self._client.chat.completions.create(**kwargs)
            except Exception as exc:
                raise LLMError(
                    str(exc),
                    deployment=self._deployment,
                    model=self._model,
                ) from exc

            content = response.choices[0].message.content
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }
            logger.debug("LLM response: %d chars, %d tokens", len(content), usage["total_tokens"])
            return {"content": content, "usage": usage}

        return _call()

