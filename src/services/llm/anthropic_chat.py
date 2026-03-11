"""Anthropic Claude LLM provider (scaffold — not yet implemented)."""
from __future__ import annotations
from src.services.llm.base import LLMProvider
from src.utils.logging import get_logger

logger = get_logger("pipeline.llm.anthropic")


class AnthropicLLMProvider(LLMProvider):
    """Chat completions via the Anthropic API (Claude models).

    To activate: implement the method below, then register in factory.py:
        factory.register_llm("anthropic", AnthropicLLMProvider)

    Note: Anthropic does not support response_format={"type":"json_object"}.
    JSON mode must be enforced via prompt instruction and by pre-filling
    the assistant turn with "{". The orchestrator's regex fallback handles
    imperfect JSON output when needed.

    Args:
        api_key: Anthropic API key (ANTHROPIC_API_KEY).
        model: Model name (e.g., "claude-3-5-haiku-20241022").
        max_completion_tokens: Maximum tokens in the response.
    """

    def __init__(self, api_key: str, model: str = "claude-3-5-haiku-20241022",
                 max_completion_tokens: int = 4096, **kwargs):
        self._model = model
        self._max_completion_tokens = max_completion_tokens
        # TODO: initialize anthropic.Anthropic(api_key=api_key)

    def chat(self, system_message: str, user_message: str,
             response_format: dict | None = None) -> dict:
        raise NotImplementedError(
            "AnthropicLLMProvider.chat is not yet implemented. "
            "See docs/SWAPPABLE_PARTS.md for the implementation spec."
        )
