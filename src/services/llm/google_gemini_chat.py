"""Google Gemini LLM provider (scaffold — not yet implemented)."""
from __future__ import annotations
from src.services.llm.base import LLMProvider
from src.utils.logging import get_logger

logger = get_logger("pipeline.llm.google_gemini")


class GoogleGeminiLLMProvider(LLMProvider):
    """Chat completions via the Google Gemini API.

    To activate: implement the method below, then register in factory.py:
        factory.register_llm("google", GoogleGeminiLLMProvider)

    JSON mode is enforced via response_mime_type="application/json" in the
    generation config — no prompt hack needed.

    Args:
        api_key: Google API key (GOOGLE_API_KEY).
        model: Gemini model name (e.g., "gemini-2.0-flash").
        max_completion_tokens: Maximum tokens in the response.
    """

    def __init__(self, api_key: str, model: str = "gemini-2.0-flash",
                 max_completion_tokens: int = 4096, **kwargs):
        self._model = model
        self._max_completion_tokens = max_completion_tokens
        # TODO: import google.generativeai as genai; genai.configure(api_key=api_key)

    def chat(self, system_message: str, user_message: str,
             response_format: dict | None = None) -> dict:
        raise NotImplementedError(
            "GoogleGeminiLLMProvider.chat is not yet implemented. "
            "See docs/SWAPPABLE_PARTS.md for the implementation spec."
        )
