from __future__ import annotations

from abc import ABC, abstractmethod

from bot.models import KnowledgeEntry


class StorageBackend(ABC):
    @abstractmethod
    async def save(self, entry: KnowledgeEntry) -> tuple[str, str]:
        """Save a knowledge entry.

        Returns (confirmation_message, storage_ref) where storage_ref is an
        opaque string that can be passed to delete_by_ref later.
        """
        ...

    @abstractmethod
    async def list_recent(self, n: int = 5) -> list[KnowledgeEntry]:
        """Return up to n most recently saved entries."""
        ...

    async def delete_by_ref(self, ref: str) -> bool:
        """Delete an entry identified by its storage_ref. Returns True if deleted."""
        return False
