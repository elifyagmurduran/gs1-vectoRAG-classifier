
"""Entry point for vector store operations: build-vectors and embed-rows."""
import argparse
import sys
from src.utils.logging import setup_logging, get_logger
from src.utils.console import console


def build_factory_for_mode(mode: str):
    """Build a minimal factory with only what the mode needs.

    This avoids importing all providers when only one mode runs.
    """
    from src.factory import ComponentFactory

    factory = ComponentFactory()

    # Both modes need embedding
    from src.services.embedding.azure_openai_embedder import AzureOpenAIEmbeddingProvider
    from src.services.embedding.huggingface import HuggingFaceEmbeddingProvider
    factory.register_embedding("azure_openai", AzureOpenAIEmbeddingProvider)
    factory.register_embedding("huggingface", HuggingFaceEmbeddingProvider)

    if mode == "build-vectors":
        from src.services.vectorstore.faiss_store import FAISSVectorStore
        factory.register_vectorstore("faiss", FAISSVectorStore)

    elif mode == "embed-rows":
        from src.services.db.azure_sql_connector import AzureSQLConnector
        from src.services.db.postgresql import PostgreSQLConnector
        factory.register_db("azure_sql", AzureSQLConnector)
        factory.register_db("postgresql", PostgreSQLConnector)

    return factory


def main():
    from src.config.models import load_config
    from src.utils.env import get_env
    from src.utils.exceptions import PipelineError

    parser = argparse.ArgumentParser(description="Vector store & embedding operations")
    subparsers = parser.add_subparsers(dest="mode", help="Operation mode")

    # build-vectors subcommand
    bv = subparsers.add_parser("build-vectors", help="Build FAISS index from taxonomy JSON")
    bv.add_argument("--config", default="config.yaml", help="Config file path")

    # embed-rows subcommand
    er = subparsers.add_parser("embed-rows", help="Embed database rows")
    er.add_argument("--config", default="config.yaml", help="Config file path")

    args = parser.parse_args()

    if args.mode is None:
        parser.print_help()
        sys.exit(1)

    # Initialise logging now that we know the mode
    mode_prefix = args.mode.replace("-", "_")  # build_vectors or embed_rows
    setup_logging(mode_prefix=mode_prefix)
    logger = get_logger("pipeline.vectorize")

    # Load config
    try:
        config = load_config(args.config)
    except PipelineError as e:
        console.error(str(e))
        sys.exit(1)

    console.pipeline_start(name=config.pipeline.name, config_path=args.config, mode=args.mode)
    logger.info("Pipeline: %s | Mode: %s", config.pipeline.name, args.mode)

    factory = build_factory_for_mode(args.mode)

    try:
        if args.mode == "build-vectors":
            _run_build_vectors(config, factory, get_env)
        elif args.mode == "embed-rows":
            _run_embed_rows(config, factory, get_env)
        console.pipeline_finished(success=True)
    except KeyboardInterrupt:
        console.interrupted()
        sys.exit(130)
    except PipelineError as e:
        console.error(str(e))
        logger.error("Pipeline failed: %s", e)
        console.pipeline_finished(success=False)
        sys.exit(1)
    except Exception as e:
        console.error(f"Unexpected error: {e}")
        logger.exception("Unexpected error")
        sys.exit(1)


def _run_build_vectors(config, factory, get_env):
    """Set up and run the build-vectors workflow."""
    from src.workflows.build_vectors import run_build_vectors

    # Create embedding provider — secrets from .env, tunables from config
    embedding_kwargs = _build_embedding_kwargs(config, get_env)
    embedding_provider = factory.create_embedding(config.embedding.type, **embedding_kwargs)

    # Create vector store
    vs_kwargs = {
        "output_dir": config.vector_store.output_dir,
        "filename_prefix": config.vector_store.filename_prefix,
        "lookup_metadata_fields": config.vector_store.lookup_metadata_fields,
        "embedding_dimensions": config.embedding.dimensions,
        "embedding_model": (
            get_env("AZURE_OPENAI_EMBEDDING_DEPLOYMENT")
            if config.embedding.type == "azure_openai"
            else (config.embedding.model_name or "unknown")
        ),
    }
    vector_store = factory.create_vectorstore(config.vector_store.type, **vs_kwargs)

    run_build_vectors(config, embedding_provider, vector_store)


def _run_embed_rows(config, factory, get_env):
    """Set up and run the embed-rows workflow."""
    from src.workflows.embed_rows import run_embed_rows

    # Create embedding provider — secrets from .env, tunables from config
    embedding_kwargs = _build_embedding_kwargs(config, get_env)
    embedding_provider = factory.create_embedding(config.embedding.type, **embedding_kwargs)

    # Create DB connector — secrets from .env, tunables from config
    db_kwargs = _build_db_kwargs(config, get_env)
    db_connector = factory.create_db(config.database.type, **db_kwargs)

    run_embed_rows(config, embedding_provider, db_connector)


def _build_embedding_kwargs(config, get_env):
    """Build kwargs for the embedding provider.

    Non-sensitive tunables come from config.yaml.
    Secrets (api_key, endpoint, deployment, api_version) come from .env.
    """
    kwargs = {
        "dimensions": config.embedding.dimensions,
        "batch_size": config.embedding.batch_size,
        "max_workers": config.embedding.max_workers,
        "max_attempts": config.system.retry.max_attempts,
        "backoff_factor": config.system.retry.backoff_factor,
        "min_wait": config.system.retry.min_wait,
        "max_wait": config.system.retry.max_wait,
    }
    if config.embedding.type == "azure_openai":
        kwargs.update({
            "api_key": get_env("AZURE_OPENAI_API_KEY"),
            "endpoint": get_env("AZURE_OPENAI_ENDPOINT"),
            "deployment": get_env("AZURE_OPENAI_EMBEDDING_DEPLOYMENT"),
            "api_version": get_env("AZURE_OPENAI_API_VERSION"),
        })
    elif config.embedding.type == "huggingface":
        kwargs["model_name"] = config.embedding.model_name
    return kwargs


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
