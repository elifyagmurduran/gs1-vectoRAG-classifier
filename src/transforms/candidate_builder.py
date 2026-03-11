"""CandidateBuilder — groups RAG results by L4 brick path into lettered candidate options."""
from __future__ import annotations
import string
from src.utils.logging import get_logger

logger = get_logger("pipeline.transforms.candidate_builder")


class CandidateBuilder:
    """Build lettered candidate options from RAG search results.

    Groups results by their L4 path (Segment > Family > Class > Brick),
    deduplicates, collects L5/L6 attribute info, sorts by best score,
    and assigns letters A-Z.
    """

    def build(self, rag_results: list[dict]) -> list[dict]:
        """Build lettered candidates from RAG search results for one product.

        Args:
            rag_results: List of dicts from VectorStore.search(), each with
                         'id', 'score', 'metadata' (which contains 'level',
                         'hierarchy_path', 'hierarchy_string', 'title', 'code').

        Returns:
            List of candidate dicts, each with:
                'letter': str (A, B, C, ...),
                'hierarchy_path': list[str] (L1-L4 titles),
                'hierarchy_string': str ("Seg > Fam > Cls > Brk"),
                'score': float (best score in this group),
                'attributes': list[dict] (L5/L6 info if found).
        """
        # [STAGE: CANDIDATE_FILTER]
        # Groups RAG results by L4 brick path, sorts, and assigns letters A-Z.
        # IndexFlatL2: lower score = better match.

        # Group by L4 brick path (first 4 levels of hierarchy_path)
        groups: dict[str, dict] = {}  # key = L4 path string -> group info

        for result in rag_results:
            meta = result.get("metadata", {})
            hierarchy = meta.get("hierarchy_path", [])
            level = meta.get("level", 0)

            # Build the L4 key (first 4 levels)
            l4_path = hierarchy[:4]
            l4_key = " > ".join(l4_path)

            if not l4_key:
                continue

            if l4_key not in groups:
                groups[l4_key] = {
                    "hierarchy_path": l4_path,
                    "hierarchy_string": l4_key,
                    "best_score": result["score"],
                    "attributes": [],
                }
            else:
                # Keep best score: lowest score wins (L2 distance — lower = more similar)
                if result["score"] < groups[l4_key]["best_score"]:
                    groups[l4_key]["best_score"] = result["score"]

            # Collect L5/L6 attribute info
            if level >= 5:
                attr_info = {
                    "level": level,
                    "code": meta.get("code", ""),
                    "title": meta.get("title", ""),
                }
                # Avoid duplicate attributes
                existing_codes = {a["code"] for a in groups[l4_key]["attributes"]}
                if attr_info["code"] not in existing_codes:
                    groups[l4_key]["attributes"].append(attr_info)

        # Sort ascending by best score (lower L2 distance = better match first).
        sorted_groups = sorted(groups.values(), key=lambda g: g["best_score"], reverse=False)

        # Assign letters (no cap — all groups are passed to the LLM)
        letters = list(string.ascii_uppercase)
        candidates = []
        for i, group in enumerate(sorted_groups):
            candidates.append({
                "letter": letters[i] if i < len(letters) else f"Z{i}",
                "hierarchy_path": group["hierarchy_path"],
                "hierarchy_string": group["hierarchy_string"],
                "score": group["best_score"],
                "attributes": group["attributes"],
            })

        logger.debug(f"Built {len(candidates)} candidates")
        return candidates
