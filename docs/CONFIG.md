# Configuration Reference

## Table of Contents

- [Config split: config.yaml vs .env](#config-split-configyaml-vs-env)
- [config.yaml — full reference](#configyaml--full-reference)
  - [pipeline](#pipeline)
  - [system](#system)
  - [source](#source)
  - [embedding](#embedding)
  - [vector_store](#vector_store)
  - [database](#database)
  - [row_embedding](#row_embedding)
  - [llm](#llm)
  - [classification](#classification)
- [.env — secrets reference](#env--secrets-reference)
- [Swappable components](#swappable-components)
  - [Embedding providers](#embedding-providers)
  - [Vector stores](#vector-stores)
  - [LLM providers](#llm-providers)
  - [Database connectors](#database-connectors)
- [How to swap a component](#how-to-swap-a-component)

---

## Config split: config.yaml vs .env

| What goes here | File |
|---|---|
| All tunables: batch sizes, thresholds, column names, template paths, retry settings, model dimensions | `config.yaml` |
| All secrets: API keys, endpoints, deployment names, DB server, DB credentials | `.env` |

`config.yaml` is committed to the repository. `.env` is git-ignored and never committed.

Inside `config.yaml` you can reference environment variables using `${VAR_NAME}` syntax. At load time, `load_config()` substitutes these with the actual values from the environment.

---

## config.yaml — full reference

### pipeline

```yaml
pipeline:
  name: "gs1-vectoRAG-classifier"
  description: "..."
```

Metadata only. Name is used in log output headers. No functional effect.

---

### system

```yaml
system:
  log_level: "INFO"       # DEBUG | INFO | WARNING | ERROR
  max_workers: 5          # thread pool size for parallel embedding API calls
  batch_size: 256         # fallback batch size (overridden by section-specific batch_size values)
  retry:
    max_attempts: 3       # total attempts (1 initial + 2 retries)
    backoff_factor: 1.5   # multiplier applied to each successive wait
    min_wait: 30.0        # minimum wait between retries (seconds)
    max_wait: 120.0       # maximum wait between retries (seconds)
```

**retry** applies to all Azure OpenAI API calls (both embedding and LLM). With these defaults: first retry waits ~30s, second waits ~45s. Increase `min_wait` and `max_wait` if you hit sustained rate limits.

**log_level:** Set to `DEBUG` to see per-batch timing, individual API call counts, and raw LLM responses. `INFO` is appropriate for production runs.

---

### source

```yaml
source:
  type: "file_json"
  path: "data/input/GS1.json"
  encoding: "utf-8"
  parser: "gs1"
  batch_size: 50
```

Used by: `build-vectors` only.

| Field | Purpose |
|---|---|
| `path` | Path to the GS1 GPC taxonomy JSON file. Relative to the project root. |
| `encoding` | File encoding. `utf-8` works for the standard GS1 GPC export. |
| `batch_size` | Number of documents sent to the embedding API per call. Lower values reduce memory pressure and API request size. Higher values may be faster. |

---

### embedding

```yaml
embedding:
  type: "azure_openai"
  dimensions: 1024
  batch_size: 256
  max_workers: 5
```

Used by: all three modes (shared).

| Field | Purpose |
|---|---|
| `type` | Embedding provider. See [Embedding providers](#embedding-providers) for all options. |
| `dimensions` | Output vector size. **Must match across all modes.** The FAISS index (`build-vectors`) and the DB row vectors (`embed-rows`) must have the same dimensions. If you switch providers or change dimensions, rebuild the FAISS index and re-run `embed-rows`. |
| `batch_size` | Texts per API call (Azure OpenAI, Cohere) or per local inference batch (HuggingFace, Ollama). |
| `max_workers` | Thread pool size for parallel API calls. Only applies to providers that support parallel calls. |

**Critical constraint:** All three modes use this same `embedding` section. This guarantees that the GS1 taxonomy vectors (built by `build-vectors`) and the product row vectors (written by `embed-rows`) are always produced by the same model — a requirement for RAG similarity search to be valid.

---

### vector_store

```yaml
vector_store:
  type: "faiss"
  output_dir: "data/vector_store"
  filename_prefix: "gs1"
  lookup_metadata_fields:
    - level
    - code
    - title
    - hierarchy_path
    - hierarchy_string
```

Used by: `build-vectors` (write) and `classify` (read/search).

| Field | Purpose |
|---|---|
| `type` | Vector store implementation. See [Vector stores](#vector-stores). |
| `output_dir` | Directory where FAISS artefacts are written and read from. |
| `filename_prefix` | Prefix for all artefact filenames (e.g. `gs1` → `faiss_gs1.index`). |
| `lookup_metadata_fields` | Which metadata fields to include in the compact `{prefix}_lookup.pkl` file loaded at classify time. Omitting fields reduces memory use but makes them unavailable in search results. |

---

### database

```yaml
database:
  type: "azure_sql"
  schema_name: "playground"
  table: "promo_bronze"
  primary_key: "id"
```

Used by: `embed-rows` and `classify`.

| Field | Purpose |
|---|---|
| `type` | Database connector. See [Database connectors](#database-connectors). |
| `schema_name` | SQL schema name (e.g. `dbo`, `public`, `playground`). |
| `table` | Table to read from and write to. |
| `primary_key` | Column used as the row identifier in `update_rows()` calls. |

---

### row_embedding

```yaml
row_embedding:
  batch_size: 50
  columns:
    - store
    - country
    - product_name
    - product_name_en
    - category
    - packaging_type
    - packaging_value
    - packaging_unit
  separator: " * "
  target_column: "embedding_context"
```

Used by: `embed-rows` only.

| Field | Purpose |
|---|---|
| `batch_size` | Rows processed per DB fetch + embed cycle. |
| `columns` | Columns concatenated to produce the embedding text. Columns are joined in listed order. `NULL` values are treated as empty strings. |
| `separator` | String inserted between column values. Default `" * "` separates fields visually. |
| `target_column` | Column where the embedding vector is written. Must exist in the table. |

The resulting text string (e.g. `"SuperStore * DE * Bio Tomaten * Organic Tomatoes * Fresh Produce * Punnet * 500 * g"`) is what gets embedded. The quality of the RAG search depends on how informative this text is — include columns that describe the product and exclude columns with irrelevant data.

---

### llm

```yaml
llm:
  type: "azure_openai"
  max_completion_tokens: 4096
```

Used by: `classify` only.

| Field | Purpose |
|---|---|
| `type` | LLM provider. See [LLM providers](#llm-providers). |
| `max_completion_tokens` | Token budget for the LLM response. The classify prompt can be long (up to ~12 candidates × 10 products) — keep this at 4096 or higher. |

---

### classification

```yaml
classification:
  rag_top_k: 30
  batch_size: 10
  prompt_columns:
    - store
    - country
    - product_name
    - product_name_en
    - packaging_type
    - packaging_value
    - packaging_unit
  target_columns:
    - gs1_segment
    - gs1_family
    - gs1_class
    - gs1_brick
    - gs1_attribute
    - gs1_attribute_value
  system_template_file: "templates/gs1_system.j2"
  prompt_template_file: "templates/gs1_classification.j2"
```

Used by: `classify` only.

| Field | Purpose |
|---|---|
| `rag_top_k` | How many nearest FAISS results to retrieve per product. All results are passed to the candidate builder — there is no score threshold filter. 30 is a good default. |
| `batch_size` | Products sent in one LLM call. Each call contains all products in a batch plus their candidate lists. Larger batches reduce API call overhead but make prompts longer. 10 is a practical default. |
| `prompt_columns` | Columns from the DB row that are included in the LLM prompt as product context. These should be the most descriptive fields. Not used by FAISS search — RAG always uses the pre-computed `embedding_context` vector. |
| `target_columns` | Columns written back to the DB after classification. Order matters — these must match the GS1 hierarchy: segment, family, class, brick, attribute, attribute_value. |
| `system_template_file` | Path to the Jinja2 system message template. |
| `prompt_template_file` | Path to the Jinja2 user message template. |

---

## .env — secrets reference

Create a `.env` file in the project root. It is git-ignored. All values are plain strings (no quotes needed unless the value contains spaces).

### Azure OpenAI (embedding + LLM)

```env
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_VERSION=2024-02-01
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-3-large
AZURE_OPENAI_CHAT_DEPLOYMENT=o4-mini
```

Both the embedding provider and the LLM provider read from these variables. They can point to the same Azure OpenAI resource or different ones.

### Azure SQL Database

```env
AZURE_SQL_SERVER=your-server.database.windows.net
AZURE_SQL_DATABASE=your-database
AZURE_SQL_CLIENT_ID=your-service-principal-client-id
AZURE_SQL_CLIENT_SECRET=your-service-principal-client-secret
```

Authentication uses Azure AD Service Principal (`ActiveDirectoryServicePrincipal` via ODBC Driver 18). No password rotation needed after initial setup.

### PostgreSQL

```env
PG_HOST=your-host
PG_PORT=5432
PG_DATABASE=your-database
PG_USERNAME=your-user
PG_PASSWORD=your-password
```

Only needed if `database.type: "postgresql"` is set in `config.yaml`.

### Other providers (when activated)

| Provider | Required variables |
|---|---|
| `openai` embedding / LLM | `OPENAI_API_KEY` |
| `cohere` embedding | `COHERE_API_KEY` |
| `anthropic` LLM | `ANTHROPIC_API_KEY` |
| `google` LLM | `GOOGLE_API_KEY` |
| `mistral` LLM | `MISTRAL_API_KEY` |
| `azure_search` vector store | `AZURE_SEARCH_ENDPOINT`, `AZURE_SEARCH_API_KEY` |
| `mysql` database | `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_DATABASE`, `MYSQL_USERNAME`, `MYSQL_PASSWORD` |

`huggingface`, `ollama`, `sqlite`, and `duckdb` require no secrets.

---

## Swappable components

Every component category has an abstract interface (`base.py`) and one or more implementations. The active implementation is selected by the `type:` key in `config.yaml`. Swapping a provider requires no code changes outside the concrete class and `src/factory.py`.

**Legend:** ✅ implemented and registered · ⬜ scaffold exists (implement methods + register to activate)

### How to activate a scaffold

1. Open the scaffold file and implement the abstract methods (they currently raise `NotImplementedError`).
2. Add one line to `build_default_factory()` in `src/factory.py`:
   ```python
   from src.services.<category>.<module> import <ClassName>
   factory.register_<category>("<type_name>", <ClassName>)
   ```
3. Set `type: "<type_name>"` in `config.yaml`.

---

### Embedding providers

**Interface:** `src/services/embedding/base.py` — `EmbeddingProvider`  
**Config key:** `embedding.type`  
**Used by:** all three modes

> All three modes share the same embedding model. The FAISS index and the DB row embeddings must come from the same model. Switching models requires rebuilding the FAISS index (`build-vectors`) and re-running `embed-rows`.

---

#### ✅ `azure_openai`
**File:** `src/services/embedding/azure_openai_embedder.py`

Calls the Azure OpenAI embedding API via the `openai` SDK. Parallel batching with `ThreadPoolExecutor`. Retries on `RateLimitError`.

**Best for:** Default choice. High-quality 1024-dim vectors for multilingual product data.

```yaml
embedding:
  type: "azure_openai"
  dimensions: 1024
  batch_size: 256
  max_workers: 5
```

`.env`: `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_EMBEDDING_DEPLOYMENT`, `AZURE_OPENAI_API_VERSION`

---

#### ✅ `huggingface`
**File:** `src/services/embedding/huggingface.py`

Runs a `sentence-transformers` model locally. No API cost. Model is downloaded from HuggingFace Hub on first use. Dimensions vary by model.

**Best for:** Local dev, cost-free testing, air-gapped environments.

```yaml
embedding:
  type: "huggingface"
  dimensions: 384          # must match the model's output dims
  model_name: "all-MiniLM-L6-v2"
```

Common models: `all-MiniLM-L6-v2` (384 dims, fast), `all-mpnet-base-v2` (768 dims, better quality).  
No `.env` secrets needed.

---

#### ⬜ `openai`
**File:** `src/services/embedding/openai_embedder.py`

Calls `api.openai.com` directly. Same as Azure provider without `azure_endpoint` or `api_version`.

```yaml
embedding:
  type: "openai"
  dimensions: 1024
  model: "text-embedding-3-large"
```

`.env`: `OPENAI_API_KEY`

---

#### ⬜ `ollama`
**File:** `src/services/embedding/ollama_embedder.py`

Sends embedding requests to a locally running [Ollama](https://ollama.com) server (`POST /api/embeddings`). No costs. Requires Ollama installed and running.

```yaml
embedding:
  type: "ollama"
  dimensions: 1024
  model_name: "mxbai-embed-large"
  base_url: "http://localhost:11434"
```

No `.env` secrets needed.

---

#### ⬜ `cohere`
**File:** `src/services/embedding/cohere_embedder.py`

Uses the Cohere Embed API. Optimised for retrieval tasks. Supports `search_document` vs `search_query` input type hints.

```yaml
embedding:
  type: "cohere"
  dimensions: 1024
  model: "embed-multilingual-v3.0"
  input_type: "search_document"
```

`.env`: `COHERE_API_KEY`

---

### Vector stores

**Interface:** `src/services/vectorstore/base.py` — `VectorStore`  
**Config key:** `vector_store.type`  
**Used by:** `build-vectors` (write), `classify` (read/search)

---

#### ✅ `faiss`
**File:** `src/services/vectorstore/faiss_store.py`

Local FAISS index stored on disk. Loads entirely into memory at query time. Exact nearest-neighbor search. Handles the GS1 taxonomy (~200k nodes) comfortably.

Produces five artefacts in `output_dir`: `.index`, `_metadata.json`, `.parquet`, `_lookup.pkl`, `build_manifest.json`.

**Best for:** Default choice. Zero infrastructure, no server.

```yaml
vector_store:
  type: "faiss"
  output_dir: "data/vector_store"
  filename_prefix: "gs1"
  lookup_metadata_fields: [level, code, title, hierarchy_path, hierarchy_string]
```

---

#### ⬜ `pgvector`
**File:** `src/services/vectorstore/pgvector_store.py`

Stores vectors in a PostgreSQL table using the `pgvector` extension. Search via `ORDER BY embedding <-> $1 LIMIT k`. Supports metadata filtering alongside vector search.

**Best for:** Vector index co-located with the product database, metadata filtering at search time, avoiding in-memory index loading.

```yaml
vector_store:
  type: "pgvector"
  table: "gs1_taxonomy"
  schema: "vectors"
```

Uses the same PostgreSQL credentials as the `postgresql` database connector.

---

#### ⬜ `azure_search`
**File:** `src/services/vectorstore/azure_ai_search_store.py`

Azure AI Search (formerly Cognitive Search) as a managed vector store. Supports hybrid search (vector + keyword). Fully managed, scales automatically.

**Best for:** Production-grade managed solution, index exceeds available memory, hybrid keyword+vector search.

```yaml
vector_store:
  type: "azure_search"
  index_name: "gs1-taxonomy"
```

`.env`: `AZURE_SEARCH_ENDPOINT`, `AZURE_SEARCH_API_KEY`

---

#### ⬜ `chromadb`
**File:** `src/services/vectorstore/chromadb_store.py`

Lightweight vector database. Runs in-process or as a server. Python-native API with metadata filtering.

**Best for:** Quick local prototyping without infrastructure setup.

```yaml
vector_store:
  type: "chromadb"
  persist_dir: "data/vector_store/chroma"
  collection_name: "gs1_taxonomy"
```

---

#### ⬜ `qdrant`
**File:** `src/services/vectorstore/qdrant_store.py`

Purpose-built vector database with HNSW indexing, rich metadata filtering, REST/gRPC API. Available as local server (Docker) or cloud.

**Best for:** Rich metadata filtering on results, purpose-built vector DB with a server API.

```yaml
vector_store:
  type: "qdrant"
  collection_name: "gs1_taxonomy"
  url: "http://localhost:6333"
```

---

### LLM providers

**Interface:** `src/services/llm/base.py` — `LLMProvider`  
**Config key:** `llm.type`  
**Used by:** `classify` only

> All LLM providers must support forced JSON output. The `classify` mode always calls with `response_format={"type": "json_object"}`. Providers that do not natively support this (e.g. Anthropic) must emulate it via prompt engineering — the orchestrator's regex fallback handles imperfect JSON.

---

#### ✅ `azure_openai`
**File:** `src/services/llm/azure_openai_chat.py`

Azure-hosted OpenAI chat model via `openai` SDK. Supports `response_format={"type": "json_object"}`. Retries on rate limits.

**Best for:** Default. `o4-mini` gives a good cost/quality balance for structured classification.

```yaml
llm:
  type: "azure_openai"
  max_completion_tokens: 4096
```

`.env`: `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_CHAT_DEPLOYMENT`, `AZURE_OPENAI_API_VERSION`

---

#### ⬜ `openai`
**File:** `src/services/llm/openai_chat.py`

Direct `api.openai.com` without Azure wrapper.

```yaml
llm:
  type: "openai"
  model: "gpt-4o-mini"
  max_completion_tokens: 4096
```

`.env`: `OPENAI_API_KEY`

---

#### ⬜ `anthropic`
**File:** `src/services/llm/anthropic_chat.py`

Anthropic Claude models via the `anthropic` SDK. JSON mode enforced via prompt instruction (no native `response_format` parameter).

**Best for:** Comparing Claude classification quality vs GPT.

```yaml
llm:
  type: "anthropic"
  model: "claude-3-5-haiku-20241022"
  max_completion_tokens: 4096
```

`.env`: `ANTHROPIC_API_KEY`

---

#### ⬜ `ollama`
**File:** `src/services/llm/ollama_chat.py`

Local Ollama server via OpenAI-compatible API (`/v1/chat/completions`). No API cost. JSON mode support varies by model.

**Best for:** Fully offline runs, zero-cost testing of pipeline logic.

```yaml
llm:
  type: "ollama"
  model: "llama3.2"
  base_url: "http://localhost:11434"
  max_completion_tokens: 4096
```

No `.env` secrets needed.

---

#### ⬜ `google`
**File:** `src/services/llm/google_gemini_chat.py`

Google Gemini via `google-generativeai` SDK. JSON output via `response_mime_type="application/json"`.

```yaml
llm:
  type: "google"
  model: "gemini-2.0-flash"
  max_completion_tokens: 4096
```

`.env`: `GOOGLE_API_KEY`

---

#### ⬜ `mistral`
**File:** `src/services/llm/mistral_chat.py`

Mistral AI via `mistralai` SDK. Supports `response_format={"type": "json_object"}`. Good multilingual coverage.

```yaml
llm:
  type: "mistral"
  model: "mistral-small-latest"
  max_completion_tokens: 4096
```

`.env`: `MISTRAL_API_KEY`

---

### Database connectors

**Interface:** `src/services/db/base.py` — `DatabaseConnector`  
**Config key:** `database.type`  
**Used by:** `embed-rows` (read + write embeddings), `classify` (read rows + write GS1 columns)

> Each connector handles the embedding storage syntax specific to its database internally. Azure SQL uses `CAST(CAST(:col AS VARCHAR(MAX)) AS VECTOR(1024))`. PostgreSQL uses `:col::vector(1024)`. When adding a new connector, that connector owns this logic.

---

#### ✅ `azure_sql`
**File:** `src/services/db/azure_sql_connector.py`

Azure SQL Database via Azure AD Service Principal auth (`ActiveDirectoryServicePrincipal`, ODBC Driver 18). Uses `pyodbc` + `SQLAlchemy`.

**Best for:** Default. Azure SQL production setup.

```yaml
database:
  type: "azure_sql"
  schema_name: "playground"
  table: "promo_bronze"
  primary_key: "id"
```

`.env`: `AZURE_SQL_SERVER`, `AZURE_SQL_DATABASE`, `AZURE_SQL_CLIENT_ID`, `AZURE_SQL_CLIENT_SECRET`

---

#### ✅ `postgresql`
**File:** `src/services/db/postgresql.py`

PostgreSQL via username/password, `psycopg2` + `SQLAlchemy`. Compatible with PostgreSQL 14+.

```yaml
database:
  type: "postgresql"
  schema_name: "public"
  table: "promo_bronze"
  primary_key: "id"
```

`.env`: `PG_HOST`, `PG_PORT`, `PG_DATABASE`, `PG_USERNAME`, `PG_PASSWORD`

---

#### ⬜ `sqlite`
**File:** `src/services/db/sqlite_connector.py`

Serverless, file-based. No native vector type — embeddings stored as JSON text.

**Best for:** Local development and testing without any database server.

```yaml
database:
  type: "sqlite"
  db_path: "data/local.db"
  schema_name: ""
  table: "promo_bronze"
  primary_key: "id"
```

No `.env` secrets needed.

---

#### ⬜ `mysql`
**File:** `src/services/db/mysql_connector.py`

MySQL / MariaDB via `pymysql` + `SQLAlchemy`. MySQL 9.0+ supports native `VECTOR` type.

```yaml
database:
  type: "mysql"
  schema_name: "your_schema"
  table: "promo_bronze"
  primary_key: "id"
```

`.env`: `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_DATABASE`, `MYSQL_USERNAME`, `MYSQL_PASSWORD`

---

#### ⬜ `duckdb`
**File:** `src/services/db/duckdb_connector.py`

Serverless analytical database. Can query Parquet, CSV, or `.duckdb` files. No native vector type. Can query the `data/vector_store/*.parquet` artefacts from `build-vectors`.

**Best for:** Batch analytics, exploring classification results, fast local development.

```yaml
database:
  type: "duckdb"
  db_path: "data/local.duckdb"
  table: "promo_bronze"
  primary_key: "id"
```

No `.env` secrets needed.

---

## How to swap a component

### Switching to an already-implemented provider

1. Change the `type:` key in `config.yaml` to the new value.
2. Add the required secrets to `.env`.
3. Run.

Example — switch from Azure OpenAI embedding to HuggingFace:

```yaml
# config.yaml
embedding:
  type: "huggingface"
  dimensions: 384
  model_name: "all-MiniLM-L6-v2"
```

Then rebuild the FAISS index and re-run embed-rows (dimensions changed):

```bash
python vectorize.py build-vectors
python vectorize.py embed-rows
```

### Activating a scaffold provider

1. Open the scaffold file and implement the abstract methods.
2. Register in `src/factory.py` inside `build_default_factory()`:
   ```python
   from src.services.embedding.openai_embedder import OpenAIEmbeddingProvider
   factory.register_embedding("openai", OpenAIEmbeddingProvider)
   ```
3. Set `type: "openai"` in `config.yaml`.
4. Add secrets to `.env`.

### Adding a brand-new provider

1. Create a new file in the appropriate `src/services/<category>/` directory.
2. Inherit from the ABC in `base.py` and implement all abstract methods.
3. Register and configure as above.
