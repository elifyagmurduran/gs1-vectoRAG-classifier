"""SQLite database connector (scaffold — not yet implemented)."""
from __future__ import annotations
import pandas as pd
from src.services.db.base import DatabaseConnector
from src.utils.logging import get_logger

logger = get_logger("pipeline.db.sqlite")


class SQLiteConnector(DatabaseConnector):
    """Connect to a local SQLite database file.

    To activate: implement the methods below, then register in factory.py:
        factory.register_db("sqlite", SQLiteConnector)

    Embeddings are stored as TEXT (JSON string) since SQLite has no native
    vector type. The connector handles serialization/deserialization internally.

    Args:
        db_path: Path to the SQLite database file.
        table: Table name.
        primary_key: Primary key column name.
    """

    def __init__(self, db_path: str = "data/local.db",
                 schema_name: str = "", table: str = "promo_bronze",
                 primary_key: str = "id", **kwargs):
        self._db_path = db_path
        self._schema = schema_name
        self._table = table
        self._pk = primary_key
        self._engine = None

    def connect(self) -> None:
        raise NotImplementedError(
            "SQLiteConnector.connect is not yet implemented. "
            "See docs/SWAPPABLE_PARTS.md for the implementation spec."
        )

    def disconnect(self) -> None:
        raise NotImplementedError(
            "SQLiteConnector.disconnect is not yet implemented. "
            "See docs/SWAPPABLE_PARTS.md for the implementation spec."
        )

    def fetch_batch(self, query: str, params: dict | None = None,
                    batch_size: int = 256) -> pd.DataFrame:
        raise NotImplementedError(
            "SQLiteConnector.fetch_batch is not yet implemented. "
            "See docs/SWAPPABLE_PARTS.md for the implementation spec."
        )

    def update_rows(self, table: str, updates: list[dict],
                    key_column: str = "id") -> int:
        raise NotImplementedError(
            "SQLiteConnector.update_rows is not yet implemented. "
            "See docs/SWAPPABLE_PARTS.md for the implementation spec."
        )

    def execute(self, query: str, params: dict | None = None) -> None:
        raise NotImplementedError(
            "SQLiteConnector.execute is not yet implemented. "
            "See docs/SWAPPABLE_PARTS.md for the implementation spec."
        )
