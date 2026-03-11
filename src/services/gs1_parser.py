"""GS1 GPC JSON parser — flattens hierarchical taxonomy into Documents."""
from __future__ import annotations
import json
from pathlib import Path
from src.dto import Document
from src.utils.logging import get_logger

logger = get_logger("pipeline.gs1_parser")

LEVEL_NAMES = {1: "Segment", 2: "Family", 3: "Class", 4: "Brick", 5: "Attribute", 6: "AttributeValue"}


class GS1Parser:
    """Parse a GS1 GPC JSON file into a flat list of Documents.

    Each node in the tree becomes one Document with:
    - id: the GS1 code
    - text: hierarchy path joined by " > ", then " | definition", then " | Excludes: ..."
    - metadata: level, code, title, hierarchy_path, hierarchy_string, definition, excludes, active, source
    """

    def __init__(self, file_path: str, encoding: str = "utf-8"):
        """
        Args:
            file_path: Path to the GS1 JSON file (e.g., "data/input/GS1.json").
            encoding: File encoding.
        """
        self.file_path = Path(file_path)
        self.encoding = encoding

    def parse(self) -> list[Document]:
        """Parse the JSON file and return a flat list of Documents.

        Returns:
            List of Document objects, one per node in the hierarchy.

        Raises:
            FileNotFoundError: If the JSON file does not exist.
            KeyError: If expected JSON structure is missing.
        """
        logger.info(f"Parsing GS1 JSON: {self.file_path}")

        with open(self.file_path, "r", encoding=self.encoding) as f:
            raw = json.load(f)

        schema = raw.get("Schema")
        if schema is None:
            raise KeyError("GS1 JSON missing top-level 'Schema' key")

        documents: list[Document] = []
        # Schema is a list of top-level segment nodes
        nodes = schema if isinstance(schema, list) else [schema]
        for node in nodes:
            self._traverse(node, hierarchy_path=[], documents=documents)

        logger.info(f"Parsed {len(documents)} documents from GS1 JSON")
        return documents

    def _traverse(self, node: dict, hierarchy_path: list[str],
                  documents: list[Document]) -> None:
        """Recursively walk the tree and emit a Document for each node.

        Args:
            node: Current tree node dict.
            hierarchy_path: List of ancestor titles leading to this node.
            documents: Accumulator list — Documents are appended in place.
        """
        code = str(node.get("Code", ""))
        title = node.get("Title", "").strip()
        level = node.get("Level", 0)
        definition = (node.get("Definition") or "").strip()
        excludes = (node.get("DefinitionExcludes") or "").strip()
        active = node.get("Active", True)

        current_path = hierarchy_path + [title]
        hierarchy_string = " > ".join(current_path)

        # Build embedding text: "Segment > Family > Class | definition | Excludes: ..."
        text_parts = [hierarchy_string]
        if definition:
            text_parts.append(definition)
        if excludes:
            text_parts.append(f"Excludes: {excludes}")
        text = " | ".join(text_parts)

        doc = Document(
            id=code,
            text=text,
            metadata={
                "source": "gs1_gpc",
                "level": level,
                "code": code,
                "title": title,
                "hierarchy_path": current_path.copy(),
                "hierarchy_string": hierarchy_string,
                "definition": definition,
                "excludes": excludes,
                "active": active,
            },
        )
        documents.append(doc)

        # Recurse into children
        children = node.get("Childs", [])
        for child in children:
            self._traverse(child, current_path, documents)
