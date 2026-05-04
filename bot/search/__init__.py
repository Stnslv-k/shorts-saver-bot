from __future__ import annotations

from typing import TYPE_CHECKING

from bot.search.base import SearchBackend

if TYPE_CHECKING:
    from bot.config import AppConfig


def build_search_backend(config: "AppConfig") -> SearchBackend | None:
    if not config.search.enabled:
        return None
    if config.search.backend == "brave" and config.search.brave_api_key:
        from bot.search.brave import BraveSearchBackend
        return BraveSearchBackend(config.search.brave_api_key)
    from bot.search.duckduckgo import DuckDuckGoBackend
    return DuckDuckGoBackend()
