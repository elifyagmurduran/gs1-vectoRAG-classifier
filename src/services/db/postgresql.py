"""PostgreSQL database connector using psycopg2 + SQLAlchemy."""
from __future__ import annotations
import pandas as pd
from sqlalchemy import create_engine, text
from src.services.db.base import DatabaseConnector
from src.utils.logging import get_logger
from src.utils.exceptions import DatabaseNotConnectedError, DatabaseError

logger = get_logger("pipeline.db.postgresql")


class PostgreSQLConnector(DatabaseConnector):
    """Connect to PostgreSQL via username/password authentication.

    Args:
        host: PostgreSQL server hostname.
        port: Port number (default 5432).
        database: Database name.
        username: Database username.
        password: Database password.
        schema_name: Default schema.
        table: Default table name.
        primary_key: Primary key column name.
    """

    def __init__(self, host: str, port: int = 5432, database: str = "",
                 username: str = "", password: str = "",
                 schema_name: str = "public", table: str = "promo_bronze",
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

    @property
    def full_table_name(self) -> str:
        return f"{self._schema}.{self._table}"

    def connect(self) -> None:
        url = (f"postgresql+psycopg2://{self._username}:{self._password}"
               f"@{self._host}:{self._port}/{self._database}")
        self._engine = create_engine(url)
        with self._engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info(f"Connected to PostgreSQL: {self._host}/{self._database}")

    def disconnect(self) -> None:
        if self._engine:
            self._engine.dispose()
            self._engine = None
            logger.info("Disconnected from PostgreSQL")

    def fetch_batch(self, query: str, params: dict | None = None,
                    batch_size: int = 256) -> pd.DataFrame:
        if self._engine is None:
            raise DatabaseNotConnectedError()
        with self._engine.connect() as conn:
            result = conn.execute(text(query), params or {})
            rows = result.fetchmany(batch_size)
            columns = result.keys()
        return pd.DataFrame(rows, columns=columns)

    def update_rows(self, table: str, updates: list[dict],
                    key_column: str = "id") -> int:
        """Update rows. For embedding columns, uses pgvector cast: ::vector(1024)."""
        if self._engine is None:
            raise DatabaseNotConnectedError()
        if not updates:
            return 0

        count = 0
        with self._engine.begin() as conn:
            for row in updates:
                key_value = row[key_column]
                set_clauses = []
                params = {key_column: key_value}

                for col, val in row.items():
                    if col == key_column:
                        continue
                    if "embedding" in col.lower():
                        set_clauses.append(f"{col} = :{col}::vector(1024)")
                    else:
                        set_clauses.append(f"{col} = :{col}")
                    params[col] = val

                sql = f"UPDATE {table} SET {', '.join(set_clauses)} WHERE {key_column} = :{key_column}"
                conn.execute(text(sql), params)
                count += 1

        logger.debug(f"Updated {count} rows in {table}")
        return count

    def execute(self, query: str, params: dict | None = None) -> None:
        if self._engine is None:
            raise DatabaseNotConnectedError()
        with self._engine.begin() as conn:
            conn.execute(text(query), params or {})
