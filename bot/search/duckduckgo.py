from __future__ import annotations

import asyncio
import logging

from bot.search._filters import build_query, pick_best_url
from bot.search.base import SearchBackend

logger = logging.getLogger(__name__)


class DuckDuckGoBackend(SearchBackend):
    async def find_url(self, tool_name: str, context: str = "", video_context: str = "") -> str | None:
        try:
            from duckduckgo_search import DDGS

            loop = asyncio.get_event_loop()

            queries = [
                build_query(tool_name, context, video_context),
                f'"{tool_name}" tool product',
                f"{tool_name} {video_context}".strip(),
            ]

            for i, query in enumerate(queries):
                if i > 0:
                    await asyncio.sleep(0.5)
                results = await loop.run_in_executor(
                    None,
                    lambda q=query: list(DDGS().text(q, max_results=5)),
                )
                url = pick_best_url([r["href"] for r in results], tool_name)
                if url:
                    return url

        except Exception as e:
            logger.warning("DuckDuckGo search failed for '%s': %s", tool_name, e)
        return None
