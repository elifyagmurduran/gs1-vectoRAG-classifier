"""ResponseParser — parse LLM JSON response into classification results."""
from __future__ import annotations
import json
import re
from src.utils.logging import get_logger
from src.utils.exceptions import LLMResponseParseError

logger = get_logger("pipeline.transforms.response_parser")


class ResponseParser:
    """Parse the LLM's JSON response and map letter choices back to candidates.

    Expected LLM output: a JSON object containing an array of
    {"product_id": ..., "choice": "A"} objects.
    """

    def parse(self, raw_response: str, product_candidates: dict[int, list[dict]],
              target_columns: list[str]) -> list[dict]:
        """Parse LLM response and map choices to full GS1 hierarchy.

        Args:
            raw_response: The raw LLM response string (should be valid JSON).
            product_candidates: Mapping of product_id -> list of candidate dicts
                                (output of CandidateBuilder.build()).
            target_columns: List of 6 GS1 column names to populate, in order:
                            [gs1_segment, gs1_family, gs1_class, gs1_brick,
                             gs1_attribute, gs1_attribute_value].

        Returns:
            List of dicts, each with 'product_id' + the 6 target column values.
        """
        # Try direct JSON parse
        choices = self._parse_json(raw_response)

        if choices is None:
            # Fallback: regex extraction of first [...] block
            logger.warning("JSON parse failed, trying regex fallback")
            choices = self._parse_regex(raw_response)

        if choices is None:
            raise LLMResponseParseError(
                "Could not parse LLM response after JSON and regex attempts",
                raw_response=raw_response,
            )

        results = []
        for item in choices:
            product_id = item.get("product_id")
            choice_letter = item.get("choice", "").upper().strip()

            candidates = product_candidates.get(product_id, [])
            matched = self._find_candidate(candidates, choice_letter)

            if matched is None:
                logger.warning(f"Product {product_id}: choice '{choice_letter}' not found in candidates")
                continue
            else:
                row = self._extract_gs1_levels(matched, target_columns)

            row["product_id"] = product_id
            results.append(row)

        return results

    def _parse_json(self, raw: str) -> list[dict] | None:
        """Try to parse the response as JSON."""
        try:
            data = json.loads(raw)
            # Handle both {"results": [...]} and [...] formats
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                # Look for a list value in the dict
                for v in data.values():
                    if isinstance(v, list):
                        return v
            return None
        except (json.JSONDecodeError, TypeError):
            return None

    def _parse_regex(self, raw: str) -> list[dict] | None:
        """Fallback: extract the first JSON array [...] from the response."""
        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                return None
        return None

    def _find_candidate(self, candidates: list[dict], letter: str) -> dict | None:
        """Find the candidate with the matching letter."""
        for c in candidates:
            if c.get("letter", "").upper() == letter:
                return c
        return None

    def _extract_gs1_levels(self, candidate: dict, target_columns: list[str]) -> dict:
        """Map a candidate's hierarchy_path to the 6 GS1 columns.

        hierarchy_path has up to 4 entries (Segment, Family, Class, Brick).
        Attributes come from candidate['attributes'] if present.
        """
        path = candidate.get("hierarchy_path", [])
        attrs = candidate.get("attributes", [])

        # Map: target_columns[0]=segment, [1]=family, [2]=class, [3]=brick,
        #       [4]=attribute, [5]=attribute_value
        result = {}
        for i, col in enumerate(target_columns):
            if i < len(path):
                result[col] = path[i]
            elif i == 4 and attrs:
                # L5 attribute — take first L5 attribute title
                l5 = [a for a in attrs if a.get("level") == 5]
                result[col] = l5[0]["title"] if l5 else ""
            elif i == 5 and attrs:
                # L6 attribute value — take first L6 title
                l6 = [a for a in attrs if a.get("level") == 6]
                result[col] = l6[0]["title"] if l6 else ""
            else:
                result[col] = ""

        return result
