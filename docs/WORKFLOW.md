# Pipeline Workflow

## Table of Contents

- [Overview](#overview)
- [Mode 1 — build-vectors](#mode-1--build-vectors)
- [Mode 2 — embed-rows](#mode-2--embed-rows)
- [Mode 3 — classify](#mode-3--classify)
- [Complete Stage Map](#complete-stage-map)
- [Debugging Reference](#debugging-reference)

---

## Overview

The pipeline has three independent modes that run in order for a fresh setup:

```
1. build-vectors   python vectorize.py build-vectors
2. embed-rows      python vectorize.py embed-rows
3. classify        python main.py
```

Modes 1 and 2 are one-time setup. Mode 3 is the production loop. All three read from the same `config.yaml`.

```
config.yaml
    │
    ├── build-vectors ──── GS1.json → embed → FAISS index on disk
    ├── embed-rows    ──── DB rows  → embed → write vector back to DB
    └── classify      ──── DB rows  → RAG + LLM → write GS1 columns to DB
```

There are two entry points:

| Entry point | Modes |
|---|---|
| `vectorize.py build-vectors` | Mode 1 |
| `vectorize.py embed-rows` | Mode 2 |
| `main.py` | Mode 3 |

### Component construction

Both entry points construct components in the same pattern:
1. Load `config.yaml` via `load_config()` → validated `AppConfig` object
2. Call `build_default_factory()` → `ComponentFactory` with all providers registered
3. Use `factory.create_*(...)` to instantiate only the components needed for that mode
4. Pass constructed objects into the workflow function (`run_build_vectors`, `run_embed_rows`, `run_classify`)

Workflow functions receive already-constructed objects. They contain no component creation logic — they are pure pipeline orchestration.

---

## Mode 1 — build-vectors

**Command:** `python vectorize.py build-vectors`

**Purpose:** Read the GS1 GPC taxonomy JSON, parse every node into a text document, embed all documents, and save a FAISS similarity index to disk. This only needs to be run once (or after changing the embedding model).

### What happens step by step

#### Stage: PARSE_SOURCE
**File:** `src/workflows/build_vectors.py` — `run_build_vectors()`  
**Class:** `GS1Parser` (`src/services/gs1_parser.py`)

Reads `data/input/GS1.json`. The JSON has a top-level `"Schema"` key containing a recursive tree of GS1 GPC taxonomy nodes. Each node has `Code`, `Title`, `Level` (1–6), `Definition`, `DefinitionExcludes`, `Active`, and `Childs`.

The parser walks the tree recursively and emits one `Document` per node. There are 6 levels:

```
Level 1 — Segment       (e.g. "Food/Beverage/Tobacco")
Level 2 — Family        (e.g. "Fruits/Vegetables/Herbs")
Level 3 — Class         (e.g. "Vegetables")
Level 4 — Brick         (e.g. "Beans (Fresh)")
Level 5 — Attribute     (e.g. "Type of Bean")
Level 6 — AttributeValue (e.g. "Runner Bean")
```

Each `Document` contains:
- `id` — the GS1 code (e.g. `"10000000"`)
- `text` — the string that will be embedded: `"Segment > Family > Class > Brick | definition | Excludes: ..."`
- `metadata` — dict with `level`, `code`, `title`, `hierarchy_path` (list), `hierarchy_string`, `definition`, `excludes`, `active`
- `embedding` — `None` at this point

#### Stage: EMBED_DOCUMENTS
**File:** `src/workflows/build_vectors.py`  
**Class:** `EmbeddingProvider` (`src/services/embedding/`)

Documents are batched (size: `source.batch_size`, default 50) and sent to the embedding provider. The provider converts each document's `text` field into a float vector and writes it back onto `document.embedding`.

For Azure OpenAI: calls `text-embedding-3-large` (or the configured deployment) via the `openai` SDK with a `ThreadPoolExecutor` (default 5 workers). Rate limit errors trigger exponential backoff retries.

After this stage, every `Document` has a populated `embedding` field.

#### Stage: INDEX_BUILD
**File:** `src/services/vectorstore/faiss_store.py` — `save()`

Builds the FAISS index from all document vectors and writes five artefacts to `data/vector_store/`:

| File | Contents |
|---|---|
| `faiss_gs1.index` | FAISS binary index (`IndexFlatL2` — L2 distance on unit vectors) |
| `faiss_gs1_metadata.json` | Maps index position → document id + full metadata |
| `embeddings_gs1.parquet` | Full archive: id, text, embedding, metadata (for re-indexing) |
| `gs1_lookup.pkl` | Compact pickle: `{int_id: {selected metadata fields}}` — loaded at query time |
| `build_manifest.json` | Audit: timestamp, model name, dimensions, document count |

Vectors are L2-normalised in-place before being added to the index for consistent magnitude. The index type is `IndexFlatL2` (squared L2 distance). Scores are in `[0, 4]` for unit vectors, lower = more similar. Query vectors are also L2-normalised before search.

### Data flow

```
data/input/GS1.json
        │
        ▼  GS1Parser.parse()
list[Document]  (text populated, embedding=None)
        │
        ▼  EmbeddingProvider.embed_batch()  [batched, parallel]
list[Document]  (embedding now populated)
        │
        ▼  FAISSVectorStore.save()
data/vector_store/
    ├── faiss_gs1.index
    ├── faiss_gs1_metadata.json
    ├── embeddings_gs1.parquet
    ├── gs1_lookup.pkl
    └── build_manifest.json
```

---

## Mode 2 — embed-rows

**Command:** `python vectorize.py embed-rows`

**Purpose:** Read product rows from the database, concatenate the configured columns into a single text string, embed that string, and write the resulting vector back to the `embedding_context` column. Only processes rows where `embedding_context IS NULL`, so it is safe to re-run.

### What happens step by step

#### Stage: EMBED_ROWS
**File:** `src/workflows/embed_rows.py` — `run_embed_rows()`

**Pagination:** `DatabaseBatcher` pages through the table with SQL `OFFSET … FETCH NEXT` batches (batch size: `row_embedding.batch_size`, default 50). Query:

```sql
SELECT id, <row_embedding.columns>
FROM schema.table
WHERE embedding_context IS NULL
ORDER BY id
OFFSET x FETCH NEXT 50 ROWS ONLY
```

**Per batch:**
1. Concatenate the configured columns for each row into one string using `row_embedding.separator` (default `" * "`). The default columns are: `store`, `country`, `product_name`, `product_name_en`, `category`, `packaging_type`, `packaging_value`, `packaging_unit`.
2. Call `embedding_provider.embed_batch(texts)` — parallel threads, same provider as `build-vectors`.
3. Write the vector back to the database in `embedding_context`:
   - Azure SQL: `CAST(CAST(:embedding_context AS VARCHAR(MAX)) AS VECTOR(1024))`
   - PostgreSQL: `:embedding_context::vector(1024)`

**Critical:** The embedding model must be identical between `embed-rows` and `build-vectors`. Both modes use the same `embedding` config section, which enforces this. If you switch models, rebuild the FAISS index and re-run `embed-rows`.

### Data flow

```
DB table (rows where embedding_context IS NULL)
        │
        ▼  DatabaseBatcher (paginated SQL)
batch of rows
        │  concatenate columns with separator
        ▼  EmbeddingProvider.embed_batch()
list[float[]] per row
        │
        ▼  DatabaseConnector.update_rows()
DB table (embedding_context column written)
```

---

## Mode 3 — classify

**Command:** `python main.py`

**Purpose:** For each unclassified product row (`gs1_segment IS NULL`), retrieve the closest GS1 taxonomy nodes via vector similarity search, build a lettered options list, call the LLM to choose, and write 6 GS1 columns back to the database.

### Initialization

```
main.py
 ├── load_config("config.yaml")
 ├── build_default_factory()          ← registers all providers
 ├── FAISSVectorStore.load()           ← reads index + metadata from disk
 │       loads faiss_gs1.index into memory
 │       loads gs1_lookup.pkl into memory
 ├── AzureOpenAILLMProvider(...)       ← initialized, no connection yet
 ├── LLMOrchestratorService(config, vector_store, llm_provider)
 └── DatabaseConnector.connect()
```

### What happens step by step

#### Stage: FETCH_ROWS
**File:** `src/workflows/classify.py` — `run_classify()`

`DatabaseBatcher` pages through unclassified rows (batch size: `classification.batch_size`, default 10):

```sql
SELECT id, product_name, product_name_en, packaging_value,
       packaging_unit, embedding_context
FROM schema.table
WHERE gs1_segment IS NULL
ORDER BY id
OFFSET x FETCH NEXT 10 ROWS ONLY
```

#### Stage: CLASSIFY_BATCH
**File:** `src/workflows/classify.py`  
**Class:** `LLMOrchestratorService` (`src/services/orchestrator.py`)

Each batch of rows is handed to `orchestrator.classify_batch(rows)`. The following substages run inside the orchestrator for every product in the batch.

---

**Substage: VECTOR_SEARCH**  
**File:** `src/services/orchestrator.py` → `src/services/vectorstore/faiss_store.py`

For each product row:
1. Parse `embedding_context` (JSON string stored in DB) into a `float[]`.
2. Pass to `vector_store.search(embedding, top_k=30)`.

Inside `FAISSVectorStore.search()`:
- L2-normalise the query vector in-place, then call `index.search(query, k=30)`. Returns scores as squared L2 distances in `[0, 4]` for unit vectors (lower = more similar).

Returns a list of dicts `{"id": ..., "score": ..., "metadata": {...}}` — one per candidate, top 30.

---

**Substage: CANDIDATE_FILTER**  
**File:** `src/transforms/candidate_builder.py` — `CandidateBuilder.build()`

Takes the 30 search results and produces a lettered options list:

1. **Group by L4 path:** Results are grouped by their Segment → Family → Class → Brick path. Multiple attribute/value variants of the same Brick collapse into one entry.
2. **Track best score per group:** lowest L2 distance per group.
3. **Sort groups:** ascending by best score (lower L2 distance = better match first).
4. **Assign letters A, B, C, ...** to each group.

All groups are passed to the LLM — there is no score threshold filter and no cap on the number of candidates.

Result: a list of candidate dicts, each with a letter, the GS1 hierarchy path, and the best matching score.

---

**Substage: PROMPT_BUILD**  
**File:** `src/services/orchestrator.py`  
**Templates:** `templates/gs1_system.j2`, `templates/gs1_classification.j2`

The entire batch (all products + their candidate lists) is rendered into a single prompt using Jinja2:
- System message: from `gs1_system.j2` — explains the GS1 classification task and output format
- User message: from `gs1_classification.j2` — lists every product in the batch with its prompt columns and its lettered candidate options

One LLM call covers the entire batch (default 10 products).

---

**Substage: LLM_CALL**  
**File:** `src/services/orchestrator.py`  
**Class:** `LLMProvider`

Calls `llm_provider.chat(system, user, response_format={"type": "json_object"})`. The LLM returns a JSON array:

```json
[
  {"product_id": 123, "choice": "B"},
  {"product_id": 124, "choice": "A"},
  ...
]
```

---

**Substage: RESPONSE_PARSE**  
**File:** `src/transforms/response_parser.py` — `ResponseParser.parse()`

1. Parse the LLM JSON response. If direct `json.loads()` fails, a regex fallback extracts JSON from the response body and logs a warning.
2. For each `{"product_id": ..., "choice": "X"}` entry, look up letter `"X"` in that product's candidate list.
3. Extract 6 GS1 values from the matched candidate's `hierarchy_path`:
   - `gs1_segment`, `gs1_family`, `gs1_class`, `gs1_brick`, `gs1_attribute`, `gs1_attribute_value`
4. Special cases:
   - `[NONE]` choice → all 6 columns set to `"NONE"`
   - Unknown letter → all 6 columns set to `"UNKNOWN"` (logged at WARNING)

#### Stage: WRITE_RESULTS
**File:** `src/workflows/classify.py`

`db_connector.update_rows()` writes the 6 GS1 columns back for every product in the batch. Failed batches are caught, logged, and appended to a JSON summary file in `logs/`.

### Data flow

```
DB table (rows where gs1_segment IS NULL)
        │
        ▼  DatabaseBatcher
batch of rows (10 products)
        │
        ├── For each product:
        │   embedding_context (JSON string)
        │       │
        │       ▼  FAISSVectorStore.search(top_k=30)
        │   top-30 candidates with scores
        │       │
        │       ▼  CandidateBuilder.build()
        │   lettered options [A, B, C, ..., NONE]
        │
        ▼  Render Jinja2 templates (full batch)
        │
        ▼  LLMProvider.chat()
        │
   JSON: [{product_id, choice}, ...]
        │
        ▼  ResponseParser.parse()
   [{id, gs1_segment, gs1_family, gs1_class, gs1_brick, gs1_attribute, gs1_attribute_value}, ...]
        │
        ▼  DatabaseConnector.update_rows()
DB table (6 GS1 columns written)
```

---

## Complete Stage Map

Every processing step is tagged `# [STAGE: NAME]` in source. Run `grep -rn "\[STAGE:" src/` to locate any stage.

| Stage | File | Function | Mode |
|---|---|---|---|
| `PARSE_SOURCE` | `src/workflows/build_vectors.py` | `run_build_vectors` | build-vectors |
| `EMBED_DOCUMENTS` | `src/workflows/build_vectors.py` | `run_build_vectors` | build-vectors |
| `INDEX_BUILD` | `src/workflows/build_vectors.py` | `run_build_vectors` | build-vectors |
| `INDEX_BUILD` | `src/services/vectorstore/faiss_store.py` | `save` | build-vectors |
| `EMBED_ROWS` | `src/workflows/embed_rows.py` | `run_embed_rows` | embed-rows |
| `FETCH_ROWS` | `src/workflows/classify.py` | `run_classify` | classify |
| `CLASSIFY_BATCH` | `src/workflows/classify.py` | `run_classify` | classify |
| `VECTOR_SEARCH` | `src/services/orchestrator.py` | `classify_batch` | classify |
| `CANDIDATE_RETRIEVAL` | `src/services/vectorstore/faiss_store.py` | `search` | classify |
| `CANDIDATE_FILTER` | `src/services/orchestrator.py` | `classify_batch` | classify |
| `CANDIDATE_FILTER` | `src/transforms/candidate_builder.py` | `build` | classify |
| `PROMPT_BUILD` | `src/services/orchestrator.py` | `classify_batch` | classify |
| `LLM_CALL` | `src/services/orchestrator.py` | `classify_batch` | classify |
| `RESPONSE_PARSE` | `src/services/orchestrator.py` | `classify_batch` | classify |
| `WRITE_RESULTS` | `src/workflows/classify.py` | `run_classify` | classify |

---

## Debugging Reference

**No FAISS artefacts / stale index:**  
Run `python vectorize.py build-vectors`. Check `data/vector_store/build_manifest.json` for model name and dimensions — they must match `config.yaml → embedding.dimensions`.

**Few or irrelevant candidates reaching the LLM:**  
The model used for `embed-rows` may differ from the model used for `build-vectors`. Check `build_manifest.json` for the model name used at build time. Both modes must use the same embedding model and dimensions.

**LLM returns unparseable JSON:**  
`ResponseParser` logs the raw response at ERROR level. A regex fallback also tries to extract JSON and logs a WARNING when it fires. Check `logs/` for the raw response.

**Rows not classified after a successful run:**  
Rows may already have a value in `gs1_segment`. The `WHERE gs1_segment IS NULL` filter skips them. Also check `logs/` for batch-level exceptions — failed batches are not retried automatically.

**Azure SQL VECTOR cast errors:**  
The `CAST(CAST(:col AS VARCHAR(MAX)) AS VECTOR(1024))` pattern requires vector dimensions to match the column definition. A dimension mismatch (e.g., index built with 1536-dim vectors, column defined as `VECTOR(1024)`) will fail here. Rebuild with matching dimensions.

**Rate limit retries visible in logs:**  
All Azure OpenAI calls use exponential backoff (configured in `system.retry`). Retry attempts log at WARNING with wait times. This is expected behaviour — not an error.

