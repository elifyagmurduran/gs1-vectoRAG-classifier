
"""Abstract base class for LLM providers."""
from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """Interface for LLM chat completion calls."""

    @abstractmethod
    def chat(self, system_message: str, user_message: str,
             response_format: dict | None = None) -> dict:
        """Send a chat completion request.

        Args:
            system_message: The system prompt.
            user_message: The user prompt.
            response_format: Optional format constraint (e.g., {"type": "json_object"}).

        Returns:
            Dict with keys: 'content' (str), 'usage' (dict with prompt_tokens,
            completion_tokens, total_tokens).
        """
        ...

