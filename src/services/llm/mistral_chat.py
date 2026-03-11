"""Mistral AI LLM provider (scaffold — not yet implemented)."""
from __future__ import annotations
from src.services.llm.base import LLMProvider
from src.utils.logging import get_logger

logger = get_logger("pipeline.llm.mistral")


class MistralLLMProvider(LLMProvider):
    """Chat completions via the Mistral AI API.

    To activate: implement the method below, then register in factory.py:
        factory.register_llm("mistral", MistralLLMProvider)

    Mistral supports response_format={"type": "json_object"} on
    mistral-small and mistral-large. Strong multilingual support.

    Args:
        api_key: Mistral API key (MISTRAL_API_KEY).
        model: Model name (e.g., "mistral-small-latest").
        max_completion_tokens: Maximum tokens in the response.
    """

    def __init__(self, api_key: str, model: str = "mistral-small-latest",
                 max_completion_tokens: int = 4096, **kwargs):
        self._model = model
        self._max_completion_tokens = max_completion_tokens
        # TODO: initialize mistralai.Mistral(api_key=api_key)

    def chat(self, system_message: str, user_message: str,
             response_format: dict | None = None) -> dict:
        raise NotImplementedError(
            "MistralLLMProvider.chat is not yet implemented. "
            "See docs/SWAPPABLE_PARTS.md for the implementation spec."
        )
