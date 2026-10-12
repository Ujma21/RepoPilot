
from abc import ABC, abstractmethod
from typing import Any


class LLMProvider(ABC):
    """Common interface for all RepoPilot LLM providers."""

    @abstractmethod
    def chat(self, messages: list[dict[str, str]]) -> str:
        """Return a text response from the model."""
        raise NotImplementedError

    @abstractmethod
    def chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Return a normalized response containing text and tool calls."""
        raise NotImplementedError