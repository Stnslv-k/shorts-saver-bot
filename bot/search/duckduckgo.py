from __future__ import annotations

import asyncio
import logging

from bot.search.base import SearchBackend

logger = logging.getLogger(__name__)


class DuckDuckGoBackend(SearchBackend):
    async def find_url(self, tool_name: str, context: str = "") -> str | None:
        query = f"{tool_name} official site"
        if context:
            query = f"{tool_name} {context} official site"
        try:
            from duckduckgo_search import DDGS

            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(
                None,
                lambda: list(DDGS().text(query, max_results=3)),
            )
            if results:
                return results[0]["href"]
        except Exception as e:
            logger.warning("DuckDuckGo search failed for '%s': %s", tool_name, e)
        return None
