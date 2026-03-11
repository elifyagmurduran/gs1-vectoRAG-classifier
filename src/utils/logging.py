"""Configure structured logging: colored console handler + verbose timestamped file handler.

Usage:
    # In main.py, at module level before def main():
    from src.utils.logging import setup_logging, get_logger
    setup_logging(mode_prefix="classify")
    logger = get_logger("pipeline.main")

    # In every other module:
    from src.utils.logging import get_logger
    logger = get_logger("pipeline.services.orchestrator")
"""
from __future__ import annotations
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# ── Double-init guard ────────────────────────────────────────────────
_INITIALIZED: bool = False

# ── ANSI colour codes ────────────────────────────────────────────────
_RESET  = "\033[0m"
_GREY   = "\033[90m"
_BLUE   = "\033[34m"
_YELLOW = "\033[33m"
_RED    = "\033[31m"

# Third-party loggers that are too verbose for console output
_NOISY_LOGGERS = [
    "azure.core.pipeline.policies.http_logging_policy",
    "azure.identity",
    "azure.identity._internal.get_token_mixin",
    "openai",
    "httpx",
    "urllib3",
    "requests",
]


class _ColorConsoleFormatter(logging.Formatter):
    """Single-line colored formatter for the console handler.

    Format:
        [•]  2026-03-09 14:30:22  pipeline.workflow.classify   Batch 1/50 started
    """

    _LEVEL_PREFIX = {
        logging.DEBUG:    (_GREY,   "[·]"),
        logging.INFO:     (_BLUE,   "[•]"),
        logging.WARNING:  (_YELLOW, "[⚠]"),
        logging.ERROR:    (_RED,    "[✗]"),
        logging.CRITICAL: (_RED,    "[✗✗]"),
    }
    _USE_COLOR: bool = sys.stdout.isatty()

    def format(self, record: logging.LogRecord) -> str:
        color, prefix = self._LEVEL_PREFIX.get(record.levelno, (_RESET, "[?]"))
        ts = self.formatTime(record, "%Y-%m-%d %H:%M:%S")
        name = record.name[:40]
        msg = record.getMessage()
        if record.exc_info:
            msg += "\n" + self.formatException(record.exc_info)
        if self._USE_COLOR:
            return f"{color}{prefix}{_RESET}  {ts}  {name:<40}  {msg}"
        return f"{prefix}  {ts}  {name:<40}  {msg}"


class _VerboseFileFormatter(logging.Formatter):
    """Verbose formatter for the file handler — milliseconds + source location.

    Format:
        2026-03-09 14:30:22.451 | DEBUG    | pipeline.services.orchestrator     | orchestrator.py:87  | RAG search: ...
    """

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S")
        ms = int(record.msecs)
        level = record.levelname.ljust(8)
        name = record.name[:35].ljust(35)
        location = f"{record.filename}:{record.lineno}"
        msg = record.getMessage()
        if record.exc_info:
            msg += "\n" + self.formatException(record.exc_info)
        return f"{ts}.{ms:03d} | {level} | {name} | {location:<25} | {msg}"


def setup_logging(
    mode_prefix: str = "pipeline",
    level: str = "INFO",
    log_file: str | None = None,
    log_dir: str = "logs",
) -> None:
    """Set up the root logger with a colored console handler and a verbose file handler.

    Safe to call multiple times — subsequent calls are no-ops due to the
    ``_INITIALIZED`` guard.

    Args:
        mode_prefix: Used to name the log file, e.g. ``"classify"`` →
                     ``logs/20260309_143022_classify.log``.
        level:       Console log level (DEBUG/INFO/WARNING/ERROR).
                     Falls back to the ``LOG_LEVEL`` environment variable, then INFO.
        log_file:    Explicit log file path; skips auto-naming when provided.
        log_dir:     Directory for auto-named log files.
    """
    global _INITIALIZED
    if _INITIALIZED:
        return
    _INITIALIZED = True

    # Resolve console level — env var overrides default, explicit arg overrides env var
    env_level = os.environ.get("LOG_LEVEL", "").upper()
    resolved_level = getattr(logging, level.upper(), None) \
        or getattr(logging, env_level, logging.INFO)

    # Resolve log file path
    if log_file is None:
        log_file = os.environ.get("LOG_FILE")
    if log_file is None:
        Path(log_dir).mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = str(Path(log_dir) / f"{ts}_{mode_prefix}.log")

    # ── Handlers ────────────────────────────────────────────────

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(resolved_level)
    console_handler.setFormatter(_ColorConsoleFormatter())

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(_VerboseFileFormatter())

    # ── Root logger ──────────────────────────────────────────────
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)  # let handlers do their own filtering
    root.handlers = [console_handler, file_handler]

    # ── Silence noisy third-party loggers on console ─────────────
    for lib_name in _NOISY_LOGGERS:
        lib_logger = logging.getLogger(lib_name)
        lib_logger.setLevel(logging.WARNING)
        lib_logger.handlers = [file_handler]
        lib_logger.propagate = False

    root.debug("Logging initialized — file: %s", log_file)


def get_logger(name: str) -> logging.Logger:
    """Return a named logger, initializing logging with defaults if not yet set up.

    Args:
        name: Logger name, e.g. ``"pipeline.services.orchestrator"``.

    Returns:
        A :class:`logging.Logger` instance.
    """
    if not _INITIALIZED:
        setup_logging()
    return logging.getLogger(name)