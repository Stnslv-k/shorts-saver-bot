from __future__ import annotations

from abc import ABC, abstractmethod

from bot.models import KnowledgeEntry


class StorageBackend(ABC):
    @abstractmethod
    async def save(self, entry: KnowledgeEntry) -> str:
        """Save a knowledge entry. Returns a human-readable confirmation string."""
        ...

    @abstractmethod
    async def list_recent(self, n: int = 5) -> list[KnowledgeEntry]:
        """Return up to n most recently saved entries."""
        ...
