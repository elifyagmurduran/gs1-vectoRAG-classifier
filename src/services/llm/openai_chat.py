"""OpenAI direct API LLM provider (scaffold — not yet implemented)."""
from __future__ import annotations
from src.services.llm.base import LLMProvider
from src.utils.logging import get_logger

logger = get_logger("pipeline.llm.openai")


class OpenAILLMProvider(LLMProvider):
    """Chat completions via the direct OpenAI API (api.openai.com).

    To activate: implement the method below, then register in factory.py:
        factory.register_llm("openai", OpenAILLMProvider)

    Args:
        api_key: OpenAI API key (OPENAI_API_KEY).
        model: Model name (e.g., "gpt-4o-mini").
        max_completion_tokens: Maximum tokens in the response.
    """

    def __init__(self, api_key: str, model: str = "gpt-4o-mini",
                 max_completion_tokens: int = 4096, **kwargs):
        self._model = model
        self._max_completion_tokens = max_completion_tokens
        # TODO: initialize openai.OpenAI(api_key=api_key)

    def chat(self, system_message: str, user_message: str,
             response_format: dict | None = None) -> dict:
        raise NotImplementedError(
            "OpenAILLMProvider.chat is not yet implemented. "
            "See docs/SWAPPABLE_PARTS.md for the implementation spec."
        )
