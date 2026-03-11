"""LLM Orchestrator Service — combines RAG search, candidate building,
prompt construction, LLM call, and response parsing into one classification flow."""
from __future__ import annotations
import json
from src.config.models import AppConfig
from src.services.vectorstore.base import VectorStore
from src.services.llm.base import LLMProvider
from src.transforms.candidate_builder import CandidateBuilder
from src.transforms.response_parser import ResponseParser
from src.utils.templates import render_template, FALLBACK_SYSTEM, FALLBACK_CLASSIFICATION
from src.utils.logging import get_logger

logger = get_logger("pipeline.services.orchestrator")


class LLMOrchestratorService:
    """Orchestrates the full RAG-powered classification flow.

    Responsibilities:
        1. Load and hold the vector store (FAISS index + lookup).
        2. For each product: RAG similarity search using its embedding.
        3. Build lettered candidate options (CandidateBuilder).
        4. Construct the LLM prompt (Jinja2 templates).
        5. Call the LLM with JSON mode forced.
        6. Parse the response (ResponseParser).
        7. Return classification results for a batch.

    Args:
        config: Validated app config.
        vector_store: Initialized and loaded vector store.
        llm_provider: Initialized LLM provider.
    """

    def __init__(self, config: AppConfig, vector_store: VectorStore,
                 llm_provider: LLMProvider):
        self._config = config
        self._vector_store = vector_store
        self._llm = llm_provider

        cls_cfg = config.classification
        self._candidate_builder = CandidateBuilder()
        self._response_parser = ResponseParser()

        self._top_k = cls_cfg.rag_top_k
        self._prompt_columns = cls_cfg.prompt_columns
        self._target_columns = cls_cfg.target_columns
        self._system_template = cls_cfg.system_template_file
        self._classification_template = cls_cfg.prompt_template_file

    def classify_batch(self, rows: list[dict]) -> list[dict]:
        """Classify a batch of product rows.

        Uses a single vectorized FAISS search for all products in the batch
        (one index.search() call) rather than N individual calls.

        Args:
            rows: List of product row dicts. Each must have:
                  - 'id' (or whatever the PK is)
                  - 'embedding_context' (JSON string or list of floats)
                  - prompt columns (product_name, etc.)

        Returns:
            List of result dicts, each with 'product_id' + 6 GS1 target columns.
        """
        # [STAGE: PARSE_EMBEDDINGS]
        # Extract valid rows and their embeddings; skip rows with missing/invalid embeddings.
        valid_rows: list[dict] = []
        embeddings: list[list[float]] = []

        for row in rows:
            product_id = row.get("id")
            embedding_raw = row.get("embedding_context")
            if embedding_raw is None:
                logger.warning(f"Product {product_id}: no embedding_context, skipping")
                continue
            if isinstance(embedding_raw, str):
                embedding = json.loads(embedding_raw)
            elif isinstance(embedding_raw, list):
                embedding = embedding_raw
            else:
                logger.warning(f"Product {product_id}: unexpected embedding type, skipping")
                continue
            valid_rows.append(row)
            embeddings.append(embedding)

        if not valid_rows:
            logger.warning("No products with valid embeddings in this batch")
            return []

        # [STAGE: VECTOR_SEARCH]
        # Single batched FAISS call for all products — one index.search(matrix, top_k).
        # Returns one result list per product; normalization handled inside search_batch().
        all_rag_results = self._vector_store.search_batch(
            query_vectors=embeddings,
            top_k=self._top_k,
        )

        # [STAGE: CANDIDATE_FILTER]
        # Per-product: group RAG results by L4 brick, filter by score threshold,
        # deduplicate, sort, assign letters A-Z.
        products_for_prompt: list[dict] = []
        product_candidates_map: dict = {}

        for row, rag_results in zip(valid_rows, all_rag_results):
            product_id = row.get("id")
            candidates = self._candidate_builder.build(rag_results)
            context = {col: str(row.get(col, "") or "") for col in self._prompt_columns}
            product_candidates_map[product_id] = candidates
            products_for_prompt.append({
                "product_id": product_id,
                "context": context,
                "candidates": candidates,
            })

        if not products_for_prompt:
            logger.warning("No products to classify in this batch")
            return []

        # [STAGE: PROMPT_BUILD]
        # Renders Jinja2 templates into system + user messages.
        # system_message = gs1_system.j2, user_message = gs1_classification.j2.
        system_message = render_template(
            self._system_template, FALLBACK_SYSTEM
        )
        user_message = render_template(
            self._classification_template, FALLBACK_CLASSIFICATION,
            products=products_for_prompt,
        )

        logger.debug(f"Prompt length: {len(user_message)} chars for {len(products_for_prompt)} products")

        # [STAGE: LLM_CALL]
        # Calls the LLM with JSON mode. Response is a JSON array of {product_id, choice}.
        llm_response = self._llm.chat(
            system_message=system_message,
            user_message=user_message,
            response_format={"type": "json_object"},
        )

        logger.info(f"LLM tokens used: {llm_response['usage']}")

        # [STAGE: RESPONSE_PARSE]
        # Maps LLM letter choice back to the full candidate metadata,
        # extracts gs1_segment/family/class/brick/attribute/attribute_value.
        return self._response_parser.parse(
            raw_response=llm_response["content"],
            product_candidates=product_candidates_map,
            target_columns=self._target_columns,
        )
