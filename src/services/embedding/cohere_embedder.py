"""Cohere embedding provider (scaffold — not yet implemented)."""
from __future__ import annotations
from src.services.embedding.base import EmbeddingProvider
from src.utils.logging import get_logger

logger = get_logger("pipeline.embedding.cohere")


class CohereEmbeddingProvider(EmbeddingProvider):
    """Embed text using the Cohere Embed API.

    To activate: implement the methods below, then register in factory.py:
        factory.register_embedding("cohere", CohereEmbeddingProvider)

    Args:
        api_key: Cohere API key (COHERE_API_KEY).
        model: Model name (e.g., "embed-multilingual-v3.0").
        dimensions: Embedding output dimensions.
        input_type: Cohere input type ("search_document" or "search_query").
    """

    def __init__(self, api_key: str, model: str = "embed-multilingual-v3.0",
                 dimensions: int = 1024,
                 input_type: str = "search_document", **kwargs):
        self._dimensions = dimensions
        self._model = model
        self._input_type = input_type
        # TODO: initialize cohere.Client(api_key=api_key)

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError(
            "CohereEmbeddingProvider.embed_batch is not yet implemented. "
            "See docs/SWAPPABLE_PARTS.md for the implementation spec."
        )
