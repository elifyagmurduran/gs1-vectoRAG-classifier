
"""classify workflow: fetch unclassified rows → RAG + LLM → write GS1 columns back."""
from __future__ import annotations
import json
import math
import time
from pathlib import Path
from src.config.models import AppConfig
from src.services.orchestrator import LLMOrchestratorService
from src.services.db.base import DatabaseConnector
from src.utils.batching import DatabaseBatcher
from src.utils.logging import get_logger
from src.utils.console import console
from src.utils.exceptions import PipelineError, BatchError

logger = get_logger("pipeline.workflow.classify")

def run_classify(config: AppConfig, orchestrator: LLMOrchestratorService,
                 db_connector: DatabaseConnector) -> None:
    """Execute the classify pipeline: loop through unclassified rows in batches.

    Uses :class:`DatabaseBatcher` to page through unclassified rows with
    ``classification.batch_size`` — the same batching pattern as ``embed-rows``.

    Steps per iteration:
        1. Fetch next batch of rows where gs1_segment IS NULL.
        2. Call orchestrator.classify_batch() for RAG + LLM classification.
        3. Write 6 GS1 columns back to DB.
        4. Repeat until DatabaseBatcher is exhausted.

    Args:
        config: Validated app config.
        orchestrator: Initialized LLMOrchestratorService.
        db_connector: Initialized database connector.
    """
    cls_cfg = config.classification
    schema = config.database.schema_name
    table = config.database.table
    full_table = f"{schema}.{table}"
    pk = config.database.primary_key
    batch_size = cls_cfg.batch_size
    target_cols = cls_cfg.target_columns
    prompt_cols = cls_cfg.prompt_columns

    # Build SELECT: need PK, prompt columns (shown to LLM), and embedding_context (for RAG)
    select_cols = [pk] + prompt_cols + ["embedding_context"]
    select_str = ", ".join(select_cols)

    base_query = f"SELECT {select_str} FROM {full_table} WHERE gs1_segment IS NULL"

    failed_products = []
    total_classified = 0
    batch_num = 0
    pipeline_start = time.time()

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
            logger.info("No unclassified rows found — nothing to do.")
            console.info("No unclassified rows", "Nothing to classify.")
            return

        total_batches = math.ceil(total_rows / batch_size)
        logger.info("Classification starting — rows: %d, batch_size: %d, batches: %d",
                    total_rows, batch_size, total_batches)
        console.classification_start(
            total_rows=total_rows,
            batch_size=batch_size,
            batch_count=total_batches,
        )

        for batch_df in batcher:
            batch_num += 1
            batch_start = time.time()
            rows = batch_df.to_dict(orient="records")
            product_names = [str(r.get(prompt_cols[0], "")) for r in rows if prompt_cols]

            logger.info("Batch %d/%d — %d rows fetched", batch_num, total_batches, len(rows))
            console.batch_start(
                batch_num=batch_num,
                total_batches=total_batches,
                row_count=len(rows),
                product_names=product_names,
            )

            try:
                # [STAGE: CLASSIFY_BATCH]
                # RAG search + candidate build + prompt + LLM call + response parse.
                results = orchestrator.classify_batch(rows)

                if not results:
                    logger.warning("Batch %d: no results returned by orchestrator", batch_num)
                    console.warning(f"Batch {batch_num}", "No results returned — skipping")
                    continue

                updates = []
                category_counts: dict[str, int] = {}
                for result in results:
                    update = {pk: result["product_id"]}
                    for col in target_cols:
                        update[col] = result.get(col, "")
                    updates.append(update)
                    # Track category distribution for console output
                    seg = result.get("gs1_segment", "")
                    if seg:
                        category_counts[seg] = category_counts.get(seg, 0) + 1

                # [STAGE: WRITE_RESULTS]
                # Writes 6 GS1 classification columns back to the DB row.
                db_connector.update_rows(full_table, updates, key_column=pk)
                logger.info("Batch %d: updated %d rows in DB", batch_num, len(updates))

                console.gs1_db_write(updates)

                total_classified += len(results)
                batch_elapsed = time.time() - batch_start

                console.batch_result(
                    classified=len(results),
                    requested=len(rows),
                    elapsed_s=batch_elapsed,
                    category_counts=category_counts,
                )
                console.progress_bar(batch_num, total_batches, label="Batches")

            except PipelineError as e:
                batch_elapsed = time.time() - batch_start
                row_ids = [r.get(pk) for r in rows]
                logger.error("Batch %d failed (PipelineError): %s", batch_num, e, exc_info=True)
                console.error(f"Batch {batch_num} failed", str(e))
                for row in rows:
                    failed_products.append({
                        "product_id": row.get(pk),
                        "batch": batch_num,
                        "error": str(e),
                    })
                logger.info("Skipping batch %d, continuing...", batch_num)
                continue
            except Exception as e:
                batch_error = BatchError(
                    f"Unexpected error in batch {batch_num}: {e}",
                    batch_num=batch_num,
                    row_ids=[r.get(pk) for r in rows],
                    cause=e,
                )
                logger.error("Batch %d failed: %s", batch_num, e, exc_info=True)
                console.error(f"Batch {batch_num} failed", str(e))
                for row in rows:
                    failed_products.append({
                        "product_id": row.get(pk),
                        "batch": batch_num,
                        "error": str(e),
                    })
                logger.info("Skipping batch %d, continuing...", batch_num)
                continue

            time.sleep(1.0)

    finally:
        db_connector.disconnect()

    total_elapsed = time.time() - pipeline_start
    failed_count = len(failed_products)

    if failed_products:
        _save_failed_products(failed_products)

    logger.info("Classification complete — classified: %d, failed: %d, elapsed: %.1fs",
                total_classified, failed_count, total_elapsed)
    console.classification_summary(
        total=total_classified + failed_count,
        classified=total_classified,
        failed=failed_count,
        elapsed_s=total_elapsed,
    )


def _save_failed_products(failed: list[dict]) -> None:
    """Write failed products to a structured JSON log."""
    log_dir = Path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / "failed_products.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(failed, f, indent=2, ensure_ascii=False)
    logger.info("Failed products log written: %s", path)

