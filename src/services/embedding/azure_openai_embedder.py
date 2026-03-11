"""Azure OpenAI embedding provider using the openai Python SDK."""
from __future__ import annotations
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from openai import AzureOpenAI, RateLimitError
from src.services.embedding.base import EmbeddingProvider
from src.utils.retry import make_retry_decorator
from src.utils.batching import iter_batches
from src.utils.logging import get_logger

logger = get_logger("pipeline.embedding.azure_openai")


class AzureOpenAIEmbeddingProvider(EmbeddingProvider):
    """Embed text using Azure OpenAI text-embedding-3-large.

    Args:
        api_key: Azure OpenAI API key.
        endpoint: Azure OpenAI endpoint URL.
        deployment: Deployment name (e.g., "text-embedding-3-large").
        api_version: API version string.
        dimensions: Embedding dimensions (default 1024).
        batch_size: Texts per API call (default 256).
        max_workers: Parallel threads for batched calls (default 5).
        max_attempts: Retry attempts on rate limit errors.
        backoff_factor: Exponential backoff multiplier.
        min_wait: Minimum wait between retries (seconds).
        max_wait: Maximum wait between retries (seconds).
    """

    def __init__(self, api_key: str, endpoint: str, deployment: str,
                 api_version: str, dimensions: int = 1024,
                 batch_size: int = 256, max_workers: int = 5,
                 max_attempts: int = 3, backoff_factor: float = 1.5,
                 min_wait: float = 30, max_wait: float = 120,
                 **kwargs):
        self._dimensions = dimensions
        self._batch_size = batch_size
        self._max_workers = max_workers
        self._deployment = deployment

        self._client = AzureOpenAI(
            api_key=api_key,
            azure_endpoint=endpoint,
            api_version=api_version,
        )

        # Build retry decorator for rate limits
        self._retry = make_retry_decorator(
            max_attempts=max_attempts,
            backoff_factor=backoff_factor,
            min_wait=min_wait,
            max_wait=max_wait,
            retry_on=(RateLimitError,),
        )

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed texts using parallel batched API calls.

        Args:
            texts: List of strings to embed.

        Returns:
            List of embedding vectors in the same order as input texts.
        """
        if not texts:
            return []

        all_embeddings: list[tuple[int, list[float]]] = []
        sub_batches = list(iter_batches(texts, self._batch_size))

        logger.info(f"Embedding {len(texts)} texts in {len(sub_batches)} sub-batches "
                     f"({self._max_workers} workers)")

        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            futures = {}
            for batch_idx, sub_batch in enumerate(sub_batches):
                future = executor.submit(self._embed_single_batch, sub_batch)
                futures[future] = batch_idx

            for future in as_completed(futures):
                batch_idx = futures[future]
                embeddings = future.result()
                offset = batch_idx * self._batch_size
                for i, emb in enumerate(embeddings):
                    all_embeddings.append((offset + i, emb))

        # Sort by original index to preserve order
        all_embeddings.sort(key=lambda x: x[0])
        return [emb for _, emb in all_embeddings]

    def _embed_single_batch(self, texts: list[str]) -> list[list[float]]:
        """Call the API for one sub-batch, with retry on rate limits."""
        @self._retry
        def _call():
            response = self._client.embeddings.create(
                input=texts,
                model=self._deployment,
                dimensions=self._dimensions,
            )
            return [item.embedding for item in response.data]
        return _call()
