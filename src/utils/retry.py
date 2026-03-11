"""Retry helpers using tenacity, configured from RetryConfig."""
import logging
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)
from src.utils.logging import get_logger

logger = get_logger("pipeline.retry")


def make_retry_decorator(max_attempts: int = 3, backoff_factor: float = 1.5,
                         min_wait: float = 30, max_wait: float = 120,
                         retry_on: tuple = (Exception,)):
    """Create a tenacity retry decorator from config values.

    Args:
        max_attempts: Maximum number of tries.
        backoff_factor: Multiplier for exponential backoff.
        min_wait: Minimum wait in seconds.
        max_wait: Maximum wait in seconds.
        retry_on: Tuple of exception types to retry on.

    Returns:
        A tenacity retry decorator.
    """
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=backoff_factor, min=min_wait, max=max_wait),
        retry=retry_if_exception_type(retry_on),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )