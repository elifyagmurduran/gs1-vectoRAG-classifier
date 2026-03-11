"""Domain-specific exceptions for gs1-vectoRAG-classifier.

Hierarchy:
    PipelineError
    ├── ConfigError
    ├── EmbeddingError
    │   └── EmbeddingDimensionError
    ├── LLMError
    │   └── LLMResponseParseError
    ├── VectorStoreError
    │   └── VectorStoreNotLoadedError
    ├── DatabaseError
    │   └── DatabaseNotConnectedError
    ├── WorkflowError
    │   └── BatchError
    └── TemplateError

No imports from the rest of src/ — keep this module dependency-free.
"""
from __future__ import annotations


# ── Root ─────────────────────────────────────────────────────────────

class PipelineError(Exception):
    """Root exception for all domain errors in the pipeline.

    All other custom exceptions inherit from this so callers can use
    a single ``except PipelineError`` to catch everything domain-specific.
    """

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message

    def __str__(self) -> str:
        return self.message


# ── Config ───────────────────────────────────────────────────────────

class ConfigError(PipelineError):
    """Config file missing, malformed, or env var not set.

    Attrs:
        config_path: Path to the config file, if relevant.
        key: The YAML key or env var name that caused the error.
    """

    def __init__(self, message: str, config_path: str = "", key: str = ""):
        super().__init__(message)
        self.config_path = config_path
        self.key = key


# ── Embedding ────────────────────────────────────────────────────────

class EmbeddingError(PipelineError):
    """Embedding API call failed (after exhausting retries if any).

    Attrs:
        provider: Provider name, e.g. ``"azure_openai"`` or ``"huggingface"``.
        batch_index: Index of the batch that failed (0-based), if known.
    """

    def __init__(self, message: str, provider: str = "", batch_index: int | None = None):
        super().__init__(message)
        self.provider = provider
        self.batch_index = batch_index


class EmbeddingDimensionError(EmbeddingError):
    """Returned vector dimensionality does not match the configured value.

    Attrs:
        expected: The dimension count the pipeline was configured for.
        actual:   The dimension count actually returned by the provider.
    """

    def __init__(self, expected: int, actual: int, provider: str = ""):
        message = (
            f"Embedding dimension mismatch: expected {expected}, got {actual}"
            + (f" (provider: {provider})" if provider else "")
        )
        super().__init__(message, provider=provider)
        self.expected = expected
        self.actual = actual


# ── LLM ──────────────────────────────────────────────────────────────

class LLMError(PipelineError):
    """LLM call failed after exhausting all retry attempts.

    Attrs:
        deployment: Azure OpenAI deployment name.
        model: Model identifier string.
        attempt: The attempt number on which the final failure occurred.
    """

    def __init__(self, message: str, deployment: str = "", model: str = "",
                 attempt: int | None = None):
        super().__init__(message)
        self.deployment = deployment
        self.model = model
        self.attempt = attempt


class LLMResponseParseError(LLMError):
    """LLM response received but could not be parsed into the expected schema.

    Attrs:
        raw_response: The raw text that could not be parsed, truncated to
                      500 characters to avoid bloating log lines.
    """

    def __init__(self, message: str, raw_response: str = "",
                 deployment: str = "", model: str = ""):
        super().__init__(message, deployment=deployment, model=model)
        # Truncate to avoid polluting logs with huge responses
        self.raw_response = raw_response[:500] if raw_response else ""


# ── Vector Store ─────────────────────────────────────────────────────

class VectorStoreError(PipelineError):
    """FAISS index build, load, or search failed.

    Attrs:
        index_path: Path to the index file, if known.
    """

    def __init__(self, message: str, index_path: str = ""):
        super().__init__(message)
        self.index_path = index_path


class VectorStoreNotLoadedError(VectorStoreError):
    """A search was attempted before ``.load()`` was called."""

    def __init__(self):
        super().__init__("VectorStore.load() must be called before search.")


# ── Database ─────────────────────────────────────────────────────────

class DatabaseError(PipelineError):
    """Database connection or query failed.

    Attrs:
        server:    DB server hostname, if known.
        database:  Database name, if known.
        operation: Which operation failed — ``"connect"``, ``"query"``, ``"update"``, etc.
    """

    def __init__(self, message: str, server: str = "", database: str = "",
                 operation: str = ""):
        super().__init__(message)
        self.server = server
        self.database = database
        self.operation = operation


class DatabaseNotConnectedError(DatabaseError):
    """A DB operation was attempted before ``.connect()`` was called."""

    def __init__(self):
        super().__init__("DB operation attempted before connect() was called.",
                         operation="pre-connect")


# ── Workflow / Batch ─────────────────────────────────────────────────

class WorkflowError(PipelineError):
    """A workflow-level failure (not specific to a single batch)."""


class BatchError(WorkflowError):
    """A single batch failed during a workflow.

    Attrs:
        batch_num: 1-based batch number that failed.
        row_ids:   Primary key values of the rows in the failing batch, if known.
        cause:     The original exception that triggered the failure.
    """

    def __init__(self, message: str, batch_num: int = 0,
                 row_ids: list | None = None,
                 cause: Exception | None = None):
        super().__init__(message)
        self.batch_num = batch_num
        self.row_ids = row_ids or []
        self.cause = cause


# ── Template ─────────────────────────────────────────────────────────

class TemplateError(PipelineError):
    """Jinja2 template render failed.

    Attrs:
        template_file: Path to the template file that caused the error.
    """

    def __init__(self, message: str, template_file: str = ""):
        super().__init__(message)
        self.template_file = template_file
