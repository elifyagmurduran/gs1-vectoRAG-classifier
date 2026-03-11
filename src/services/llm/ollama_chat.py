"""Ollama local LLM provider (scaffold — not yet implemented)."""
from __future__ import annotations
from src.services.llm.base import LLMProvider
from src.utils.logging import get_logger

logger = get_logger("pipeline.llm.ollama")


class OllamaLLMProvider(LLMProvider):
    """Chat completions via a locally running Ollama server.

    To activate: implement the method below, then register in factory.py:
        factory.register_llm("ollama", OllamaLLMProvider)

    Ollama exposes an OpenAI-compatible endpoint at /v1/chat/completions,
    so this can use the openai SDK with base_url pointing to Ollama.

    Args:
        model: Ollama model name (e.g., "llama3.2", "mistral", "qwen2.5").
        base_url: Ollama server URL (default: "http://localhost:11434").
        max_completion_tokens: Maximum tokens in the response.
    """

    def __init__(self, model: str = "llama3.2",
                 base_url: str = "http://localhost:11434",
                 max_completion_tokens: int = 4096, **kwargs):
        self._model = model
        self._base_url = base_url
        self._max_completion_tokens = max_completion_tokens
        # TODO: initialize openai.OpenAI(base_url=f"{base_url}/v1", api_key="ollama")

    def chat(self, system_message: str, user_message: str,
             response_format: dict | None = None) -> dict:
        raise NotImplementedError(
            "OllamaLLMProvider.chat is not yet implemented. "
            "See docs/SWAPPABLE_PARTS.md for the implementation spec."
        )
