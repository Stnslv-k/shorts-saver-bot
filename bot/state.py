from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from bot.config import AppConfig
    from bot.llm.base import LLMBackend
    from bot.search.base import SearchBackend
    from bot.storage.base import StorageBackend
    from bot.vision.base import VisionBackend

logger = logging.getLogger(__name__)


@dataclass
class BotState:
    config: AppConfig
    llm_backend: LLMBackend | None = field(default=None)
    storage_backend: StorageBackend | None = field(default=None)
    vision_backend: VisionBackend | None = field(default=None)
    search_backend: SearchBackend | None = field(default=None)

    def rebuild_backends(self) -> None:
        from bot.llm import build_llm_backend
        from bot.search import build_search_backend
        from bot.storage import build_storage_backend
        from bot.vision import build_vision_backend

        try:
            self.llm_backend = build_llm_backend(self.config.llm)
            logger.info("LLM backend built: %s", self.config.llm.backend)
        except Exception as e:
            logger.warning("Failed to build LLM backend: %s", e)
            self.llm_backend = None

        try:
            self.storage_backend = build_storage_backend(self.config.storage)
            logger.info("Storage backend built: %s", self.config.storage.backend)
        except Exception as e:
            logger.warning("Failed to build storage backend: %s", e)
            self.storage_backend = None

        if self.config.vision.enabled:
            try:
                self.vision_backend = build_vision_backend(self.config.vision)
                logger.info("Vision backend built: %s", self.config.vision.backend)
            except Exception as e:
                logger.warning("Failed to build vision backend: %s", e)
                self.vision_backend = None
        else:
            self.vision_backend = None

        try:
            self.search_backend = build_search_backend(self.config)
            if self.search_backend is not None:
                logger.info("Search backend built: %s", self.config.search.backend)
        except Exception as e:
            logger.warning("Failed to build search backend: %s", e)
            self.search_backend = None

    def is_ready(self) -> bool:
        return self.llm_backend is not None and self.storage_backend is not None
