"""FAISS vector store — builds, saves, loads, and searches a FAISS IndexFlatL2 (L2 distance)."""
from __future__ import annotations
import json
import pickle
from datetime import datetime, timezone
from pathlib import Path

import faiss
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from src.dto import Document
from src.services.vectorstore.base import VectorStore
from src.utils.logging import get_logger
from src.utils.exceptions import VectorStoreError, VectorStoreNotLoadedError

logger = get_logger("pipeline.vectorstore.faiss")


class FAISSVectorStore(VectorStore):
    """FAISS-based vector store that produces 5 artefacts on save.

    Artefacts (per prefix):
        1. faiss_{prefix}.index        — FAISS IndexFlatIP binary (cosine similarity)
        2. faiss_{prefix}_metadata.json — Full metadata mapping (ids + metadata list)
        3. embeddings_{prefix}.parquet  — Parquet archive (id, text, embedding, metadata)
        4. {prefix}_lookup.pkl          — Compact pickle: {int(id): {metadata subset}}
        5. build_manifest.json          — Audit trail (timestamp, model, dims, doc count)

    Args:
        output_dir: Directory for artefact files.
        index_type: FAISS index type string (only "FlatIP" supported).
        filename_prefix: Prefix for all artefact filenames.
        lookup_metadata_fields: Which metadata keys to include in the lookup pickle.
        embedding_dimensions: Vector dimensionality (for manifest).
        embedding_model: Model name string (for manifest).
    """

    def __init__(self, output_dir: str = "data/vector_store",
                 index_type: str = "FlatIP",
                 filename_prefix: str = "gs1",
                 lookup_metadata_fields: list[str] | None = None,
                 embedding_dimensions: int = 1024,
                 embedding_model: str = "unknown",
                 **kwargs):
        self._output_dir = Path(output_dir)
        self._prefix = filename_prefix
        self._lookup_fields = lookup_metadata_fields or [
            "level", "code", "title", "hierarchy_path", "hierarchy_string"
        ]
        self._dimensions = embedding_dimensions
        self._model_name = embedding_model

        self._index: faiss.Index | None = None  # IndexFlatL2 (squared L2 distance)
        self._lookup: dict[int, dict] = {}    # int(id) -> metadata subset
        self._ids: list[str] = []             # index position -> doc id
        self._metadata: list[dict] = []       # index position -> full metadata

    def save(self, documents: list[Document], output_dir: str | None = None,
             prefix: str | None = None) -> None:
        """Build the FAISS index and write all 5 artefacts to disk.

        Args:
            documents: Documents with .embedding populated (list of floats).
            output_dir: Override output directory (optional).
            prefix: Override filename prefix (optional).

        Raises:
            ValueError: If any document is missing its embedding.
        """
        out = Path(output_dir) if output_dir else self._output_dir
        pfx = prefix or self._prefix
        out.mkdir(parents=True, exist_ok=True)

        # Validate all docs have embeddings
        for doc in documents:
            if doc.embedding is None:
                raise VectorStoreError(
                    f"Document {doc.id} has no embedding — run embed-rows first"
                )

        logger.info(f"Building FAISS index from {len(documents)} documents")

        # [STAGE: INDEX_BUILD]
        # Constructs the FAISS IndexFlatL2 from document embeddings.
        # Vectors are L2-normalised in-place for consistent magnitude before distance calc.
        # Build numpy matrix
        vectors = np.array([doc.embedding for doc in documents], dtype=np.float32)
        dimension = vectors.shape[1]

        # Build IndexFlatL2: normalize vectors in-place, then use squared L2 distance.
        # Scores are squared L2 distances in [0, 4] for unit vectors (lower = more similar).
        faiss.normalize_L2(vectors)            # normalize in-place for consistent magnitude
        index = faiss.IndexFlatL2(dimension)   # squared L2 distance on unit vectors
        index.add(vectors)
        index_path = out / f"faiss_{pfx}.index"
        faiss.write_index(index, str(index_path))
        logger.info(f"Saved FAISS index: {index_path} ({index.ntotal} vectors)")

        # 2. Metadata JSON
        ids = [doc.id for doc in documents]
        metadata_list = [doc.metadata for doc in documents]
        meta_path = out / f"faiss_{pfx}_metadata.json"
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump({"ids": ids, "metadata": metadata_list}, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved metadata JSON: {meta_path}")

        # 3. Parquet archive
        parquet_path = out / f"embeddings_{pfx}.parquet"
        table = pa.table({
            "id": [doc.id for doc in documents],
            "text": [doc.text for doc in documents],
            "embedding": [json.dumps(doc.embedding) for doc in documents],
            "metadata": [json.dumps(doc.metadata, ensure_ascii=False) for doc in documents],
        })
        pq.write_table(table, str(parquet_path))
        logger.info(f"Saved parquet archive: {parquet_path}")

        # 4. Lookup pickle
        lookup = {}
        for doc in documents:
            try:
                key = int(doc.id)
            except (ValueError, TypeError):
                key = doc.id
            lookup[key] = {k: doc.metadata.get(k) for k in self._lookup_fields}
        lookup_path = out / f"{pfx}_lookup.pkl"
        with open(lookup_path, "wb") as f:
            pickle.dump(lookup, f)
        logger.info(f"Saved lookup pickle: {lookup_path}")

        # 5. Build manifest
        manifest = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "model": self._model_name,
            "dimensions": dimension,
            "document_count": len(documents),
            "index_type": "FlatL2",
            "prefix": pfx,
        }
        manifest_path = out / "build_manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)
        logger.info(f"Saved build manifest: {manifest_path}")

    def load(self, output_dir: str | None = None, prefix: str | None = None) -> None:
        """Load the FAISS index and lookup pickle from disk.

        Args:
            output_dir: Directory containing artefacts.
            prefix: Filename prefix.

        Raises:
            FileNotFoundError: If required files are missing.
        """
        out = Path(output_dir) if output_dir else self._output_dir
        pfx = prefix or self._prefix

        # Load FAISS index
        index_path = out / f"faiss_{pfx}.index"
        if not index_path.exists():
            raise VectorStoreError(
                f"FAISS index not found: {index_path}",
                index_path=str(index_path),
            )
        self._index = faiss.read_index(str(index_path))
        logger.info(f"Loaded FAISS index: {index_path} ({self._index.ntotal} vectors)")

        # Load lookup pickle
        lookup_path = out / f"{pfx}_lookup.pkl"
        if not lookup_path.exists():
            raise VectorStoreError(
                f"Lookup file not found: {lookup_path}",
                index_path=str(lookup_path),
            )
        with open(lookup_path, "rb") as f:
            self._lookup = pickle.load(f)
        logger.info(f"Loaded lookup: {lookup_path} ({len(self._lookup)} entries)")

        # Load metadata for id mapping
        meta_path = out / f"faiss_{pfx}_metadata.json"
        if meta_path.exists():
            with open(meta_path, "r", encoding="utf-8") as f:
                meta_data = json.load(f)
            self._ids = meta_data.get("ids", [])
            self._metadata = meta_data.get("metadata", [])

    def search(self, query_vector: list[float], top_k: int = 30) -> list[dict]:
        """Search the loaded FAISS index for nearest neighbors.

        Args:
            query_vector: Query embedding (list of floats).
            top_k: Number of neighbors to retrieve.

        Returns:
            List of dicts with keys: 'id', 'score', 'metadata'.
            Scores are squared L2 distances in [0, 4] for unit vectors (lower = more similar).
            FAISS returns results in ascending order (lower score = more similar).

        Raises:
            RuntimeError: If index is not loaded.
        """
        if self._index is None:
            raise VectorStoreNotLoadedError()

        # [STAGE: CANDIDATE_RETRIEVAL]
        # Executes nearest-neighbour search against the loaded FAISS IndexFlatL2.
        # L2-normalise the query vector for consistent magnitude before distance calc.
        query = np.array([query_vector], dtype=np.float32)
        faiss.normalize_L2(query)  # in-place; normalise for consistent magnitude

        distances, indices = self._index.search(query, top_k)

        results = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx == -1:
                continue  # FAISS returns -1 for missing results
            doc_id = self._ids[idx] if idx < len(self._ids) else str(idx)

            # Look up metadata from pickle (by int key) or from metadata JSON
            metadata = {}
            try:
                metadata = self._lookup.get(int(doc_id), {})
            except (ValueError, TypeError):
                if idx < len(self._metadata):
                    metadata = self._metadata[idx]

            results.append({
                "id": doc_id,
                "score": float(dist),
                "metadata": metadata,
            })

        return results

    def search_batch(
        self,
        query_vectors: list[list[float]],
        top_k: int = 30,
    ) -> list[list[dict]]:
        """Batch search: one FAISS index.search() call for all query vectors at once.

        Replaces N individual search() calls with a single vectorized operation,
        one result list per input query.

        Args:
            query_vectors: N query embeddings (each a list of floats).
            top_k: Number of nearest neighbors to retrieve per query.

        Returns:
            List of N result lists, one per input query. Same structure as search().
        """
        if self._index is None:
            raise VectorStoreNotLoadedError()

        query_matrix = np.array(query_vectors, dtype=np.float32)
        faiss.normalize_L2(query_matrix)  # in-place; normalise for consistent magnitude

        distances, indices = self._index.search(query_matrix, top_k)

        all_results: list[list[dict]] = []
        for dist_row, idx_row in zip(distances, indices):
            per_query: list[dict] = []
            for dist, idx in zip(dist_row, idx_row):
                if idx == -1:
                    continue
                doc_id = self._ids[idx] if idx < len(self._ids) else str(idx)
                metadata: dict = {}
                try:
                    metadata = self._lookup.get(int(doc_id), {})
                except (ValueError, TypeError):
                    if idx < len(self._metadata):
                        metadata = self._metadata[idx]
                per_query.append({
                    "id": doc_id,
                    "score": float(dist),
                    "metadata": metadata,
                })
            all_results.append(per_query)

        return all_results
