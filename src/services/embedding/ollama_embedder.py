"""Ollama local embedding provider (scaffold — not yet implemented)."""
from __future__ import annotations
from src.services.embedding.base import EmbeddingProvider
from src.utils.logging import get_logger

logger = get_logger("pipeline.embedding.ollama")


class OllamaEmbeddingProvider(EmbeddingProvider):
    """Embed text using a locally running Ollama server.

    To activate: implement the methods below, then register in factory.py:
        factory.register_embedding("ollama", OllamaEmbeddingProvider)

    Args:
        model_name: Ollama model name (e.g., "mxbai-embed-large").
        dimensions: Embedding output dimensions (must match the model).
        base_url: Ollama server URL (default: "http://localhost:11434").
    """

    def __init__(self, model_name: str = "mxbai-embed-large",
                 dimensions: int = 1024,
                 base_url: str = "http://localhost:11434", **kwargs):
        self._dimensions = dimensions
        self._model_name = model_name
        self._base_url = base_url
        # TODO: configure requests session or httpx client for Ollama REST API

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError(
            "OllamaEmbeddingProvider.embed_batch is not yet implemented. "
            "See docs/SWAPPABLE_PARTS.md for the implementation spec."
        )
