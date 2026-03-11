# Prompt: Design Document for a Product Classification Pipeline

You are a senior software architect. I need you to write a **design document** (implementation guide) for a Python application — a **simple, YAML-configurable, extensible pipeline** that handles vector store creation, database row embedding, and RAG-powered product classification.

Read this entire prompt carefully. At the end, you will find the **finalized design decisions** (PART 5) that have already been approved. Use those decisions as binding constraints when writing the full design document.

---

## PART 1 — WHAT THE APP DOES

The application has **two entry points** and **three pipeline modes**. All three modes share infrastructure (embedding provider, database connector, vector store, logging, retry logic) and are controlled by a single `config.yaml` file.

**Entry points:**
- **`main.py`** — The primary entry point. Runs the `classify` mode by default (classifies unclassified rows in the database). Running `python main.py` with no arguments starts classification immediately.
- **`vectorize.py`** — Separate entry point for vector store operations. Has CLI flags for settings. Supports two sub-modes: `build-vectors` (build the FAISS index from a taxonomy JSON) and `embed-rows` (embed database rows). Example: `python vectorize.py build-vectors --config config.yaml` or `python vectorize.py embed-rows`.

---

### Mode 1: `build-vectors` — Build a Vector Store from a Data Source

**Purpose:** Read a structured data file (e.g. a GS1 GPC taxonomy JSON), parse it into flat documents, generate vector embeddings via Azure OpenAI, and save everything to disk as a FAISS index + supporting artefacts.

**Input:**
- A GS1 GPC JSON file (e.g. `data/input/GS1.json`). The JSON has a top-level `"Schema"` key containing a recursive tree. Each node has: `Code`, `Title`, `Level` (1–6), `Definition`, `DefinitionExcludes`, `Active`, `Childs` (array of child nodes). The 6 levels are: Segment → Family → Class → Brick → Attribute → AttributeValue.

**Processing:**
- A parser plugin recursively traverses the tree and produces one `Document` per node. Each Document has:
  - `id`: the GS1 code (e.g. `"10000000"`)
  - `text`: embedding text built as `"Segment > Family > Class > Brick | definition | Excludes: ..."` (hierarchy path joined with ` > `, then definition, then excludes — separated by ` | `)
  - `metadata`: dict with `source`, `level`, `code`, `title`, `hierarchy_path` (list), `hierarchy_string`, `definition`, `excludes`, `active`
- Documents are batched and sent to Azure OpenAI `text-embedding-3-large` (1024 dimensions by default) via the `openai` Python SDK's `AzureOpenAI` client. Parallel batching with `ThreadPoolExecutor` (default 5 workers, 256 texts per API call). Retry with `tenacity` on `RateLimitError` (exponential backoff, max 3 attempts, 30–120s waits).
- Embedded documents are saved to disk.

**Output (5 artefacts):**
1. `faiss_{prefix}.index` — FAISS index binary file (always `IndexFlatL2`; vectors are L2-normalised in-place for consistent magnitude before indexing; scores are squared L2 distances in [0, 4] for unit vectors — lower = more similar)
2. `faiss_{prefix}_metadata.json` — JSON mapping: `{ "ids": [...], "metadata": [...] }` (index position → doc ID + full metadata)
3. `embeddings_{prefix}.parquet` — Parquet archive of all documents (id, text, embedding, metadata). For re-indexing without re-calling the API.
4. `{prefix}_lookup.pkl` — Compact Python pickle: `{ int(id): { selected metadata fields } }`. Loaded at query time by the classifier. Fields are configurable (default: all metadata; can be restricted via `lookup_metadata_fields` config).
5. `build_manifest.json` — Audit trail: timestamp, model, dimension, doc count, index type, prefix.

**Architecture requirements for this mode:**
- The vector store is a **system**, not just an index. Building it requires: a parser (to flatten the tree into documents), an embedder (to vectorize them), an indexer (FAISS), and file I/O (to produce all 5 artefacts). At query time, it provides: load index + lookup → search → return metadata.
- **Critical constraint:** The embedding model and dimensions used for the vector store MUST match those used for database row embeddings (`embed-rows` mode). Both read from the same `embedding` config section to guarantee this. Otherwise RAG similarity search between product embeddings and taxonomy embeddings would be comparing incompatible vectors.
- The source is always a JSON file in `data/`. However, the JSON structure may vary — it could be GS1 GPC today, or a different hierarchical taxonomy tomorrow. Each node in the tree is a path from root to its deepest leaf. The vector store creates one document per such node-path.
- Concrete parser: `GS1Parser` — parses the specific GS1 JSON structure. Other parsers can be written for different tree formats, but this is lowest priority. The `GS1Parser` is a concrete class (not behind a swappable interface for now).
- Swappable components via interfaces: `EmbeddingProvider` (embed_batch, dimension property), `VectorStore` (save, load, search).
- Concrete implementations to build first: `AzureOpenAIEmbeddingProvider`, `HuggingFaceEmbeddingProvider`, `FAISSVectorStore`.
- A `ComponentFactory` with registries mapping config type strings to classes. A `build_default_factory()` helper pre-registers all built-in implementations.
- Config-driven: YAML validated by Pydantic models. Supports env-var interpolation (`${VAR_NAME}`).
- **FAISS index type:** Always uses `IndexFlatL2`. Vectors are L2-normalised in-place before indexing for consistent magnitude. Scores are squared L2 distances in [0, 4] for unit vectors — lower = more similar. There is no cosine similarity / inner product mode.

**Config for this mode** (matches actual `config.yaml`):
```yaml
version: "2.0"
pipeline:
  name: "gs1-vectoRAG-classifier"
  description: "Vector store creation, row embedding, and RAG-powered classification"
system:
  log_level: "INFO"
  max_workers: 5
  batch_size: 256
  retry:
    max_attempts: 3
    backoff_factor: 1.5
    min_wait: 30.0
    max_wait: 120.0
source:
  type: "file_json"           # always a JSON file from data/ directory
  path: "data/input/GS1.json"
  encoding: "utf-8"
  parser: "gs1"               # concrete parser for GS1 JSON structure
  batch_size: 50              # documents per embedding batch during build-vectors
# Secrets (api_key, endpoint, deployment, api_version) live in .env only.
embedding:
  type: "azure_openai"        # also scaffolded: huggingface, openai, ollama, cohere
  dimensions: 1024
  batch_size: 256
  max_workers: 5
  # model_name: "all-MiniLM-L6-v2"   # only used for huggingface type
vector_store:
  type: "faiss"               # also scaffolded: chromadb, azure_search
  output_dir: "data/vector_store"
  filename_prefix: "gs1"
  lookup_metadata_fields:
    - level
    - code
    - title
    - hierarchy_path
    - hierarchy_string
```

---

### Mode 2: `embed-rows` — Embed Database Rows

**Purpose:** Read product rows from an Azure SQL Database in batches, concatenate selected text columns into a single string, generate vector embeddings via Azure OpenAI, and write the embeddings back to the same rows in the database.

**Input:**
- Product rows from an Azure SQL table (e.g. `playground.promo_bronze`). The table contains promotional product data from European retailers. Columns include: `id` (PK), `store`, `country`, `product_name`, `product_name_en`, `origin`, `class`, `packaging_value`, `packaging_unit`, `packaging_type`, `category`, prices, dates, image URLs, and 6 `gs1_*` columns (segment, family, class, brick, attribute, attribute_value), plus an `embedding_context` vector column.

**Processing:**
Concatenates configured columns with `" * "` separator (default: `store, country, product_name, product_name_en, category, packaging_type, packaging_value, packaging_unit`). The resulting string is embedded and stored in the `embedding_context` column. This embedding is used later by the `classify` mode for RAG similarity search.

**Update modes:**
- `empty` (only mode implemented): Process rows where the target embedding column is `NULL`. This is the default and only supported mode — the pipeline always resumes from where it left off.

> Note: An `all` mode (recompute all embeddings) may be added in the future by removing the `WHERE target IS NULL` filter.

**Batch processing:** Uses a `DatabaseBatcher` class that paginates through the table with `OFFSET … FETCH NEXT` SQL, yielding one `batch_size` chunk at a time — no full table load into memory. Each batch: fetch rows → preprocess text → call embedding API → **write embeddings back to DB immediately after that batch completes**.

**Embedding:** Same `EmbeddingProvider` used by `build-vectors` mode (same model, same dimensions — critical for RAG compatibility). Default: Azure OpenAI `text-embedding-3-large`, 1024 dimensions, `openai` SDK `AzureOpenAI` client. Retry on rate limits (configurable: max_attempts, backoff_factor via `tenacity`).

**Database:** Azure SQL (Service Principal auth via pyodbc + SQLAlchemy) or PostgreSQL (username/password via psycopg2 + SQLAlchemy). Configurable in YAML — switching databases means changing config, not code.

**Config for this mode should expose:**
- Which columns to concatenate (and their separator)
- Target column to write the embedding to
- Row batch size
- All DB connection params and credential env-var names (via `.env`)

> Note: The `update_mode` setting (empty vs. all) is not yet in config. The workflow always processes only rows where the target column is `NULL`.

---

### Mode 3: `classify` — RAG-Powered Product Classification

**Purpose:** Fetch unclassified product rows from the database, use RAG (vector similarity search against the FAISS index built by `build-vectors` mode) to find candidate GS1 categories, build a prompt with the candidates, send it to Azure OpenAI chat completions (LLM), parse the LLM's JSON response, and write the 6-level GS1 classification back to the database.

This mode is powered by the **LLM Orchestrator Service** — a single service class that combines vector store loading, RAG similarity search, candidate building, prompt construction, LLM calls, and response parsing into one cohesive flow.

**Input:**
- Unclassified product rows from the database (WHERE `gs1_segment IS NULL`). Each row must already have an `embedding_context` column (populated by `embed-rows` mode).
- The FAISS index + lookup files built by `build-vectors` mode (loaded from `data/vector_store/`).

**Detailed classification flow (per batch of ~10 products):**

1. **Fetch:** Query DB for up to `BATCH_SIZE` (default 10) rows where `gs1_segment IS NULL`. Returns a pandas DataFrame.

2. **Parse embeddings:** Extract the `embedding_context` column from each row. It's stored as a JSON string of floats. Parse it into a Python list of floats.

3. **FAISS search (batch):** For all products in the batch at once, normalize each embedding vector (L2 norm), pass the full matrix to `FAISSVectorStore.search_batch()` (single `index.search(matrix, top_k)` call). Each result carries metadata from the lookup pickle: `level`, `code`, `title`, `hierarchy_path`, `hierarchy_string`. All `top_k` results are returned — there is no score threshold filter.

4. **Build candidates (per product):** Group RAG results by their L4 "brick path" (first 4 levels of hierarchy: Segment > Family > Class > Brick). Deduplicate, keeping the best score per group (lowest L2 distance wins). Also attach L5/L6 attribute info if present in the results. Sort ascending by best score (lower L2 distance = better match first). Assign letters A, B, C, ..., Z to each unique candidate path. All groups are passed to the LLM — there is no cap on the number of candidates.

5. **Build prompt:** Construct messages for the LLM:
   - A **system message** rendered from `templates/gs1_system.j2` (or fallback hardcoded string). Establishes the assistant role and output format.
   - A **user message** rendered from `templates/gs1_classification.j2` (or fallback hardcoded string). Contains context fields and the lettered candidate block per product.
   - Expected output format (in templates): a JSON object `{"results": [{"product_id": ..., "choice": "A"}, ...]}`

6. **LLM call:** Send the prompt to Azure OpenAI chat completions (e.g. GPT-4o) with `response_format={"type": "json_object"}` to force valid JSON output. Returns the JSON response + token usage.

7. **Parse response:** Parse the JSON response with `json.loads()`. The expected format is `{"results": [...]}`. If JSON parsing fails, fall back to regex extraction of the first `[...]` block. For each product, map the chosen letter (e.g. "A") back to the candidate's full hierarchy path. Extract the 6 GS1 levels: segment, family, class, brick, attribute, attribute_value. Special cases: `[NONE]` choice → all 6 columns set to `"NONE"`; unknown letter → all 6 columns set to `"UNKNOWN"` (logged at WARNING).

8. **Update DB:** Write the 6 GS1 columns back to the database **immediately after each batch completes**. Safety: the UPDATE query includes `WHERE gs1_segment IS NULL` to never overwrite existing classifications.

9. **Loop:** Repeat until no unclassified rows remain. Each batch is independent — if one fails after retries, log the error, skip it, continue with the next.

**RAG tuning parameters:**
- `RAG_TOP_K = 30` (how many FAISS neighbors to retrieve)
- `EMBEDDING_DIMENSIONS = 1024`
- `BATCH_SIZE = 10` (products per LLM call)

**Database schema details:**
- Schema: `playground`, Table: `promo_bronze` (configurable)
- Primary key: `id`
- GS1 target columns: `gs1_segment`, `gs1_family`, `gs1_class`, `gs1_brick`, `gs1_attribute`, `gs1_attribute_value`
- Prompt columns (sent to LLM): `store`, `country`, `product_name`, `product_name_en`, `packaging_type`, `packaging_value`, `packaging_unit`

---

## PART 2 — ARCHITECTURE & DESIGN REQUIREMENTS

### 2.1 Architecture Principles
- **Simple and flat.** Avoid over-engineering. No more than 2 levels of directory nesting under `src/`. Two clear entry points: `main.py` (classify) and `vectorize.py` (build-vectors, embed-rows).
- **YAML-first configuration.** A single `config.yaml` controls everything. Each section is clearly labeled by which component it belongs to. Minimal reliance on environment variables (only secrets like API keys and passwords should come from `.env`).
- **Extensible via interfaces.** 4 swappable interfaces: `EmbeddingProvider`, `VectorStore`, `LLMProvider`, `DatabaseConnector`. Concrete classes registered in a factory. Adding a new provider means: write the class, add one line to the factory, use it in config. No core code changes.
- **LLM Orchestrator Service.** The classification mode uses a service that combines the LLM client + RAG search into one cohesive service class. This orchestrator: loads the vector store, performs similarity search, builds candidates, constructs prompts, calls the LLM, and parses responses.
- **Thin repository pattern for database.** `DatabaseConnector` interface with clean Python methods (`fetch_batch`, `update_rows`, etc.) that hide raw SQL inside. Two implementations: `AzureSQLConnector` (pyodbc + Service Principal) and `PostgreSQLConnector` (psycopg2 + username/password). Schema, table, columns all configurable in YAML.
- **Pydantic-validated config.** The entire YAML is validated at startup with Pydantic models. Bad config → clear error → exit immediately.
- **Environment variable interpolation in YAML.** Any value can use `${VAR_NAME}` syntax, resolved from `.env` or OS environment.
- **Prompt templates in separate files.** Prompt templates stored in `.j2` files (Jinja2 syntax) in `templates/`, referenced by `system_template_file` and `prompt_template_file` keys in `config.yaml`. Hardcoded fallback strings in `src/utils/templates.py` are used if a file is missing or path is null.

### 2.2 Shared Infrastructure
All three modes should share:
- **Embedding provider** (swappable interface — implement Azure OpenAI + HuggingFace at start, extensible for others)
- **Database connector** (swappable interface — implement Azure SQL + PostgreSQL, thin repository pattern)
- **Vector store** (swappable interface — implement FAISS at start, extensible for pgvector/Azure AI Search later)
- **LLM provider** (swappable interface — implement Azure OpenAI at start, extensible for direct OpenAI/Anthropic/Ollama later)
- **Logging** (file + console, structured, with configurable level)
- **Console output** (pretty-printed progress, phases, timing)
- **Retry / resilience** (configurable retry strategy for all external calls, rate limiting)
- **Batch processing utilities** (generic batcher for DB rows and API calls — each batch written to DB/store immediately after completion)

### 2.3 What Must Be Configurable in YAML
At a minimum, these should be configurable (not hardcoded). Each section is clearly labeled by the component it belongs to:

**Global / System:**
- Pipeline name, description
- Log level, batch size, max workers, retry strategy (`max_attempts`, `backoff_factor`, `min_wait`, `max_wait` under `system.retry`)

**Database (used by `embed-rows` and `classify`):**
- Connection type (e.g. `azure_sql`, `postgresql`)
- Server, database name
- Credential env-var names (supports service principal for Azure SQL, username/password for PostgreSQL)
- Schema, table name, primary key column
- Custom column mappings (which columns to read, which to write)

**Embedding (shared by all 3 modes — critical: same model+dimensions for vector store and DB row embeddings):**
- Provider type (`azure_openai`, `huggingface`; scaffolded: `openai`, `ollama`, `cohere`)
- Tunables in config: `dimensions`, `batch_size`, `max_workers`, and `model_name` (HuggingFace only)
- Secrets (API key, endpoint, deployment, API version) live exclusively in `.env` — **not** in `config.yaml`. The entry points call `get_env()` with hardcoded env var names.

**Vector store (used by `build-vectors` and `classify`):**
- Store type (`faiss`; scaffolded: `chromadb`, `azure_search`)
- Store params: `output_dir`, `filename_prefix`, `lookup_metadata_fields`
- Source file path (JSON taxonomy file in `data/`)
- Parser type (e.g. `gs1`)
- `source.batch_size`: documents per embedding call during build

**LLM (used by `classify`):**
- Provider type (`azure_openai`; scaffolded: `openai`, `anthropic`, `google_gemini`, `mistral`, `ollama`)
- `max_completion_tokens`: maximum tokens in the LLM response (default 4096)
- Secrets (API key, endpoint, deployment, API version) live exclusively in `.env`

> Note: There is no `temperature` setting. The default model is `o4-mini` (o-series reasoning models do not support `temperature`).

**Classification / RAG (used by `classify`):**
- RAG parameter: `rag_top_k` (how many FAISS neighbors to retrieve per product; default 30)
- Target columns (which DB columns to write classification results to)
- Prompt columns (`prompt_columns`): which product fields to include in the LLM prompt (NOTE: not used by FAISS search — only for the prompt text)
- `system_template_file`: path to system-message `.j2` template (e.g. `templates/gs1_system.j2`)
- `prompt_template_file`: path to user-message `.j2` template (e.g. `templates/gs1_classification.j2`)
- Batch size (products per LLM call)

**Row embedding (used by `embed-rows`):**
- `columns`: list of columns to concatenate
- `separator`: column separator string (default `" * "`)
- `target_column`: column to write embeddings to
- `batch_size`: rows per batch

### 2.4 Data Flow Summary

```
          ┌────────────────────────────────────────────────┐
          │                   config.yaml                  │
          └──────────────────────┬─────────────────────────┘
                                 │
          ┌──────────────────────▼─────────────────────────┐
          │          vectorize.py          main.py          │
          │     (build-vectors,        (classify mode)      │
          │      embed-rows modes)                          │
          └──┬──────────────────┬──────────────────┬───────┘
             │                  │                  │
    ┌────────▼─────┐   ┌───────▼──────┐   ┌──────▼───────┐
    │ build-vectors│   │  embed-rows  │   │   classify   │
    │              │   │              │   │              │
    │ JSON→Parse   │   │ DB→Concat    │   │ DB→RAG→LLM  │
    │ →Embed→FAISS │   │ →Embed→DB    │   │ →Parse→DB   │
    │  +artefacts  │   │  (per batch) │   │  (per batch) │
    └──────────────┘   └──────────────┘   └──────────────┘
```

### 2.5 Technology Stack
- **Python 3.10+**
- **Azure OpenAI** (embeddings + chat completions) via the `openai` SDK
- **FAISS-cpu** for vector indexing/search
- **Azure SQL** via `pyodbc` + `SQLAlchemy` with Azure AD Service Principal auth
- **PostgreSQL** via `psycopg2` + `SQLAlchemy` with username/password auth
- **pandas** for in-memory data handling
- **Pydantic** for config validation
- **PyYAML** for config loading
- **Jinja2** for prompt template rendering
- **python-dotenv** for `.env` loading
- **tenacity** for retry logic
- **numpy** for vector operations
- **pyarrow** for Parquet I/O
- **sentence-transformers** for HuggingFace embedding provider

---

## PART 3 — DETAILED DOMAIN KNOWLEDGE

This section contains critical implementation details the design must account for.

### 3.1 GS1 GPC Hierarchy Structure
The GS1 GPC (Global Product Classification) standard organizes products into a 5-level hierarchy:
- **Level 1 — Segment** (e.g. "Food/Beverage/Tobacco")
- **Level 2 — Family** (e.g. "Beverages")
- **Level 3 — Class** (e.g. "Coffee")
- **Level 4 — Brick** (e.g. "Instant Coffee")
- **Level 5 — Attribute** (e.g. "Caffeine")
- **(Level 6) — Attribute Value** (e.g. "Caffeinated", "Not Caffeinated") — sometimes present

The hierarchy has ~200,000 nodes total. Each node has a numeric code, title, definition, and optional excludes text.

### 3.2 How the Vector Store Lookup Works
The lookup pickle maps integer vector IDs to metadata dicts. At query time, after FAISS returns the top-K nearest neighbor indices, the classifier looks up each index in this dict to get the human-readable hierarchy path, level, code, etc. The metadata JSON serves a similar purpose but is the full dump (larger, for debugging/inspection).

### 3.3 How Candidate Building Works
After RAG search returns ~30 raw results per product (each a point in the GS1 taxonomy tree), the candidate builder:
1. Groups results by their L4 path (Segment > Family > Class > Brick) — because the LLM needs to choose at the brick level, not at individual attribute level.
2. Deduplicates within each group (keeps best score — lowest L2 distance wins).
3. Collects any L5/L6 attribute info found within the same group and attaches it as supplementary info.
4. Sorts all unique L4 paths ascending by best score (lower L2 distance = better match first).
5. Assigns letters A through Z to each path.

All groups are passed to the LLM — there is no cap on the number of candidates and no score threshold filter.

### 3.4 How the LLM Prompt Looks
The prompt to the LLM contains:
- A system message establishing the assistant's role
- For each product in the batch: a JSON row with context fields + a lettered candidate block
- A required output format: `[{"product_id": ..., "choice": "A"}, ...]`

The LLM picks one letter per product. That letter maps back to a full GS1 hierarchy path.

### 3.5 Database Connection Patterns

**Azure SQL with Service Principal** (env vars: `AZURE_SQL_SERVER`, `AZURE_SQL_DATABASE`, `AZURE_SQL_CLIENT_ID`, `AZURE_SQL_CLIENT_SECRET`):
```python
conn_str = (
    f"DRIVER={{ODBC Driver 18 for SQL Server}};"
    f"SERVER={server};"
    f"DATABASE={database};"
    f"UID={client_id};"  # Service Principal App ID
    f"PWD={client_secret};"
    f"Authentication=ActiveDirectoryServicePrincipal;"
    f"Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;"
)
engine = create_engine(f"mssql+pyodbc:///?odbc_connect={quoted_conn_str}")
```

**PostgreSQL with username/password** (env vars: `PG_HOST`, `PG_PORT`, `PG_DATABASE`, `PG_USERNAME`, `PG_PASSWORD`):
```python
engine = create_engine(
    f"postgresql+psycopg2://{username}:{password}@{host}:{port}/{database}"
)
```

Both connectors implement the same `DatabaseConnector` interface. Switching is config-only (`database.type`).

Both use `DatabaseBatcher` for pagination — rows are paged with `ORDER BY pk OFFSET n FETCH NEXT batch_size ROWS ONLY` so the pipeline never loads the full table into memory.

### 3.6 Embedding Storage in Database

**Azure SQL** uses the `VECTOR(1024)` type:
```sql
UPDATE table SET embedding_context = CAST(CAST(:embedding AS VARCHAR(MAX)) AS VECTOR(1024))
WHERE id = :id
```

**PostgreSQL** uses the `pgvector` extension:
```sql
UPDATE table SET embedding_context = :embedding::vector(1024)
WHERE id = :id
```

In both cases, the embedding value is a JSON string of 1024 floats like `"[0.123, -0.456, ...]"`. The `DatabaseConnector` implementation handles the DB-specific casting syntax internally.

---

## PART 4 — WHAT I NEED FROM YOU

### Write the Design Document

All design decisions have been finalized (see PART 5 below). Write the full design document covering:

1. **Architecture overview** — diagram, component descriptions, data flow for each mode
2. **Project structure** — every file and folder with one-line descriptions (max 2 levels under `src/`, descriptive names)
3. **Config schema** — full `config.yaml` reference with all sections clearly labeled by component, types, defaults, descriptions
4. **Interface definitions** — every abstract base class with method signatures and docstrings (4 swappable: `EmbeddingProvider`, `VectorStore`, `LLMProvider`, `DatabaseConnector`)
5. **Component registry** — how the factory pattern works, how to register new providers
6. **Implementation guide per mode:**
   - `build-vectors`: step-by-step flow, vector store as a system (parser → embedder → indexer → artefacts), CLI via `vectorize.py`
   - `embed-rows`: step-by-step flow, DB read → embed → DB write (batch-level commit), CLI via `vectorize.py`
   - `classify`: step-by-step flow, the full RAG pipeline via LLM Orchestrator Service, entry via `main.py`
7. **LLM Orchestrator Service** — how it combines LLM client + RAG + candidate building + prompt building + response parsing into one service
8. **Shared utilities** — logging, console, retry, rate limiting, batching
9. **Extension guide** — how to add a new embedding provider, vector store, LLM provider, or database connector (with code examples)
10. **CLI design** — `main.py` (classify, no args needed), `vectorize.py` (subcommands + flags)
11. **Environment variables** — full list of required/optional env vars (see below for the actual names used in the codebase)

**Required env vars (all from `.env` or OS environment — never in `config.yaml`):**

| Variable | Used by | Description |
|---|---|---|
| `AZURE_OPENAI_API_KEY` | embedding, LLM | Azure OpenAI API key |
| `AZURE_OPENAI_ENDPOINT` | embedding, LLM | Azure OpenAI endpoint URL |
| `AZURE_OPENAI_EMBEDDING_DEPLOYMENT` | embedding | Embedding model deployment name |
| `AZURE_OPENAI_CHAT_DEPLOYMENT` | LLM | Chat model deployment name |
| `AZURE_OPENAI_API_VERSION` | embedding, LLM | API version string |
| `AZURE_SQL_SERVER` | Azure SQL | SQL Server hostname |
| `AZURE_SQL_DATABASE` | Azure SQL | Database name |
| `AZURE_SQL_CLIENT_ID` | Azure SQL | Service Principal App (Client) ID |
| `AZURE_SQL_CLIENT_SECRET` | Azure SQL | Service Principal client secret |
| `PG_HOST` | PostgreSQL | PostgreSQL server hostname |
| `PG_PORT` | PostgreSQL | PostgreSQL port (typically 5432) |
| `PG_DATABASE` | PostgreSQL | Database name |
| `PG_USERNAME` | PostgreSQL | Database username |
| `PG_PASSWORD` | PostgreSQL | Database password |

---

## PART 5 — FINALIZED DESIGN DECISIONS

These decisions were collaboratively agreed upon and are **binding constraints** for the design document.

### Decision 1: Entry Point Pattern
**Two entry points:**
- `main.py` — runs `classify` mode by default. `python main.py` starts classifying empty rows in the DB immediately.
- `vectorize.py` — separate entry point with CLI subcommands for `build-vectors` and `embed-rows`. Has CLI flags for settings (e.g. `--config`).

### Decision 2: Config File Structure
**One monolithic `config.yaml`** with all modes' settings. Each section is clearly labeled by the component it belongs to (e.g. `# === Database Configuration ===`).

### Decision 3: LLM Client Architecture
**`openai` Python SDK** for both embeddings and chat completions. Wrapped behind an `LLMProvider` interface. Combined with RAG into an **LLM Orchestrator Service** — a single service class that owns the full classification flow: vector store loading → similarity search → candidate building → prompt construction → LLM call → response parsing.

### Decision 4: Response Parsing Strategy
**Force JSON output from LLM** using `response_format={"type": "json_object"}` on the API call. Parse with `json.loads()`. The expected format is `{"results": [{"product_id": ..., "choice": "<letter>"}]}`. Handles both `{"results": [...]}` and bare `[...]` formats. Regex fallback (extract first `[...]` block) as safety net if JSON parsing fails entirely. Response parser is a **concrete class** (not a swappable interface).

### Decision 5: Swappable Interfaces (4 total)
| Interface | Fully Implemented | Scaffolded (not yet implemented) |
|---|---|---|
| `EmbeddingProvider` | Azure OpenAI, HuggingFace | OpenAI direct (`openai_embedder.py`), Ollama (`ollama_embedder.py`), Cohere (`cohere_embedder.py`) |
| `VectorStore` | FAISS (full system: parse→embed→index→artefacts) | ChromaDB (`chromadb_store.py`), Azure AI Search (`azure_ai_search_store.py`) |
| `LLMProvider` | Azure OpenAI | OpenAI direct (`openai_chat.py`), Anthropic (`anthropic_chat.py`), Google Gemini (`google_gemini_chat.py`), Mistral (`mistral_chat.py`), Ollama (`ollama_chat.py`) |
| `DatabaseConnector` | Azure SQL (Service Principal), PostgreSQL | SQLite (`sqlite_connector.py`), DuckDB (`duckdb_connector.py`), MySQL (`mysql_connector.py`) |

**Not swappable (concrete classes):**
- `GS1Parser` — concrete parser for GS1 JSON. Other tree parsers can be added later (lowest priority).
- `CandidateBuilder` — GS1-specific RAG candidate grouping logic.
- `ResponseParser` — concrete JSON response parser.
- Source loading — always reads from a JSON file in `data/`. No `SourceAdapter` interface needed.

### Decision 6: Database Abstraction
**Thin repository pattern.** `DatabaseConnector` interface with clean Python methods (`fetch_batch()`, `update_rows()`, `execute()`) that hide raw parameterized SQL inside. Two implementations:
- `AzureSQLConnector` — pyodbc + Service Principal auth
- `PostgreSQLConnector` — psycopg2 + username/password auth

Schema, table, and column names are all configurable in YAML. Switching databases = changing config, not code.

**`DatabaseBatcher`** is a pagination helper class in `src/utils/batching.py` that wraps a `DatabaseConnector` and yields one `pd.DataFrame` batch at a time using `ORDER BY pk OFFSET n FETCH NEXT batch_size ROWS ONLY` SQL. Used by both `embed-rows` and `classify` workflows to avoid loading full tables into memory.

### Decision 7: Project Layout
Max 2 levels under `src/`. Folder and file names must be descriptive of their purpose in the program. The implemented structure:

```
config.yaml              # Single monolithic config
main.py                  # Entry point: classify mode
vectorize.py             # Entry point: build-vectors + embed-rows
src/
  dto.py                 # Document dataclass (id, text, metadata, embedding)
  factory.py             # ComponentFactory + build_default_factory()
  config/
    models.py            # Pydantic AppConfig and all sub-models; load_config()
  services/
    gs1_parser.py        # GS1Parser — concrete parser for GS1 JSON taxonomy
    orchestrator.py      # LLMOrchestratorService — full RAG+LLM classify flow
    db/                  # DatabaseConnector interface + connectors
    embedding/           # EmbeddingProvider interface + providers
    llm/                 # LLMProvider interface + providers
    vectorstore/         # VectorStore interface + stores
  transforms/
    candidate_builder.py # CandidateBuilder — groups RAG results into lettered options
    response_parser.py   # ResponseParser — maps LLM letter choice to GS1 levels
  utils/
    batching.py          # iter_batches() + DatabaseBatcher (pagination)
    console.py           # Human-readable terminal output (separate from logging)
    env.py               # get_env() + resolve_env_vars() for ${VAR} interpolation
    exceptions.py        # PipelineError hierarchy (ConfigError, LLMError, etc.)
    logging.py           # setup_logging() + get_logger() (file + colored console)
    retry.py             # make_retry_decorator() wrapping tenacity
    templates.py         # render_template() + hardcoded fallback strings
  workflows/
    build_vectors.py     # run_build_vectors() workflow function
    classify.py          # run_classify() workflow function
    embed_rows.py        # run_embed_rows() workflow function
templates/
  gs1_system.j2          # LLM system message template
  gs1_classification.j2  # LLM user message template (products + candidates)
data/
  input/                 # Source JSON files (e.g. GS1.json)
  vector_store/          # FAISS artefact output directory
logs/                    # Log files (per-run, with mode prefix in filename)
tests/                   # pytest unit + smoke tests
```

### Decision 8: Prompt Template System
**Hybrid approach:**
- Prompt templates stored in separate `.j2` files using Jinja2 syntax in the `templates/` directory.
- Two template files are used in `classify` mode:
  - `templates/gs1_system.j2` — the system message (assistant role + output format instructions)
  - `templates/gs1_classification.j2` — the user message (product context + lettered candidates)
- `config.yaml` has `system_template_file` and `prompt_template_file` fields pointing to these paths.
- If a template file path is set to `null` or the file is missing, hardcoded fallback strings in `src/utils/templates.py` are used.
- Jinja2 templates receive `products` (list of dicts with `product_id`, `context`, `candidates`) as context.
- Keeps YAML clean; prompts are easy to edit and version-control independently.

### Decision 9: Testing Strategy
- **Working run after every component's implementation.** Each component should be testable independently.
- **Unit tests** (pytest) for pure logic: GS1 parser, candidate builder, response parser, config validation. Mock external services.

### Decision 10: Error Handling & Resilience
- **Batch-level processing:** Data is large, batches are small. Every batch is written back to DB or vector store **immediately after that batch completes**. No waiting until the end.
- **Retry on failure:** Failed batches are retried (configurable: max_attempts, backoff_factor, min_wait, max_wait via `tenacity`). Rate limiters for API calls.
- **Per-batch error handling:** If a batch still fails after retries, log the error with full context, skip it, continue with the next batch. Don't let one bad batch kill a large run.
- **Structured error logging:** Failed product IDs + error messages written to a structured JSON log file (e.g. `logs/failed_products.json`).
- **Fail-fast on startup:** Config validation errors, missing env vars, unreachable DB → fail immediately with a clear error message.

### Decision 11: Vector Store as a System
The vector store is more than just a FAISS index. It is a **system** that encompasses:
1. **Parser:** Reads a JSON tree from `data/`, flattens it into documents (one per root-to-leaf node path).
2. **Embedder:** Uses the **same** `EmbeddingProvider` (same model, same dimensions) as `embed-rows` mode. This is critical — RAG similarity search compares product embeddings (from DB) against taxonomy embeddings (from FAISS). They must be compatible vectors.
3. **Indexer:** Always builds `IndexFlatL2`. Vectors are L2-normalised in-place before being added to the index for consistent magnitude. Scores are squared L2 distances in [0, 4] for unit vectors — lower = more similar.
4. **Artefact writer:** Produces 5 output files (index, metadata JSON, parquet archive, lookup pickle, build manifest). The `build_manifest.json` records `index_type: "FlatL2"` along with the model name and embedding dimensions.
5. **Search interface:** At query time, loads the index + lookup, L2-normalises the query vectors, and calls `search_batch()` to issue a single vectorised FAISS search for all products in the batch at once.

The source is always a JSON file in `data/`. The structure of the JSON may vary (GS1 today, different taxonomy tomorrow). The parser handles the specific JSON schema; the rest of the system is generic.

---

*These decisions are final. Proceed directly to writing the full design document.*
