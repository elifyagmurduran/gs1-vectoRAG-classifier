"""embed-rows workflow: DB → concatenate columns → embed → write embeddings back.

Uses :class:`DatabaseBatcher` to page through the source table one
``row_embedding.batch_size`` chunk at a time so the pipeline never loads the
entire data set into memory.  Each batch is processed end-to-end
(fetch → embed → write) before the next batch is fetched, which means:

* Already-written rows are safe if the process is interrupted.
* Resuming automatically skips rows that already have embeddings.
* Memory usage stays constant regardless of table size.
"""
from __future__ import annotations
import json
import time
from src.config.models import AppConfig
from src.services.embedding.base import EmbeddingProvider
from src.services.db.base import DatabaseConnector
from src.utils.batching import DatabaseBatcher
from src.utils.console import console
from src.utils.logging import get_logger

logger = get_logger("pipeline.workflow.embed_rows")


def run_embed_rows(config: AppConfig, embedding_provider: EmbeddingProvider,
                   db_connector: DatabaseConnector) -> None:
    """Execute the embed-rows pipeline.

    Steps:
        1. Connect to DB.
        2. Count matching rows for progress reporting.
        3. Page through rows via :class:`DatabaseBatcher`
           (batch_size from ``config.row_embedding.batch_size``):
           a. Concatenate selected columns into a text string.
           b. Embed the batch via the embedding provider.
           c. Write embeddings back to DB.
        4. Disconnect.

    Args:
        config: Validated app config.
        embedding_provider: Initialized embedding provider.
        db_connector: Initialized database connector.
    """
    re_cfg = config.row_embedding
    schema = config.database.schema_name
    table = config.database.table
    full_table = f"{schema}.{table}"
    pk = config.database.primary_key
    batch_size = re_cfg.batch_size

    # Build SELECT query — only rows where target column is NULL
    columns_str = ", ".join([pk] + re_cfg.columns)
    where_clause = f"WHERE {re_cfg.target_column} IS NULL"

    base_query = f"SELECT {columns_str} FROM {full_table} {where_clause}"

    processed = 0
    batch_num = 0

    t_start = time.time()
    console.step(f"embed-rows → {re_cfg.target_column}")
    db_connector.connect()
    try:
        batcher = DatabaseBatcher(
            db_connector=db_connector,
            base_query=base_query,
            order_by=pk,
            batch_size=batch_size,
        )

        total_rows = batcher.count()
        if total_rows == 0:
            logger.info("No rows to process.")
            return

        # Estimate total batches for progress bar
        import math
        total_batches = math.ceil(total_rows / batch_size)

        # [STAGE: EMBED_ROWS]
        # Fetch → embed → write back. Processes one batch at a time
        # to keep memory usage constant regardless of table size.
        for batch_df in batcher:
            # Concatenate columns into text strings
            texts = []
            for _, row in batch_df.iterrows():
                parts = [str(row.get(col, "") or "") for col in re_cfg.columns]
                texts.append(re_cfg.separator.join(parts))

            # Embed
            embeddings = embedding_provider.embed_batch(texts)

            # Build updates
            updates = []
            for i, (_, row) in enumerate(batch_df.iterrows()):
                embedding_json = json.dumps(embeddings[i])
                updates.append({
                    pk: row[pk],
                    re_cfg.target_column: embedding_json,
                })

            # Write back to DB
            db_connector.update_rows(full_table, updates, key_column=pk)

            processed += len(batch_df)
            batch_num += 1
            console.progress_bar(batch_num, total_batches, label="Embed-rows")

            # Small sleep to avoid rate-limiting
            time.sleep(0.5)

    finally:
        db_connector.disconnect()

    elapsed = time.time() - t_start
    logger.info("embed-rows complete. %d rows embedded in %.1fs.", processed, elapsed)
    console.step(f"embed-rows complete — {processed} rows in {elapsed:.1f}s", done=True)

