"""MySQL / MariaDB database connector (scaffold — not yet implemented)."""
from __future__ import annotations
import pandas as pd
from src.services.db.base import DatabaseConnector
from src.utils.logging import get_logger

logger = get_logger("pipeline.db.mysql")


class MySQLConnector(DatabaseConnector):
    """Connect to MySQL or MariaDB via pymysql + SQLAlchemy.

    To activate: implement the methods below, then register in factory.py:
        factory.register_db("mysql", MySQLConnector)

    Pagination uses LIMIT … OFFSET syntax (different from SQL Server / PostgreSQL).
    MySQL 9.0+ supports a native VECTOR type; older versions store embeddings
    as LONGTEXT.

    Args:
        host: MySQL server hostname (MYSQL_HOST).
        port: Port number (MYSQL_PORT, default 3306).
        database: Database name (MYSQL_DATABASE).
        username: MySQL username (MYSQL_USERNAME).
        password: MySQL password (MYSQL_PASSWORD).
        schema_name: Schema / database name.
        table: Table name.
        primary_key: Primary key column name.
    """

    def __init__(self, host: str, port: int = 3306, database: str = "",
                 username: str = "", password: str = "",
                 schema_name: str = "", table: str = "promo_bronze",
                 primary_key: str = "id", **kwargs):
        self._host = host
        self._port = port
        self._database = database
        self._username = username
        self._password = password
        self._schema = schema_name
        self._table = table
        self._pk = primary_key
        self._engine = None

    def connect(self) -> None:
        raise NotImplementedError(
            "MySQLConnector.connect is not yet implemented. "
            "See docs/SWAPPABLE_PARTS.md for the implementation spec."
        )

    def disconnect(self) -> None:
        raise NotImplementedError(
            "MySQLConnector.disconnect is not yet implemented. "
            "See docs/SWAPPABLE_PARTS.md for the implementation spec."
        )

    def fetch_batch(self, query: str, params: dict | None = None,
                    batch_size: int = 256) -> pd.DataFrame:
        raise NotImplementedError(
            "MySQLConnector.fetch_batch is not yet implemented. "
            "See docs/SWAPPABLE_PARTS.md for the implementation spec."
        )

    def update_rows(self, table: str, updates: list[dict],
                    key_column: str = "id") -> int:
        raise NotImplementedError(
            "MySQLConnector.update_rows is not yet implemented. "
            "See docs/SWAPPABLE_PARTS.md for the implementation spec."
        )

    def execute(self, query: str, params: dict | None = None) -> None:
        raise NotImplementedError(
            "MySQLConnector.execute is not yet implemented. "
            "See docs/SWAPPABLE_PARTS.md for the implementation spec."
        )
