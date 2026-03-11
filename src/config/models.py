"""Pydantic config models and YAML loader with env-var interpolation."""
from __future__ import annotations
import yaml
from pathlib import Path
from pydantic import BaseModel, Field
from typing import Optional
from src.utils.env import resolve_env_vars
from src.utils.exceptions import ConfigError


# ── Retry ────────────────────────────────────────────────────────────
class RetryConfig(BaseModel):
    max_attempts: int = 3
    backoff_factor: float = 1.5
    min_wait: float = 30.0
    max_wait: float = 120.0


# ── System ───────────────────────────────────────────────────────────
class SystemConfig(BaseModel):
    log_level: str = "INFO"
    max_workers: int = 5
    batch_size: int = 256
    retry: RetryConfig = Field(default_factory=RetryConfig)


# ── Pipeline ─────────────────────────────────────────────────────────
class PipelineConfig(BaseModel):
    name: str = "gs1-vectoRAG-classifier"
    description: str = ""


# ── Source ───────────────────────────────────────────────────────────
class SourceConfig(BaseModel):
    type: str = "file_json"
    path: str = "data/input/GS1.json"
    encoding: str = "utf-8"
    parser: str = "gs1"
    batch_size: int

# ── Embedding ────────────────────────────────────────────────────────
# Secrets (api_key, endpoint, deployment, api_version) live in .env only.
class EmbeddingConfig(BaseModel):
    type: str = "azure_openai"
    dimensions: int = 1024
    batch_size: int = 256
    max_workers: int = 5
    model_name: Optional[str] = None  # For HuggingFace


# ── Vector Store ─────────────────────────────────────────────────────
class VectorStoreConfig(BaseModel):
    type: str = "faiss"
    output_dir: str = "data/vector_store"
    filename_prefix: str = "gs1"
    lookup_metadata_fields: list[str] = Field(default_factory=lambda: [
        "level", "code", "title", "hierarchy_path", "hierarchy_string"
    ])


# ── Database ─────────────────────────────────────────────────────────
# Secrets (server, database, credentials) live in .env only.
class DatabaseConfig(BaseModel):
    type: str = "azure_sql"
    schema_name: str = "playground"
    table: str = "promo_bronze"
    primary_key: str = "id"


# ── Row Embedding (for embed-rows) ───────────────────────────────────
class RowEmbeddingConfig(BaseModel):
    batch_size: int
    columns: list[str] = Field(default_factory=list)
    separator: str = " * "
    target_column: str = "embedding_context"


# ── LLM ──────────────────────────────────────────────────────────────
# Secrets (api_key, endpoint, deployment, api_version) live in .env only.
class LLMConfig(BaseModel):
    type: str = "azure_openai"
    max_completion_tokens: int = 4096


# ── Classification / RAG ────────────────────────────────────────────
class ClassificationConfig(BaseModel):
    rag_top_k: int = 30
    batch_size: int
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


# ── Root Config ──────────────────────────────────────────────────────
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
    """Load YAML config, resolve env vars, validate.

    Args:
        config_path: Path to main config YAML.

    Returns:
        Validated AppConfig object.

    Raises:
        ConfigError: If config file does not exist or env var is missing.
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