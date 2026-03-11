"""ComponentFactory — registry mapping config type strings to concrete classes."""
from __future__ import annotations
from src.utils.logging import get_logger
from src.utils.exceptions import PipelineError

logger = get_logger("pipeline.factory")


class ComponentFactory:
    """Central registry for all swappable component implementations.

    Usage:
        factory = ComponentFactory()
        factory.register_embedding("azure_openai", AzureOpenAIEmbeddingProvider)
        provider = factory.create_embedding("azure_openai", **config_params)
    """

    def __init__(self):
        self._embedding_registry: dict[str, type] = {}
        self._vectorstore_registry: dict[str, type] = {}
        self._llm_registry: dict[str, type] = {}
        self._db_registry: dict[str, type] = {}

    # ── Registration ──────────────────────────────────────────────

    def register_embedding(self, type_name: str, cls: type) -> None:
        logger.debug(f"Registered embedding provider: {type_name}")
        self._embedding_registry[type_name] = cls

    def register_vectorstore(self, type_name: str, cls: type) -> None:
        logger.debug(f"Registered vector store: {type_name}")
        self._vectorstore_registry[type_name] = cls

    def register_llm(self, type_name: str, cls: type) -> None:
        logger.debug(f"Registered LLM provider: {type_name}")
        self._llm_registry[type_name] = cls

    def register_db(self, type_name: str, cls: type) -> None:
        logger.debug(f"Registered database connector: {type_name}")
        self._db_registry[type_name] = cls

    # ── Creation ──────────────────────────────────────────────────

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
            available = ", ".join(registry.keys()) or "(none)"
            raise PipelineError(
                f"Unknown {category} type: '{type_name}'. "
                f"Available: {available}"
            )
        logger.info(f"Creating {category}: {type_name}")
        return cls(**kwargs)


def build_default_factory() -> ComponentFactory:
    """Build a factory pre-loaded with all built-in implementations.

    Call this once at startup. Import and register all concrete classes here.
    To add a new provider: import it, add one register line.
    """
    factory = ComponentFactory()

    # ── Embedding providers ───────────────────────────────────────
    from src.services.embedding.azure_openai_embedder import AzureOpenAIEmbeddingProvider
    from src.services.embedding.huggingface import HuggingFaceEmbeddingProvider
    factory.register_embedding("azure_openai", AzureOpenAIEmbeddingProvider)
    factory.register_embedding("huggingface", HuggingFaceEmbeddingProvider)

    # ── Vector stores ─────────────────────────────────────────────
    from src.services.vectorstore.faiss_store import FAISSVectorStore
    factory.register_vectorstore("faiss", FAISSVectorStore)

    # ── LLM providers ─────────────────────────────────────────────
    from src.services.llm.azure_openai_chat import AzureOpenAILLMProvider
    factory.register_llm("azure_openai", AzureOpenAILLMProvider)

    # ── Database connectors ───────────────────────────────────────
    from src.services.db.azure_sql_connector import AzureSQLConnector
    from src.services.db.postgresql import PostgreSQLConnector
    factory.register_db("azure_sql", AzureSQLConnector)
    factory.register_db("postgresql", PostgreSQLConnector)

    return factory