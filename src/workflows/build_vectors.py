"""build-vectors workflow: JSON → parse → embed → FAISS index + artefacts."""
from __future__ import annotations
import time
from src.config.models import AppConfig
from src.services.gs1_parser import GS1Parser
from src.services.embedding.base import EmbeddingProvider
from src.services.vectorstore.base import VectorStore
from src.utils.batching import iter_batches
from src.utils.logging import get_logger
from src.utils.console import console

logger = get_logger("pipeline.workflow.build_vectors")


def run_build_vectors(config: AppConfig, embedding_provider: EmbeddingProvider,
                      vector_store: VectorStore) -> None:
    """Execute the build-vectors pipeline.

    Steps:
        1. Parse the source JSON into Documents.
        2. Embed all documents in batches.
        3. Save the FAISS index + all artefacts.

    Args:
        config: Validated app config.
        embedding_provider: Initialized embedding provider.
        vector_store: Initialized vector store (will call .save()).
    """
    # [STAGE: PARSE_SOURCE]
    # Reads data/input/GS1.json, traverses the hierarchy tree recursively,
    # and emits one Document per node (L1 Segment → L6 AttributeValue).
    console.step("Parsing source JSON")
    parse_start = time.time()
    parser = GS1Parser(
        file_path=config.source.path,
        encoding=config.source.encoding,
    )
    documents = parser.parse()
    parse_elapsed = time.time() - parse_start
    logger.info("Parsed %d documents from %s (%.1fs)", len(documents), config.source.path, parse_elapsed)
    console.step(f"Parsed {len(documents):,} documents in {parse_elapsed:.1f}s", done=True)

    # [STAGE: EMBED_DOCUMENTS]
    # Sends document texts to the embedding provider in batches.
    # Writes float vectors back onto each Document object.
    console.step("Generating embeddings")
    embed_start = time.time()
    batch_size = config.source.batch_size
    all_texts = [doc.text for doc in documents]
    total = len(all_texts)
    embedded_count = 0

    for batch in iter_batches(all_texts, batch_size):
        vectors = embedding_provider.embed_batch(batch)
        for i, vec in enumerate(vectors):
            documents[embedded_count + i].embedding = vec
        embedded_count += len(batch)
        logger.debug("Embedded %d/%d documents", embedded_count, total)
        console.progress_bar(embedded_count, total, label="Embedding progress")

    embed_elapsed = time.time() - embed_start
    logger.info("Embedding complete — %d documents in %.1fs", total, embed_elapsed)
    console.step(f"Embedded {total:,} documents in {embed_elapsed:.1f}s", done=True)

    # [STAGE: INDEX_BUILD]
    # Builds the FAISS IndexFlatIP (cosine similarity),
    # writes index binary + metadata JSON + parquet + lookup pickle + manifest.
    console.step("Saving vector store artefacts")
    save_start = time.time()
    vector_store.save(
        documents=documents,
        output_dir=config.vector_store.output_dir,
        prefix=config.vector_store.filename_prefix,
    )
    save_elapsed = time.time() - save_start
    logger.info("build-vectors complete — %d documents indexed (%.1fs)", len(documents), save_elapsed)
    console.step(f"Saved vector store to {config.vector_store.output_dir} in {save_elapsed:.1f}s", done=True)