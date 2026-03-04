"""Base tool abstraction."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Tool(ABC):
    """Abstract base for all worker tools."""

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        ...

    @abstractmethod
    def parameters(self) -> dict[str, Any]:
        """Return JSON Schema for tool parameters."""
        ...

    @abstractmethod
    async def execute(self, arguments: dict[str, Any]) -> str:
        ...

    def schema(self) -> dict[str, Any]:
        """Return OpenAI function schema."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters(),
        }
