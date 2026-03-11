# gs1-vectoRAG-classifier

A YAML-configurable RAG pipeline that builds a FAISS vector index from the GS1 GPC taxonomy, embeds product rows from a database, and classifies them using vector similarity + LLM inference.

## What it does

Three modes run in order:

1. **build-vectors** — reads `data/input/GS1.json`, embeds every GS1 taxonomy node, saves a FAISS index to disk
2. **embed-rows** — reads product rows from the database, embeds a concatenated text of selected columns, writes the vector back to the DB
3. **classify** — for each unclassified row, retrieves the closest GS1 nodes via vector similarity, builds a candidate list, calls an LLM to pick the best match, writes 6 GS1 columns back to the DB

## Prerequisites

- Python 3.11+
- An Azure OpenAI resource with an embedding deployment and a chat deployment (or swap to HuggingFace + another LLM — see [docs/CONFIG.md](docs/CONFIG.md))
- A database — Azure SQL or PostgreSQL (or swap to a local alternative)
- ODBC Driver 18 for SQL Server (Azure SQL only)

## Setup

```bash
pip install -e .
```

Copy `.env.example` to `.env` and fill in your API keys and database credentials. All tunables (batch sizes, thresholds, column names) live in `config.yaml`.

## Running

```bash
# 1. Build the FAISS index from GS1.json  (run once, or after changing embedding model)
python vectorize.py build-vectors

# 2. Embed product rows in the database  (run once, or after adding new rows)
python vectorize.py embed-rows

# 3. Classify unclassified rows
python main.py
```

## Tests

```bash
pytest tests/
```

## Documentation

- [docs/WORKFLOW.md](docs/WORKFLOW.md) — full step-by-step explanation of what each pipeline mode does, data flow, stage map, and debugging reference
- [docs/CONFIG.md](docs/CONFIG.md) — every `config.yaml` field explained, `.env` secrets reference, and full guide to all swappable components (embedding providers, vector stores, LLM providers, database connectors)
