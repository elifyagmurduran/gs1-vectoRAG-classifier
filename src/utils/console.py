"""Human-readable terminal output for gs1-vectoRAG-classifier.

This module is completely separate from the logging system. It writes only
via ``print()`` and never via ``logging``. Import the module-level singleton:

    from src.utils.console import console

Rule of thumb:
    logger.*  → status/diagnostic messages  →  log file + console (via logging.py)
    console.* → user-facing visual layout   →  terminal only, always readable
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass

# ── Unicode capability check ─────────────────────────────────────────
try:
    "└─✓❌⚠️🚀📋🔍🪙💾⏱".encode(sys.stdout.encoding or "utf-8")
    _UNICODE = True
except (UnicodeEncodeError, LookupError):
    _UNICODE = False

# ── Symbols (with ASCII fallbacks) ───────────────────────────────────
_S_BOX_TL   = "┌─" if _UNICODE else "/--"
_S_BOX_BL   = "└─" if _UNICODE else "\\-"
_S_BOX_SIDE = "│"  if _UNICODE else "|"
_S_BOX_TL_F = "┌"  if _UNICODE else "/"
_S_BOX_TR_F = "┐"  if _UNICODE else "\\"
_S_BOX_BL_F = "└"  if _UNICODE else "\\"
_S_BOX_BR_F = "┘"  if _UNICODE else "/"
_S_BOX_H    = "─"  if _UNICODE else "-"
_S_OK       = "✓"  if _UNICODE else "OK"
_S_FAIL     = "✗"  if _UNICODE else "FAIL"
_S_WARN     = "⚠️"  if _UNICODE else "(!!)"
_S_ROCKET   = "🚀" if _UNICODE else ">>"
_S_ERR      = "❌" if _UNICODE else "[X]"
_S_INFO     = "📋" if _UNICODE else "[i]"
_S_RAG      = "🔍" if _UNICODE else "[?]"
_S_TOKEN    = "🪙" if _UNICODE else "[$]"
_S_DB       = "💾" if _UNICODE else "[DB]"
_S_TIME     = "⏱"  if _UNICODE else "[t]"
_S_STEP     = "└─" if _UNICODE else "  \\_"
_S_FILL     = "█"  if _UNICODE else "#"
_S_EMPTY    = "░"  if _UNICODE else "-"

_BOX_WIDTH = 66  # inner width of full-width header box

# ── GS1 category abbreviations ───────────────────────────────────────
_CATEGORY_ABBREV = [
    ("Prepared/Processed", "Prep."),
    ("Beverages - Non-Alcoholic", "Non-Alc. Bev."),
    ("Beverages - Alcoholic", "Alc. Bev."),
    ("Health & Beauty", "H&B"),
    ("Household & Office", "HH&O"),
]


@dataclass
class ConsoleConfig:
    """Runtime configuration for the Console class, read from env vars."""
    colors: bool = True
    max_products_shown: int = 3
    max_product_name_len: int = 35
    verbose: bool = False

    @classmethod
    def from_env(cls) -> "ConsoleConfig":
        def _bool(var: str, default: bool) -> bool:
            val = os.environ.get(var, "").lower()
            if val in ("1", "true", "yes"):
                return True
            if val in ("0", "false", "no"):
                return False
            return default

        return cls(
            colors=_bool("CONSOLE_COLORS", True),
            max_products_shown=int(os.environ.get("CONSOLE_MAX_PRODUCTS", "3")),
            max_product_name_len=int(os.environ.get("CONSOLE_MAX_PRODUCT_LEN", "35")),
            verbose=_bool("CONSOLE_VERBOSE", False),
        )


class Console:
    """Structured, emoji-annotated terminal output for the classification pipeline.

    All output goes through ``_print()`` which wraps ``print(flush=True)`` with
    a ``UnicodeEncodeError`` fallback so box-drawing characters degrade gracefully.

    Instantiate via ``ConsoleConfig.from_env()`` or pass a config directly.
    Import the module-level singleton instead of creating your own instance:

        from src.utils.console import console
    """

    def __init__(self, config: ConsoleConfig | None = None):
        self._cfg = config or ConsoleConfig()

    # ── Internal helpers ─────────────────────────────────────────

    def _print(self, *args, **kwargs) -> None:
        """``print(flush=True)`` with UnicodeEncodeError fallback."""
        try:
            print(*args, **kwargs, flush=True)
        except UnicodeEncodeError:
            safe = " ".join(str(a) for a in args).encode(
                sys.stdout.encoding or "utf-8", errors="replace"
            ).decode(sys.stdout.encoding or "utf-8")
            print(safe, flush=True)

    def _truncate(self, text: str, max_len: int | None = None) -> str:
        limit = max_len if max_len is not None else self._cfg.max_product_name_len
        if len(text) > limit:
            return text[:limit - 1] + "…"
        return text

    @staticmethod
    def _shorten_category(category: str) -> str:
        for full, short in _CATEGORY_ABBREV:
            category = category.replace(full, short)
        return category

    @staticmethod
    def _fmt_elapsed(seconds: float) -> str:
        """Format elapsed seconds as ``4.1s``, ``2m 3s``, or ``1h 4m``."""
        s = int(seconds)
        if s < 60:
            return f"{seconds:.1f}s"
        if s < 3600:
            return f"{s // 60}m {s % 60}s"
        return f"{s // 3600}h {(s % 3600) // 60}m"

    # ── Phase indicators ────────────────────────────────────────

    def start(self, title: str, detail: str | None = None) -> None:
        """🚀 Pipeline / phase started."""
        line = f"  {_S_ROCKET}  {title}"
        if detail:
            line += f"  —  {detail}"
        self._print(line)

    def success(self, title: str, detail: str | None = None) -> None:
        """✅ Successful completion."""
        line = f"  {_S_OK}  {title}"
        if detail:
            line += f"  —  {detail}"
        self._print(line)

    def error(self, title: str, detail: str | None = None) -> None:
        """❌ Error occurred."""
        line = f"  {_S_ERR}  {title}"
        if detail:
            line += f"  —  {detail}"
        self._print(line)

    def warning(self, title: str, detail: str | None = None) -> None:
        """⚠️  Non-fatal warning."""
        line = f"  {_S_WARN}  {title}"
        if detail:
            line += f"  —  {detail}"
        self._print(line)

    def info(self, title: str, detail: str | None = None) -> None:
        """📋 Informational line."""
        line = f"  {_S_INFO}  {title}"
        if detail:
            line += f"  —  {detail}"
        self._print(line)

    def step(self, message: str, done: bool = False) -> None:
        """└─ Indented step, optionally marked done."""
        suffix = f" {_S_OK}" if done else " …"
        self._print(f"  {_S_STEP}  {message}{suffix}")

    # ── Pipeline lifecycle ───────────────────────────────────────

    def pipeline_start(self, name: str, config_path: str, mode: str) -> None:
        """Print full-width header box at pipeline start.

        Example:
            ┌──────────────────────────────────────────────────────────────┐
            │  🚀  GS1 Product Classifier                                   │
            │      Mode: classify  |  Config: config.yaml                   │
            └──────────────────────────────────────────────────────────────┘
        """
        w = _BOX_WIDTH
        h = _S_BOX_H
        self._print(f"{_S_BOX_TL_F}{h * (w + 2)}{_S_BOX_TR_F}")
        title_line = f"  {_S_ROCKET}  {name}"
        self._print(f"{_S_BOX_SIDE}  {title_line:<{w}}  {_S_BOX_SIDE}")
        sub_line = f"      Mode: {mode}  |  Config: {config_path}"
        self._print(f"{_S_BOX_SIDE}  {sub_line:<{w}}  {_S_BOX_SIDE}")
        self._print(f"{_S_BOX_BL_F}{h * (w + 2)}{_S_BOX_BR_F}")

    def classification_start(self, total_rows: int, batch_size: int,
                              batch_count: int) -> None:
        """Print a summary of the upcoming classification run.

        Example:
            📋  Classification run
                Rows to classify : 2,540
                Batch size       : 20
                Total batches    : 127
        """
        self._print(f"\n{_S_INFO}  Classification run")
        self._print(f"    Rows to classify : {total_rows:,}")
        self._print(f"    Batch size       : {batch_size}")
        self._print(f"    Total batches    : {batch_count}")

    def batch_start(self, batch_num: int, total_batches: int, row_count: int,
                    product_names: list[str] | None = None) -> None:
        """Open the batch box.

        Example:
            ┌─ Batch 3/127  (20 rows)
            │  Gouda 500g, Coca-Cola 1.5L, Heinz Ketchup 500ml  +17 more
            │
        """
        self._print(f"\n{_S_BOX_TL} Batch {batch_num}/{total_batches}  ({row_count} rows)")
        if product_names:
            shown = [self._truncate(n) for n in product_names[:self._cfg.max_products_shown]]
            remainder = row_count - len(shown)
            preview = ", ".join(shown)
            if remainder > 0:
                preview += f"  +{remainder} more"
            self._print(f"{_S_BOX_SIDE}  {preview}")
        self._print(f"{_S_BOX_SIDE}")

    def batch_result(self, classified: int, requested: int, elapsed_s: float,
                     category_counts: dict[str, int] | None = None) -> None:
        """Close the batch box with results.

        Example:
            │  ✓ 20/20 classified in 4.1s
            │    Dairy & Eggs ×6  |  Beverages ×5  |  Condiments ×4  |  +3 more
            └────────────────────────────────────────────────────────────────
        """
        self._print(f"{_S_BOX_SIDE}  {_S_OK} {classified}/{requested} classified in "
                    f"{self._fmt_elapsed(elapsed_s)}")
        if category_counts:
            sorted_cats = sorted(category_counts.items(), key=lambda x: x[1], reverse=True)
            shown_cats = sorted_cats[:4]
            extra = len(sorted_cats) - len(shown_cats)
            cat_str = "  |  ".join(
                f"{self._shorten_category(k)} ×{v}" for k, v in shown_cats
            )
            if extra > 0:
                cat_str += f"  |  +{extra} more"
            self._print(f"{_S_BOX_SIDE}    {cat_str}")
        self._print(f"{_S_BOX_BL}{_S_BOX_H * 64}")

    def progress_bar(self, current: int, total: int, label: str = "Progress") -> None:
        """Print an inline progress bar (overwrites the current line with ``\\r``).

        Example:
              Progress  [████████████████░░░░░░░░░░░░░░░░]  60/127  (47.2%)
        """
        if total <= 0:
            return
        bar_width = 32
        filled = int(bar_width * current / total)
        empty = bar_width - filled
        bar = _S_FILL * filled + _S_EMPTY * empty
        pct = current / total * 100
        line = f"\r  {label}  [{bar}]  {current}/{total}  ({pct:.1f}%)"
        try:
            print(line, end="", flush=True)
            if current >= total:
                print()  # newline once complete
        except UnicodeEncodeError:
            safe = line.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(
                sys.stdout.encoding or "utf-8"
            )
            print(safe, end="", flush=True)
            if current >= total:
                print()

    def classification_summary(self, total: int, classified: int, failed: int,
                                elapsed_s: float) -> None:
        """Print the final classification run summary.

        Example:
            ✅  Classification complete
                Total rows     : 2,540
                Classified     : 2,531
                Failed/skipped : 9
                Total time     : 8m 42s
        """
        self._print(f"\n  {_S_OK}  Classification complete")
        self._print(f"    Total rows     : {total:,}")
        self._print(f"    Classified     : {classified:,}")
        self._print(f"    Failed/skipped : {failed:,}")
        self._print(f"    Total time     : {self._fmt_elapsed(elapsed_s)}")

    def pipeline_finished(self, success: bool = True) -> None:
        """Print the final pipeline status line."""
        if success:
            self._print(f"\n  {_S_OK}  Pipeline finished successfully.")
        else:
            self._print(f"\n  {_S_ERR}  Pipeline finished with errors.")

    def interrupted(self) -> None:
        """Print an interruption notice (e.g. on KeyboardInterrupt)."""
        self._print(f"\n  {_S_WARN}  Pipeline interrupted by user.")

    # ── GS1 verbose detail methods ───────────────────────────────
    # These are only printed when ConsoleConfig.verbose is True.

    def gs1_rag_details(self, rag_hits: list[dict]) -> None:
        """Print RAG hit scores inside the batch box.

        Example:
            │  🔍 RAG hits (top 5)
            │     0.924  Cheese - Natural > Dairy & Eggs > ...
        """
        if not self._cfg.verbose:
            return
        self._print(f"{_S_BOX_SIDE}  {_S_RAG} RAG hits (top {len(rag_hits)})")
        for hit in rag_hits:
            score = hit.get("score", 0.0)
            label = self._truncate(hit.get("hierarchy_string", hit.get("title", "")), 55)
            self._print(f"{_S_BOX_SIDE}     {score:.3f}  {label}")

    def gs1_candidates(self, candidates: dict[int, list[dict]]) -> None:
        """Print candidate letters and scores inside the batch box.

        Example:
            │  📋 Candidates
            │     A  0.924  Cheese - Natural
        """
        if not self._cfg.verbose:
            return
        self._print(f"{_S_BOX_SIDE}  {_S_INFO} Candidates")
        for _pid, cands in candidates.items():
            for c in cands:
                letter = c.get("letter", "?")
                score = c.get("score", 0.0)
                label = self._truncate(c.get("title", ""), 50)
                self._print(f"{_S_BOX_SIDE}     {letter}  {score:.3f}  {label}")

    def gs1_prompt(self, prompt_text: str) -> None:
        """Print the first 300 chars of the prompt inside the batch box."""
        if not self._cfg.verbose:
            return
        preview = self._truncate(prompt_text.replace("\n", " "), 300)
        self._print(f"{_S_BOX_SIDE}  📤 Prompt  {preview}")

    def gs1_tokens(self, prompt: int, completion: int, total: int) -> None:
        """Print token usage inside the batch box.

        Example:
            │  🪙 Tokens — prompt: 1,204  |  completion: 87  |  total: 1,291
        """
        if not self._cfg.verbose:
            return
        self._print(
            f"{_S_BOX_SIDE}  {_S_TOKEN} Tokens — "
            f"prompt: {prompt:,}  |  completion: {completion:,}  |  total: {total:,}"
        )

    def gs1_db_write(self, updates: list[dict]) -> None:
        """Print a DB write confirmation inside the batch box.

        Example:
            │  💾 DB write — 20 rows
        """
        if not self._cfg.verbose:
            return
        self._print(f"{_S_BOX_SIDE}  {_S_DB} DB write — {len(updates)} rows")

    def gs1_timing(self, rag_s: float, llm_s: float, db_s: float,
                   total_s: float) -> None:
        """Print timing breakdown inside the batch box.

        Example:
            │  ⏱ Timing — RAG: 0.3s  |  LLM: 3.6s  |  DB: 0.2s  |  total: 4.1s
        """
        if not self._cfg.verbose:
            return
        self._print(
            f"{_S_BOX_SIDE}  {_S_TIME} Timing — "
            f"RAG: {self._fmt_elapsed(rag_s)}  |  "
            f"LLM: {self._fmt_elapsed(llm_s)}  |  "
            f"DB: {self._fmt_elapsed(db_s)}  |  "
            f"total: {self._fmt_elapsed(total_s)}"
        )


# ── Module-level singleton ───────────────────────────────────────────
console = Console(ConsoleConfig.from_env())
