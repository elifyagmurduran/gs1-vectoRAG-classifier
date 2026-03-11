"""Load and render Jinja2 prompt templates."""
from __future__ import annotations
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, BaseLoader, TemplateError as JinjaTemplateError
from src.utils.logging import get_logger
from src.utils.exceptions import TemplateError

logger = get_logger("pipeline.utils.templates")

# ── Hardcoded fallback templates ─────────────────────────────────
# Used when config sets template paths to null or the file is missing.
FALLBACK_SYSTEM = (
    "You are a product classification assistant. Classify grocery/retail products "
    "using the GS1 GPC standard. Respond with JSON: "
    '{"results": [{"product_id": <id>, "choice": "<letter>"}]}'
)

FALLBACK_CLASSIFICATION = (
    "Classify these products into GS1 GPC categories.\n\n"
    "{% for product in products %}"
    "--- Product {{ product.product_id }} ---\n"
    "{{ product.context | tojson }}\n\n"
    "Candidates:\n"
    "{% for c in product.candidates %}"
    "[{{ c.letter }}] {{ c.hierarchy_string }}\n"
    "{% endfor %}\n"
    "{% endfor %}\n"
    'Respond with: {"results": [{"product_id": <id>, "choice": "<letter>"}]}'
)


def render_template(template_path: str | None, fallback: str, **kwargs) -> str:
    """Load a Jinja2 template from file, or use the fallback string.

    Args:
        template_path: Path to the .j2 template file (None to use fallback).
        fallback: Fallback Jinja2 template string.
        **kwargs: Variables to pass to the template.

    Returns:
        Rendered template string.
    """
    if template_path and Path(template_path).exists():
        template_dir = str(Path(template_path).parent)
        template_name = Path(template_path).name
        env = Environment(loader=FileSystemLoader(template_dir))
        template = env.get_template(template_name)
        logger.debug(f"Using template file: {template_path}")
    else:
        if template_path:
            logger.warning(f"Template file not found: {template_path}, using fallback")
        env = Environment(loader=BaseLoader())
        template = env.from_string(fallback)

    try:
        return template.render(**kwargs)
    except JinjaTemplateError as exc:
        raise TemplateError(
            f"Template render failed: {exc}",
            template_file=template_path or "<inline fallback>",
        ) from exc
