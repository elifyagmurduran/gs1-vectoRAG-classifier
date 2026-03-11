
"""Entry point: classify mode. Run with: python main.py"""
import sys
from src.utils.logging import setup_logging, get_logger
from src.utils.console import console

# ── Logging initialized at module level, before anything else runs ──
setup_logging(mode_prefix="classify")
logger = get_logger("pipeline.main")


def main():
    from src.config.models import load_config
    from src.utils.env import get_env
    from src.factory import ComponentFactory
    from src.utils.exceptions import PipelineError

    config_path = "config.yaml"

    try:
        config = load_config(config_path)
    except PipelineError as e:
        logger.error("Config error: %s", e)
        console.error("Config Error", str(e))
        sys.exit(1)

    console.pipeline_start(
        name=config.pipeline.name,
        config_path=config_path,
        mode="classify",
    )

    logger.info("Pipeline: %s", config.pipeline.name)
    logger.info("Mode: classify")

    try:
        from src.services.embedding.azure_openai_embedder import AzureOpenAIEmbeddingProvider
        from src.services.embedding.huggingface import HuggingFaceEmbeddingProvider
        from src.services.vectorstore.faiss_store import FAISSVectorStore
        from src.services.llm.azure_openai_chat import AzureOpenAILLMProvider
        from src.services.db.azure_sql_connector import AzureSQLConnector
        from src.services.db.postgresql import PostgreSQLConnector
        from src.services.orchestrator import LLMOrchestratorService
        from src.workflows.classify import run_classify

        # Build factory — classify needs all 4 component types
        factory = ComponentFactory()
        factory.register_embedding("azure_openai", AzureOpenAIEmbeddingProvider)
        factory.register_embedding("huggingface", HuggingFaceEmbeddingProvider)
        factory.register_vectorstore("faiss", FAISSVectorStore)
        factory.register_llm("azure_openai", AzureOpenAILLMProvider)
        factory.register_db("azure_sql", AzureSQLConnector)
        factory.register_db("postgresql", PostgreSQLConnector)

        # ── Create vector store and load the saved index ──────────────
        vs_kwargs = {
            "output_dir": config.vector_store.output_dir,
            "filename_prefix": config.vector_store.filename_prefix,
            "lookup_metadata_fields": config.vector_store.lookup_metadata_fields,
            "embedding_dimensions": config.embedding.dimensions,
        }
        vector_store = factory.create_vectorstore(config.vector_store.type, **vs_kwargs)
        vector_store.load()

        # ── Create LLM provider ──────────────────────────────────────
        llm_kwargs = _build_llm_kwargs(config, get_env)
        llm_provider = factory.create_llm(config.llm.type, **llm_kwargs)

        # ── Create orchestrator ──────────────────────────────────────
        orchestrator = LLMOrchestratorService(config, vector_store, llm_provider)

        # ── Create DB connector ──────────────────────────────────────
        db_kwargs = _build_db_kwargs(config, get_env)
        db_connector = factory.create_db(config.database.type, **db_kwargs)

        # ── Run classify workflow ────────────────────────────────────
        run_classify(config, orchestrator, db_connector)
        console.pipeline_finished(success=True)

    except KeyboardInterrupt:
        console.interrupted()
        logger.warning("Pipeline interrupted by user")
        sys.exit(130)
    except PipelineError as e:
        logger.error("Pipeline error: %s", e, exc_info=True)
        console.error("Pipeline Error", str(e))
        console.pipeline_finished(success=False)
        sys.exit(1)
    except Exception as e:
        logger.exception("Unexpected error: %s", e)
        console.error("Unexpected Error", str(e))
        console.pipeline_finished(success=False)
        sys.exit(1)


def _build_llm_kwargs(config, get_env):
    """Build kwargs for the LLM provider.

    Non-sensitive tunables come from config.yaml.
    Secrets (api_key, endpoint, deployment, api_version) come from .env.
    """
    return {
        "api_key": get_env("AZURE_OPENAI_API_KEY"),
        "endpoint": get_env("AZURE_OPENAI_ENDPOINT"),
        "deployment": get_env("AZURE_OPENAI_CHAT_DEPLOYMENT"),
        "api_version": get_env("AZURE_OPENAI_API_VERSION"),
        "max_completion_tokens": config.llm.max_completion_tokens,
        "max_attempts": config.system.retry.max_attempts,
        "backoff_factor": config.system.retry.backoff_factor,
        "min_wait": config.system.retry.min_wait,
        "max_wait": config.system.retry.max_wait,
    }


def _build_db_kwargs(config, get_env):
    """Build kwargs for the database connector.

    Non-sensitive tunables (schema, table, pk) come from config.yaml.
    Secrets (server, credentials) come from .env.
    """
    kwargs = {
        "schema_name": config.database.schema_name,
        "table": config.database.table,
        "primary_key": config.database.primary_key,
    }
    if config.database.type == "azure_sql":
        kwargs.update({
            "server": get_env("AZURE_SQL_SERVER"),
            "database": get_env("AZURE_SQL_DATABASE"),
            "client_id": get_env("AZURE_SQL_CLIENT_ID"),
            "client_secret": get_env("AZURE_SQL_CLIENT_SECRET"),
        })
    elif config.database.type == "postgresql":
        kwargs.update({
            "host": get_env("PG_HOST"),
            "port": int(get_env("PG_PORT")),
            "database": get_env("PG_DATABASE"),
            "username": get_env("PG_USERNAME"),
            "password": get_env("PG_PASSWORD"),
        })
    return kwargs


if __name__ == "__main__":
    main()

