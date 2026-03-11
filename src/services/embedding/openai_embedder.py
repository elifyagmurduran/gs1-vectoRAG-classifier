"""OpenAI direct API embedding provider (scaffold — not yet implemented)."""
from __future__ import annotations
from src.services.embedding.base import EmbeddingProvider
from src.utils.logging import get_logger

logger = get_logger("pipeline.embedding.openai")


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """Embed text using the direct OpenAI API (api.openai.com).

    To activate: implement the methods below, then register in factory.py:
        factory.register_embedding("openai", OpenAIEmbeddingProvider)

    Args:
        api_key: OpenAI API key (OPENAI_API_KEY).
        model: Model name (e.g., "text-embedding-3-large").
        dimensions: Embedding output dimensions.
        batch_size: Number of texts per API call.
        max_workers: Parallel threads for batching.
    """

    def __init__(self, api_key: str, model: str = "text-embedding-3-large",
                 dimensions: int = 1024, batch_size: int = 256,
                 max_workers: int = 5, **kwargs):
        self._dimensions = dimensions
        self._model = model
        self._batch_size = batch_size
        self._max_workers = max_workers
        # TODO: initialize openai.OpenAI(api_key=api_key)

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError(
            "OpenAIEmbeddingProvider.embed_batch is not yet implemented. "
            "See docs/SWAPPABLE_PARTS.md for the implementation spec."
        )
