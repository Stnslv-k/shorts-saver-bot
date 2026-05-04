from __future__ import annotations

import asyncio
import logging

from bot.search._filters import build_query, pick_best_url
from bot.search.base import SearchBackend

logger = logging.getLogger(__name__)


class DuckDuckGoBackend(SearchBackend):
    async def find_url(self, tool_name: str, context: str = "") -> str | None:
        query = build_query(tool_name, context)
        try:
            from duckduckgo_search import DDGS

            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(
                None,
                lambda: list(DDGS().text(query, max_results=5)),
            )
            return pick_best_url([r["href"] for r in results])
        except Exception as e:
            logger.warning("DuckDuckGo search failed for '%s': %s", tool_name, e)
        return None
