# Build Guide — Part 2 of 2

**Phases 11 – 18:** build-vectors workflow, database connectors, embed-rows workflow, LLM providers, transforms, prompt templates, orchestrator, classify workflow, and the two entry points.

> **Prerequisite:** Complete [BUILD_GUIDE_PART_1.md](BUILD_GUIDE_PART_1.md) (Phases 0–10) before starting here.

---

## Table of Contents

- [Phase 11 — build-vectors Workflow](#phase-11--build-vectors-workflow)
- [Phase 12 — Database Connectors](#phase-12--database-connectors)
- [Phase 13 — embed-rows Workflow](#phase-13--embed-rows-workflow)
- [Phase 14 — LLM Providers](#phase-14--llm-providers)
- [Phase 15 — Transforms: CandidateBuilder + ResponseParser](#phase-15--transforms-candidatebuilder--responseparser)
- [Phase 16 — Prompt Templates](#phase-16--prompt-templates)
- [Phase 17 — LLM Orchestrator Service](#phase-17--llm-orchestrator-service)
- [Phase 18 — Classify Workflow + Entry Points](#phase-18--classify-workflow--entry-points)

---

## Phase 11 — build-vectors Workflow

**Goal:** Build the pipeline function that uses `GS1Parser`, `EmbeddingProvider`, and `VectorStore` to turn a GS1 JSON file into a searchable FAISS index.

**Where this fits:** `run_build_vectors()` is a pure pipeline function. It takes already-constructed objects and runs the end-to-end logic. It has no CLI parsing and no knowledge of Azure or FAISS internals. The entry point (`vectorize.py`) is responsible for constructing those objects and calling this function.

### 11.1 `src/workflows/build_vectors.py`

Three stages — Parse, Embed, Index:

```python
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

    Stages:
        1. PARSE_SOURCE   — reads GS1 JSON, traverses recursively,
                            emits one Document per taxonomy node.
        2. EMBED_DOCUMENTS — sends document texts to the embedding provider
                            in batches (config.source.batch_size), writing
                            vectors back onto each Document.
        3. INDEX_BUILD    — builds the FAISS index and writes all 5 artefacts.

    Args:
        config: Validated app config.
        embedding_provider: Initialized embedding provider.
        vector_store: Initialized vector store (will call .save()).
    """
    # [STAGE: PARSE_SOURCE]
    console.step("Parsing source JSON")
    parse_start = time.time()
    parser = GS1Parser(
        file_path=config.source.path,
        encoding=config.source.encoding,
    )
    documents = parser.parse()
    parse_elapsed = time.time() - parse_start
    logger.info("Parsed %d documents from %s (%.1fs)",
                len(documents), config.source.path, parse_elapsed)
    console.step(f"Parsed {len(documents):,} documents in {parse_elapsed:.1f}s", done=True)

    # [STAGE: EMBED_DOCUMENTS]
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
    console.step("Saving vector store artefacts")
    save_start = time.time()
    vector_store.save(
        documents=documents,
        output_dir=config.vector_store.output_dir,
        prefix=config.vector_store.filename_prefix,
    )
    save_elapsed = time.time() - save_start
    logger.info("build-vectors complete — %d documents indexed (%.1fs)",
                len(documents), save_elapsed)
    console.step(
        f"Saved vector store to {config.vector_store.output_dir} in {save_elapsed:.1f}s",
        done=True,
    )
```

**What happens when you run `python vectorize.py build-vectors`:**

```
┌─────────────────────────────────────────────────────────┐
│  python vectorize.py build-vectors                      │
│                                                         │
│  vectorize.py                                           │
│  ├─ parse args → mode = "build-vectors"                 │
│  ├─ setup_logging(mode_prefix="build_vectors")          │
│  ├─ load_config("config.yaml")                          │
│  ├─ console.pipeline_start(mode="build-vectors")        │
│  ├─ build_factory_for_mode("build-vectors")             │
│  │   └─ registers: azure_openai embedder + faiss        │
│  ├─ _run_build_vectors(config, factory, get_env)        │
│  │   ├─ create AzureOpenAIEmbeddingProvider             │
│  │   ├─ create FAISSVectorStore (5 kwargs)              │
│  │   └─ run_build_vectors(config, embedder, vs)         │
│  │       ├─ GS1Parser.parse() → list[Document]         │
│  │       ├─ embed all docs in batches of source.batch_size│
│  │       └─ FAISSVectorStore.save() → 5 artefacts       │
│  └─ console.pipeline_finished(success=True)             │
└─────────────────────────────────────────────────────────┘
```

**5 artefacts written to `data/vector_store/`:**

```
data/vector_store/
├── faiss_gs1.index              # FAISS binary — loaded at query time
├── faiss_gs1_metadata.json      # Full metadata — for inspection/debugging
├── embeddings_gs1.parquet       # Full doc archive — for reindexing
├── gs1_lookup.pkl               # Compact position → metadata dict — loaded at query time
└── build_manifest.json          # Build provenance — metric is read back at load time
```

See [TESTING_GUIDE.md §Phase 11](TESTING_GUIDE.md#phase-11-tests) for verification steps.

---

## Phase 12 — Database Connectors

**Goal:** Implement the two production database connectors: Azure SQL (Service Principal auth) and PostgreSQL (username/password). Then sketch the three scaffolded connectors.

**Where `services/db/` fits:** The `DatabaseConnector` ABC (Phase 6) defined the interface. These concrete classes are the only ones that know SQL or connection strings. Workflows interact exclusively through the ABC — they never import these concrete classes.

**Why `services/db/`, not a top-level `db/`?** Database operations are a *service* the pipeline consumes — just like the LLM and the vector store. Grouping all service dependencies under `services/` makes the architecture easier to reason about and the separation from pure logic (`transforms/`) explicit.

### 12.1 Azure SQL prerequisites

Azure SQL connector requires:
1. **ODBC Driver 18 for SQL Server** installed on the machine. Download it from Microsoft's website.
2. `pyodbc` Python package (already in `requirements.txt`).
3. A **Service Principal** configured in Azure AD with the `db_datareader`, `db_datawriter` roles on your Azure SQL database.
4. The four env vars in `.env`: `AZURE_SQL_SERVER`, `AZURE_SQL_DATABASE`, `AZURE_SQL_CLIENT_ID`, `AZURE_SQL_CLIENT_SECRET`.

### 12.2 `src/services/db/azure_sql_connector.py`

```python
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

    Authentication flow:
        pyodbc → ODBC Driver 18 → Azure AD → Service Principal credential
                                             (client_id + client_secret)

    Embedding storage:
        Azure SQL stores vectors using its native VECTOR type. Python sends
        a JSON-encoded list of floats (string), which is cast to VECTOR(1024)
        via: CAST(CAST(:embedding AS VARCHAR(MAX)) AS VECTOR(1024))
        Do NOT try to store raw arrays — Azure SQL requires this double-cast.

    Args:
        server: Azure SQL server hostname (e.g., "my-server.database.windows.net").
        database: Database name.
        client_id: Service Principal Application (Client) ID.
        client_secret: Service Principal client secret.
        schema_name: Default schema (default "playground").
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
        """Build the connection string and create a SQLAlchemy engine.

        Uses ActiveDirectoryServicePrincipal authentication.
        Calls SELECT 1 to verify the connection is working.
        """
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
        with self._engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("Connected to Azure SQL: %s/%s", self._server, self._database)

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
        """Update rows. Detects embedding columns by name and applies VECTOR cast.

        For any column whose name contains "embedding", writes via:
            CAST(CAST(:col AS VARCHAR(MAX)) AS VECTOR(1024))

        This is required for Azure SQL VECTOR columns.
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
                        # Azure SQL native VECTOR type requires this double CAST
                        set_clauses.append(
                            f"{col} = CAST(CAST(:{col} AS VARCHAR(MAX)) AS VECTOR(1024))"
                        )
                    else:
                        set_clauses.append(f"{col} = :{col}")
                    params[col] = val

                sql = (f"UPDATE {table} SET {', '.join(set_clauses)} "
                       f"WHERE {key_column} = :{key_column}")
                conn.execute(text(sql), params)
                count += 1

        logger.debug("Updated %d rows in %s", count, table)
        return count

    def execute(self, query: str, params: dict | None = None) -> None:
        if self._engine is None:
            raise DatabaseNotConnectedError()
        with self._engine.begin() as conn:
            conn.execute(text(query), params or {})
```

### 12.3 `src/services/db/postgresql.py`

```python
"""PostgreSQL database connector using psycopg2 + SQLAlchemy."""
from __future__ import annotations
import pandas as pd
from sqlalchemy import create_engine, text
from src.services.db.base import DatabaseConnector
from src.utils.logging import get_logger
from src.utils.exceptions import DatabaseNotConnectedError, DatabaseError

logger = get_logger("pipeline.db.postgresql")


class PostgreSQLConnector(DatabaseConnector):
    """Connect to PostgreSQL via username/password (SQLAlchemy + psycopg2).

    Embedding storage:
        PostgreSQL uses the pgvector extension. Embed JSON strings are cast with:
            col = :col::vector(1024)
        Install pgvector on your PostgreSQL server first.

    Args:
        host: Hostname.
        port: Port (default 5432).
        database: Database name.
        username: DB username.
        password: DB password.
        schema_name: Default schema (default "public").
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
        logger.info("Connected to PostgreSQL: %s/%s", self._host, self._database)

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
        """Update rows. Embedding columns use pgvector cast: ::vector(1024)."""
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

                sql = (f"UPDATE {table} SET {', '.join(set_clauses)} "
                       f"WHERE {key_column} = :{key_column}")
                conn.execute(text(sql), params)
                count += 1

        logger.debug("Updated %d rows in %s", count, table)
        return count

    def execute(self, query: str, params: dict | None = None) -> None:
        if self._engine is None:
            raise DatabaseNotConnectedError()
        with self._engine.begin() as conn:
            conn.execute(text(query), params or {})
```

### 12.4 Scaffolded DB connectors

Create the following stub files. Each raises `NotImplementedError`:

- `src/services/db/duckdb_connector.py` — `DuckDBConnector`
- `src/services/db/mysql_connector.py` — `MySQLConnector`
- `src/services/db/sqlite_connector.py` — `SQLiteConnector`

Pattern:
```python
from src.services.db.base import DatabaseConnector

class DuckDBConnector(DatabaseConnector):
    def connect(self): raise NotImplementedError("DuckDB connector not yet implemented")
    def disconnect(self): pass
    def fetch_batch(self, query, params=None, batch_size=256): raise NotImplementedError
    def update_rows(self, table, updates, key_column="id"): raise NotImplementedError
    def execute(self, query, params=None): raise NotImplementedError
```

See [TESTING_GUIDE.md §Phase 12](TESTING_GUIDE.md#phase-12-tests) for verification steps.

---

## Phase 13 — embed-rows Workflow

**Goal:** Write the pipeline function that reads unembedded rows from the database, concatenates the configured columns into text, embeds them, and writes the vectors back.

**Why OFFSET 0?** The batcher always fetches at `OFFSET 0`. The `WHERE target_column IS NULL` filter means already-processed rows are invisible to the next fetch. If the offset were advanced by `batch_size`, rows at those positions would be skipped. This design makes the workflow **resumable** — interrupt and restart from any point without losing or double-processing rows.

**Embedding columns:** `row_embedding.columns` — listed in `config.yaml`. Concatenated with `row_embedding.separator` (default `" * "`). Empty or null column values are treated as empty strings. The concatenated string (called `embedding_context`) is what gets embedded and written back.

### 13.1 `src/workflows/embed_rows.py`

```python
"""embed-rows workflow: DB → concatenate columns → embed → write embeddings back.

Memory model: processes one batch at a time (fetch → embed → write),
keeping memory usage constant regardless of table size.

Resumability: uses WHERE target_column IS NULL. Rows that are written back
become invisible to the next batch fetch, so interrupted runs resume from
where they left off.
"""
from __future__ import annotations
import json
import math
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
        2. COUNT: how many rows have NULL in target_column.
        3. Loop via DatabaseBatcher (OFFSET 0, WHERE target IS NULL):
           a. Concatenate row_embedding.columns with row_embedding.separator.
           b. embed_batch() → embeddings.
           c. json.dumps() each embedding, write back via update_rows().
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

    columns_str = ", ".join([pk] + re_cfg.columns)
    base_query = (
        f"SELECT {columns_str} FROM {full_table} "
        f"WHERE {re_cfg.target_column} IS NULL"
    )

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
            logger.info("No rows to process — all rows already have embeddings.")
            return

        total_batches = math.ceil(total_rows / batch_size)
        logger.info("embed-rows: %d rows, batch_size=%d, batches=%d",
                    total_rows, batch_size, total_batches)

        for batch_df in batcher:
            # Concatenate configured columns into embedding text
            texts = []
            for _, row in batch_df.iterrows():
                parts = [str(row.get(col, "") or "") for col in re_cfg.columns]
                texts.append(re_cfg.separator.join(parts))

            embeddings = embedding_provider.embed_batch(texts)

            # Build update list: [{pk: ..., target_column: json_str}, ...]
            updates = []
            for i, (_, row) in enumerate(batch_df.iterrows()):
                updates.append({
                    pk: row[pk],
                    re_cfg.target_column: json.dumps(embeddings[i]),
                })

            db_connector.update_rows(full_table, updates, key_column=pk)

            processed += len(batch_df)
            batch_num += 1
            console.progress_bar(batch_num, total_batches, label="Embed-rows")
            logger.info("Batch %d/%d: embedded %d rows (total: %d)",
                        batch_num, total_batches, len(batch_df), processed)

            time.sleep(0.5)  # brief pause to avoid rate limit bursts

    finally:
        db_connector.disconnect()

    elapsed = time.time() - t_start
    logger.info("embed-rows complete — %d rows in %.1fs", processed, elapsed)
    console.step(f"embed-rows complete — {processed} rows in {elapsed:.1f}s", done=True)
```

**How embeddings are stored:**
After `embed_batch()`, you have a `list[list[float]]`. Each inner list is `json.dumps()`-ed into a string like `"[0.032, -0.142, ...]"`. This string is stored in the DB column (`target_column`). Azure SQL and PostgreSQL both cast this string to their native VECTOR type inside `update_rows()`. When the classify workflow later reads the row, it calls `json.loads()` to recover the float list.

See [TESTING_GUIDE.md §Phase 13](TESTING_GUIDE.md#phase-13-tests) for verification steps.

---

## Phase 14 — LLM Providers

**Goal:** Implement `AzureOpenAILLMProvider` and stub the remaining providers.

**Critical constraint for o-series models (o4-mini, o3, etc.):** These models do NOT accept a `temperature` parameter. They also do NOT accept `top_p`, `frequency_penalty`, or `presence_penalty`. Use only `max_completion_tokens`. If you send `temperature`, the API will return a 400 error. This is different from GPT-4 series models.

**JSON mode:** Pass `response_format={"type": "json_object"}` to force the model to output a valid JSON string. The system prompt must explicitly mention JSON output — the Azure OpenAI API requires confirmation in the system prompt that JSON is expected.

### 14.1 `src/services/llm/azure_openai_chat.py`

```python
"""Azure OpenAI LLM provider for chat completions (o-series models)."""
from __future__ import annotations
from openai import AzureOpenAI, RateLimitError
from src.services.llm.base import LLMProvider
from src.utils.retry import make_retry_decorator
from src.utils.logging import get_logger
from src.utils.exceptions import LLMError

logger = get_logger("pipeline.llm.azure_openai")


class AzureOpenAILLMProvider(LLMProvider):
    """Chat completion via Azure OpenAI, designed for o-series models (o4-mini, o3).

    IMPORTANT — o-series model constraints:
        - Do NOT pass 'temperature' — the API will reject it.
        - Do NOT pass 'top_p', 'frequency_penalty', 'presence_penalty'.
        - Use 'max_completion_tokens' (not 'max_tokens').

    JSON mode:
        Pass response_format={"type": "json_object"} AND mention JSON in
        the system prompt. The system prompt MUST reference JSON output
        explicitly for the API to honour this mode.

    Args:
        api_key: Azure OpenAI API key.
        endpoint: Azure OpenAI endpoint URL.
        deployment: Deployment name (e.g., "o4-mini").
        api_version: API version string.
        model: Model name for logging/manifest.
        max_completion_tokens: Response length limit.
        max_attempts: Retry attempts on RateLimitError.
        backoff_factor / min_wait / max_wait: Exponential backoff config.
    """

    def __init__(self, api_key: str, endpoint: str, deployment: str,
                 api_version: str, model: str = "o4-mini",
                 max_completion_tokens: int = 4096,
                 max_attempts: int = 3, backoff_factor: float = 1.5,
                 min_wait: float = 30, max_wait: float = 120, **kwargs):
        self._deployment = deployment
        self._model = model
        self._max_completion_tokens = max_completion_tokens

        self._client = AzureOpenAI(
            api_key=api_key,
            azure_endpoint=endpoint,
            api_version=api_version,
        )
        self._retry = make_retry_decorator(
            max_attempts=max_attempts,
            backoff_factor=backoff_factor,
            min_wait=min_wait,
            max_wait=max_wait,
            retry_on=(RateLimitError,),
        )

    def chat(self, system_message: str, user_message: str,
             response_format: dict | None = None) -> dict:
        """Send a chat completion request.

        Returns:
            Dict with keys:
                'content': The model's text response.
                'usage': Dict with prompt_tokens, completion_tokens, total_tokens.
        """
        @self._retry
        def _call():
            kwargs = {
                "model": self._deployment,
                "messages": [
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": user_message},
                ],
                "max_completion_tokens": self._max_completion_tokens,
                # NOTE: do NOT add temperature= here — o-series models reject it
            }
            if response_format:
                kwargs["response_format"] = response_format

            try:
                response = self._client.chat.completions.create(**kwargs)
            except Exception as exc:
                raise LLMError(str(exc),
                               deployment=self._deployment,
                               model=self._model) from exc

            content = response.choices[0].message.content
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }
            logger.debug("LLM response: %d chars, %d tokens",
                         len(content), usage["total_tokens"])
            return {"content": content, "usage": usage}

        return _call()
```

### 14.2 Scaffolded LLM providers

Create stub files that raise `NotImplementedError`:

- `src/services/llm/openai_chat.py` — `OpenAILLMProvider`
- `src/services/llm/anthropic_chat.py` — `AnthropicLLMProvider`
- `src/services/llm/google_gemini_chat.py` — `GeminiLLMProvider`
- `src/services/llm/mistral_chat.py` — `MistralLLMProvider`
- `src/services/llm/ollama_chat.py` — `OllamaLLMProvider`

Each stub follows the same pattern as the embedding scaffolds. Documented in [SWAPPABLE_PARTS.md](explanations/SWAPPABLE_PARTS.md).

See [TESTING_GUIDE.md §Phase 14](TESTING_GUIDE.md#phase-14-tests) for verification steps.

---

## Phase 15 — Transforms: CandidateBuilder + ResponseParser

**Goal:** Build the two pure-logic classes that bridge the RAG search results and the LLM response to the final GS1 column values.

**Why in `transforms/`?** These classes have:
- No I/O (no file reads, no DB calls)
- No external API calls (no embeddings, no LLM)
- No dependency on any other `src/services/` module

They are pure data transformations. This makes them trivially testable — pass in a list of dicts, get a list of dicts back. No mocks needed at all.

### 15.1 Understanding the data flow

```
VectorStore.search() returns:
    [
        {"id": "10000124", "score": 0.87, "metadata": {
            "level": 4,
            "code": "10000124",
            "title": "Bread",
            "hierarchy_path": ["Food/Beverage/Tobacco", "Bread/Bakery Products",
                               "Bread", "Bread"],
            "hierarchy_string": "Food/... > Bread/... > Bread > Bread",
        }},
        ...30 results
    ]
               │
               ▼ CandidateBuilder.build()
    [
        {"letter": "A", "hierarchy_string": "Food > Bread > Bread > White Bread",
         "score": 0.87, "attributes": [...]},
        {"letter": "B", ...},
        ...
    ]
               │ (goes into Jinja2 prompt)
               ▼ LLM returns:
    '{"results": [{"product_id": 42, "choice": "A"}]}'
               │
               ▼ ResponseParser.parse()
    [
        {"product_id": 42,
         "gs1_segment": "Food/Beverage/Tobacco",
         "gs1_family": "Bread/Bakery Products",
         "gs1_class": "Bread",
         "gs1_brick": "White Bread",
         "gs1_attribute": "",
         "gs1_attribute_value": ""}
    ]
```

### 15.2 `src/transforms/candidate_builder.py`

```python
"""CandidateBuilder: groups RAG results by L4 brick path into lettered options."""
from __future__ import annotations
import string
from src.utils.logging import get_logger

logger = get_logger("pipeline.transforms.candidate_builder")


class CandidateBuilder:
    """Build lettered candidate options from RAG search results.

    Algorithm:
        1. Group results by their L4 brick path (hierarchy_path[:4]).
        2. Track best score per group (lowest L2 distance wins).
        3. Collect L5/L6 attribute info per group.
        4. Sort ascending by best score (lower L2 distance = better match).
        5. Assign letters A, B, C, ...

    All groups are passed to the LLM — there is no score threshold filter
    and no cap on the number of candidates.
    """

    def build(self, rag_results: list[dict]) -> list[dict]:
        """Build lettered candidates from RAG results for one product.

        Returns:
            List of candidate dicts. Each has:
                'letter', 'hierarchy_path', 'hierarchy_string',
                'score', 'attributes'.
        """
        # Group by L4 brick path
        groups: dict[str, dict] = {}
        for result in rag_results:
            meta = result.get("metadata", {})
            hierarchy = meta.get("hierarchy_path", [])
            level = meta.get("level", 0)

            l4_path = hierarchy[:4]
            l4_key = " > ".join(l4_path)
            if not l4_key:
                continue

            if l4_key not in groups:
                groups[l4_key] = {
                    "hierarchy_path": l4_path,
                    "hierarchy_string": l4_key,
                    "best_score": result["score"],
                    "attributes": [],
                }
            else:
                # Keep best score: lowest score wins (L2 distance — lower = more similar)
                if result["score"] < groups[l4_key]["best_score"]:
                    groups[l4_key]["best_score"] = result["score"]

            # Collect L5/L6 attributes
            if level >= 5:
                attr_info = {
                    "level": level,
                    "code": meta.get("code", ""),
                    "title": meta.get("title", ""),
                }
                existing_codes = {a["code"] for a in groups[l4_key]["attributes"]}
                if attr_info["code"] not in existing_codes:
                    groups[l4_key]["attributes"].append(attr_info)

        # Sort ascending by best score (lower L2 distance = better match first).
        sorted_groups = sorted(
            groups.values(), key=lambda g: g["best_score"], reverse=False
        )

        # Assign letters (no cap — all groups are passed to the LLM)
        letters = list(string.ascii_uppercase)
        candidates = []
        for i, group in enumerate(sorted_groups):
            candidates.append({
                "letter": letters[i] if i < len(letters) else f"Z{i}",
                "hierarchy_path": group["hierarchy_path"],
                "hierarchy_string": group["hierarchy_string"],
                "score": group["best_score"],
                "attributes": group["attributes"],
            })

        logger.debug("Built %d candidates", len(candidates))
        return candidates
```

### 15.3 `src/transforms/response_parser.py`

```python
"""ResponseParser: parse LLM JSON response into GS1 classification results."""
from __future__ import annotations
import json
import re
from src.utils.logging import get_logger
from src.utils.exceptions import LLMResponseParseError

logger = get_logger("pipeline.transforms.response_parser")


class ResponseParser:
    """Parse the LLM's JSON response and map letter choices to GS1 hierarchy.

    Expected LLM output format:
        {"results": [{"product_id": 42, "choice": "A"}, ...]}

    The 'choice' letter is looked up in the candidate list built by
    CandidateBuilder. The matched candidate's hierarchy_path is mapped
    to the 6 GS1 output columns.
    """

    def parse(self, raw_response: str, product_candidates: dict,
              target_columns: list[str]) -> list[dict]:
        """Parse the LLM response into a list of classification result dicts.

        Args:
            raw_response: The raw LLM response string.
            product_candidates: {product_id: [candidate dicts]} from CandidateBuilder.
            target_columns: 6 GS1 column names in order:
                [gs1_segment, gs1_family, gs1_class, gs1_brick,
                 gs1_attribute, gs1_attribute_value].

        Returns:
            List of dicts, each with 'product_id' + all 6 target column values.

        Raises:
            LLMResponseParseError: If both JSON parse and regex fallback fail.
        """
        choices = self._parse_json(raw_response)

        if choices is None:
            logger.warning("JSON parse failed, trying regex fallback")
            choices = self._parse_regex(raw_response)

        if choices is None:
            raise LLMResponseParseError(
                "Could not parse LLM response after JSON and regex attempts",
                raw_response=raw_response,
            )

        results = []
        for item in choices:
            product_id = item.get("product_id")
            choice_letter = item.get("choice", "").upper().strip()
            candidates = product_candidates.get(product_id, [])
            matched = self._find_candidate(candidates, choice_letter)

            if matched is None:
                logger.warning("Product %s: choice '%s' not found in candidates",
                               product_id, choice_letter)
                continue   # skip this product — LLM returned an unrecognised letter
            else:
                row = self._extract_gs1_levels(matched, target_columns)

            row["product_id"] = product_id
            results.append(row)

        return results

    def _parse_json(self, raw: str) -> list[dict] | None:
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                for v in data.values():
                    if isinstance(v, list):
                        return v
            return None
        except (json.JSONDecodeError, TypeError):
            return None

    def _parse_regex(self, raw: str) -> list[dict] | None:
        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                return None
        return None

    def _find_candidate(self, candidates: list[dict], letter: str) -> dict | None:
        for c in candidates:
            if c.get("letter", "").upper() == letter:
                return c
        return None

    def _extract_gs1_levels(self, candidate: dict, target_columns: list[str]) -> dict:
        """Map hierarchy_path to the 6 GS1 columns.

        hierarchy_path has 4 entries (Seg, Family, Class, Brick).
        L5/L6 come from candidate['attributes'].
        """
        path = candidate.get("hierarchy_path", [])
        attrs = candidate.get("attributes", [])
        result = {}
        for i, col in enumerate(target_columns):
            if i < len(path):
                result[col] = path[i]
            elif i == 4 and attrs:
                l5 = [a for a in attrs if a.get("level") == 5]
                result[col] = l5[0]["title"] if l5 else ""
            elif i == 5 and attrs:
                l6 = [a for a in attrs if a.get("level") == 6]
                result[col] = l6[0]["title"] if l6 else ""
            else:
                result[col] = ""
        return result
```

See [TESTING_GUIDE.md §Phase 15](TESTING_GUIDE.md#phase-15-tests) for verification steps.

---

## Phase 16 — Prompt Templates

**Goal:** Write the two Jinja2 prompt templates that the orchestrator uses to construct the LLM input.

**How templates work in this codebase:**
1. `config.yaml` sets `classification.system_template_file` and `classification.prompt_template_file`.
2. The orchestrator passes those paths to `render_template()` (Phase 5).
3. `render_template()` loads the `.j2` file and renders it with the data.
4. If the file doesn't exist or is `null`, `render_template()` uses the hardcoded fallback strings from `src/utils/templates.py`.

This means the `.j2` files are the **preferred** renderer but the pipeline never crashes without them.

### 16.1 `templates/gs1_system.j2`

The system prompt tells the LLM its role, the task, and the expected output format. This is rendered **without variables** (no Jinja2 context needed):

```
You are a product classification assistant. Your job is to classify grocery and retail products using the GS1 GPC (Global Product Classification) standard.

For each product, you will receive:
- Product information (name, packaging, category hints, etc.). Product names may be in German or other languages — use the English name (product_name_en) when available, otherwise interpret the local-language name to determine the product type.
- A list of candidate GS1 categories found by similarity search, labeled with letters [A], [B], [C], etc.

Choose the single best matching category for each product by selecting its letter. Always make a selection — pick the closest match even if it is not perfect. Never skip a product.

Respond with a JSON object containing a "results" key with an array of objects:
{"results": [{"product_id": <id>, "choice": "<letter>"}]}

Be precise. Choose the most specific matching category.
```

**Key design notes:**
- Language-awareness: the system prompt instructs the LLM to handle German product names via `product_name_en`.
- **No NONE option.** The LLM is instructed to always pick the closest match. The candidate builder provides real candidates for every product (falling back to top-K raw results if threshold filters everything).
- JSON mode is enforced via `response_format={"type": "json_object"}` in the API call; this prompt confirms JSON is expected, which the Azure OpenAI API requires.

### 16.2 `templates/gs1_classification.j2`

The user prompt lists all products in the batch with their candidates. Receives a `products` list — each item has `product_id`, `context` (dict), and `candidates` (list from CandidateBuilder):

```jinja2
Classify the following {{ products | length }} product(s) into GS1 GPC categories.

{% for product in products %}
--- Product {{ product.product_id }} ---
{% for key, value in product.context.items() %}{% if value %}{{ key }}: {{ value }}
{% endif %}{% endfor %}
Candidate categories:
{% for candidate in product.candidates %}[{{ candidate.letter }}] {{ candidate.hierarchy_string }}{% if candidate.attributes %} | {{ candidate.attributes | map(attribute='title') | join(', ') }}{% endif %}
{% endfor %}
{% endfor %}
Respond with a JSON object containing a "results" key:
{"results": [{"product_id": <id>, "choice": "<letter>"}, ...]}
```

**Template variable reference:**

| Variable | Type | Source | Description |
|---|---|---|---|
| `products` | `list` | orchestrator | One item per product in the batch |
| `product.product_id` | `any` | DB row | Primary key value |
| `product.context` | `dict` | orchestrator | E.g. `{"product_name": "Weissbrot", "product_name_en": "White bread", "packaging_value": "500", "packaging_unit": "g"}` |
| `product.candidates` | `list` | CandidateBuilder | Lettered options |
| `candidate.letter` | `str` | CandidateBuilder | "A", "B", ... |
| `candidate.hierarchy_string` | `str` | CandidateBuilder | Full L1–L4 path string |
| `candidate.attributes` | `list` | CandidateBuilder | L5/L6 attribute dicts — rendered inline with `\|` separator |

**Context format:** Product fields are printed as `key: value` lines (only non-empty values). Attributes appear inline after the candidate path, separated by `|`.

**Rendered example (2 products, abbreviated):**

```
Classify the following 2 product(s) into GS1 GPC categories.

--- Product 101 ---
product_name: Vollkornbrot
product_name_en: Whole grain wheat bread
packaging_value: 400
packaging_unit: g

Candidate categories:
[A] Food/Beverage/Tobacco > Bread/Bakery Products > Bread > White & Wholemeal Bread | Pre-sliced Brown Bread
[B] Food/Beverage/Tobacco > Bread/Bakery Products > Bread > Specialty Bread

--- Product 102 ---
...

Respond with a JSON object containing a "results" key:
{"results": [{"product_id": <id>, "choice": "<letter>"}, ...]}
```

See [TESTING_GUIDE.md §Phase 16](TESTING_GUIDE.md#phase-16-tests) for verification steps.

---

## Phase 17 — LLM Orchestrator Service

**Goal:** Write `LLMOrchestratorService`, which combines all the pieces built in Phases 9–16 into a single `classify_batch()` method.

**What the orchestrator does NOT do:**
- It does not fetch from the DB.
- It does not write to the DB.
- It does not loop over batches.
- It does not know about `config.database` — it receives pre-built objects.

**What the orchestrator DOES do:**
- Accepts a list of dicts (one per product), each already containing the DB row data.
- For each product: deserialize the stored embedding → RAG search → filter/group into candidates.
- Render the prompt with all products at once.
- Call the LLM once per batch (not once per product).
- Parse the response → map letter choices back to candidates → extract GS1 levels.

**Why batch all products into a single LLM call?** Fewer API round trips → lower latency and lower API cost. The templates are designed to handle N products in one call. The tradeoff is that a single response parse error fails the whole batch — which is why the `classify` workflow catches `PipelineError` per batch and continues.

### 17.1 `src/services/orchestrator.py`

```python
"""LLM Orchestrator Service: RAG search + candidate build + prompt + LLM + parse."""
from __future__ import annotations
import json
from src.config.models import AppConfig
from src.services.vectorstore.base import VectorStore
from src.services.llm.base import LLMProvider
from src.transforms.candidate_builder import CandidateBuilder
from src.transforms.response_parser import ResponseParser
from src.utils.templates import render_template, FALLBACK_SYSTEM, FALLBACK_CLASSIFICATION
from src.utils.logging import get_logger

logger = get_logger("pipeline.services.orchestrator")


class LLMOrchestratorService:
    """Orchestrates the full RAG-powered classification flow for one batch.

    Args:
        config: Validated app config.
        vector_store: Already-loaded vector store (load() was called by the entry point).
        llm_provider: Initialized LLM provider.
    """

    def __init__(self, config: AppConfig, vector_store: VectorStore,
                 llm_provider: LLMProvider):
        self._config = config
        self._vector_store = vector_store
        self._llm = llm_provider

        cls_cfg = config.classification
        self._candidate_builder = CandidateBuilder()
        self._response_parser = ResponseParser()

        self._top_k = cls_cfg.rag_top_k
        self._prompt_columns = cls_cfg.prompt_columns
        self._target_columns = cls_cfg.target_columns
        self._system_template = cls_cfg.system_template_file
        self._classification_template = cls_cfg.prompt_template_file

    def classify_batch(self, rows: list[dict]) -> list[dict]:
        """Classify a batch of product rows via RAG + LLM.

        Uses a single vectorized FAISS call (`search_batch`) for all products
        in the batch — one `index.search(matrix, top_k)` — rather than N
        individual calls. Normalization is handled inside `search_batch()`.

        Args:
            rows: Product row dicts. Each must have:
                  - the primary key column (usually 'id')
                  - 'embedding_context' (JSON-encoded float list)
                  - the prompt columns (product_name, etc.)

        Returns:
            List of result dicts: {'product_id': ..., 'gs1_segment': ..., ...}
        """
        products_for_prompt = []
        product_candidates_map = {}

        # [STAGE: PARSE_EMBEDDINGS]
        valid_rows: list[dict] = []
        embeddings: list[list[float]] = []

        for row in rows:
            product_id = row.get("id")
            embedding_raw = row.get("embedding_context")
            if embedding_raw is None:
                logger.warning("Product %s: no embedding_context, skipping", product_id)
                continue
            if isinstance(embedding_raw, str):
                embedding = json.loads(embedding_raw)
            elif isinstance(embedding_raw, list):
                embedding = embedding_raw
            else:
                logger.warning("Product %s: unexpected embedding type, skipping", product_id)
                continue
            valid_rows.append(row)
            embeddings.append(embedding)

        if not valid_rows:
            logger.warning("No products with valid embeddings in this batch")
            return []

        # [STAGE: VECTOR_SEARCH]
        # Single batched FAISS call for all products — one index.search(matrix, top_k).
        # Returns one result list per product; normalization handled inside search_batch().
        all_rag_results = self._vector_store.search_batch(
            query_vectors=embeddings,
            top_k=self._top_k,
        )

        # [STAGE: CANDIDATE_FILTER]
        for row, rag_results in zip(valid_rows, all_rag_results):
            product_id = row.get("id")
            candidates = self._candidate_builder.build(rag_results)
            context = {col: str(row.get(col, "") or "") for col in self._prompt_columns}
            product_candidates_map[product_id] = candidates
            products_for_prompt.append({
                "product_id": product_id,
                "context": context,
                "candidates": candidates,
            })

        if not products_for_prompt:
            logger.warning("No products to classify in this batch")
            return []

        # [STAGE: PROMPT_BUILD] — render system + user messages
        system_message = render_template(self._system_template, FALLBACK_SYSTEM)
        user_message = render_template(
            self._classification_template, FALLBACK_CLASSIFICATION,
            products=products_for_prompt,
        )
        logger.debug("Prompt: %d chars for %d products",
                     len(user_message), len(products_for_prompt))
        llm_response = self._llm.chat(
            system_message=system_message,
            user_message=user_message,
            response_format={"type": "json_object"},
        )
        logger.info("LLM usage: %s", llm_response["usage"])

        # [STAGE: RESPONSE_PARSE] — map letter choices back to GS1 columns
        return self._response_parser.parse(
            raw_response=llm_response["content"],
            product_candidates=product_candidates_map,
            target_columns=self._target_columns,
        )
```

See [TESTING_GUIDE.md §Phase 17](TESTING_GUIDE.md#phase-17-tests) for verification steps.

---

## Phase 18 — Classify Workflow + Entry Points

**Goal:** Write `run_classify()` (the classify pipeline loop) and the two complete entry point files.

### 18.1 `src/workflows/classify.py`

The classify workflow is the most complex pipeline function. It drives a `DatabaseBatcher` loop and calls the orchestrator per batch:

```python
"""classify workflow: fetch unclassified rows → RAG + LLM → write GS1 columns."""
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
    """Execute the classify pipeline.

    For each batch:
        1. Fetch rows where gs1_segment IS NULL.
        2. Call orchestrator.classify_batch() — RAG + LLM.
        3. Write result to 6 GS1 columns in DB.
        4. Catch PipelineError per batch → append to failed list → continue.

    Failed products are written to logs/failed_products.json.

    Args:
        config: Validated app config.
        orchestrator: Initialized LLMOrchestratorService.
        db_connector: Initialized database connector.
    """
    cls_cfg = config.classification
    full_table = f"{config.database.schema_name}.{config.database.table}"
    pk = config.database.primary_key
    batch_size = cls_cfg.batch_size
    target_cols = cls_cfg.target_columns
    prompt_cols = cls_cfg.prompt_columns

    select_cols = [pk] + prompt_cols + ["embedding_context"]
    base_query = (
        f"SELECT {', '.join(select_cols)} FROM {full_table} "
        f"WHERE gs1_segment IS NULL"
    )

    failed_products: list[dict] = []
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
        logger.info("Classify starting: %d rows, batch_size=%d, batches=%d",
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

            logger.info("Batch %d/%d — %d rows", batch_num, total_batches, len(rows))
            console.batch_start(
                batch_num=batch_num,
                total_batches=total_batches,
                row_count=len(rows),
                product_names=product_names,
            )

            try:
                results = orchestrator.classify_batch(rows)

                if not results:
                    logger.warning("Batch %d: no results returned", batch_num)
                    console.warning(f"Batch {batch_num}", "No results returned — skipping")
                    continue

                # Build update dicts
                updates = []
                category_counts: dict[str, int] = {}
                for result in results:
                    update = {pk: result["product_id"]}
                    for col in target_cols:
                        update[col] = result.get(col, "")
                    updates.append(update)
                    seg = result.get("gs1_segment", "")
                    if seg:
                        category_counts[seg] = category_counts.get(seg, 0) + 1

                db_connector.update_rows(full_table, updates, key_column=pk)
                logger.info("Batch %d: wrote %d rows to DB", batch_num, len(updates))

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
                logger.error("Batch %d failed: %s", batch_num, e, exc_info=True)
                console.error(f"Batch {batch_num} failed", str(e))
                for row in rows:
                    failed_products.append({
                        "product_id": row.get(pk),
                        "batch": batch_num,
                        "error": str(e),
                    })
                continue   # skip this batch, continue with the next
            except Exception as e:
                logger.error("Batch %d unexpected error: %s", batch_num, e, exc_info=True)
                console.error(f"Batch {batch_num} failed", str(e))
                for row in rows:
                    failed_products.append({
                        "product_id": row.get(pk),
                        "batch": batch_num,
                        "error": str(e),
                    })
                continue

            time.sleep(1.0)   # brief pause between batches

    finally:
        db_connector.disconnect()

    total_elapsed = time.time() - pipeline_start
    failed_count = len(failed_products)

    if failed_products:
        _save_failed_products(failed_products)

    logger.info("Classify complete — classified: %d, failed: %d, elapsed: %.1fs",
                total_classified, failed_count, total_elapsed)
    console.classification_summary(
        total=total_classified + failed_count,
        classified=total_classified,
        failed=failed_count,
        elapsed_s=total_elapsed,
    )


def _save_failed_products(failed: list[dict]) -> None:
    """Write failed products to logs/failed_products.json."""
    log_dir = Path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / "failed_products.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(failed, f, indent=2, ensure_ascii=False)
    logger.info("Failed products log: %s", path)
```

### 18.2 `main.py` — classify entry point

```python
"""Entry point: classify mode. Run with: python main.py"""
import argparse
import sys
from src.utils.logging import setup_logging, get_logger
from src.utils.console import console

# ── Logging initialized at module level, before anything else runs.
# Imports in main() are deferred to avoid importing providers before logging.
setup_logging(mode_prefix="classify")
logger = get_logger("pipeline.main")


def main():
    from src.config.models import load_config
    from src.utils.env import get_env
    from src.factory import ComponentFactory
    from src.utils.exceptions import PipelineError

    parser = argparse.ArgumentParser(description="Product classification pipeline")
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()

    try:
        config = load_config(args.config)
    except PipelineError as e:
        logger.error("Config error: %s", e)
        console.error("Config Error", str(e))
        sys.exit(1)

    console.pipeline_start(name=config.pipeline.name, config_path=args.config, mode="classify")
    logger.info("Pipeline: %s | Mode: classify", config.pipeline.name)

    try:
        from src.services.embedding.azure_openai_embedder import AzureOpenAIEmbeddingProvider
        from src.services.embedding.huggingface import HuggingFaceEmbeddingProvider
        from src.services.vectorstore.faiss_store import FAISSVectorStore
        from src.services.llm.azure_openai_chat import AzureOpenAILLMProvider
        from src.services.db.azure_sql_connector import AzureSQLConnector
        from src.services.db.postgresql import PostgreSQLConnector
        from src.services.orchestrator import LLMOrchestratorService
        from src.workflows.classify import run_classify

        # classify needs all 4 component types
        factory = ComponentFactory()
        factory.register_embedding("azure_openai", AzureOpenAIEmbeddingProvider)
        factory.register_embedding("huggingface", HuggingFaceEmbeddingProvider)
        factory.register_vectorstore("faiss", FAISSVectorStore)
        factory.register_llm("azure_openai", AzureOpenAILLMProvider)
        factory.register_db("azure_sql", AzureSQLConnector)
        factory.register_db("postgresql", PostgreSQLConnector)

        # Load FAISS index from disk
        vs_kwargs = {
            "output_dir": config.vector_store.output_dir,
            "filename_prefix": config.vector_store.filename_prefix,
            "lookup_metadata_fields": config.vector_store.lookup_metadata_fields,
            "embedding_dimensions": config.embedding.dimensions,
        }
        vector_store = factory.create_vectorstore(config.vector_store.type, **vs_kwargs)
        vector_store.load()   # reads index + lookup + manifest from disk

        llm_provider = factory.create_llm(config.llm.type, **_build_llm_kwargs(config, get_env))
        orchestrator = LLMOrchestratorService(config, vector_store, llm_provider)
        db_connector = factory.create_db(config.database.type, **_build_db_kwargs(config, get_env))

        run_classify(config, orchestrator, db_connector)
        console.pipeline_finished(success=True)

    except KeyboardInterrupt:
        console.interrupted()
        logger.warning("Pipeline interrupted by user")
        sys.exit(130)
    except PipelineError as e:
        logger.error("Pipeline error: %s", e, exc_info=True)
        console.error("Pipeline Error", str(e))
        console.pipeline_finished(success=False)
        sys.exit(1)
    except Exception as e:
        logger.exception("Unexpected error: %s", e)
        console.error("Unexpected Error", str(e))
        console.pipeline_finished(success=False)
        sys.exit(1)


def _build_llm_kwargs(config, get_env):
    """Secrets come from .env; tunables come from config.yaml."""
    return {
        "api_key":               get_env("AZURE_OPENAI_API_KEY"),
        "endpoint":              get_env("AZURE_OPENAI_ENDPOINT"),
        "deployment":            get_env("AZURE_OPENAI_CHAT_DEPLOYMENT"),
        "api_version":           get_env("AZURE_OPENAI_API_VERSION"),
        "max_completion_tokens": config.llm.max_completion_tokens,
        "max_attempts":          config.system.retry.max_attempts,
        "backoff_factor":        config.system.retry.backoff_factor,
        "min_wait":              config.system.retry.min_wait,
        "max_wait":              config.system.retry.max_wait,
    }


def _build_db_kwargs(config, get_env):
    """Secrets come from .env; tunables come from config.yaml."""
    kwargs = {
        "schema_name": config.database.schema_name,
        "table":       config.database.table,
        "primary_key": config.database.primary_key,
    }
    if config.database.type == "azure_sql":
        kwargs.update({
            "server":        get_env("AZURE_SQL_SERVER"),
            "database":      get_env("AZURE_SQL_DATABASE"),
            "client_id":     get_env("AZURE_SQL_CLIENT_ID"),
            "client_secret": get_env("AZURE_SQL_CLIENT_SECRET"),
        })
    elif config.database.type == "postgresql":
        kwargs.update({
            "host":     get_env("PG_HOST"),
            "port":     int(get_env("PG_PORT")),
            "database": get_env("PG_DATABASE"),
            "username": get_env("PG_USERNAME"),
            "password": get_env("PG_PASSWORD"),
        })
    return kwargs


if __name__ == "__main__":
    main()
```

### 18.3 `vectorize.py` — build-vectors + embed-rows entry point

This entry point handles two subcommands via `argparse`. A key design feature: `setup_logging()` is called **after** the mode is determined (so the log filename contains the mode name). Everything else in `main.py` follows the same pattern.

```python
"""Entry point for vector store operations. Usage:
    python vectorize.py build-vectors [--config config.yaml]
    python vectorize.py embed-rows    [--config config.yaml]
"""
import argparse
import sys
from src.utils.logging import setup_logging, get_logger
from src.utils.console import console


def build_factory_for_mode(mode: str):
    """Build a minimal factory with only the providers the mode needs.

    build-vectors: embedding + vectorstore
    embed-rows:    embedding + database
    """
    from src.factory import ComponentFactory
    from src.services.embedding.azure_openai_embedder import AzureOpenAIEmbeddingProvider
    from src.services.embedding.huggingface import HuggingFaceEmbeddingProvider

    factory = ComponentFactory()
    factory.register_embedding("azure_openai", AzureOpenAIEmbeddingProvider)
    factory.register_embedding("huggingface", HuggingFaceEmbeddingProvider)

    if mode == "build-vectors":
        from src.services.vectorstore.faiss_store import FAISSVectorStore
        factory.register_vectorstore("faiss", FAISSVectorStore)
    elif mode == "embed-rows":
        from src.services.db.azure_sql_connector import AzureSQLConnector
        from src.services.db.postgresql import PostgreSQLConnector
        factory.register_db("azure_sql", AzureSQLConnector)
        factory.register_db("postgresql", PostgreSQLConnector)

    return factory


def main():
    from src.config.models import load_config
    from src.utils.env import get_env
    from src.utils.exceptions import PipelineError

    parser = argparse.ArgumentParser(description="Vector store & embedding operations")
    sub = parser.add_subparsers(dest="mode", help="Operation mode")

    bv = sub.add_parser("build-vectors", help="Build FAISS index from taxonomy JSON")
    bv.add_argument("--config", default="config.yaml")

    er = sub.add_parser("embed-rows", help="Embed database rows")
    er.add_argument("--config", default="config.yaml")

    args = parser.parse_args()

    if args.mode is None:
        parser.print_help()
        sys.exit(1)

    # Logging now knows the mode — log file is named accordingly
    mode_prefix = args.mode.replace("-", "_")   # "build_vectors" or "embed_rows"
    setup_logging(mode_prefix=mode_prefix)
    logger = get_logger("pipeline.vectorize")

    try:
        config = load_config(args.config)
    except PipelineError as e:
        console.error(str(e))
        sys.exit(1)

    console.pipeline_start(name=config.pipeline.name, config_path=args.config, mode=args.mode)
    logger.info("Pipeline: %s | Mode: %s", config.pipeline.name, args.mode)

    factory = build_factory_for_mode(args.mode)

    try:
        if args.mode == "build-vectors":
            _run_build_vectors(config, factory, get_env)
        elif args.mode == "embed-rows":
            _run_embed_rows(config, factory, get_env)
        console.pipeline_finished(success=True)
    except KeyboardInterrupt:
        console.interrupted()
        sys.exit(130)
    except PipelineError as e:
        console.error(str(e))
        logger.error("Pipeline failed: %s", e)
        console.pipeline_finished(success=False)
        sys.exit(1)
    except Exception as e:
        console.error(f"Unexpected error: {e}")
        logger.exception("Unexpected error")
        sys.exit(1)


def _run_build_vectors(config, factory, get_env):
    from src.workflows.build_vectors import run_build_vectors

    embedding_provider = factory.create_embedding(
        config.embedding.type, **_build_embedding_kwargs(config, get_env)
    )
    vs_kwargs = {
        "output_dir":            config.vector_store.output_dir,
        "filename_prefix":       config.vector_store.filename_prefix,
        "lookup_metadata_fields": config.vector_store.lookup_metadata_fields,
        "embedding_dimensions":  config.embedding.dimensions,
        "embedding_model": (
            get_env("AZURE_OPENAI_EMBEDDING_DEPLOYMENT")
            if config.embedding.type == "azure_openai"
            else (config.embedding.model_name or "unknown")
        ),
    }
    vector_store = factory.create_vectorstore(config.vector_store.type, **vs_kwargs)
    run_build_vectors(config, embedding_provider, vector_store)


def _run_embed_rows(config, factory, get_env):
    from src.workflows.embed_rows import run_embed_rows

    embedding_provider = factory.create_embedding(
        config.embedding.type, **_build_embedding_kwargs(config, get_env)
    )
    db_connector = factory.create_db(
        config.database.type, **_build_db_kwargs(config, get_env)
    )
    run_embed_rows(config, embedding_provider, db_connector)


def _build_embedding_kwargs(config, get_env) -> dict:
    kwargs = {
        "dimensions":    config.embedding.dimensions,
        "batch_size":    config.embedding.batch_size,
        "max_workers":   config.embedding.max_workers,
        "max_attempts":  config.system.retry.max_attempts,
        "backoff_factor": config.system.retry.backoff_factor,
        "min_wait":      config.system.retry.min_wait,
        "max_wait":      config.system.retry.max_wait,
    }
    if config.embedding.type == "azure_openai":
        kwargs.update({
            "api_key":    get_env("AZURE_OPENAI_API_KEY"),
            "endpoint":   get_env("AZURE_OPENAI_ENDPOINT"),
            "deployment": get_env("AZURE_OPENAI_EMBEDDING_DEPLOYMENT"),
            "api_version": get_env("AZURE_OPENAI_API_VERSION"),
        })
    elif config.embedding.type == "huggingface":
        kwargs["model_name"] = config.embedding.model_name
    return kwargs


def _build_db_kwargs(config, get_env) -> dict:
    kwargs = {
        "schema_name": config.database.schema_name,
        "table":       config.database.table,
        "primary_key": config.database.primary_key,
    }
    if config.database.type == "azure_sql":
        kwargs.update({
            "server":        get_env("AZURE_SQL_SERVER"),
            "database":      get_env("AZURE_SQL_DATABASE"),
            "client_id":     get_env("AZURE_SQL_CLIENT_ID"),
            "client_secret": get_env("AZURE_SQL_CLIENT_SECRET"),
        })
    elif config.database.type == "postgresql":
        kwargs.update({
            "host":     get_env("PG_HOST"),
            "port":     int(get_env("PG_PORT")),
            "database": get_env("PG_DATABASE"),
            "username": get_env("PG_USERNAME"),
            "password": get_env("PG_PASSWORD"),
        })
    return kwargs


if __name__ == "__main__":
    main()
```

### 18.4 Complete build sequence summary

The full pipeline is now complete. Here is where each file lives and what it does:

```
Entry points:
  main.py                        classify mode
  vectorize.py                   build-vectors / embed-rows modes

Config:
  config.yaml                    all settings
  .env                           secrets
  src/utils/env.py               ${VAR} interpolation
  src/config/models.py           Pydantic AppConfig + load_config()

Utilities (no src/ deps):
  src/utils/exceptions.py        PipelineError hierarchy
  src/utils/logging.py           setup_logging() + get_logger()
  src/utils/console.py           Console class (terminal output)
  src/utils/batching.py          iter_batches() + DatabaseBatcher
  src/utils/retry.py             make_retry_decorator()
  src/utils/templates.py         render_template()

Domain types:
  src/dto.py                     Document dataclass

Interfaces (ABCs):
  src/services/embedding/base.py EmbeddingProvider
  src/services/vectorstore/base.py VectorStore
  src/services/llm/base.py       LLMProvider
  src/services/db/base.py        DatabaseConnector

Implementations:
  src/services/embedding/azure_openai_embedder.py  AzureOpenAIEmbeddingProvider
  src/services/embedding/huggingface.py            HuggingFaceEmbeddingProvider
  src/services/vectorstore/faiss_store.py          FAISSVectorStore
  src/services/llm/azure_openai_chat.py            AzureOpenAILLMProvider
  src/services/db/azure_sql_connector.py           AzureSQLConnector
  src/services/db/postgresql.py                    PostgreSQLConnector

Pure transforms:
  src/transforms/candidate_builder.py  CandidateBuilder
  src/transforms/response_parser.py    ResponseParser

Services:
  src/services/gs1_parser.py           GS1Parser
  src/services/orchestrator.py         LLMOrchestratorService

Workflows:
  src/workflows/build_vectors.py       run_build_vectors()
  src/workflows/embed_rows.py          run_embed_rows()
  src/workflows/classify.py            run_classify()

Prompt templates:
  templates/gs1_system.j2
  templates/gs1_classification.j2

Registry:
  src/factory.py                 ComponentFactory + build_default_factory()
```

See [TESTING_GUIDE.md §Phase 18](TESTING_GUIDE.md#phase-18-tests) for final end-to-end verification steps.

---

*This completes the Build Guide. See [TESTING_GUIDE.md](TESTING_GUIDE.md) for the complete test suite.*
