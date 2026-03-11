"""Document DTO — the Data Transfer Object passed between pipeline stages.

Carries one parseable node (e.g., a GS1 taxonomy entry) from GS1Parser
through EmbeddingProvider to FAISSVectorStore.
"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class Document:
    """A single document for embedding and indexing.

    Attributes:
        id: Unique identifier (e.g., GS1 code "10000000").
        text: The text to embed — built from hierarchy path + definition.
        metadata: Arbitrary dict of metadata (level, code, title, hierarchy, etc.).
        embedding: The vector embedding (list of floats). None until embedded.
    """
    id: str
    text: str
    metadata: dict = field(default_factory=dict)
    embedding: list[float] | None = None
