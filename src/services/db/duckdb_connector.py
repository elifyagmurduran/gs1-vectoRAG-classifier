"""DuckDB analytical database connector (scaffold — not yet implemented)."""
from __future__ import annotations
import pandas as pd
from src.services.db.base import DatabaseConnector
from src.utils.logging import get_logger

logger = get_logger("pipeline.db.duckdb")


class DuckDBConnector(DatabaseConnector):
    """Connect to a DuckDB database file (serverless, columnar analytics).

    To activate: implement the methods below, then register in factory.py:
        factory.register_db("duckdb", DuckDBConnector)

    DuckDB can query Parquet files directly, making it useful for inspecting
    the data/vector_store/*.parquet artefacts produced by the build-vectors
    workflow. Embeddings are stored as FLOAT[] or VARCHAR.

    Args:
        db_path: Path to the DuckDB database file (e.g., "data/local.duckdb").
        table: Table name.
        primary_key: Primary key column name.
    """

    def __init__(self, db_path: str = "data/local.duckdb",
                 table: str = "promo_bronze", primary_key: str = "id",
                 **kwargs):
        self._db_path = db_path
        self._table = table
        self._pk = primary_key
        self._conn = None

    def connect(self) -> None:
        raise NotImplementedError(
            "DuckDBConnector.connect is not yet implemented. "
            "See docs/SWAPPABLE_PARTS.md for the implementation spec."
        )

    def disconnect(self) -> None:
        raise NotImplementedError(
            "DuckDBConnector.disconnect is not yet implemented. "
            "See docs/SWAPPABLE_PARTS.md for the implementation spec."
        )

    def fetch_batch(self, query: str, params: dict | None = None,
                    batch_size: int = 256) -> pd.DataFrame:
        raise NotImplementedError(
            "DuckDBConnector.fetch_batch is not yet implemented. "
            "See docs/SWAPPABLE_PARTS.md for the implementation spec."
        )

    def update_rows(self, table: str, updates: list[dict],
                    key_column: str = "id") -> int:
        raise NotImplementedError(
            "DuckDBConnector.update_rows is not yet implemented. "
            "See docs/SWAPPABLE_PARTS.md for the implementation spec."
        )

    def execute(self, query: str, params: dict | None = None) -> None:
        raise NotImplementedError(
            "DuckDBConnector.execute is not yet implemented. "
            "See docs/SWAPPABLE_PARTS.md for the implementation spec."
        )
