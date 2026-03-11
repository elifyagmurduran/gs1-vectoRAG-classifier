"""Generic batch iterators for lists and database cursors."""
from __future__ import annotations
from typing import TypeVar, Iterator, Sequence, TYPE_CHECKING
from src.utils.logging import get_logger

if TYPE_CHECKING:
    import pandas as pd
    from src.services.db.base import DatabaseConnector

T = TypeVar("T")

logger = get_logger("pipeline.batching")


def iter_batches(items: Sequence[T], batch_size: int) -> Iterator[list[T]]:
    """Yield successive batches from a sequence.

    Args:
        items: The full sequence to batch.
        batch_size: Number of items per batch.

    Yields:
        Lists of up to batch_size items.
    """
    for i in range(0, len(items), batch_size):
        yield items[i : i + batch_size]


class DatabaseBatcher:
    """Paginated fetcher that yields one DataFrame batch at a time.

    Uses SQL Server ``OFFSET … FETCH NEXT`` syntax to stream rows from the
    database without loading the entire result set into memory.  Each call
    to :pymethod:`__next__` issues exactly one query for ``batch_size`` rows.

    Usage::

        batcher = DatabaseBatcher(
            db_connector=db,
            base_query="SELECT id, name FROM playground.products WHERE embedding IS NULL",
            order_by="id",
            batch_size=256,
        )
        for batch_df in batcher:
            process(batch_df)
        print(batcher.total_fetched)

    Args:
        db_connector: An already-connected :class:`DatabaseConnector`.
        base_query: The SELECT … FROM … WHERE portion (no ORDER BY / OFFSET).
        order_by: Column(s) for deterministic ordering (e.g. ``"id"``).
        batch_size: Maximum rows per page.
    """

    def __init__(
        self,
        db_connector: DatabaseConnector,
        base_query: str,
        order_by: str,
        batch_size: int = 256,
    ) -> None:
        self._db = db_connector
        self._base_query = base_query
        self._order_by = order_by
        self._batch_size = batch_size
        self._offset = 0
        self._exhausted = False
        self._total_fetched = 0

    # ── public properties ─────────────────────────────────────────
    @property
    def total_fetched(self) -> int:
        """Number of rows fetched so far across all pages."""
        return self._total_fetched

    @property
    def batch_size(self) -> int:
        return self._batch_size

    # ── iterator protocol ─────────────────────────────────────────
    def __iter__(self) -> "DatabaseBatcher":
        return self

    def __next__(self) -> "pd.DataFrame":
        if self._exhausted:
            raise StopIteration

        paged_query = (
            f"{self._base_query} ORDER BY {self._order_by} "
            f"OFFSET {self._offset} ROWS FETCH NEXT {self._batch_size} ROWS ONLY"
        )
        logger.info(f"Fetching batch at offset {self._offset} (batch_size={self._batch_size})")

        batch_df = self._db.fetch_batch(paged_query, batch_size=self._batch_size)

        if batch_df.empty:
            self._exhausted = True
            raise StopIteration

        fetched = len(batch_df)
        self._total_fetched += fetched
        logger.info(f"Fetched {fetched} rows (total so far: {self._total_fetched})")

        if fetched < self._batch_size:
            self._exhausted = True

        return batch_df

    def count(self) -> int:
        """Run a COUNT(*) query with the same WHERE clause and return the total.

        Useful for progress bars before iterating.
        """
        # Extract the FROM … WHERE portion from the base query
        upper = self._base_query.upper()
        from_idx = upper.find("FROM")
        if from_idx == -1:
            raise ValueError(f"Cannot parse FROM clause from: {self._base_query}")
        from_clause = self._base_query[from_idx:]
        count_query = f"SELECT COUNT(*) AS cnt {from_clause}"
        count_df = self._db.fetch_batch(count_query, batch_size=1)
        total = int(count_df.iloc[0]["cnt"]) if not count_df.empty else 0
        logger.info(f"Total rows matching query: {total}")
        return total