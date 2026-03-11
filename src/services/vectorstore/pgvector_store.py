"""PostgreSQL + pgvector vector store (scaffold — not yet implemented)."""
from __future__ import annotations
from src.services.vectorstore.base import VectorStore
from src.dto import Document
from src.utils.logging import get_logger

logger = get_logger("pipeline.vectorstore.pgvector")


class PgVectorVectorStore(VectorStore):
    """Vector store backed by PostgreSQL with the pgvector extension.

    To activate: implement the methods below, then register in factory.py:
        factory.register_vectorstore("pgvector", PgVectorVectorStore)

    Args:
        table: Target table name for storing vectors.
        schema: PostgreSQL schema name.
        # Connection params are shared with the DB connector via env vars.
    """

    def __init__(self, table: str = "gs1_taxonomy", schema: str = "vectors",
                 **kwargs):
        self._table = table
        self._schema = schema
        # TODO: store connection params and initialize SQLAlchemy engine

    def save(self, documents: list[Document], output_dir: str, prefix: str) -> None:
        raise NotImplementedError(
            "PgVectorVectorStore.save is not yet implemented. "
            "See docs/SWAPPABLE_PARTS.md for the implementation spec."
        )

    def load(self, output_dir: str, prefix: str) -> None:
        raise NotImplementedError(
            "PgVectorVectorStore.load is not yet implemented. "
            "See docs/SWAPPABLE_PARTS.md for the implementation spec."
        )

    def search(self, query_vector: list[float], top_k: int = 30) -> list[dict]:
        raise NotImplementedError(
            "PgVectorVectorStore.search is not yet implemented. "
            "See docs/SWAPPABLE_PARTS.md for the implementation spec."
        )
