# Swappable Parts — Usage Guide

All four component interfaces live in `src/*/base.py`. Each component has a set of ready-to-use implementations and a set of scaffolded implementations (file exists, but methods raise `NotImplementedError`).

**To activate any option:**

1. Open the scaffold file and implement the methods.
2. Register the class in `src/factory.py` inside `build_default_factory()`:
   ```python
   from src.services.<category>.<module> import <ClassName>
   factory.register_<category>("<type_name>", <ClassName>)
   ```
3. Set the matching `type:` key in `config.yaml`.

No other code changes are needed.

**Legend:** ✅ implemented and registered · ⬜ scaffold exists (not yet implemented)

---

## 1. Embedding Provider

**Interface:** `src/services/embedding/base.py` — `EmbeddingProvider`
**Config key:** `embedding.type`
**Used by:** all three modes (`build-vectors`, `embed-rows`, `classify`)

> **Critical:** All three modes must use the same model and the same `embedding.dimensions`. The FAISS index (built by `build-vectors`) and the DB row embeddings (written by `embed-rows`) must come from the same model. Switching models requires rebuilding the FAISS index and re-running `embed-rows`.

---

### ✅ `azure_openai` — Azure OpenAI Embedder
**File:** `src/services/embedding/azure_openai_embedder.py`
**Class:** `AzureOpenAIEmbeddingProvider`

Calls the Azure OpenAI `text-embedding-3-large` deployment (or any other deployment you configure). Uses the `openai` Python SDK with an `AzureOpenAI` client. Batches texts in parallel using `ThreadPoolExecutor`. Retries on `RateLimitError` with configurable exponential backoff.

**When to use:** Default choice. You already have an Azure OpenAI resource. Produces high-quality 1024-dim vectors. Works for both taxonomy (FAISS) and product rows (DB).

**Config:**
```yaml
embedding:
  type: "azure_openai"
  dimensions: 1024
  batch_size: 256
  max_workers: 5
```
Secrets in `.env`: `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_EMBEDDING_DEPLOYMENT`, `AZURE_OPENAI_API_VERSION`

---

### ✅ `huggingface` — HuggingFace Local Embedder
**File:** `src/services/embedding/huggingface.py`
**Class:** `HuggingFaceEmbeddingProvider`

Runs a `sentence-transformers` model locally (no API calls, no cost). Model is downloaded from HuggingFace Hub on first use and cached locally. Good for development, testing, or air-gapped environments. No retry logic needed — it's local. Dimensions vary by model (e.g., `all-MiniLM-L6-v2` → 384 dims, `all-mpnet-base-v2` → 768 dims).

**When to use:** Local dev/testing, cost-sensitive runs, or experimenting with different models without spending API credits. Rebuild the FAISS index if you switch models.

**Config:**
```yaml
embedding:
  type: "huggingface"
  dimensions: 384        # must match the chosen model's output dims
  model_name: "all-MiniLM-L6-v2"
```
No `.env` secrets needed.

---

### ⬜ `openai` — Direct OpenAI Embedder
**File:** `src/services/embedding/openai_embedder.py`
**Class:** `OpenAIEmbeddingProvider`

Same as the Azure provider but hits the standard OpenAI API (`api.openai.com`) directly. No `azure_endpoint` or `api_version` needed — just an API key. Uses the same `openai` SDK. Useful if you have a direct OpenAI subscription but no Azure OpenAI resource.

**Config:**
```yaml
embedding:
  type: "openai"
  dimensions: 1024
  model: "text-embedding-3-large"
```
Secrets in `.env`: `OPENAI_API_KEY`

---

### ⬜ `ollama` — Ollama Local Embedder
**File:** `src/services/embedding/ollama_embedder.py`
**Class:** `OllamaEmbeddingProvider`

Sends embedding requests to a locally running [Ollama](https://ollama.com) server via its REST API (`POST /api/embeddings`). No external API costs. Supports models like `nomic-embed-text` (768 dims) and `mxbai-embed-large` (1024 dims). Requires Ollama to be installed and running.

**Config:**
```yaml
embedding:
  type: "ollama"
  dimensions: 1024
  model_name: "mxbai-embed-large"
  base_url: "http://localhost:11434"
```
No `.env` secrets needed.

---

### ⬜ `cohere` — Cohere Embedder
**File:** `src/services/embedding/cohere_embedder.py`
**Class:** `CohereEmbeddingProvider`

Uses the Cohere Embed API via their Python SDK. Cohere's embeddings are optimised for retrieval/search tasks and support input type hints (`search_document` vs `search_query`). Dimensions: 1024 (default). Paid API.

**Config:**
```yaml
embedding:
  type: "cohere"
  dimensions: 1024
  model: "embed-multilingual-v3.0"
  input_type: "search_document"
```
Secrets in `.env`: `COHERE_API_KEY`

---

## 2. Vector Store

**Interface:** `src/services/vectorstore/base.py` — `VectorStore`
**Config key:** `vector_store.type`
**Used by:** `build-vectors` (write), `classify` (read/search)

> The vector store is responsible for building from embedded documents, saving all artefacts to disk, loading them back at query time, and executing similarity search. Switching stores means the new implementation handles all of this end-to-end.

---

### ✅ `faiss` — FAISS Local Index
**File:** `src/services/vectorstore/faiss_store.py`
**Class:** `FAISSVectorStore`

Builds and queries a Facebook FAISS index stored on local disk. Exact nearest-neighbor search — no approximation. Loads entirely into memory at query time. At build time produces five artefacts in `data/vector_store/`: the binary `.index` file, a `_metadata.json` lookup, a `build_manifest.json`, an `embeddings_{prefix}.parquet` archive, and a `{prefix}_lookup.pkl` compact pickle.

Always uses `IndexFlatL2` (squared L2 distance on L2-normalised vectors). Vectors are normalised in-place for consistent magnitude before indexing and searching. Scores are squared L2 distances in `[0, 4]` for unit vectors — lower = more similar.

**When to use:** Default choice. The GS1 taxonomy has ~200k nodes — FAISS handles this comfortably in memory. Zero infrastructure, no server needed.

**Config:**
```yaml
vector_store:
  type: "faiss"
  output_dir: "data/vector_store"
  filename_prefix: "gs1"
  lookup_metadata_fields: [level, code, title, hierarchy_path, hierarchy_string]
```

---

### ⬜ `pgvector` — PostgreSQL + pgvector
**File:** `src/services/vectorstore/pgvector_store.py`
**Class:** `PgVectorVectorStore`

Stores vectors directly in a PostgreSQL table using the `pgvector` extension. No additional infrastructure if you already run PostgreSQL. The FAISS index is replaced by a `CREATE INDEX USING hnsw` or `ivfflat` index on the vector column. Search is a SQL query: `ORDER BY embedding <-> $1 LIMIT $k`. Supports filtering by metadata columns alongside the ANN search.

**When to use:** When you want your vector index co-located with your product database, need metadata filtering at search time, or want to avoid loading a full index into memory.

**Config:**
```yaml
vector_store:
  type: "pgvector"
  table: "gs1_taxonomy"
  schema: "vectors"
```
Secrets in `.env`: same PostgreSQL credentials as the `postgresql` database connector.

---

### ⬜ `azure_search` — Azure AI Search
**File:** `src/services/vectorstore/azure_ai_search_store.py`
**Class:** `AzureAISearchVectorStore`

Uses Azure AI Search (formerly Cognitive Search) as a managed vector store. Upload documents to a search index and query via the `azure-search-documents` SDK. Supports hybrid search (vector + keyword) and built-in filtering. Fully managed, no server to maintain, scales automatically.

**When to use:** Production-grade managed solution in Azure. Useful when the index exceeds available memory, or when hybrid keyword+vector search is needed out of the box.

**Config:**
```yaml
vector_store:
  type: "azure_search"
  index_name: "gs1-taxonomy"
```
Secrets in `.env`: `AZURE_SEARCH_ENDPOINT`, `AZURE_SEARCH_API_KEY`

---

### ⬜ `chromadb` — ChromaDB
**File:** `src/services/vectorstore/chromadb_store.py`
**Class:** `ChromaDBVectorStore`

Lightweight vector database that runs either in-process (no server) or as a client-server. Good for development, experimentation, and smaller datasets. Python-native API with built-in metadata filtering. Persistent storage to a local directory.

**When to use:** Quick local prototyping or testing classification without setting up infrastructure. Not recommended for production with large indexes.

**Config:**
```yaml
vector_store:
  type: "chromadb"
  persist_dir: "data/vector_store/chroma"
  collection_name: "gs1_taxonomy"
```

---

### ⬜ `qdrant` — Qdrant
**File:** `src/services/vectorstore/qdrant_store.py`
**Class:** `QdrantVectorStore`

Qdrant is a dedicated vector database with strong payload (metadata) filtering, HNSW indexing, and both in-memory and persistent modes. Available as a local server (Docker) or cloud. The `qdrant-client` Python SDK supports uploading, searching, and filtering in one call.

**When to use:** When you need rich metadata filtering on results (e.g., filter by GS1 level, or scope a search to a specific segment), or when you want a purpose-built vector DB with a REST/gRPC API.

**Config:**
```yaml
vector_store:
  type: "qdrant"
  collection_name: "gs1_taxonomy"
  url: "http://localhost:6333"
```
No `.env` secrets needed (add an API key for cloud deployments).

---

## 3. LLM Provider

**Interface:** `src/services/llm/base.py` — `LLMProvider`
**Config key:** `llm.type`
**Used by:** `classify` mode only

> The LLM provider receives a system message and a user message, and returns the response content plus token usage. The `classify` mode always calls with `response_format={"type": "json_object"}` — any provider you add must support forced JSON output or emulate it reliably via prompt engineering.

---

### ✅ `azure_openai` — Azure OpenAI Chat
**File:** `src/services/llm/azure_openai_chat.py`
**Class:** `AzureOpenAILLMProvider`

Calls an Azure-hosted OpenAI chat model (`o4-mini` or any other deployment) via the `openai` SDK's `AzureOpenAI` client. Supports `response_format={"type": "json_object"}`. Retries on `RateLimitError`. Returns response content + token usage counts.

**When to use:** Default choice. `o4-mini` gives a good cost/quality tradeoff for structured classification tasks.

**Config:**
```yaml
llm:
  type: "azure_openai"
  max_completion_tokens: 4096
```
Secrets in `.env`: `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_CHAT_DEPLOYMENT`, `AZURE_OPENAI_API_VERSION`

---

### ⬜ `openai` — Direct OpenAI Chat
**File:** `src/services/llm/openai_chat.py`
**Class:** `OpenAILLMProvider`

Same as the Azure provider but targets `api.openai.com` directly. No `azure_endpoint` or `api_version`. Supports the same `response_format` JSON mode. Useful if you have a direct OpenAI subscription but no Azure resource.

**Config:**
```yaml
llm:
  type: "openai"
  model: "gpt-4o-mini"
  max_completion_tokens: 4096
```
Secrets in `.env`: `OPENAI_API_KEY`

---

### ⬜ `anthropic` — Anthropic Claude
**File:** `src/services/llm/anthropic_chat.py`
**Class:** `AnthropicLLMProvider`

Uses the `anthropic` Python SDK to call Claude models (e.g., `claude-3-5-haiku`, `claude-opus-4`). Anthropic does not have a `response_format` parameter — JSON mode is enforced via prompt instruction and by pre-filling the assistant turn with `{`. The orchestrator's regex fallback handles cases where the JSON is imperfect.

**When to use:** When comparing Claude's classification quality against GPT, or when you have Anthropic credits. Claude follows complex structured instructions well.

**Config:**
```yaml
llm:
  type: "anthropic"
  model: "claude-3-5-haiku-20241022"
  max_completion_tokens: 4096
```
Secrets in `.env`: `ANTHROPIC_API_KEY`

---

### ⬜ `ollama` — Ollama Local LLM
**File:** `src/services/llm/ollama_chat.py`
**Class:** `OllamaLLMProvider`

Sends chat requests to a locally running Ollama server. Ollama exposes an OpenAI-compatible REST API (`/v1/chat/completions`), so this can be implemented with the same `openai` SDK using `base_url="http://localhost:11434/v1"`. Models like `llama3.2`, `mistral`, and `qwen2.5` run locally with no API cost. JSON mode support varies by model.

**When to use:** Fully offline runs, zero-cost experimentation, or testing pipeline logic without spending API credits. Classification quality will be lower than GPT-4o-class models for complex tasks.

**Config:**
```yaml
llm:
  type: "ollama"
  model: "llama3.2"
  base_url: "http://localhost:11434"
  max_completion_tokens: 4096
```
No `.env` secrets needed.

---

### ⬜ `google` — Google Gemini
**File:** `src/services/llm/google_gemini_chat.py`
**Class:** `GoogleGeminiLLMProvider`

Uses the `google-generativeai` SDK to call Gemini models (`gemini-2.0-flash`, `gemini-2.5-pro`, etc.). Supports structured JSON output via `response_mime_type="application/json"`. Competitive quality and a generous free tier on lower-tier models.

**Config:**
```yaml
llm:
  type: "google"
  model: "gemini-2.0-flash"
  max_completion_tokens: 4096
```
Secrets in `.env`: `GOOGLE_API_KEY`

---

### ⬜ `mistral` — Mistral AI
**File:** `src/services/llm/mistral_chat.py`
**Class:** `MistralLLMProvider`

Uses the `mistralai` Python SDK. `mistral-small` and `mistral-large` both support JSON mode via `response_format={"type": "json_object"}`. Strong multilingual support — well-suited for product names in multiple European languages.

**Config:**
```yaml
llm:
  type: "mistral"
  model: "mistral-small-latest"
  max_completion_tokens: 4096
```
Secrets in `.env`: `MISTRAL_API_KEY`

---

## 4. Database Connector

**Interface:** `src/services/db/base.py` — `DatabaseConnector`
**Config key:** `database.type`
**Used by:** `embed-rows` (write embeddings), `classify` (read rows + write GS1 columns)

> The connector hides all SQL syntax differences. Azure SQL and PostgreSQL have different vector casting syntax — each connector handles this internally. When adding a new connector, that connector is responsible for all embedding storage syntax specific to that database.

---

### ✅ `azure_sql` — Azure SQL (Service Principal)
**File:** `src/services/db/azure_sql_connector.py`
**Class:** `AzureSQLConnector`

Connects to Azure SQL Database using Azure AD Service Principal authentication (`ActiveDirectoryServicePrincipal` via ODBC Driver 18). Uses `pyodbc` + `SQLAlchemy`. Embedding vectors are written using Azure SQL's native `VECTOR(1024)` type with the cast pattern: `CAST(CAST(:col AS VARCHAR(MAX)) AS VECTOR(1024))`. Pagination uses `OFFSET … FETCH NEXT` syntax.

**When to use:** Default. Your production database is Azure SQL. Service Principal auth means no passwords to rotate.

**Config:**
```yaml
database:
  type: "azure_sql"
  schema_name: "playground"
  table: "promo_bronze"
  primary_key: "id"
```
Secrets in `.env`: `AZURE_SQL_SERVER`, `AZURE_SQL_DATABASE`, `AZURE_SQL_CLIENT_ID`, `AZURE_SQL_CLIENT_SECRET`

---

### ✅ `postgresql` — PostgreSQL (Username/Password)
**File:** `src/services/db/postgresql.py`
**Class:** `PostgreSQLConnector`

Connects to PostgreSQL using standard username/password auth via `psycopg2` + `SQLAlchemy`. Embedding vectors are written using the `pgvector` extension cast: `:col::vector(1024)`. Pagination uses the same `OFFSET … FETCH NEXT` SQL. Works with any PostgreSQL 14+ instance (local, cloud, managed).

**When to use:** When your database is PostgreSQL instead of Azure SQL. Change `database.type` in config, set PG env vars, done.

**Config:**
```yaml
database:
  type: "postgresql"
  schema_name: "public"
  table: "promo_bronze"
  primary_key: "id"
```
Secrets in `.env`: `PG_HOST`, `PG_PORT`, `PG_DATABASE`, `PG_USERNAME`, `PG_PASSWORD`

---

### ⬜ `sqlite` — SQLite
**File:** `src/services/db/sqlite_connector.py`
**Class:** `SQLiteConnector`

Serverless, zero-infrastructure, file-based database. No native vector type — embeddings are stored as `TEXT` (JSON string). The connector handles serialization/deserialization internally. Good for local development and testing without any database server.

**When to use:** Local testing, unit test fixtures, or running the pipeline on a laptop with no database server. Not suitable for production or large datasets.

**Config:**
```yaml
database:
  type: "sqlite"
  db_path: "data/local.db"
  schema_name: ""      # SQLite has no schemas
  table: "promo_bronze"
  primary_key: "id"
```
No `.env` secrets needed.

---

### ⬜ `mysql` — MySQL / MariaDB
**File:** `src/services/db/mysql_connector.py`
**Class:** `MySQLConnector`

Connects via `pymysql` + `SQLAlchemy`. MySQL 9.0+ has a native `VECTOR` type; older versions store embeddings as `LONGTEXT`. Pagination uses `LIMIT … OFFSET` syntax (different from SQL Server / PostgreSQL).

**When to use:** When your existing data warehouse runs on MySQL or MariaDB.

**Config:**
```yaml
database:
  type: "mysql"
  schema_name: "your_schema"
  table: "promo_bronze"
  primary_key: "id"
```
Secrets in `.env`: `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_DATABASE`, `MYSQL_USERNAME`, `MYSQL_PASSWORD`

---

### ⬜ `duckdb` — DuckDB
**File:** `src/services/db/duckdb_connector.py`
**Class:** `DuckDBConnector`

Serverless analytical database, extremely fast for batch reads on columnar data. Can query Parquet, CSV, or its own `.duckdb` file directly. No native vector type — store as `FLOAT[]` or `VARCHAR`. Can query the `data/vector_store/*.parquet` artefacts produced by `build-vectors`, making it useful for inspection and debugging workflows.

**When to use:** Batch analytics, exploring classification results, or as a fast local alternative for development where you want SQL but no server.

**Config:**
```yaml
database:
  type: "duckdb"
  db_path: "data/local.duckdb"
  table: "promo_bronze"
  primary_key: "id"
```
No `.env` secrets needed.
