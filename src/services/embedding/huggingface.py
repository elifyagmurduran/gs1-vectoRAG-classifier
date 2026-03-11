"""HuggingFace sentence-transformers embedding provider."""
from __future__ import annotations
from sentence_transformers import SentenceTransformer
from src.services.embedding.base import EmbeddingProvider
from src.utils.logging import get_logger

logger = get_logger("pipeline.embedding.huggingface")


class HuggingFaceEmbeddingProvider(EmbeddingProvider):
    """Embed text using a local HuggingFace sentence-transformers model.

    Args:
        model_name: HuggingFace model identifier (e.g., "all-MiniLM-L6-v2").
        dimensions: Expected embedding dimensions. Note: actual dimensions
                    depend on the model. This is for compatibility checks.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2",
                 dimensions: int = 384, **kwargs):
        self._dimensions = dimensions
        self._model = SentenceTransformer(model_name)
        logger.info(f"Loaded HuggingFace model: {model_name}")

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed texts locally using sentence-transformers.

        Args:
            texts: List of strings.

        Returns:
            List of embedding vectors.
        """
        if not texts:
            return []
        embeddings = self._model.encode(texts, show_progress_bar=False)
        return [emb.tolist() for emb in embeddings]
