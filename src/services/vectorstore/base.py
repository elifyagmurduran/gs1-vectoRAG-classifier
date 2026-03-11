
"""Abstract base class for vector stores."""
from __future__ import annotations
from abc import ABC, abstractmethod
from src.dto import Document


class VectorStore(ABC):
    """Interface for vector index storage and retrieval."""

    @abstractmethod
    def save(self, documents: list[Document], output_dir: str, prefix: str) -> None:
        """Build the index from documents and save all artefacts to disk.

        Args:
            documents: List of Documents with embeddings populated.
            output_dir: Directory to write output files.
            prefix: Filename prefix for all artefacts.
        """
        ...

    @abstractmethod
    def load(self, output_dir: str, prefix: str) -> None:
        """Load a previously saved index + lookup from disk.

        Args:
            output_dir: Directory containing the artefacts.
            prefix: Filename prefix used when saving.
        """
        ...

    @abstractmethod
    def search(self, query_vector: list[float], top_k: int = 30) -> list[dict]:
        """Search the index for nearest neighbors.

        Args:
            query_vector: The query embedding vector.
            top_k: Number of nearest neighbors to return.

        Returns:
            List of dicts, each with keys: 'id', 'score', 'metadata'.
        """
        ...

