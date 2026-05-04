from bot.config import StorageConfig
from bot.storage.base import StorageBackend
from bot.storage.notion import NotionAdapter
from bot.storage.obsidian import ObsidianAdapter


def build_storage_backend(config: StorageConfig) -> StorageBackend:
    if config.backend == "notion":
        return NotionAdapter(config.notion)
    if config.backend == "obsidian":
        return ObsidianAdapter(config.obsidian)
    raise ValueError(f"Unknown storage backend: {config.backend!r}")
