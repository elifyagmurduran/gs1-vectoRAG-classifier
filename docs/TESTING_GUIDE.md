# Testing Guide

This guide contains all verification steps for the project. Every "VERIFY THIS STEP" item from the Build Guide belongs here. Tests progress from smoke checks against real services (with secrets) through unit tests that run offline with no external dependencies.

Before running anything, activate the virtual environment and install all dependencies:
```powershell
.\.venv\Scripts\activate
pip install -r requirements.txt
```

---

## Table of Contents

- [Environment Checklist](#environment-checklist)
- [Phase 0–1 Tests — Config + Env](#phase-01-tests--config--env)
- [Phase 2 Tests — Exceptions](#phase-2-tests--exceptions)
- [Phase 3 Tests — Logging](#phase-3-tests--logging)
- [Phase 4 Tests — Console + Batching + Retry](#phase-4-tests--console--batching--retry)
- [Phase 5 Tests — Templates](#phase-5-tests--templates)
- [Phase 6 Tests — Interfaces + Document DTO](#phase-6-tests--interfaces--document-dto)
- [Phase 7 Tests — Factory](#phase-7-tests--factory)
- [Phase 8 Tests — GS1 Parser](#phase-8-tests--gs1-parser)
- [Phase 9 Tests — Embedding Providers](#phase-9-tests--embedding-providers)
- [Phase 10 Tests — FAISS Vector Store](#phase-10-tests--faiss-vector-store)
- [Phase 11 Tests — build-vectors Workflow](#phase-11-tests--build-vectors-workflow)
- [Phase 12 Tests — Database Connectors](#phase-12-tests--database-connectors)
- [Phase 13 Tests — embed-rows Workflow](#phase-13-tests--embed-rows-workflow)
- [Phase 14 Tests — LLM Providers](#phase-14-tests--llm-providers)
- [Phase 15 Tests — CandidateBuilder + ResponseParser](#phase-15-tests--candidatebuilder--responseparser)
- [Phase 16 Tests — Prompt Templates](#phase-16-tests--prompt-templates)
- [Phase 17 Tests — Orchestrator](#phase-17-tests--orchestrator)
- [Phase 18 Tests — Full Pipeline (End-to-End)](#phase-18-tests--full-pipeline-end-to-end)
- [Offline Unit Test Suite](#offline-unit-test-suite)
- [Smoke Test Suite](#smoke-test-suite)
- [Common Failure Patterns](#common-failure-patterns)

---

## Environment Checklist

Before any test that touches an external service, confirm:

```powershell
# .env is present and populated
Get-Content .env | Select-String -Pattern "AZURE|PG_"

# Secrets that must be set:
# AZURE_OPENAI_API_KEY
# AZURE_OPENAI_ENDPOINT
# AZURE_OPENAI_API_VERSION
# AZURE_OPENAI_EMBEDDING_DEPLOYMENT
# AZURE_OPENAI_CHAT_DEPLOYMENT
# AZURE_SQL_SERVER (or PG_HOST etc. — depending on config.yaml)
# AZURE_SQL_DATABASE
# AZURE_SQL_CLIENT_ID
# AZURE_SQL_CLIENT_SECRET

# config.yaml is valid
python -c "from src.config.models import load_config; c = load_config(); print('Config OK:', c.pipeline.name)"
```

---

## Phase 0–1 Tests — Config + Env

### Config loads without error

```python
from src.config.models import load_config
config = load_config()          # uses config.yaml by default
print(config.pipeline.name)    # e.g. "gs1-vectoRAG-classifier"
print(config.source.path)      # e.g. "data/input/GS1.json"
print(config.source.batch_size)                # required field — must not be None
print(config.row_embedding.batch_size)         # required field — must not be None
print(config.classification.batch_size)        # required field — must not be None
```

All three `batch_size` fields are **required** — Pydantic raises `ValidationError` if any is missing from `config.yaml`.

### ConfigError is raised for missing file

```python
from src.config.models import load_config
from src.utils.exceptions import ConfigError
try:
    load_config("nonexistent.yaml")
except ConfigError as e:
    print("ConfigError raised correctly:", e)
```

### Env var loading

```python
from src.utils.env import get_env
val = get_env("AZURE_OPENAI_API_KEY")
print("Key length:", len(val))   # should be > 0
```

`get_env()` reads from `.env` automatically. If the var is missing, it raises `EnvVarNotFoundError` — not `KeyError`.

### Env var validation in config

Set a required env var to empty in `.env`, then call `load_config()`. You should get a meaningful error message from Pydantic, not a bare `KeyError`.

---

## Phase 2 Tests — Exceptions

### Exception hierarchy is importable

```python
from src.utils.exceptions import (
    PipelineError,
    ConfigError,
    EnvVarNotFoundError,
    DatabaseError,
    DatabaseNotConnectedError,
    EmbeddingError,
    EmbeddingDimensionMismatchError,
    VectorStoreError,
    VectorStoreNotLoadedError,
    LLMError,
    LLMResponseParseError,
    BatchError,
    TemplateError,
)
print("All exceptions imported OK")
```

### Inheritance chain is correct

```python
from src.utils.exceptions import *

# All should be PipelineError subtypes
assert issubclass(ConfigError, PipelineError)
assert issubclass(DatabaseError, PipelineError)
assert issubclass(EmbeddingError, PipelineError)
assert issubclass(VectorStoreError, PipelineError)
assert issubclass(LLMError, PipelineError)
assert issubclass(BatchError, PipelineError)
assert issubclass(DatabaseNotConnectedError, DatabaseError)
assert issubclass(EmbeddingDimensionMismatchError, EmbeddingError)
assert issubclass(VectorStoreNotLoadedError, VectorStoreError)
assert issubclass(LLMResponseParseError, LLMError)
print("All inheritance checks passed")
```

### Exceptions carry context

```python
from src.utils.exceptions import LLMResponseParseError
e = LLMResponseParseError("Parse failed", raw_response='{"bad": "json"')
print(e.raw_response)   # should print the bad JSON string
print(str(e))           # human-readable message
```

---

## Phase 3 Tests — Logging

### setup_logging initializes without error

```python
from src.utils.logging import setup_logging, get_logger
setup_logging(mode_prefix="test")
logger = get_logger("tests.phase3")
logger.info("Logging test message")
logger.debug("Debug message (should appear in log file only if console level > DEBUG)")
```

### Log file is created

After calling `setup_logging(mode_prefix="test")`, a log file should appear in `logs/`:
```powershell
Get-ChildItem logs/ | Sort-Object LastWriteTime -Descending | Select-Object -First 3
```

Expected file name pattern: `test_YYYYMMDD_HHMMSS.log`

### Double-init guard works

```python
from src.utils.logging import setup_logging, get_logger
setup_logging(mode_prefix="test")
setup_logging(mode_prefix="another")   # should NOT raise; guard prevents double-init
logger = get_logger("tests.phase3.guard")
logger.info("Guard test")
print("Double-init guard: OK")
```

---

## Phase 4 Tests — Console + Batching + Retry

### Console class is importable and functional

```python
from src.utils.console import console
console.step("Test step")
console.step("Test step done", done=True)
console.progress_bar(30, 100, label="Test progress")
console.progress_bar(100, 100, label="Test progress")
console.error("Test context", "Something went wrong")
console.info("Test", "Informational message")
print("Console: OK")
```

Inspect the terminal output — step lines and progress bar should be visible.

### iter_batches splits correctly

```python
from src.utils.batching import iter_batches
items = list(range(10))
batches = list(iter_batches(items, 3))
assert batches == [[0,1,2], [3,4,5], [6,7,8], [9]], f"Got {batches}"
print("iter_batches: OK")

# Edge case: exactly divisible
batches2 = list(iter_batches(list(range(6)), 3))
assert batches2 == [[0,1,2], [3,4,5]]
print("iter_batches exact: OK")

# Edge case: empty
batches3 = list(iter_batches([], 3))
assert batches3 == []
print("iter_batches empty: OK")
```

### make_retry_decorator decorates without error

```python
from src.utils.retry import make_retry_decorator

call_count = 0

def flaky_fn():
    global call_count
    call_count += 1
    if call_count < 3:
        raise ValueError("temporary error")
    return "success"

retry = make_retry_decorator(max_attempts=5, backoff_factor=0.1, min_wait=0.01, max_wait=0.1,
                              retry_on=(ValueError,))

@retry
def retried():
    return flaky_fn()

result = retried()
assert result == "success", result
assert call_count == 3, call_count
print("Retry decorator: OK")
```

---

## Phase 5 Tests — Templates

### Template renders correctly

```python
from src.utils.templates import render_template, FALLBACK_SYSTEM, FALLBACK_CLASSIFICATION

# Test fallback (no file)
result = render_template(None, FALLBACK_SYSTEM)
assert "GS1" in result or len(result) > 0
print("Fallback system template: OK")

# Test with actual file
result2 = render_template("templates/gs1_classification.j2", FALLBACK_CLASSIFICATION,
                           products=[{"product_id": 1, "context": {"name": "milk"},
                                      "candidates": [{"letter": "A",
                                                       "hierarchy_string": "A > B > C > D",
                                                       "attributes": []},
                                                      {"letter": "B",
                                                       "hierarchy_string": "NONE",
                                                       "attributes": []}]}])
print("Classification template preview:")
print(result2[:200])
assert "[A]" in result2
assert "NONE" in result2
print("Jinja2 template render: OK")
```

### TemplateError raised for bad syntax

```python
from src.utils.templates import render_template
from src.utils.exceptions import TemplateError

# Create a temp file with bad syntax to test error handling
import tempfile, os
with tempfile.NamedTemporaryFile(mode="w", suffix=".j2", delete=False) as f:
    f.write("{{ unclosed")
    tmpname = f.name
try:
    render_template(tmpname, "fallback", name="test")
    print("ERROR: Should have raised TemplateError")
except TemplateError as e:
    print("TemplateError raised correctly:", e)
finally:
    os.unlink(tmpname)
```

---

## Phase 6 Tests — Interfaces + Document DTO

### Document DTO is importable and correct

```python
from src.dto import Document

doc = Document(id="123", text="hello world")
assert doc.id == "123"
assert doc.text == "hello world"
assert doc.metadata == {}
assert doc.embedding is None

# With embedding
doc2 = Document(id="456", text="test", embedding=[0.1, 0.2, 0.3])
assert doc2.embedding == [0.1, 0.2, 0.3]
print("Document DTO: OK")
```

### ABCs cannot be instantiated

```python
from src.services.embedding.base import EmbeddingProvider
from src.services.vectorstore.base import VectorStore
from src.services.llm.base import LLMProvider
from src.services.db.base import DatabaseConnector

for cls in (EmbeddingProvider, VectorStore, LLMProvider, DatabaseConnector):
    try:
        cls()
        print(f"ERROR: {cls.__name__} should not be instantiable")
    except TypeError:
        print(f"{cls.__name__} is abstract: OK")
```

---

## Phase 7 Tests — Factory

### Factory creates registered components

```python
from src.factory import ComponentFactory, build_default_factory

factory = build_default_factory()
print("Factory loaded OK")
```

### PipelineError raised for unknown type

```python
from src.factory import ComponentFactory
from src.utils.exceptions import PipelineError

factory = ComponentFactory()

try:
    factory.create_embedding("nonexistent_provider")
except PipelineError as e:
    print("PipelineError raised for unknown embedding:", e)

try:
    factory.create_db("nonexistent_db")
except PipelineError as e:
    print("PipelineError raised for unknown db:", e)
```

Note: it must be `PipelineError`, NOT `ValueError`. If `ValueError` is raised, the workflow-level error handlers will not catch it — it will crash the pipeline instead of being logged and skipped.

---

## Phase 8 Tests — GS1 Parser

### GS1 JSON parses without error

```python
from src.services.gs1_parser import GS1Parser
from src.dto import Document

parser = GS1Parser(file_path="data/input/GS1.json", encoding="utf-8-sig")
docs = parser.parse()
print(f"Parsed {len(docs)} documents")
assert len(docs) > 0
assert all(isinstance(d, Document) for d in docs)

# Check a sample document
sample = docs[0]
print("Sample doc ID:", sample.id)
print("Sample text:", sample.text[:100])
print("Sample metadata keys:", list(sample.metadata.keys()))
assert "hierarchy_path" in sample.metadata
assert "level" in sample.metadata
print("GS1Parser: OK")
```

### Text format is correct

```python
from src.services.gs1_parser import GS1Parser

parser = GS1Parser("data/input/GS1.json")
docs = parser.parse()
for doc in docs[:3]:
    print(repr(doc.text[:120]))
# Expected format: "Seg > Fam > Cls > Brk | Definition | Excludes: ..."
# The pipe separators should be present.
```

### Pytest unit test

```bash
pytest tests/test_gs1_parser.py -v
```

---

## Phase 9 Tests — Embedding Providers

### Azure OpenAI embedder smoke test (requires API key)

```bash
python tests/smoke_test_embedding.py
```

This script should:
1. Create `AzureOpenAIEmbeddingProvider` from env vars.
2. Call `embed_batch(["test document", "another document"])`.
3. Print the shape of the result — expect two vectors of length 1024.

Manual check:
```python
from src.utils.env import get_env
from src.services.embedding.azure_openai_embedder import AzureOpenAIEmbeddingProvider

provider = AzureOpenAIEmbeddingProvider(
    api_key=get_env("AZURE_OPENAI_API_KEY"),
    endpoint=get_env("AZURE_OPENAI_ENDPOINT"),
    deployment=get_env("AZURE_OPENAI_EMBEDDING_DEPLOYMENT"),
    api_version=get_env("AZURE_OPENAI_API_VERSION"),
    dimensions=1024,
    batch_size=16,
    max_workers=1,
)
vecs = provider.embed_batch(["Hello world", "Test product"])
print("Embedding shape:", len(vecs), "x", len(vecs[0]))
assert len(vecs) == 2
assert len(vecs[0]) == 1024
print("AzureOpenAI embedder: OK")
```

### HuggingFace embedder (offline, no API key needed)

```python
from src.services.embedding.huggingface import HuggingFaceEmbeddingProvider

provider = HuggingFaceEmbeddingProvider(model_name="sentence-transformers/all-MiniLM-L6-v2")
vecs = provider.embed_batch(["Hello world", "Test product"])
print("HuggingFace shape:", len(vecs), "x", len(vecs[0]))
assert len(vecs) == 2
print("HuggingFace embedder: OK")
```

---

## Phase 10 Tests — FAISS Vector Store

### Save and load round-trip (offline)

```python
import numpy as np
from src.dto import Document
from src.services.vectorstore.faiss_store import FAISSVectorStore

# Build a small vector store
dims = 8
docs = [
    Document(id=f"d{i}", text=f"doc {i}",
             metadata={"level": 4, "hierarchy_path": ["A", "B", "C", f"D{i}"],
                       "code": f"code{i}", "title": f"Title {i}"},
             embedding=list(np.random.rand(dims).astype(float)))
    for i in range(10)
]

vs = FAISSVectorStore(
    output_dir="data/vector_store_test",
    filename_prefix="test",
    lookup_metadata_fields=["level", "hierarchy_path", "code", "title"],
    embedding_dimensions=dims,
    embedding_model="test-model",
)
vs.save(documents=docs, output_dir="data/vector_store_test", prefix="test")
print("Save: OK")

# Load and search
vs2 = FAISSVectorStore(
    output_dir="data/vector_store_test",
    filename_prefix="test",
    lookup_metadata_fields=["level", "hierarchy_path"],
    embedding_dimensions=dims,
    embedding_model="test-model",
)
vs2.load()

query = list(np.random.rand(dims).astype(float))
results = vs2.search(query_vector=query, top_k=3)
print("Search results:", len(results))
assert len(results) == 3
assert all("score" in r for r in results)
print("FAISS round-trip: OK")

# Clean up test artefacts
import shutil
shutil.rmtree("data/vector_store_test", ignore_errors=True)
```

### 5 artefacts are written

After a real `build-vectors` run:
```powershell
Get-ChildItem data/vector_store/ | Format-Table Name, Length
```
Expect:
- `faiss_gs1.index` — FAISS binary
- `faiss_gs1_metadata.json` — full metadata
- `embeddings_gs1.parquet` — full document archive
- `gs1_lookup.pkl` — compact lookup
- `build_manifest.json` — provenance

---

## Phase 11 Tests — build-vectors Workflow

### Dry run with real data

Run the full build-vectors pipeline and verify the artefacts are created:

```bash
python vectorize.py build-vectors --config config.yaml
```

Expected console output:
```
  → Parsing source JSON ...
  ✓ Parsed X,XXX documents in ...
  → Generating embeddings ...
  [████████████████████] Embedding progress  100% (X,XXX/X,XXX)
  ✓ Embedded X,XXX documents in ...
  → Saving vector store artefacts ...
  ✓ Saved vector store to data/vector_store/ in ...
```

After completion:
```powershell
Get-ChildItem data/vector_store/ | Format-Table Name, Length
```
All 5 artefacts should be present and non-zero size.

### Workflow function unit test (no API)

```python
from unittest.mock import MagicMock, patch
from src.dto import Document

# Mock embedding provider and vector store
mock_embed = MagicMock()
mock_embed.embed_batch.return_value = [[0.1] * 1024, [0.2] * 1024]

mock_vs = MagicMock()
mock_vs.save = MagicMock()

# Mock config
config = MagicMock()
config.source.path = "data/input/GS1.json"
config.source.encoding = "utf-8-sig"
config.source.batch_size = 2
config.vector_store.output_dir = "data/vector_store"
config.vector_store.filename_prefix = "gs1"

# Mock parser
with patch("src.workflows.build_vectors.GS1Parser") as MockParser:
    MockParser.return_value.parse.return_value = [
        Document(id="1", text="doc1", embedding=None),
        Document(id="2", text="doc2", embedding=None),
    ]
    from src.workflows.build_vectors import run_build_vectors
    run_build_vectors(config, mock_embed, mock_vs)

mock_embed.embed_batch.assert_called()
mock_vs.save.assert_called_once()
print("build_vectors workflow unit test: OK")
```

---

## Phase 12 Tests — Database Connectors

### Azure SQL smoke test (requires ODBC Driver 18 + valid credentials)

```bash
python tests/smoke_test_db.py
```

Manual:
```python
from src.utils.env import get_env
from src.services.db.azure_sql_connector import AzureSQLConnector

conn = AzureSQLConnector(
    server=get_env("AZURE_SQL_SERVER"),
    database=get_env("AZURE_SQL_DATABASE"),
    client_id=get_env("AZURE_SQL_CLIENT_ID"),
    client_secret=get_env("AZURE_SQL_CLIENT_SECRET"),
)
conn.connect()
print("Azure SQL connected")
df = conn.fetch_batch("SELECT TOP 5 id FROM playground.promo_bronze ORDER BY id")
print(df)
conn.disconnect()
print("Azure SQL smoke test: OK")
```

### PostgreSQL smoke test

```python
from src.utils.env import get_env
from src.services.db.postgresql import PostgreSQLConnector

conn = PostgreSQLConnector(
    host=get_env("PG_HOST"),
    port=int(get_env("PG_PORT")),
    database=get_env("PG_DATABASE"),
    username=get_env("PG_USERNAME"),
    password=get_env("PG_PASSWORD"),
)
conn.connect()
df = conn.fetch_batch("SELECT id FROM playground.promo_bronze LIMIT 5")
print(df)
conn.disconnect()
print("PostgreSQL smoke test: OK")
```

### update_rows with VECTOR cast (Azure SQL)

Run a test update with a fake embedding to verify the CAST syntax works:
```python
import json, numpy as np

fake_embedding = json.dumps(list(np.random.rand(1024).astype(float)))
test_update = [{"id": 99999, "embedding_context": fake_embedding}]

conn.connect()
try:
    # This will fail with a foreign key / not-found error if 99999 doesn't exist —
    # which is fine. What we're testing is that the SQL is syntactically correct
    # (no error about CAST or VECTOR).
    conn.update_rows("playground.promo_bronze", test_update, key_column="id")
except Exception as e:
    if "VECTOR" in str(e).upper() or "CAST" in str(e).upper():
        print("ERROR: VECTOR cast failed:", e)
    else:
        print("CAST syntax OK (row not found is expected):", type(e).__name__)
finally:
    conn.disconnect()
```

### DatabaseNotConnectedError before connect()

```python
from src.services.db.azure_sql_connector import AzureSQLConnector
from src.utils.exceptions import DatabaseNotConnectedError

conn = AzureSQLConnector(server="dummy", database="dummy", client_id="x", client_secret="y")
try:
    conn.fetch_batch("SELECT 1")
    print("ERROR: Should have raised DatabaseNotConnectedError")
except DatabaseNotConnectedError:
    print("DatabaseNotConnectedError raised correctly: OK")
```

---

## Phase 13 Tests — embed-rows Workflow

### embed-rows smoke test (requires DB + API key)

```bash
python vectorize.py embed-rows --config config.yaml
```

Expected output:
```
  → embed-rows → embedding_context
  [████████████████████] Embed-rows  100%
  ✓ embed-rows complete — X rows in ...
```

After completion, check that `embedding_context` is populated:
```python
from src.utils.env import get_env
from src.services.db.azure_sql_connector import AzureSQLConnector

conn = AzureSQLConnector(...)
conn.connect()
df = conn.fetch_batch("SELECT TOP 5 id, embedding_context FROM playground.promo_bronze WHERE embedding_context IS NOT NULL")
print(df[["id"]].head())
print("Embedding is JSON string:", isinstance(df["embedding_context"].iloc[0], str))
import json
embedding = json.loads(df["embedding_context"].iloc[0])
print("Embedding length:", len(embedding))  # should be 1024
conn.disconnect()
```

### Resumability test

1. Run `embed-rows` and interrupt it mid-way (`Ctrl+C`).
2. Run `embed-rows` again — it should continue from where it stopped (not re-embed already-processed rows).

This works because the WHERE clause is `WHERE embedding_context IS NULL` and previously embedded rows now have a non-NULL value.

---

## Phase 14 Tests — LLM Providers

### Azure OpenAI LLM smoke test (requires API key)

```bash
python tests/smoke_test_llm.py
```

Manual:
```python
from src.utils.env import get_env
from src.services.llm.azure_openai_chat import AzureOpenAILLMProvider

llm = AzureOpenAILLMProvider(
    api_key=get_env("AZURE_OPENAI_API_KEY"),
    endpoint=get_env("AZURE_OPENAI_ENDPOINT"),
    deployment=get_env("AZURE_OPENAI_CHAT_DEPLOYMENT"),
    api_version=get_env("AZURE_OPENAI_API_VERSION"),
    max_completion_tokens=100,
    max_attempts=1,
)
response = llm.chat(
    system_message="You are a helpful assistant.",
    user_message="Say hello in one word.",
)
print("Response content:", response["content"])
print("Usage:", response["usage"])
assert "content" in response
assert "usage" in response
assert "total_tokens" in response["usage"]
print("AzureOpenAI LLM smoke test: OK")
```

### JSON mode works

```python
response = llm.chat(
    system_message="You are an assistant. Respond in JSON format: {\"answer\": \"...\"}",
    user_message="What is 2+2?",
    response_format={"type": "json_object"},
)
import json
data = json.loads(response["content"])
print("JSON mode response:", data)
print("JSON mode: OK")
```

### No temperature parameter — o-series constraint

Verify that passing `temperature` would cause an error. This is enforced by the implementation (never passing it), but you can test the API directly if in doubt:
```python
# This SHOULD cause a 400 API error if uncommented:
# response = llm._client.chat.completions.create(
#     model=llm._deployment,
#     messages=[{"role": "user", "content": "hi"}],
#     temperature=0.7,  # illegal for o-series
# )
print("o-series constraint documented: temperature is never passed")
```

---

## Phase 15 Tests — CandidateBuilder + ResponseParser

### Run pytest unit tests

```bash
pytest tests/test_candidate_builder.py -v
pytest tests/test_response_parser.py -v
```

### CandidateBuilder — manual smoke test

```python
from src.transforms.candidate_builder import CandidateBuilder

builder = CandidateBuilder()
rag_results = [
    {"score": 0.15, "metadata": {
        "level": 4, "code": "10000124", "title": "White Bread",
        "hierarchy_path": ["Food", "Bakery", "Bread", "White Bread"],
        "hierarchy_string": "Food > Bakery > Bread > White Bread"}},
    {"score": 0.25, "metadata": {
        "level": 4, "code": "10000125", "title": "Brown Bread",
        "hierarchy_path": ["Food", "Bakery", "Bread", "Brown Bread"],
        "hierarchy_string": "Food > Bakery > Bread > Brown Bread"}},
    {"score": 1.85, "metadata": {
        "level": 4, "code": "99999", "title": "Electronics",
        "hierarchy_path": ["Electronics", "Devices", "Phones", "Smartphones"],
        "hierarchy_string": "Electronics > ..."}},
]
candidates = builder.build(rag_results)
print("Candidates:")
for c in candidates:
    print(f"  [{c['letter']}] {c['hierarchy_string']!r}  score={c['score']:.4f}")

assert len(candidates) == 3   # all 3 groups (no filtering, no cap)
# Verify sort order: ascending by L2 distance (lower = better match first)
assert candidates[0]["score"] <= candidates[1]["score"]
print("CandidateBuilder: OK")
```

### ResponseParser — manual smoke test

```python
from src.transforms.response_parser import ResponseParser

parser = ResponseParser()
raw = '{"results": [{"product_id": 42, "choice": "A"}]}'
product_candidates = {
    42: [
        {"letter": "A",
         "hierarchy_path": ["Food", "Bakery", "Bread", "White Bread"],
         "hierarchy_string": "Food > Bakery > Bread > White Bread",
         "attributes": []},
        {"letter": "B",
         "hierarchy_string": "NONE",
         "hierarchy_path": [], "attributes": []},
    ]
}
target_cols = ["gs1_segment", "gs1_family", "gs1_class", "gs1_brick",
               "gs1_attribute", "gs1_attribute_value"]
results = parser.parse(raw, product_candidates, target_cols)
print("Result:", results[0])
assert results[0]["gs1_segment"] == "Food"
assert results[0]["gs1_brick"] == "White Bread"
print("ResponseParser: OK")
```

### LLMResponseParseError on unparseable response

```python
from src.transforms.response_parser import ResponseParser
from src.utils.exceptions import LLMResponseParseError

parser = ResponseParser()
try:
    parser.parse("This is not JSON or any list", {}, [])
    print("ERROR: Should have raised LLMResponseParseError")
except LLMResponseParseError as e:
    print("LLMResponseParseError raised: OK")
```

### Regex fallback works

```python
from src.transforms.response_parser import ResponseParser

parser = ResponseParser()
# LLM sometimes wraps JSON in text
raw = 'Here is my answer: [{"product_id": 1, "choice": "A"}] Hope that helps!'
product_candidates = {
    1: [{"letter": "A", "hierarchy_path": ["X", "Y", "Z", "W"],
         "hierarchy_string": "X > Y > Z > W", "attributes": []}]
}
results = parser.parse(raw, product_candidates, ["c1", "c2", "c3", "c4", "c5", "c6"])
print("Regex fallback result:", results[0])
assert results[0]["c1"] == "X"
print("Regex fallback: OK")
```

---

## Phase 16 Tests — Prompt Templates

### Templates render without error

```bash
pytest tests/test_templates.py -v
```

### Manual template rendering

```python
from src.utils.templates import render_template, FALLBACK_CLASSIFICATION

products = [
    {
        "product_id": 101,
        "context": {"product_name": "Whole grain bread", "weight_g": "400"},
        "candidates": [
            {"letter": "A", "hierarchy_string": "Food > Bakery > Bread > Wholemeal Bread",
             "attributes": [{"level": 5, "code": "50000001", "title": "Pre-sliced Brown Bread"}]},
            {"letter": "B", "hierarchy_string": "NONE",
             "attributes": []},
        ],
    }
]
rendered = render_template("templates/gs1_classification.j2", FALLBACK_CLASSIFICATION,
                            products=products)
print(rendered)
assert "[A]" in rendered
assert "Wholemeal Bread" in rendered
assert "NONE" in rendered
assert "Pre-sliced Brown Bread" in rendered
print("Template render: OK")
```

---

## Phase 17 Tests — Orchestrator

### Smoke test (requires loaded vector store + LLM)

```bash
python tests/smoke_test_orchestrator.py
```

### Mock-based unit test

```python
from unittest.mock import MagicMock, patch
import json

# Build mock objects
mock_config = MagicMock()
mock_config.classification.rag_top_k = 10
mock_config.classification.prompt_columns = ["product_name"]
mock_config.classification.target_columns = [
    "gs1_segment", "gs1_family", "gs1_class", "gs1_brick",
    "gs1_attribute", "gs1_attribute_value"
]
mock_config.classification.system_template_file = None
mock_config.classification.prompt_template_file = None

mock_vs = MagicMock()
mock_vs.search.return_value = [
    {"score": 0.9, "metadata": {
        "level": 4, "code": "123", "title": "White Bread",
        "hierarchy_path": ["Food", "Bakery", "Bread", "White Bread"],
        "hierarchy_string": "Food > Bakery > Bread > White Bread"}}
]

mock_llm = MagicMock()
mock_llm.chat.return_value = {
    "content": '{"results": [{"product_id": 1, "choice": "A"}]}',
    "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
}

from src.services.orchestrator import LLMOrchestratorService

orchestrator = LLMOrchestratorService(mock_config, mock_vs, mock_llm)

rows = [{"id": 1, "product_name": "Whole grain bread",
         "embedding_context": json.dumps([0.1] * 1024)}]
results = orchestrator.classify_batch(rows)
print("Orchestrator result:", results)
assert len(results) == 1
assert results[0]["gs1_segment"] == "Food"
assert results[0]["product_id"] == 1
print("Orchestrator unit test: OK")
```

---

## Phase 18 Tests — Full Pipeline (End-to-End)

### Complete 3-step run

Execute all three pipeline modes in order:

```bash
# Step 1: Build the FAISS index from GS1 taxonomy
python vectorize.py build-vectors --config config.yaml

# Step 2: Embed product rows in the database
python vectorize.py embed-rows --config config.yaml

# Step 3: Classify products via RAG + LLM
python main.py --config config.yaml
```

Each step should complete without error. Check log files after each step:
```powershell
Get-ChildItem logs/ | Sort-Object LastWriteTime -Descending | Select-Object -First 6
```

### Verify classifications were written to DB

```python
from src.utils.env import get_env
from src.services.db.azure_sql_connector import AzureSQLConnector

conn = AzureSQLConnector(
    server=get_env("AZURE_SQL_SERVER"),
    database=get_env("AZURE_SQL_DATABASE"),
    client_id=get_env("AZURE_SQL_CLIENT_ID"),
    client_secret=get_env("AZURE_SQL_CLIENT_SECRET"),
)
conn.connect()
df = conn.fetch_batch("""
    SELECT TOP 10 id, gs1_segment, gs1_family, gs1_class, gs1_brick
    FROM playground.promo_bronze
    WHERE gs1_segment IS NOT NULL
    ORDER BY id
""")
print(df)
conn.disconnect()
```

### Verify no rows were skipped

```python
# Count rows without classification
df = conn.fetch_batch("""
    SELECT COUNT(*) as remaining
    FROM playground.promo_bronze
    WHERE gs1_segment IS NULL
""")
print("Unclassified rows remaining:", df["remaining"].iloc[0])
```

A non-zero count means some batches failed. Check `logs/failed_products.json`:
```powershell
if (Test-Path logs/failed_products.json) {
    Get-Content logs/failed_products.json | ConvertFrom-Json | Select-Object -First 5
} else {
    Write-Host "No failed products"
}
```

### KeyboardInterrupt exits cleanly

1. Start `python main.py`.
2. Press `Ctrl+C` during execution.
3. Expect exit code 130, not an ugly traceback:
```powershell
python main.py
# Press Ctrl+C
echo "Exit code: $LASTEXITCODE"   # should be 130
```

---

## Offline Unit Test Suite

These tests run without any API keys or DB connections:

```bash
# Run all offline tests
pytest tests/ -v -k "not smoke"
```

| Test file | What it tests |
|---|---|
| `tests/test_config.py` | Config loading, validation, missing fields |
| `tests/test_gs1_parser.py` | JSON parsing, Document format, hierarchy |
| `tests/test_candidate_builder.py` | Filtering, grouping, sorting, NONE candidate |
| `tests/test_response_parser.py` | JSON parse, regex fallback, NONE choice, parse error |
| `tests/test_templates.py` | Template loading, fallback, rendering |

Run a specific test file:
```bash
pytest tests/test_candidate_builder.py -v
pytest tests/test_gs1_parser.py -v
pytest tests/test_response_parser.py -v
```

---

## Smoke Test Suite

These tests require API keys and/or a database connection:

```bash
# Run all smoke tests (needs .env populated)
pytest tests/ -v -k "smoke"
```

| Test file | Requires |
|---|---|
| `tests/smoke_test_embedding.py` | `AZURE_OPENAI_*` env vars |
| `tests/smoke_test_llm.py` | `AZURE_OPENAI_*` env vars |
| `tests/smoke_test_db.py` | `AZURE_SQL_*` or `PG_*` env vars |
| `tests/smoke_test_vectorstore.py` | None (uses temp FAISS store) |
| `tests/smoke_test_orchestrator.py` | All of the above |
| `tests/smoke_test_factory.py` | None |
| `tests/smoke_test_interfaces.py` | None |
| `tests/smoke_test_utils.py` | None |

Run individual smoke tests:
```bash
python tests/smoke_test_embedding.py
python tests/smoke_test_llm.py
python tests/smoke_test_db.py
```

---

## Common Failure Patterns

| Symptom | Cause | Fix |
|---|---|---|
| `ValidationError: batch_size` | Missing required field in `config.yaml` | Add `batch_size` to `source`, `row_embedding`, and `classification` sections |
| `ConfigError: ... not found` | `config.yaml` path is wrong | Run from the repo root or pass `--config` explicitly |
| `EnvVarNotFoundError: AZURE_...` | Missing `.env` entry | Copy `.env.example` to `.env` and fill in secrets |
| `PipelineError: Unknown embedding type` | Typo in `config.yaml embedding.type` | Must match exactly: `azure_openai`, `huggingface`, etc. |
| `PipelineError: Unknown db type` | Typo in `config.yaml database.type` | Must match exactly: `azure_sql`, `postgresql` |
| `VectorStoreNotLoadedError` | Called `search()` before `load()` | Call `vector_store.load()` in entry point before creating orchestrator |
| `ValueError: temperature` from API | Passed `temperature` to o-series model | Remove temperature from LLM kwargs — o-series uses `max_completion_tokens` only |
| `LLMResponseParseError` | LLM returned non-JSON | Check prompt templates — system prompt must mention JSON |
| `DatabaseNotConnectedError` | Called `fetch_batch()` before `connect()` | Always call `db_connector.connect()` before the batcher loop |
| `CAST(CAST(... VECTOR)` SQL error | Wrong pyodbc/SQLAlchemy version | Upgrade to `pyodbc>=5` and `sqlalchemy>=2` |
| Progress stops at same count each run | `DatabaseBatcher` using wrong OFFSET logic | Verify batcher always uses `OFFSET 0` — resume via WHERE IS NULL, not by advancing offset |
| All products assigned "NONE" | Embedding model mismatch between build-vectors and embed-rows | Check `build_manifest.json` model matches the configured embedding model |
| `logs/failed_products.json` grows on reruns | Failed batch retried but same error occurs | Check LLM quota, embedding availability, or null embedding_context |
