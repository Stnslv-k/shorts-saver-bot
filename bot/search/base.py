from __future__ import annotations

from abc import ABC, abstractmethod


class SearchBackend(ABC):
    @abstractmethod
    async def find_url(self, tool_name: str, context: str = "") -> str | None:
        """Search for the official URL of a tool. Returns URL string or None."""
        ...
