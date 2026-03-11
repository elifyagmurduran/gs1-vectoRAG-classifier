# Build Guide — Part 1 of 2

**Phases 0 – 10:** Project scaffold, config system, exceptions, logging, console, utilities, interfaces, factory, GS1 parser, embedding providers, and FAISS vector store.

> **Who this is for:** A developer starting from a completely empty repository who wants to rebuild this project from scratch, without any AI assistance. Every file, every class, every design decision is explained here.
>
> **How to use this guide:** Follow each phase in order. Do not skip ahead. Each phase's output is required by the next. After completing a phase, switch to the [TESTING GUIDE](TESTING_GUIDE.md) and run the corresponding verification steps before continuing.

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Phase 0 — Project Scaffold & Dependencies](#phase-0--project-scaffold--dependencies)
- [Phase 1 — Config System](#phase-1--config-system)
- [Phase 2 — Domain Exceptions](#phase-2--domain-exceptions)
- [Phase 3 — Logging](#phase-3--logging)
- [Phase 4 — Console, Batching & Retry Utilities](#phase-4--console-batching--retry-utilities)
- [Phase 5 — Template Utility](#phase-5--template-utility)
- [Phase 6 — Interfaces (Abstract Base Classes) & Document DTO](#phase-6--interfaces-abstract-base-classes--document-dto)
- [Phase 7 — Component Factory](#phase-7--component-factory)
- [Phase 8 — GS1 Parser](#phase-8--gs1-parser)
- [Phase 9 — Embedding Providers](#phase-9--embedding-providers)
- [Phase 10 — FAISS Vector Store](#phase-10--faiss-vector-store)

---

## Architecture Overview

The application is a **YAML-configurable, extensible pipeline** with two entry points and three pipeline modes.

### Entry Points

| File | Purpose |
|---|---|
| `main.py` | `classify` mode. Run with `python main.py`. Classifies unclassified rows in the database. |
| `vectorize.py` | `build-vectors` and `embed-rows` modes. Run with `python vectorize.py build-vectors` or `python vectorize.py embed-rows`. |

### Three Pipeline Modes

```
┌────────────────────────────────────────────────────────────────┐
│                        config.yaml                             │
└──────────────────────────┬─────────────────────────────────────┘
                           │
     ┌─────────────────────┼─────────────────────────┐
     │                     │                         │
     ▼                     ▼                         ▼
build-vectors          embed-rows                classify
(vectorize.py)         (vectorize.py)            (main.py)
     │                     │                         │
JSON → Parse          DB → Concat            DB → RAG → LLM
→ Embed → FAISS       → Embed → DB           → Parse → DB
+ 5 artefacts         (per batch)            (per batch)
```

| Mode | Description | Entry |
|---|---|---|
| `build-vectors` | Read GS1 JSON taxonomy → parse into Documents → embed → save FAISS index | `vectorize.py build-vectors` |
| `embed-rows` | Read product rows from DB → embed text → write embedding vector back | `vectorize.py embed-rows` |
| `classify` | Fetch unclassified rows → RAG similarity search → LLM prompt → write GS1 columns | `main.py` |

### Folder Structure (Final — build this layout now)

```
gs1-vectoRAG-classifier/
├── main.py                      # Entry point: classify mode
├── vectorize.py                 # Entry point: build-vectors + embed-rows
├── config.yaml                  # Single config file for all modes
├── .env                         # Secrets (API keys, DB passwords) — git-ignored
├── pyproject.toml
├── requirements.txt
├── data/
│   ├── input/                   # Source data files (GS1.json)
│   └── vector_store/            # FAISS artefact output directory
├── templates/                   # Jinja2 prompt templates
│   ├── gs1_system.j2
│   └── gs1_classification.j2
├── logs/                        # Per-run log files (auto-created)
├── tests/
│   ├── __init__.py
│   ├── fixtures/                # Small JSON files for unit tests
│   │   └── gs1_sample.json
│   └── (test files added per phase)
├── docs/
└── src/
    ├── __init__.py
    ├── dto.py                   # Document dataclass — the data unit flowing through
    ├── factory.py               # ComponentFactory: config strings → concrete classes
    ├── config/
    │   ├── __init__.py
    │   └── models.py            # Pydantic AppConfig + load_config()
    ├── services/
    │   ├── __init__.py
    │   ├── gs1_parser.py        # GS1Parser: parse GS1 JSON → list[Document]
    │   ├── orchestrator.py      # LLMOrchestratorService: RAG + LLM classify flow
    │   ├── db/                  # DatabaseConnector interface + implementations
    │   │   ├── __init__.py
    │   │   ├── base.py          # ABC: connect/disconnect/fetch_batch/update_rows
    │   │   ├── azure_sql_connector.py
    │   │   ├── postgresql.py
    │   │   ├── duckdb_connector.py    # scaffold (NotImplementedError)
    │   │   ├── mysql_connector.py     # scaffold
    │   │   └── sqlite_connector.py    # scaffold
    │   ├── embedding/           # EmbeddingProvider interface + implementations
    │   │   ├── __init__.py
    │   │   ├── base.py          # ABC: embed_batch(texts) / dimensions property
    │   │   ├── azure_openai_embedder.py
    │   │   ├── huggingface.py
    │   │   ├── openai_embedder.py     # scaffold
    │   │   ├── ollama_embedder.py     # scaffold
    │   │   └── cohere_embedder.py     # scaffold
    │   ├── llm/                 # LLMProvider interface + implementations
    │   │   ├── __init__.py
    │   │   ├── base.py          # ABC: chat(system, user, response_format)
    │   │   ├── azure_openai_chat.py
    │   │   ├── openai_chat.py         # scaffold
    │   │   ├── anthropic_chat.py      # scaffold
    │   │   ├── google_gemini_chat.py  # scaffold
    │   │   ├── mistral_chat.py        # scaffold
    │   │   └── ollama_chat.py         # scaffold
    │   └── vectorstore/         # VectorStore interface + implementations
    │       ├── __init__.py
    │       ├── base.py          # ABC: save/load/search
    │       ├── faiss_store.py
    │       ├── chromadb_store.py      # scaffold
    │       └── azure_ai_search_store.py  # scaffold
    ├── transforms/              # Pure transformation logic (no I/O, no external calls)
    │   ├── __init__.py
    │   ├── candidate_builder.py # CandidateBuilder: RAG results → lettered options
    │   └── response_parser.py   # ResponseParser: letter choice → GS1 levels
    ├── utils/
    │   ├── __init__.py
    │   ├── batching.py          # iter_batches() + DatabaseBatcher (SQL pagination)
    │   ├── console.py           # Console class: rich terminal output (separate from logging)
    │   ├── env.py               # get_env() + resolve_env_vars() for ${VAR} interpolation
    │   ├── exceptions.py        # PipelineError hierarchy (domain-specific exceptions)
    │   ├── logging.py           # setup_logging() + get_logger() (colored + file)
    │   ├── retry.py             # make_retry_decorator() via tenacity
    │   └── templates.py         # render_template(): Jinja2 + fallback strings
    └── workflows/
        ├── __init__.py
        ├── build_vectors.py     # run_build_vectors() pipeline function
        ├── classify.py          # run_classify() pipeline function
        └── embed_rows.py        # run_embed_rows() pipeline function
```

### Key Architectural Decisions

**4 swappable interfaces.** `EmbeddingProvider`, `VectorStore`, `LLMProvider`, `DatabaseConnector`. Each has one or more concrete implementations. To switch providers, change one line in `config.yaml`. The `ComponentFactory` maps type strings to classes.

**Config-first.** A single `config.yaml` validated by Pydantic at startup. Secrets (API keys, passwords) live only in `.env` and are never in the YAML.

**Batch-level commit.** All data writes — to the DB and to disk — happen immediately after each batch completes. If the process is interrupted mid-run, it can be safely resumed from where it left off.

**Separation: logging vs. console.** `logging.py` writes to the log file AND the console, for diagnostics. `console.py` writes only to the terminal via `print()`, for structured visual output (boxes, progress bars, summaries). They never cross-call.

**`transforms/` is pure logic.** `candidate_builder.py` and `response_parser.py` have zero I/O and zero external calls. They can be tested with no mocks whatsoever.

---

## Phase 0 — Project Scaffold & Dependencies

**Goal:** Create the project skeleton and install dependencies so `pip install -e .` works and `import src` succeeds.

### 0.1 Create the VirtualEnvironment

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
# OR
source .venv/bin/activate     # Linux / macOS
```

### 0.2 Create the Folder Structure

Create every folder now, including all `__init__.py` files. You will fill them in over the following phases. Empty `__init__.py` files simply tell Python "this directory is a Python package."

```bash
mkdir -p src/config src/services/db src/services/embedding src/services/llm
mkdir -p src/services/vectorstore src/transforms src/utils src/workflows
mkdir -p data/input data/vector_store templates logs tests/fixtures docs
```

Then create all empty `__init__.py` files:

```bash
touch src/__init__.py
touch src/config/__init__.py
touch src/services/__init__.py
touch src/services/db/__init__.py
touch src/services/embedding/__init__.py
touch src/services/llm/__init__.py
touch src/services/vectorstore/__init__.py
touch src/transforms/__init__.py
touch src/utils/__init__.py
touch src/workflows/__init__.py
touch tests/__init__.py
```

### 0.3 `requirements.txt`

```
openai>=1.30.0
faiss-cpu>=1.7.4
pyodbc>=5.1
psycopg2-binary>=2.9
SQLAlchemy>=2.0
pandas>=2.1
pydantic>=2.5
PyYAML>=6.0
Jinja2>=3.1
python-dotenv>=1.0
tenacity>=8.2
numpy>=1.26
pyarrow>=15.0
sentence-transformers>=2.6
pytest>=8.0
```

### 0.4 `pyproject.toml`

This file lets Python find the `src/` package when you run `pip install -e .`. The `pythonpath = ["."]` line in `pytest` settings ensures `import src` works from test files.

```toml
[build-system]
requires = ["setuptools>=68.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "gs1-vectoRAG-classifier"
version = "0.1.0"
requires-python = ">=3.10"
description = "YAML-configurable RAG pipeline that classifies products against the GS1 GPC taxonomy using vector similarity and LLM inference"

[tool.setuptools.packages.find]
where = ["."]
include = ["src*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```

### 0.5 `.env` template

Create a `.env` file containing placeholder values. **Add `.env` to `.gitignore` immediately** — it will hold real API keys and passwords that must never be committed.

```env
# === Azure OpenAI (used by embedding and LLM providers) ===
AZURE_OPENAI_API_KEY=your-key-here
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-3-large
AZURE_OPENAI_CHAT_DEPLOYMENT=o4-mini
AZURE_OPENAI_API_VERSION=2024-06-01

# === Azure SQL (Service Principal auth) ===
AZURE_SQL_SERVER=your-server.database.windows.net
AZURE_SQL_DATABASE=your-db
AZURE_SQL_CLIENT_ID=your-app-id
AZURE_SQL_CLIENT_SECRET=your-secret

# === PostgreSQL (username/password auth) ===
PG_HOST=localhost
PG_PORT=5432
PG_DATABASE=your-db
PG_USERNAME=your-user
PG_PASSWORD=your-password
```

See [TESTING_GUIDE.md §Phase 0](TESTING_GUIDE.md#phase-0-tests) for verification steps.

---

## Phase 1 — Config System

**Goal:** Load `config.yaml`, interpolate `${ENV_VARS}`, validate with Pydantic. Bad config → clear error → halt.

This phase teaches the application to read its settings. Every downstream phase uses the `AppConfig` object produced here. Getting this right first means every later component gets correct values without redundant argument passing.

### 1.1 `src/utils/env.py` — Environment variable interpolation

This module has two functions:

- `get_env(var_name)` — reads a required env var; raises `ValueError` if missing.
- `resolve_env_vars(value)` — recursively replaces any `${VAR_NAME}` in a config structure (string, dict, list) with the actual env var value.

**Why:** Secrets (API keys, passwords) should never be stored in `config.yaml`. By writing `${AZURE_OPENAI_API_KEY}` in the YAML, the config file stays safe to commit, while the actual values come from `.env` at runtime.

```python
"""Resolve ${VAR_NAME} placeholders in config values from environment."""
import os
import re
from dotenv import load_dotenv

load_dotenv()  # populates os.environ from .env

_ENV_PATTERN = re.compile(r"\$\{(\w+)\}")


def get_env(var_name: str) -> str:
    """Get a required environment variable.

    Reads from os.environ (already populated by python-dotenv).
    Use this for secrets that live exclusively in .env and are NOT
    in config.yaml at all.

    Raises:
        ValueError: If the variable is not set.
    """
    val = os.environ.get(var_name)
    if val is None:
        raise ValueError(
            f"Environment variable '{var_name}' is not set. "
            f"Add it to .env or export it."
        )
    return val


def resolve_env_vars(value):
    """Recursively resolve ${VAR} placeholders in a config structure.

    Raises:
        ValueError: If a referenced env var is not set.
    """
    if isinstance(value, str):
        def _replace(match):
            var_name = match.group(1)
            env_val = os.environ.get(var_name)
            if env_val is None:
                raise ValueError(
                    f"Environment variable '{var_name}' is not set. "
                    f"Add it to .env or export it."
                )
            return env_val
        return _ENV_PATTERN.sub(_replace, value)
    elif isinstance(value, dict):
        return {k: resolve_env_vars(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [resolve_env_vars(item) for item in value]
    return value
```

### 1.2 `src/config/models.py` — Pydantic models + YAML loader

Define one Pydantic model per section of `config.yaml`. Pydantic validates types, provides typed attribute access, and fills in defaults. The `load_config()` function ties everything together.

**Why Pydantic?** A raw YAML dict gives no type checking. With Pydantic, `config.embedding.dimensions` is guaranteed to be an `int`, not the string `"1024"`. Errors are caught at startup with a clear message identifying the exact field that's wrong.

```python
"""Pydantic config models and YAML loader with env-var interpolation."""
from __future__ import annotations
import yaml
from pathlib import Path
from pydantic import BaseModel, Field
from typing import Optional
from src.utils.env import resolve_env_vars
from src.utils.exceptions import ConfigError


class RetryConfig(BaseModel):
    max_attempts: int = 3
    backoff_factor: float = 1.5
    min_wait: float = 30.0
    max_wait: float = 120.0


class SystemConfig(BaseModel):
    log_level: str = "INFO"
    max_workers: int = 5
    batch_size: int = 256
    retry: RetryConfig = Field(default_factory=RetryConfig)


class PipelineConfig(BaseModel):
    name: str = "gs1-vectoRAG-classifier"
    description: str = ""


class SourceConfig(BaseModel):
    type: str = "file_json"
    path: str = "data/input/GS1.json"
    encoding: str = "utf-8"
    parser: str = "gs1"
    batch_size: int          # required — must be in config.yaml


class EmbeddingConfig(BaseModel):
    type: str = "azure_openai"
    dimensions: int = 1024
    batch_size: int = 256
    max_workers: int = 5
    model_name: Optional[str] = None  # Only for HuggingFace


class VectorStoreConfig(BaseModel):
    type: str = "faiss"
    output_dir: str = "data/vector_store"
    filename_prefix: str = "gs1"
    lookup_metadata_fields: list[str] = Field(default_factory=lambda: [
        "level", "code", "title", "hierarchy_path", "hierarchy_string"
    ])


class DatabaseConfig(BaseModel):
    type: str = "azure_sql"
    schema_name: str = "playground"
    table: str = "promo_bronze"
    primary_key: str = "id"


class RowEmbeddingConfig(BaseModel):
    batch_size: int          # required — must be in config.yaml
    columns: list[str] = Field(default_factory=list)
    separator: str = " * "
    target_column: str = "embedding_context"


class LLMConfig(BaseModel):
    type: str = "azure_openai"
    max_completion_tokens: int = 4096


class ClassificationConfig(BaseModel):
    rag_top_k: int = 30
    batch_size: int          # required — must be in config.yaml
    # Columns fetched from DB and shown to the LLM in the prompt.
    # NOT used by RAG — FAISS always uses the pre-computed embedding_context vector.
    prompt_columns: list[str] = Field(default_factory=lambda: [
        "product_name", "product_name_en", "packaging_value", "packaging_unit"
    ])
    target_columns: list[str] = Field(default_factory=lambda: [
        "gs1_segment", "gs1_family", "gs1_class",
        "gs1_brick", "gs1_attribute", "gs1_attribute_value"
    ])
    prompt_template_file: Optional[str] = None
    system_template_file: Optional[str] = None


class AppConfig(BaseModel):
    version: str = "2.0"
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)
    system: SystemConfig = Field(default_factory=SystemConfig)
    source: SourceConfig = Field(default_factory=SourceConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    vector_store: VectorStoreConfig = Field(default_factory=VectorStoreConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    row_embedding: RowEmbeddingConfig = Field(default_factory=RowEmbeddingConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    classification: ClassificationConfig = Field(default_factory=ClassificationConfig)


def load_config(config_path: str = "config.yaml") -> AppConfig:
    """Load YAML config, resolve env vars, validate with Pydantic.

    Raises:
        ConfigError: If config file does not exist.
        ValueError: If a ${VAR} env var is not set.
        pydantic.ValidationError: If config shape is invalid.
    """
    path = Path(config_path)
    if not path.exists():
        raise ConfigError(
            f"Config file not found: {config_path}",
            config_path=config_path,
        )
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    resolved = resolve_env_vars(raw)
    return AppConfig(**resolved)
```

**Important:** `SourceConfig.batch_size`, `RowEmbeddingConfig.batch_size`, and `ClassificationConfig.batch_size` have no default. They are **required** fields in `config.yaml`. Pydantic will raise `ValidationError` if any of them is missing.

### 1.3 `config.yaml` — The complete configuration file

This is the single source of truth for all runtime settings. Paste this exactly:

```yaml
# ═══════════════════════════════════════════════════════════════════
# config.yaml — Single configuration file for all pipeline modes
# Secrets (API keys, passwords) live in .env — NEVER put them here.
# ═══════════════════════════════════════════════════════════════════

version: "2.0"

# === Pipeline Metadata ===
pipeline:
  name: "gs1-vectoRAG-classifier"
  description: "Vector store creation, row embedding, and RAG-powered classification"

# === System Settings ===
system:
  log_level: "INFO"
  max_workers: 5
  batch_size: 256
  retry:
    max_attempts: 3
    backoff_factor: 1.5
    min_wait: 30.0
    max_wait: 120.0

# === Source Data (build-vectors reads this) ===
source:
  type: "file_json"
  path: "data/input/GS1.json"
  encoding: "utf-8"
  parser: "gs1"
  batch_size: 50             # documents per embedding batch during build

# === Embedding Provider (shared by ALL three modes — MUST match!) ===
# Secrets in .env: AZURE_OPENAI_API_KEY, AZURE_OPENAI_ENDPOINT,
#                  AZURE_OPENAI_EMBEDDING_DEPLOYMENT, AZURE_OPENAI_API_VERSION
embedding:
  type: "azure_openai"       # also supported: huggingface
  dimensions: 1024
  batch_size: 256
  max_workers: 5
  # model_name: "all-MiniLM-L6-v2"   # only for huggingface type

# === Vector Store (build-vectors + classify) ===
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

# === Database (embed-rows + classify) ===
# Secrets in .env: AZURE_SQL_SERVER, AZURE_SQL_DATABASE,
#                  AZURE_SQL_CLIENT_ID, AZURE_SQL_CLIENT_SECRET
database:
  type: "azure_sql"           # also supported: postgresql
  schema_name: "playground"
  table: "promo_bronze"
  primary_key: "id"

# === Row Embedding (embed-rows) ===
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

# === LLM Provider (classify) ===
# Secrets in .env: AZURE_OPENAI_API_KEY, AZURE_OPENAI_ENDPOINT,
#                  AZURE_OPENAI_CHAT_DEPLOYMENT, AZURE_OPENAI_API_VERSION
llm:
  type: "azure_openai"
  max_completion_tokens: 4096

# === Classification / RAG (classify) ===
classification:
  rag_top_k: 30
  batch_size: 10
  # prompt_columns: fetched from DB and shown to LLM in the prompt.
  # NOT used by the FAISS search — RAG always uses the pre-computed embedding_context vector.
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

See [TESTING_GUIDE.md §Phase 1](TESTING_GUIDE.md#phase-1-tests) for verification steps.

---

## Phase 2 — Domain Exceptions

**Goal:** Define the custom exception hierarchy that every other module will use. Build this **before** anything else in `src/utils/` because it has zero dependencies.

**Why custom exceptions?** Python's built-in exceptions (`ValueError`, `RuntimeError`) carry no structured context. When a batch fails, you want to know which batch (`batch_num`) and which products (`row_ids`). When a DB operation fails, you want to know the `operation` type. Custom exceptions let callers catch at the right granularity — an `except PipelineError` at the top catches everything; an `except DatabaseError` catches only DB failures.

### 2.1 `src/utils/exceptions.py`

The hierarchy is:

```
PipelineError(Exception)           ← root — catch-all for domain errors
│
├── ConfigError                    ← config.yaml missing / bad / env var unset
│
├── EmbeddingError                 ← embedding API call failed after retries
│   └── EmbeddingDimensionError    ← returned vector size ≠ configured size
│
├── LLMError                       ← LLM call failed after retries
│   └── LLMResponseParseError      ← response received, but JSON malformed
│
├── VectorStoreError               ← FAISS load/save/search failed
│   └── VectorStoreNotLoadedError  ← search() called before load()
│
├── DatabaseError                  ← DB connection or query failed
│   └── DatabaseNotConnectedError  ← operation before connect()
│
├── WorkflowError                  ← pipeline-level failure
│   └── BatchError                 ← single-batch failure with batch_num + row_ids
│
└── TemplateError                  ← Jinja2 render failed
```

**Rules:**
1. Every class stores its context fields as **public instance attributes** (not just embedded in the message string). This lets callers do `except BatchError as e: log(e.batch_num)`.
2. Every `__init__` calls `super().__init__(message)` so `str(e)` is always readable.
3. Always use `raise NewError(...) from original_exc` when wrapping a caught exception — this preserves the original traceback in `__cause__`.
4. **Do NOT import anything from `src/` in this file.** It must be dependency-free so every other module can import it without circular-import risk.

```python
"""Domain-specific exceptions for gs1-vectoRAG-classifier.

No imports from the rest of src/ — keep this module dependency-free.
"""
from __future__ import annotations


class PipelineError(Exception):
    """Root exception for all domain errors in the pipeline."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message

    def __str__(self) -> str:
        return self.message


class ConfigError(PipelineError):
    """Config file missing, malformed, or ${VAR} env var not set."""

    def __init__(self, message: str, config_path: str = "", key: str = ""):
        super().__init__(message)
        self.config_path = config_path
        self.key = key


class EmbeddingError(PipelineError):
    """Embedding API call failed (after exhausting retries)."""

    def __init__(self, message: str, provider: str = "", batch_index: int | None = None):
        super().__init__(message)
        self.provider = provider
        self.batch_index = batch_index


class EmbeddingDimensionError(EmbeddingError):
    """Returned vector size does not match the configured dimension."""

    def __init__(self, expected: int, actual: int, provider: str = ""):
        message = (
            f"Embedding dimension mismatch: expected {expected}, got {actual}"
            + (f" (provider: {provider})" if provider else "")
        )
        super().__init__(message, provider=provider)
        self.expected = expected
        self.actual = actual


class LLMError(PipelineError):
    """LLM call failed after exhausting all retry attempts."""

    def __init__(self, message: str, deployment: str = "", model: str = "",
                 attempt: int | None = None):
        super().__init__(message)
        self.deployment = deployment
        self.model = model
        self.attempt = attempt


class LLMResponseParseError(LLMError):
    """LLM returned a response but it could not be parsed as valid JSON."""

    def __init__(self, message: str, raw_response: str = "", **kwargs):
        super().__init__(message, **kwargs)
        # Truncate to avoid huge log lines
        self.raw_response = raw_response[:500] if raw_response else ""


class VectorStoreError(PipelineError):
    """FAISS index build/load/search failed."""

    def __init__(self, message: str, index_path: str = ""):
        super().__init__(message)
        self.index_path = index_path


class VectorStoreNotLoadedError(VectorStoreError):
    """search() was called before load()."""

    def __init__(self):
        super().__init__("VectorStore.load() must be called before search.")


class DatabaseError(PipelineError):
    """Database connection or query failed."""

    def __init__(self, message: str, server: str = "", database: str = "",
                 operation: str = ""):
        super().__init__(message)
        self.server = server
        self.database = database
        self.operation = operation


class DatabaseNotConnectedError(DatabaseError):
    """DB operation attempted before connect() was called."""

    def __init__(self):
        super().__init__("DB operation attempted before connect() was called.")


class WorkflowError(PipelineError):
    """Top-level pipeline-stage failure."""


class BatchError(WorkflowError):
    """A single-batch failure inside a workflow loop."""

    def __init__(self, message: str, batch_num: int = 0,
                 row_ids: list | None = None,
                 cause: Exception | None = None):
        super().__init__(message)
        self.batch_num = batch_num
        self.row_ids = row_ids or []
        self.cause = cause


class TemplateError(PipelineError):
    """Jinja2 template render failed."""

    def __init__(self, message: str, template_file: str = ""):
        super().__init__(message)
        self.template_file = template_file
```

See [TESTING_GUIDE.md §Phase 2](TESTING_GUIDE.md#phase-2-tests) for verification steps.

---

## Phase 3 — Logging

**Goal:** Structured logging to a timestamped file (verbose, with source location) and the console (minimal, colored by level). Single `get_logger()` factory for every module.

### Design decisions

**Two handlers, two formats:**
- **Console handler**: minimal, one-line, ANSI-colored by level. Shows only `INFO` and above. Falls back to plain text if stdout is not a TTY.
- **File handler**: verbose with milliseconds and `filename:lineno`. Records `DEBUG` and above. Files are named `{YYYYMMDD_HHMMSS}_{mode_prefix}.log` so each run is separate.

**`setup_logging()` is idempotent:** A module-level `_INITIALIZED` flag ensures a second call is a no-op. This means you can call it at module level in `main.py` and never worry about double-initialization from imports.

**`get_logger(name)`**: Every module calls `get_logger(__name__)` or passes an explicit consistent name (see naming convention below). Returns a `logging.Logger` instance.

### Logger naming convention

```
pipeline.main                    ← main.py
pipeline.workflow.build_vectors  ← workflows/build_vectors.py
pipeline.workflow.embed_rows     ← workflows/embed_rows.py
pipeline.workflow.classify       ← workflows/classify.py
pipeline.services.orchestrator   ← services/orchestrator.py
pipeline.llm.azure_openai        ← services/llm/azure_openai_chat.py
pipeline.embedding.azure_openai  ← services/embedding/azure_openai_embedder.py
pipeline.embedding.huggingface   ← services/embedding/huggingface.py
pipeline.vectorstore.faiss       ← services/vectorstore/faiss_store.py
pipeline.db.azure_sql            ← services/db/azure_sql_connector.py
pipeline.db.postgresql           ← services/db/postgresql.py
pipeline.transforms.candidate_builder
pipeline.transforms.response_parser
pipeline.utils.retry
pipeline.batching
pipeline.factory
pipeline.gs1_parser
```

### 3.1 `src/utils/logging.py`

```python
"""Configure structured logging: colored console + verbose timestamped file handler.

Usage — in main.py (module level, before def main()):
    from src.utils.logging import setup_logging, get_logger
    setup_logging(mode_prefix="classify")
    logger = get_logger("pipeline.main")

Usage — in every other module:
    from src.utils.logging import get_logger
    logger = get_logger("pipeline.services.orchestrator")
"""
from __future__ import annotations
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# ── Double-init guard ─────────────────────────────────────────────────
_INITIALIZED: bool = False

# ── ANSI colour codes ─────────────────────────────────────────────────
_RESET  = "\033[0m"
_GREY   = "\033[90m"
_BLUE   = "\033[34m"
_YELLOW = "\033[33m"
_RED    = "\033[31m"

_NOISY_LOGGERS = [
    "azure.core.pipeline.policies.http_logging_policy",
    "azure.identity",
    "azure.identity._internal.get_token_mixin",
    "openai",
    "httpx",
    "urllib3",
    "requests",
]


class _ColorConsoleFormatter(logging.Formatter):
    """One-line colored formatter for console output.

    Example:
        [•]  2026-03-09 14:30:22  pipeline.workflow.classify      Batch 1/50 started
    """

    _LEVEL_PREFIX = {
        logging.DEBUG:    (_GREY,   "[·]"),
        logging.INFO:     (_BLUE,   "[•]"),
        logging.WARNING:  (_YELLOW, "[⚠]"),
        logging.ERROR:    (_RED,    "[✗]"),
        logging.CRITICAL: (_RED,    "[✗✗]"),
    }
    _USE_COLOR: bool = sys.stdout.isatty()

    def format(self, record: logging.LogRecord) -> str:
        color, prefix = self._LEVEL_PREFIX.get(record.levelno, (_RESET, "[?]"))
        ts = self.formatTime(record, "%Y-%m-%d %H:%M:%S")
        name = record.name[:40]
        msg = record.getMessage()
        if record.exc_info:
            msg += "\n" + self.formatException(record.exc_info)
        if self._USE_COLOR:
            return f"{color}{prefix}{_RESET}  {ts}  {name:<40}  {msg}"
        return f"{prefix}  {ts}  {name:<40}  {msg}"


class _VerboseFileFormatter(logging.Formatter):
    """Verbose formatter for the file handler — milliseconds + source location.

    Example:
        2026-03-09 14:30:22.451 | DEBUG    | pipeline.services.orchestrator     | orchestrator.py:87  | RAG search: ...
    """

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S")
        ms = int(record.msecs)
        level = record.levelname.ljust(8)
        name = record.name[:35].ljust(35)
        location = f"{record.filename}:{record.lineno}"
        msg = record.getMessage()
        if record.exc_info:
            msg += "\n" + self.formatException(record.exc_info)
        return f"{ts}.{ms:03d} | {level} | {name} | {location:<25} | {msg}"


def setup_logging(
    mode_prefix: str = "pipeline",
    level: str = "INFO",
    log_file: str | None = None,
    log_dir: str = "logs",
) -> None:
    """Set up the root logger. Safe to call multiple times — ignores second call.

    Args:
        mode_prefix: Appears in the auto-generated filename (e.g. "classify").
        level:       Console log level (default "INFO"). File always uses DEBUG.
        log_file:    Explicit path override (skips auto-naming).
        log_dir:     Directory for auto-named log files.
    """
    global _INITIALIZED
    if _INITIALIZED:
        return
    _INITIALIZED = True

    # ── Resolve log file path ──────────────────────────────────────
    if log_file:
        log_path = Path(log_file)
    elif lf := os.environ.get("LOG_FILE"):
        log_path = Path(lf)
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        Path(log_dir).mkdir(parents=True, exist_ok=True)
        log_path = Path(log_dir) / f"{ts}_{mode_prefix}.log"

    log_path.parent.mkdir(parents=True, exist_ok=True)

    # ── Console handler ────────────────────────────────────────────
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, level.upper(), logging.INFO))
    console_handler.setFormatter(_ColorConsoleFormatter())

    # ── File handler ───────────────────────────────────────────────
    file_handler = logging.FileHandler(str(log_path), encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(_VerboseFileFormatter())

    # ── Root logger ────────────────────────────────────────────────
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.handlers = [console_handler, file_handler]

    # ── Suppress noisy third-party loggers on console ──────────────
    for name in _NOISY_LOGGERS:
        lib_logger = logging.getLogger(name)
        lib_logger.setLevel(logging.WARNING)
        lib_logger.handlers = [file_handler]
        lib_logger.propagate = False


def get_logger(name: str) -> logging.Logger:
    """Return a logger by name.

    If setup_logging() has not been called yet, calls it with defaults.
    This is a safe fallback for module-level logger instantiation.
    """
    if not _INITIALIZED:
        setup_logging()
    return logging.getLogger(name)
```

**What to log at each level:**

| Level | Use for |
|---|---|
| `DEBUG` | RAG scores, prompt text, token counts, SQL query text, retry attempt |
| `INFO` | Batch start/end, row counts, phase transitions, DB connected, index loaded |
| `WARNING` | Product skipped (no embedding), empty batch, retry triggered |
| `ERROR` | Batch failed (with exc_info=True), DB write failed, LLM exhausted retries |
| `EXCEPTION` | Unexpected top-level failure in `main()` — includes full traceback |

See [TESTING_GUIDE.md §Phase 3](TESTING_GUIDE.md#phase-3-tests) for verification steps.

---

## Phase 4 — Console, Batching & Retry Utilities

**Goal:** Finish the three remaining utility modules: a rich terminal output class (`console.py`), SQL pagination (`batching.py`), and a configurable retry decorator (`retry.py`).

### 4.1 Design — Why separate console from logging?

`logging.py` sends `INFO`-level lines to both the file and the terminal. These are diagnostic lines — they tell you what happened and go into the log file for post-mortem review.

`console.py` handles **visual structure** — the batch boxes with box-drawing characters, progress bars, summary tables, phase headers. These are formatted for a human watching the terminal in real time. They:
- Always appear regardless of `log_level`
- Use formatting (`print()`) that `logging.Formatter` cannot produce cleanly
- Go nowhere except the terminal

**Rule of thumb:** If it needs to end up in the log file → use `logger.*`. If it's visual terminal structure for a human watching live → use `console.*`.

### 4.2 `src/utils/retry.py` — Retry decorator

Wraps `tenacity` in a helper that accepts scalar configuration values.

```python
"""Retry helpers using tenacity, configured from RetryConfig."""
import logging
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)
from src.utils.logging import get_logger

logger = get_logger("pipeline.retry")


def make_retry_decorator(max_attempts: int = 3, backoff_factor: float = 1.5,
                         min_wait: float = 30, max_wait: float = 120,
                         retry_on: tuple = (Exception,)):
    """Create a tenacity retry decorator from config values.

    Args:
        max_attempts: Maximum number of tries (including the first).
        backoff_factor: Multiplier for exponential backoff.
        min_wait: Minimum wait between retries (seconds).
        max_wait: Maximum wait between retries (seconds).
        retry_on: Tuple of exception types that trigger a retry.

    Returns:
        A tenacity @retry decorator.
    """
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=backoff_factor, min=min_wait, max=max_wait),
        retry=retry_if_exception_type(retry_on),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,   # re-raise the original exception after all retries fail
    )
```

**How it is used:** The embedding and LLM providers call `make_retry_decorator(retry_on=(RateLimitError,))` in their `__init__` and wrap their API calls with the resulting decorator. The retry strategy is fully configurable from `config.yaml` (`system.retry.*`).

### 4.3 `src/utils/batching.py` — Generic batch iterators

Contains two primitives — one for in-memory sequences, one for database pagination.

**Critical design note about `DatabaseBatcher`:** The batcher always fetches from `OFFSET 0`. This is intentional. Both `embed-rows` and `classify` use a `WHERE column IS NULL` filter. After a batch is processed, those rows are written back and the target column is no longer `NULL` — so they disappear from subsequent queries automatically. If the offset were advanced by `batch_size` after each page, already-processed rows would be skipped and unprocessed rows at the correct offsets would also be skipped. Fixed offset 0 is the correct pattern here.

```python
"""Generic batch iterators for lists and database cursors."""
from __future__ import annotations
from typing import TypeVar, Iterator, Sequence, TYPE_CHECKING
from src.utils.logging import get_logger

if TYPE_CHECKING:
    import pandas as pd
    from src.services.db.base import DatabaseConnector

T = TypeVar("T")
logger = get_logger("pipeline.batching")


def iter_batches(items: Sequence[T], batch_size: int) -> Iterator[list[T]]:
    """Yield successive batches from a sequence.

    Args:
        items: The full sequence to batch.
        batch_size: Number of items per batch.

    Yields:
        Lists of up to batch_size items.
    """
    for i in range(0, len(items), batch_size):
        yield items[i : i + batch_size]


class DatabaseBatcher:
    """Paginated fetcher: yields one DataFrame batch at a time via OFFSET 0.

    IMPORTANT: Always fetches OFFSET 0. This is correct when the WHERE clause
    filters out already-processed rows (e.g., WHERE target IS NULL). After a
    batch is written back, those rows disappear from the result set, so the
    next OFFSET 0 fetch returns the next unprocessed batch.

    Usage:
        batcher = DatabaseBatcher(db, "SELECT id, name FROM t WHERE x IS NULL", "id", 50)
        for batch_df in batcher:
            process(batch_df)
        print(batcher.total_fetched)
    """

    def __init__(self, db_connector, base_query: str,
                 order_by: str, batch_size: int = 256) -> None:
        self._db = db_connector
        self._base_query = base_query
        self._order_by = order_by
        self._batch_size = batch_size
        self._exhausted = False
        self._total_fetched = 0

    @property
    def total_fetched(self) -> int:
        return self._total_fetched

    @property
    def batch_size(self) -> int:
        return self._batch_size

    def __iter__(self) -> "DatabaseBatcher":
        return self

    def __next__(self) -> "pd.DataFrame":
        if self._exhausted:
            raise StopIteration

        paged_query = (
            f"{self._base_query} ORDER BY {self._order_by} "
            f"OFFSET 0 ROWS FETCH NEXT {self._batch_size} ROWS ONLY"
        )
        logger.info("Fetching batch (batch_size=%d)", self._batch_size)

        batch_df = self._db.fetch_batch(paged_query, batch_size=self._batch_size)

        if batch_df.empty:
            self._exhausted = True
            raise StopIteration

        fetched = len(batch_df)
        self._total_fetched += fetched
        logger.info("Fetched %d rows (total so far: %d)", fetched, self._total_fetched)

        if fetched < self._batch_size:
            self._exhausted = True

        return batch_df

    def count(self) -> int:
        """Run COUNT(*) with the same WHERE clause and return the total."""
        upper = self._base_query.upper()
        from_idx = upper.find("FROM")
        if from_idx == -1:
            raise ValueError(f"Cannot parse FROM clause: {self._base_query}")
        from_clause = self._base_query[from_idx:]
        count_query = f"SELECT COUNT(*) AS cnt {from_clause}"
        count_df = self._db.fetch_batch(count_query, batch_size=1)
        total = int(count_df.iloc[0]["cnt"]) if not count_df.empty else 0
        logger.info("Total rows matching query: %d", total)
        return total
```

**Per-mode batch sizes** — every mode owns its own `batch_size` key in config:

| Mode | Config key | Default |
|---|---|---|
| `build-vectors` | `source.batch_size` | `50` |
| `embed-rows` | `row_embedding.batch_size` | `50` |
| `classify` | `classification.batch_size` | `10` |

`embedding.batch_size` (default 256) controls how many texts the embedding provider packs into a single API call internally — separate concern.

### 4.4 `src/utils/console.py` — Rich terminal output

The `Console` class handles all visual output. The full implementation is large; below is the required structure. Every module imports the module-level singleton:

```python
from src.utils.console import console
```

**`ConsoleConfig` dataclass — read from env vars:**

```python
@dataclass
class ConsoleConfig:
    colors: bool = True
    max_products_shown: int = 3          # CONSOLE_MAX_PRODUCTS
    max_product_name_len: int = 35       # CONSOLE_MAX_PRODUCT_LEN
    verbose: bool = False                # CONSOLE_VERBOSE — shows gs1_* detail methods

    @classmethod
    def from_env(cls) -> "ConsoleConfig":
        # Read CONSOLE_COLORS, CONSOLE_MAX_PRODUCTS, etc. from os.environ
        ...
```

**Required public methods:**

| Method | Visual output |
|---|---|
| `pipeline_start(name, config_path, mode)` | Full-width box with 🚀 and mode info |
| `pipeline_finished(success=True)` | ✅ or ❌ with total elapsed time |
| `classification_start(total_rows, batch_size, batch_count)` | Stats table |
| `batch_start(batch_num, total_batches, row_count, product_names)` | Opens a batch box |
| `batch_result(classified, requested, elapsed_s, category_counts)` | Closes the batch box |
| `progress_bar(current, total, label)` | `[████░░░░]  60/127 (47.2%)` |
| `classification_summary(total, classified, failed, elapsed_s)` | Summary table |
| `start(title, detail)` / `success(title)` / `error(title)` / `warning(title)` / `info(title)` | Phase indicators |
| `step(message, done=False)` | `└─ message [✓]` |
| `interrupted()` | Interrupted message |

**Verbose-only methods** (shown when `CONSOLE_VERBOSE=1`):
- `gs1_rag_details(rag_hits)` — top RAG scores
- `gs1_candidates(candidates)` — lettered candidate list
- `gs1_prompt(prompt_text)` — full prompt text
- `gs1_tokens(prompt, completion, total)` — token counts
- `gs1_db_write(updates)` — rows written
- `gs1_timing(rag_s, llm_s, db_s, total_s)` — timing breakdown

**Unicode fallback:** At module load time, try to encode `"└─✓❌⚠️🚀"` with `sys.stdout.encoding`. If it fails, set `_UNICODE = False` and use ASCII replacements throughout (`└─` → `\-`, `✓` → `OK`, etc.).

**All output goes through `_print()`:**
```python
def _print(self, *args, **kwargs):
    try:
        print(*args, **kwargs, flush=True)
    except UnicodeEncodeError:
        safe = " ".join(str(a) for a in args).encode(
            sys.stdout.encoding, errors="replace"
        ).decode(sys.stdout.encoding)
        print(safe, flush=True)
```

**Module-level singleton (last line of the file):**
```python
console = Console(ConsoleConfig.from_env())
```

See [TESTING_GUIDE.md §Phase 4](TESTING_GUIDE.md#phase-4-tests) for verification steps.

---

## Phase 5 — Template Utility

**Goal:** Build the Jinja2 template renderer that is used by the orchestrator to construct LLM prompts.

**Why in `utils/`?** Template rendering is a pure function (`str → str`) that depends only on `jinja2`. It belongs with the other pure utilities, not inside the classifier or orchestrator. This also makes it trivially unit-testable.

### 5.1 `src/utils/templates.py`

The design uses a **hybrid approach**: templates are normally loaded from `.j2` files specified in `config.yaml`. If the path is `null` or the file doesn't exist, the renderer falls back to hardcoded template strings. This means the pipeline never crashes just because the template files are missing or misnamed.

```python
"""Load and render Jinja2 prompt templates."""
from __future__ import annotations
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, BaseLoader
from jinja2 import TemplateError as JinjaTemplateError
from src.utils.logging import get_logger
from src.utils.exceptions import TemplateError

logger = get_logger("pipeline.utils.templates")

# ── Hardcoded fallback templates ──────────────────────────────────────
# Used when config sets template paths to null, or the file is missing.
FALLBACK_SYSTEM = (
    "You are a product classification assistant. Classify grocery/retail products "
    "using the GS1 GPC standard. Respond with JSON: "
    '{"results": [{"product_id": <id>, "choice": "<letter>"}]}'
)

FALLBACK_CLASSIFICATION = (
    "Classify these products into GS1 GPC categories.\n\n"
    "{% for product in products %}"
    "--- Product {{ product.product_id }} ---\n"
    "{{ product.context | tojson }}\n\n"
    "Candidates:\n"
    "{% for c in product.candidates %}"
    "[{{ c.letter }}] {{ c.hierarchy_string }}\n"
    "{% endfor %}\n"
    "{% endfor %}\n"
    '{"results": [{"product_id": <id>, "choice": "<letter>"}]}'
)


def render_template(template_path: str | None, fallback: str, **kwargs) -> str:
    """Load a Jinja2 template from file, or use the fallback string.

    Args:
        template_path: Path to the .j2 file (None or missing → use fallback).
        fallback: Jinja2 template string used when the file is unavailable.
        **kwargs: Variables passed to the template context.

    Returns:
        Rendered string.

    Raises:
        TemplateError: If the template renders with a Jinja2 error.
    """
    if template_path and Path(template_path).exists():
        template_dir = str(Path(template_path).parent)
        template_name = Path(template_path).name
        env = Environment(loader=FileSystemLoader(template_dir))
        template = env.get_template(template_name)
        logger.debug("Using template file: %s", template_path)
    else:
        if template_path:
            logger.warning("Template file not found: %s — using fallback", template_path)
        env = Environment(loader=BaseLoader())
        template = env.from_string(fallback)

    try:
        return template.render(**kwargs)
    except JinjaTemplateError as exc:
        raise TemplateError(
            f"Template render failed: {exc}",
            template_file=template_path or "<inline fallback>",
        ) from exc
```

See [TESTING_GUIDE.md §Phase 5](TESTING_GUIDE.md#phase-5-tests) for verification steps.

---

## Phase 6 — Interfaces (Abstract Base Classes) & Document DTO

**Goal:** Define the 4 swappable interfaces and the `Document` data structure. No implementations yet — only contracts.

**Why interfaces first?** The concrete implementations (Azure OpenAI, FAISS, etc.) are written in later phases. If workflows and the orchestrator are written against the interface types, you can swap any concrete class without touching any other code. The `ComponentFactory` maps config type strings to concrete classes; the workflows never know which concrete class they're using.

### 6.1 `src/dto.py` — Document dataclass

`Document` is the single data unit that flows from the `GS1Parser`, through the `EmbeddingProvider`, into the `FAISSVectorStore`. It carries an ID, embedding text, rich metadata, and eventually the float vector.

```python
"""Document DTO — the data unit passed between pipeline stages.

Carries one taxonomy node (e.g., a GS1 GPC entry) from GS1Parser
through EmbeddingProvider to FAISSVectorStore.
"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class Document:
    """A single document for embedding and indexing.

    Attributes:
        id: Unique identifier (e.g., GS1 code "10000000").
        text: The text to embed — hierarchy path + definition + excludes.
        metadata: Arbitrary dict (level, code, title, hierarchy_path, etc.).
        embedding: Float vector. None until embedded by EmbeddingProvider.
    """
    id: str
    text: str
    metadata: dict = field(default_factory=dict)
    embedding: list[float] | None = None
```

**Location:** `src/dto.py` (top level of `src/`, not in a subdirectory). Named `dto.py` because it's a Data Transfer Object shared across all pipeline stages.

### 6.2 `src/services/embedding/base.py` — EmbeddingProvider ABC

```python
"""Abstract base class for embedding providers."""
from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    """Interface for generating vector embeddings from text."""

    @abstractmethod
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of text strings into vectors.

        Args:
            texts: List of strings to embed.

        Returns:
            List of embedding vectors in the same order as input.
        """
        ...

    @property
    @abstractmethod
    def dimensions(self) -> int:
        """Return the dimensionality of each embedding vector."""
        ...
```

### 6.3 `src/services/vectorstore/base.py` — VectorStore ABC

```python
"""Abstract base class for vector stores."""
from __future__ import annotations
from abc import ABC, abstractmethod
from src.dto import Document


class VectorStore(ABC):
    """Interface for vector index storage and retrieval."""

    @abstractmethod
    def save(self, documents: list[Document], output_dir: str, prefix: str) -> None:
        """Build the index from documents and persist all artefacts to disk."""
        ...

    @abstractmethod
    def load(self) -> None:
        """Load a previously saved index + lookup from disk."""
        ...

    @abstractmethod
    def search(self, query_vector: list[float], top_k: int = 30) -> list[dict]:
        """Search the index for nearest neighbors.

        Returns:
            List of dicts, each with keys: 'id', 'score', 'metadata'.
        """
        ...
```

### 6.4 `src/services/llm/base.py` — LLMProvider ABC

```python
"""Abstract base class for LLM providers."""
from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """Interface for LLM chat completion calls."""

    @abstractmethod
    def chat(self, system_message: str, user_message: str,
             response_format: dict | None = None) -> dict:
        """Send a chat completion request.

        Args:
            system_message: The system prompt.
            user_message: The user prompt.
            response_format: e.g., {"type": "json_object"}.

        Returns:
            Dict with 'content' (str) and 'usage' (dict with token counts).
        """
        ...
```

### 6.5 `src/services/db/base.py` — DatabaseConnector ABC

```python
"""Abstract base class for database connectors (thin repository pattern)."""
from abc import ABC, abstractmethod
import pandas as pd


class DatabaseConnector(ABC):
    """Interface for database operations. SQL is hidden inside implementations."""

    @abstractmethod
    def connect(self) -> None:
        """Establish connection. Raises DatabaseError on failure."""
        ...

    @abstractmethod
    def disconnect(self) -> None:
        """Close the connection and free resources."""
        ...

    @abstractmethod
    def fetch_batch(self, query: str, params: dict | None = None,
                    batch_size: int = 256) -> pd.DataFrame:
        """Run a SELECT query and return results as a DataFrame.

        Raises:
            DatabaseNotConnectedError: If called before connect().
        """
        ...

    @abstractmethod
    def update_rows(self, table: str, updates: list[dict],
                    key_column: str = "id") -> int:
        """Update rows in `table`. Each dict has key_column + columns to update.

        Returns:
            Number of rows updated.

        Raises:
            DatabaseNotConnectedError: If called before connect().
        """
        ...

    @abstractmethod
    def execute(self, query: str, params: dict | None = None) -> None:
        """Execute a non-SELECT statement (INSERT, UPDATE, CREATE, etc.)."""
        ...
```

See [TESTING_GUIDE.md §Phase 6](TESTING_GUIDE.md#phase-6-tests) for verification steps.

---

## Phase 7 — Component Factory

**Goal:** Build the registry that maps config type strings (e.g. `"azure_openai"`) to concrete classes. This is the only place in the codebase where concrete class names appear in lookup tables.

**How it works:**
1. `ComponentFactory` holds four dicts mapping type names to classes.
2. `register_*(name, cls)` adds a class to a registry.
3. `create_*(type_name, **kwargs)` looks up the class, instantiates it with `**kwargs`, and returns the object.
4. `build_default_factory()` pre-registers all built-in implementations.

**To add a new provider:** Write the class (must implement the ABC), add one `register_*` line to `build_default_factory()`, and set the matching `type:` in `config.yaml`. Zero other changes needed.

### 7.1 `src/factory.py`

```python
"""ComponentFactory — registry mapping config type strings to concrete classes."""
from __future__ import annotations
from src.utils.logging import get_logger
from src.utils.exceptions import PipelineError

logger = get_logger("pipeline.factory")


class ComponentFactory:
    """Central registry for all swappable component implementations."""

    def __init__(self):
        self._embedding_registry: dict[str, type] = {}
        self._vectorstore_registry: dict[str, type] = {}
        self._llm_registry: dict[str, type] = {}
        self._db_registry: dict[str, type] = {}

    # ── Registration ───────────────────────────────────────────────

    def register_embedding(self, type_name: str, cls: type) -> None:
        logger.debug("Registered embedding provider: %s", type_name)
        self._embedding_registry[type_name] = cls

    def register_vectorstore(self, type_name: str, cls: type) -> None:
        logger.debug("Registered vector store: %s", type_name)
        self._vectorstore_registry[type_name] = cls

    def register_llm(self, type_name: str, cls: type) -> None:
        logger.debug("Registered LLM provider: %s", type_name)
        self._llm_registry[type_name] = cls

    def register_db(self, type_name: str, cls: type) -> None:
        logger.debug("Registered database connector: %s", type_name)
        self._db_registry[type_name] = cls

    # ── Creation ───────────────────────────────────────────────────

    def create_embedding(self, type_name: str, **kwargs):
        return self._create(self._embedding_registry, "embedding", type_name, **kwargs)

    def create_vectorstore(self, type_name: str, **kwargs):
        return self._create(self._vectorstore_registry, "vector store", type_name, **kwargs)

    def create_llm(self, type_name: str, **kwargs):
        return self._create(self._llm_registry, "LLM", type_name, **kwargs)

    def create_db(self, type_name: str, **kwargs):
        return self._create(self._db_registry, "database", type_name, **kwargs)

    def _create(self, registry: dict, category: str, type_name: str, **kwargs):
        cls = registry.get(type_name)
        if cls is None:
            available = ", ".join(registry.keys()) or "(none registered)"
            raise PipelineError(
                f"Unknown {category} type: '{type_name}'. "
                f"Available: {available}"
            )
        logger.info("Creating %s: %s", category, type_name)
        return cls(**kwargs)


def build_default_factory() -> ComponentFactory:
    """Build a factory pre-loaded with all built-in implementations.

    Import all concrete classes here and register them. This function
    is the only place in the codebase that references concrete class names
    directly. To add a new provider: import it and add one register line.
    """
    factory = ComponentFactory()

    # ── Embedding providers ─────────────────────────────────────────
    from src.services.embedding.azure_openai_embedder import AzureOpenAIEmbeddingProvider
    from src.services.embedding.huggingface import HuggingFaceEmbeddingProvider
    factory.register_embedding("azure_openai", AzureOpenAIEmbeddingProvider)
    factory.register_embedding("huggingface", HuggingFaceEmbeddingProvider)

    # ── Vector stores ───────────────────────────────────────────────
    from src.services.vectorstore.faiss_store import FAISSVectorStore
    factory.register_vectorstore("faiss", FAISSVectorStore)

    # ── LLM providers ───────────────────────────────────────────────
    from src.services.llm.azure_openai_chat import AzureOpenAILLMProvider
    factory.register_llm("azure_openai", AzureOpenAILLMProvider)

    # ── Database connectors ─────────────────────────────────────────
    from src.services.db.azure_sql_connector import AzureSQLConnector
    from src.services.db.postgresql import PostgreSQLConnector
    factory.register_db("azure_sql", AzureSQLConnector)
    factory.register_db("postgresql", PostgreSQLConnector)

    return factory
```

**Note:** The entry points (`main.py`, `vectorize.py`) do NOT call `build_default_factory()`. Instead, they build a minimal factory with only the providers their mode needs. This avoids importing all heavy dependencies (sentence-transformers, FAISS etc.) when they're not needed. The important thing is that `build_default_factory()` exists for testing and as a reference.

See [TESTING_GUIDE.md §Phase 7](TESTING_GUIDE.md#phase-7-tests) for verification steps.

---

## Phase 8 — GS1 Parser

**Goal:** Write the `GS1Parser` class that reads `data/input/GS1.json` and produces a flat `list[Document]`.

**Why a dedicated parser?** The GS1 GPC JSON has a specific recursive tree structure. Isolating the parsing logic into one class means the rest of the pipeline is taxonomy-format-agnostic. If a different taxonomy format is used in the future, only this class needs to change.

**About the GS1 GPC structure:**
The JSON has a top-level `"Schema"` key containing a list of nodes. Each node has:
- `Code`, `Title`, `Level` (1–6), `Definition`, `DefinitionExcludes`, `Active`, `Childs` (list of child nodes)

Level names: 1=Segment, 2=Family, 3=Class, 4=Brick, 5=Attribute, 6=AttributeValue.

The parser traverses recursively and emits **one `Document` per node**, carrying the full hierarchy path from root to that node.

**Text format** (used as embedding input):
```
Segment > Family > Class > Brick | Definition text | Excludes: ...
```
- Parts are separated by ` | `
- If there is no definition, the separator is omitted
- Excludes are prefixed with `Excludes: ` and only included if non-empty

### 8.1 `src/services/gs1_parser.py`

```python
"""GS1 GPC JSON parser — flattens the hierarchical taxonomy into Documents."""
from __future__ import annotations
import json
from pathlib import Path
from src.dto import Document
from src.utils.logging import get_logger

logger = get_logger("pipeline.gs1_parser")

LEVEL_NAMES = {1: "Segment", 2: "Family", 3: "Class",
               4: "Brick", 5: "Attribute", 6: "AttributeValue"}


class GS1Parser:
    """Parse a GS1 GPC JSON file into a flat list of Documents.

    Each node in the tree becomes one Document with:
      - id: the GS1 code
      - text: hierarchy path joined with " > ", then " | definition",
              then " | Excludes: ..." (if present)
      - metadata: level, code, title, hierarchy_path (list), hierarchy_string,
                  definition, excludes, active, source
    """

    def __init__(self, file_path: str, encoding: str = "utf-8"):
        self.file_path = Path(file_path)
        self.encoding = encoding

    def parse(self) -> list[Document]:
        """Parse the JSON file and return a flat list of Documents.

        Raises:
            FileNotFoundError: If the JSON file does not exist.
            KeyError: If the expected 'Schema' key is missing.
        """
        if not self.file_path.exists():
            raise FileNotFoundError(f"GS1 JSON not found: {self.file_path}")

        logger.info("Parsing GS1 JSON: %s", self.file_path)
        with open(self.file_path, "r", encoding=self.encoding) as f:
            raw = json.load(f)

        schema = raw.get("Schema")
        if schema is None:
            raise KeyError("GS1 JSON missing top-level 'Schema' key")

        documents: list[Document] = []
        nodes = schema if isinstance(schema, list) else [schema]
        for node in nodes:
            self._traverse(node, hierarchy_path=[], documents=documents)

        logger.info("Parsed %d documents from GS1 JSON", len(documents))
        return documents

    def _traverse(self, node: dict, hierarchy_path: list[str],
                  documents: list[Document]) -> None:
        """Recursively walk the tree and emit a Document for each node."""
        code = str(node.get("Code", ""))
        title = node.get("Title", "").strip()
        level = node.get("Level", 0)
        definition = (node.get("Definition") or "").strip()
        excludes = (node.get("DefinitionExcludes") or "").strip()
        active = node.get("Active", True)

        current_path = hierarchy_path + [title]
        hierarchy_string = " > ".join(current_path)

        # Build embedding text
        text_parts = [hierarchy_string]
        if definition:
            text_parts.append(definition)
        if excludes:
            text_parts.append(f"Excludes: {excludes}")
        text = " | ".join(text_parts)

        doc = Document(
            id=code,
            text=text,
            metadata={
                "source": str(self.file_path),
                "level": level,
                "code": code,
                "title": title,
                "hierarchy_path": current_path,
                "hierarchy_string": hierarchy_string,
                "definition": definition,
                "excludes": excludes,
                "active": active,
            }
        )
        documents.append(doc)

        for child in node.get("Childs", []):
            self._traverse(child, current_path, documents)
```

### 8.2 `tests/fixtures/gs1_sample.json` — Test fixture

Create a minimal GS1 JSON fixture for unit tests. It should contain:
- 1 Segment (Level 1)
- 1 Family (Level 2)
- 1 Class (Level 3)
- 3 Brick nodes (Level 4) — enough to test deduplication in candidate building
- Several Attribute and AttributeValue nodes (Level 5-6)

The fixture should test the text format (with definition, without definition, with excludes). Build it as a real but small subset of the GS1 GPC hierarchy.

See [TESTING_GUIDE.md §Phase 8](TESTING_GUIDE.md#phase-8-tests) for verification steps.

---

## Phase 9 — Embedding Providers

**Goal:** Implement both fully working embedding providers. The Azure OpenAI provider is the primary one; HuggingFace is the local fallback.

**Critical constraint:** Whatever provider you use for `build-vectors`, you MUST use the same provider, the same model, and the same `dimensions` setting when you run `embed-rows`. The FAISS index and the DB row embeddings must be vectors from the **same model**. RAG similarity search compares DB product embeddings against FAISS taxonomy embeddings — they must be in the same metric space.

### 9.1 `src/services/embedding/azure_openai_embedder.py`

Calls Azure OpenAI `text-embedding-3-large` (configurable deployment). Uses `ThreadPoolExecutor` for parallel sub-batch calls.

```python
"""Azure OpenAI embedding provider using the openai Python SDK."""
from __future__ import annotations
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from openai import AzureOpenAI, RateLimitError
from src.services.embedding.base import EmbeddingProvider
from src.utils.retry import make_retry_decorator
from src.utils.batching import iter_batches
from src.utils.logging import get_logger

logger = get_logger("pipeline.embedding.azure_openai")


class AzureOpenAIEmbeddingProvider(EmbeddingProvider):
    """Embed text using Azure OpenAI (e.g., text-embedding-3-large).

    Args:
        api_key: Azure OpenAI API key.
        endpoint: Azure OpenAI endpoint URL.
        deployment: Deployment name (e.g., "text-embedding-3-large").
        api_version: API version string.
        dimensions: Embedding dimensions (default 1024).
        batch_size: Texts per API call (default 256).
        max_workers: Parallel threads for batched calls (default 5).
        max_attempts / backoff_factor / min_wait / max_wait: Retry config.
    """

    def __init__(self, api_key: str, endpoint: str, deployment: str,
                 api_version: str, dimensions: int = 1024,
                 batch_size: int = 256, max_workers: int = 5,
                 max_attempts: int = 3, backoff_factor: float = 1.5,
                 min_wait: float = 30, max_wait: float = 120,
                 **kwargs):
        self._dimensions = dimensions
        self._batch_size = batch_size
        self._max_workers = max_workers
        self._deployment = deployment

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

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed texts using parallel batched API calls.

        Internally splits 'texts' into sub-batches of self._batch_size,
        submits all sub-batches in parallel via ThreadPoolExecutor,
        and reassembles results in order.
        """
        if not texts:
            return []

        all_embeddings: list[tuple[int, list[float]]] = []
        sub_batches = list(iter_batches(texts, self._batch_size))
        logger.info("Embedding %d texts in %d sub-batches (%d workers)",
                    len(texts), len(sub_batches), self._max_workers)

        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            futures = {}
            for idx, batch in enumerate(sub_batches):
                future = executor.submit(self._embed_one_batch, batch, idx)
                futures[future] = idx

            for future in as_completed(futures):
                batch_idx = futures[future]
                vectors = future.result()   # raises if _embed_one_batch raised
                offset = batch_idx * self._batch_size
                for i, vec in enumerate(vectors):
                    all_embeddings.append((offset + i, vec))

        all_embeddings.sort(key=lambda x: x[0])
        return [vec for _, vec in all_embeddings]

    def _embed_one_batch(self, texts: list[str], batch_idx: int) -> list[list[float]]:
        """Embed a single sub-batch with retries."""
        @self._retry
        def _call():
            response = self._client.embeddings.create(
                model=self._deployment,
                input=texts,
                dimensions=self._dimensions,
            )
            return [item.embedding for item in response.data]
        return _call()
```

### 9.2 `src/services/embedding/huggingface.py`

Runs a `sentence-transformers` model locally. No API calls, no retry needed.

```python
"""HuggingFace local embedding provider using sentence-transformers."""
from __future__ import annotations
from src.services.embedding.base import EmbeddingProvider
from src.utils.logging import get_logger

logger = get_logger("pipeline.embedding.huggingface")


class HuggingFaceEmbeddingProvider(EmbeddingProvider):
    """Embed text using a local sentence-transformers model.

    Args:
        model_name: HuggingFace model ID (default "all-MiniLM-L6-v2").
        dimensions: Expected dimensions (used for validation; model determines actual).
        **kwargs: Ignored — accepts extra kwargs for factory compatibility.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2",
                 dimensions: int = 384, **kwargs):
        self._model_name = model_name
        self._dimensions = dimensions
        self._model = None  # lazy-loaded on first embed call

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def _get_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            logger.info("Loading HuggingFace model: %s", self._model_name)
            self._model = SentenceTransformer(self._model_name)
        return self._model

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed texts locally. Downloads model on first call."""
        if not texts:
            return []
        model = self._get_model()
        embeddings = model.encode(texts, convert_to_numpy=True)
        return embeddings.tolist()
```

### 9.3 Scaffolded embedding providers

Create stub files (methods raise `NotImplementedError`) so the import structure is complete. These are documented in [SWAPPABLE_PARTS.md](explanations/SWAPPABLE_PARTS.md).

- `src/services/embedding/openai_embedder.py` — `OpenAIEmbeddingProvider`
- `src/services/embedding/ollama_embedder.py` — `OllamaEmbeddingProvider`
- `src/services/embedding/cohere_embedder.py` — `CohereEmbeddingProvider`

Each scaffold follows this pattern:
```python
class OpenAIEmbeddingProvider(EmbeddingProvider):
    def __init__(self, **kwargs): raise NotImplementedError("OpenAI embedder not yet implemented")
    def embed_batch(self, texts): raise NotImplementedError
    @property
    def dimensions(self): raise NotImplementedError
```

See [TESTING_GUIDE.md §Phase 9](TESTING_GUIDE.md#phase-9-tests) for verification steps.

---

## Phase 10 — FAISS Vector Store

**Goal:** Implement `FAISSVectorStore` — the full system that builds, saves, loads, and searches the FAISS index.

The vector store is not just a FAISS index. It is a **system** that encompasses:
1. **Indexer:** Builds a FAISS `IndexFlatL2` from L2-normalised document embeddings. Scores are squared L2 distances in [0, 4] for unit vectors — lower = more similar.
2. **Artefact writer:** Saves 5 files on build; loads 2 of them (index + lookup) at query time.
3. **Search interface:** Takes a query vector, L2-normalises it, and returns metadata-enriched results.

**The 5 artefacts produced by `save()`:**

| File | Contents | Used at |
|---|---|---|
| `faiss_{prefix}.index` | FAISS index binary | Query time: vector search |
| `faiss_{prefix}_metadata.json` | `{ids: [...], metadata: [...]}` | Debug/inspection |
| `embeddings_{prefix}.parquet` | Full document archive (id, text, embedding, metadata) | Re-indexing |
| `{prefix}_lookup.pkl` | `{int_id: {metadata subset}}` | Query time: metadata lookup |
| `build_manifest.json` | timestamp, model, dims, doc count | Query time: audit |

**Why the lookup pickle?** At query time, FAISS returns integer indices (positions in the index). The lookup maps `int(index_position) → metadata dict`. It contains only the fields listed in `config.yaml` under `vector_store.lookup_metadata_fields`, keeping it compact and fast to load.

Vectors are L2-normalised in-place at build time for consistent magnitude. The index type is always `IndexFlatL2` (squared L2 distance on unit vectors). Scores are in `[0, 4]`, lower = more similar. Query vectors are also L2-normalised before search.

### 10.1 `src/services/vectorstore/faiss_store.py` — Key implementation points

```python
"""FAISS vector store: build, save, load, and search."""
from __future__ import annotations
import json, pickle
from datetime import datetime, timezone
from pathlib import Path
import faiss, numpy as np, pandas as pd
import pyarrow as pa, pyarrow.parquet as pq
from src.dto import Document
from src.services.vectorstore.base import VectorStore
from src.utils.logging import get_logger
from src.utils.exceptions import VectorStoreError, VectorStoreNotLoadedError

logger = get_logger("pipeline.vectorstore.faiss")


class FAISSVectorStore(VectorStore):
    """FAISS-based vector store: 5-artefact save / selective load / L2 distance search.

    Args:
        output_dir: Directory for artefact files.
        filename_prefix: Prefix for all artefact filenames.
        lookup_metadata_fields: Which metadata keys to include in the lookup pickle.
        embedding_dimensions: Vector dimensionality.
        embedding_model: Model name for the manifest.
    """

    def __init__(self, output_dir: str = "data/vector_store",
                 filename_prefix: str = "gs1",
                 lookup_metadata_fields: list[str] | None = None,
                 embedding_dimensions: int = 1024,
                 embedding_model: str = "unknown",
                 **kwargs):
        self._output_dir = Path(output_dir)
        self._prefix = filename_prefix
        self._lookup_fields = lookup_metadata_fields or [
            "level", "code", "title", "hierarchy_path", "hierarchy_string"
        ]
        self._dimensions = embedding_dimensions
        self._model_name = embedding_model

        self._index = None
        self._lookup: dict[int, dict] = {}
        self._ids: list[str] = []
        self._metadata: list[dict] = []

    def save(self, documents: list[Document],
             output_dir: str | None = None,
             prefix: str | None = None) -> None:
        """Build index and write all 5 artefacts."""
        out = Path(output_dir) if output_dir else self._output_dir
        pfx = prefix or self._prefix
        out.mkdir(parents=True, exist_ok=True)

        vecs = np.array([doc.embedding for doc in documents], dtype="float32")

        # Build IndexFlatL2: L2-normalise vectors in-place for consistent magnitude
        faiss.normalize_L2(vecs)                   # normalize in-place
        index = faiss.IndexFlatL2(vecs.shape[1])   # squared L2 distance on unit vectors

        index.add(vecs)
        self._index = index

        # 1. Binary index
        index_path = out / f"faiss_{pfx}.index"
        faiss.write_index(index, str(index_path))

        # 2. Metadata JSON (full)
        ids = [doc.id for doc in documents]
        meta_path = out / f"faiss_{pfx}_metadata.json"
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump({"ids": ids, "metadata": [doc.metadata for doc in documents]}, f)

        # 3. Parquet archive
        parquet_path = out / f"embeddings_{pfx}.parquet"
        table = pa.table({
            "id": ids,
            "text": [doc.text for doc in documents],
            "embedding": [doc.embedding for doc in documents],
            "metadata": [json.dumps(doc.metadata) for doc in documents],
        })
        pq.write_table(table, str(parquet_path))

        # 4. Compact lookup pickle  {int(position): {selected fields}}
        self._ids = ids
        self._metadata = [doc.metadata for doc in documents]
        self._lookup = {}
        for i, meta in enumerate(self._metadata):
            self._lookup[i] = {k: meta.get(k) for k in self._lookup_fields}
        lookup_path = out / f"{pfx}_lookup.pkl"
        with open(lookup_path, "wb") as f:
            pickle.dump(self._lookup, f)

        # 5. Build manifest
        manifest = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "model": self._model_name,
            "dimensions": self._dimensions,
            "doc_count": len(documents),
            "index_type": "FlatL2",
        }
        manifest_path = out / "build_manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        logger.info("Saved %d documents to %s", len(documents), out)

    def load(self) -> None:
        """Load the FAISS index and lookup pickle from disk.

        Raises:
            VectorStoreError: If required files are not found.
        """
        out = self._output_dir
        pfx = self._prefix

        manifest_path = out / "build_manifest.json"
        if manifest_path.exists():
            with open(manifest_path) as f:
                manifest = json.load(f)
            logger.info("Loaded manifest: docs=%d", manifest.get("doc_count", -1))

        index_path = out / f"faiss_{pfx}.index"
        if not index_path.exists():
            raise VectorStoreError(
                f"FAISS index not found: {index_path}. "
                "Run 'python vectorize.py build-vectors' first.",
                index_path=str(index_path),
            )
        self._index = faiss.read_index(str(index_path))
        logger.info("Loaded FAISS index: %d vectors", self._index.ntotal)

        lookup_path = out / f"{pfx}_lookup.pkl"
        if not lookup_path.exists():
            raise VectorStoreError(
                f"Lookup pickle not found: {lookup_path}.",
                index_path=str(lookup_path),
            )
        with open(lookup_path, "rb") as f:
            self._lookup = pickle.load(f)
        logger.info("Loaded lookup: %d entries", len(self._lookup))

    def search(self, query_vector: list[float], top_k: int = 30) -> list[dict]:
        """Search for nearest neighbors.

        Returns:
            List of dicts with 'id', 'score', 'metadata'.

        Raises:
            VectorStoreNotLoadedError: If load() was not called.
        """
        if self._index is None:
            raise VectorStoreNotLoadedError()

        q = np.array([query_vector], dtype="float32")
        faiss.normalize_L2(q)    # L2-normalise query for consistent magnitude

        scores, indices = self._index.search(q, top_k)

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0:  # FAISS returns -1 for "no result"
                continue
            meta = self._lookup.get(int(idx), {})
            results.append({
                "id": meta.get("code", str(idx)),
                "score": float(score),
                "metadata": meta,
            })
        return results
```

### 10.2 Scaffolded vector store providers

- `src/services/vectorstore/chromadb_store.py` — `ChromaDBVectorStore`
- `src/services/vectorstore/azure_ai_search_store.py` — `AzureAISearchVectorStore`

Each raises `NotImplementedError`. Documented in [SWAPPABLE_PARTS.md](explanations/SWAPPABLE_PARTS.md).

See [TESTING_GUIDE.md §Phase 10](TESTING_GUIDE.md#phase-10-tests) for verification steps.

---

*Continue to [BUILD_GUIDE_PART_2.md](BUILD_GUIDE_PART_2.md) for Phases 11–17: build-vectors workflow, database connectors, embed-rows, LLM providers, transforms, orchestrator, classify workflow, and entry points.*
