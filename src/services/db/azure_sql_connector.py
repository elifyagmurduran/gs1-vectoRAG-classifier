
"""Azure SQL database connector using pyodbc + SQLAlchemy with Service Principal auth."""
from __future__ import annotations
from urllib.parse import quote_plus
import pandas as pd
from sqlalchemy import create_engine, text
from src.services.db.base import DatabaseConnector
from src.utils.logging import get_logger
from src.utils.exceptions import DatabaseNotConnectedError, DatabaseError

logger = get_logger("pipeline.db.azure_sql")


class AzureSQLConnector(DatabaseConnector):
    """Connect to Azure SQL Database via Service Principal authentication.

    Args:
        server: Azure SQL server hostname.
        database: Database name.
        client_id: Azure AD Service Principal Application (Client) ID.
        client_secret: Service Principal client secret.
        schema_name: Default schema (e.g., "playground").
        table: Default table name.
        primary_key: Primary key column name.
    """

    def __init__(self, server: str, database: str, client_id: str,
                 client_secret: str, schema_name: str = "playground",
                 table: str = "promo_bronze", primary_key: str = "id",
                 **kwargs):
        self._server = server
        self._database = database
        self._client_id = client_id
        self._client_secret = client_secret
        self._schema = schema_name
        self._table = table
        self._pk = primary_key
        self._engine = None

    @property
    def full_table_name(self) -> str:
        return f"{self._schema}.{self._table}"

    def connect(self) -> None:
        conn_str = (
            f"DRIVER={{ODBC Driver 18 for SQL Server}};"
            f"SERVER={self._server};"
            f"DATABASE={self._database};"
            f"UID={self._client_id};"
            f"PWD={self._client_secret};"
            f"Authentication=ActiveDirectoryServicePrincipal;"
            f"Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;"
        )
        quoted = quote_plus(conn_str)
        self._engine = create_engine(f"mssql+pyodbc:///?odbc_connect={quoted}")
        # Test the connection
        with self._engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info(f"Connected to Azure SQL: {self._server}/{self._database}")

    def disconnect(self) -> None:
        if self._engine:
            self._engine.dispose()
            self._engine = None
            logger.info("Disconnected from Azure SQL")

    def fetch_batch(self, query: str, params: dict | None = None,
                    batch_size: int = 256) -> pd.DataFrame:
        if self._engine is None:
            raise DatabaseNotConnectedError()
        with self._engine.connect() as conn:
            return pd.read_sql_query(text(query), conn, params=params or {})

    def update_rows(self, table: str, updates: list[dict],
                    key_column: str = "id") -> int:
        """Update rows. Each dict must contain key_column + columns to update.

        For embedding columns, uses Azure SQL VECTOR cast:
            CAST(CAST(:embedding AS VARCHAR(MAX)) AS VECTOR(1024))
        """
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
                        # Azure SQL VECTOR cast
                        set_clauses.append(
                            f"{col} = CAST(CAST(:{col} AS VARCHAR(MAX)) AS VECTOR(1024))"
                        )
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
