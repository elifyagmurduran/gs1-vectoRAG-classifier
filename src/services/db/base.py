
"""Abstract base class for database connectors (thin repository pattern)."""
from abc import ABC, abstractmethod
import pandas as pd


class DatabaseConnector(ABC):
    """Interface for database operations. Hides SQL behind clean Python methods."""

    @abstractmethod
    def connect(self) -> None:
        """Establish connection to the database."""
        ...

    @abstractmethod
    def disconnect(self) -> None:
        """Close the database connection."""
        ...

    @abstractmethod
    def fetch_batch(self, query: str, params: dict | None = None,
                    batch_size: int = 256) -> pd.DataFrame:
        """Fetch a batch of rows from the database.

        Args:
            query: SQL SELECT query.
            params: Optional query parameters.
            batch_size: Maximum rows to return.

        Returns:
            pandas DataFrame of results.
        """
        ...

    @abstractmethod
    def update_rows(self, table: str, updates: list[dict],
                    key_column: str = "id") -> int:
        """Update multiple rows in a table.

        Args:
            table: Fully-qualified table name (schema.table).
            updates: List of dicts, each containing the key column + columns to update.
            key_column: Name of the primary key column.

        Returns:
            Number of rows updated.
        """
        ...

    @abstractmethod
    def execute(self, query: str, params: dict | None = None) -> None:
        """Execute a raw SQL statement (e.g., DDL, custom update).

        Args:
            query: SQL statement.
            params: Optional parameters.
        """
        ...
