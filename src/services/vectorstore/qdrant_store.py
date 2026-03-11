"""Qdrant vector store (scaffold — not yet implemented)."""
from __future__ import annotations
from src.services.vectorstore.base import VectorStore
from src.dto import Document
from src.utils.logging import get_logger

logger = get_logger("pipeline.vectorstore.qdrant")


class QdrantVectorStore(VectorStore):
    """Vector store backed by Qdrant (local Docker or cloud).

    To activate: implement the methods below, then register in factory.py:
        factory.register_vectorstore("qdrant", QdrantVectorStore)

    Args:
        collection_name: Qdrant collection name.
        url: Qdrant server URL.
    """

    def __init__(self, collection_name: str = "gs1_taxonomy",
                 url: str = "http://localhost:6333",
                 **kwargs):
        self._collection_name = collection_name
        self._url = url
        # TODO: initialize qdrant_client.QdrantClient(url=url)

    def save(self, documents: list[Document], output_dir: str, prefix: str) -> None:
        raise NotImplementedError(
            "QdrantVectorStore.save is not yet implemented. "
            "See docs/SWAPPABLE_PARTS.md for the implementation spec."
        )

    def load(self, output_dir: str, prefix: str) -> None:
        raise NotImplementedError(
            "QdrantVectorStore.load is not yet implemented. "
            "See docs/SWAPPABLE_PARTS.md for the implementation spec."
        )

    def search(self, query_vector: list[float], top_k: int = 30) -> list[dict]:
        raise NotImplementedError(
            "QdrantVectorStore.search is not yet implemented. "
            "See docs/SWAPPABLE_PARTS.md for the implementation spec."
        )
