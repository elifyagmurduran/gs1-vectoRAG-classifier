"""Azure AI Search vector store (scaffold — not yet implemented)."""
from __future__ import annotations
from src.services.vectorstore.base import VectorStore
from src.dto import Document
from src.utils.logging import get_logger

logger = get_logger("pipeline.vectorstore.azure_ai_search")


class AzureAISearchVectorStore(VectorStore):
    """Vector store backed by Azure AI Search (formerly Cognitive Search).

    To activate: implement the methods below, then register in factory.py:
        factory.register_vectorstore("azure_search", AzureAISearchVectorStore)

    Args:
        index_name: Azure AI Search index name.
        endpoint: Azure AI Search service endpoint (AZURE_SEARCH_ENDPOINT).
        api_key: Azure AI Search admin key (AZURE_SEARCH_API_KEY).
    """

    def __init__(self, index_name: str = "gs1-taxonomy",
                 endpoint: str = "", api_key: str = "",
                 **kwargs):
        self._index_name = index_name
        self._endpoint = endpoint
        self._api_key = api_key
        # TODO: initialize azure.search.documents.SearchClient

    def save(self, documents: list[Document], output_dir: str, prefix: str) -> None:
        raise NotImplementedError(
            "AzureAISearchVectorStore.save is not yet implemented. "
            "See docs/SWAPPABLE_PARTS.md for the implementation spec."
        )

    def load(self, output_dir: str, prefix: str) -> None:
        raise NotImplementedError(
            "AzureAISearchVectorStore.load is not yet implemented. "
            "See docs/SWAPPABLE_PARTS.md for the implementation spec."
        )

    def search(self, query_vector: list[float], top_k: int = 30) -> list[dict]:
        raise NotImplementedError(
            "AzureAISearchVectorStore.search is not yet implemented. "
            "See docs/SWAPPABLE_PARTS.md for the implementation spec."
        )
