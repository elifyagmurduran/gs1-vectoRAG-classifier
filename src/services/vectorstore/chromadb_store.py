"""ChromaDB vector store (scaffold — not yet implemented)."""
from __future__ import annotations
from src.services.vectorstore.base import VectorStore
from src.dto import Document
from src.utils.logging import get_logger

logger = get_logger("pipeline.vectorstore.chromadb")


class ChromaDBVectorStore(VectorStore):
    """Vector store backed by ChromaDB (local persistent or client-server).

    To activate: implement the methods below, then register in factory.py:
        factory.register_vectorstore("chromadb", ChromaDBVectorStore)

    Args:
        persist_dir: Local directory for ChromaDB persistent storage.
        collection_name: ChromaDB collection name.
    """

    def __init__(self, persist_dir: str = "data/vector_store/chroma",
                 collection_name: str = "gs1_taxonomy", **kwargs):
        self._persist_dir = persist_dir
        self._collection_name = collection_name
        # TODO: initialize chromadb.PersistentClient(path=persist_dir)

    def save(self, documents: list[Document], output_dir: str, prefix: str) -> None:
        raise NotImplementedError(
            "ChromaDBVectorStore.save is not yet implemented. "
            "See docs/SWAPPABLE_PARTS.md for the implementation spec."
        )

    def load(self, output_dir: str, prefix: str) -> None:
        raise NotImplementedError(
            "ChromaDBVectorStore.load is not yet implemented. "
            "See docs/SWAPPABLE_PARTS.md for the implementation spec."
        )

    def search(self, query_vector: list[float], top_k: int = 30) -> list[dict]:
        raise NotImplementedError(
            "ChromaDBVectorStore.search is not yet implemented. "
            "See docs/SWAPPABLE_PARTS.md for the implementation spec."
        )
