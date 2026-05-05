from __future__ import annotations

import asyncio
import logging

from bot.search._filters import GOOGLE_SITE_QUERY, build_query, is_google_context, pick_best_url
from bot.search.base import SearchBackend

logger = logging.getLogger(__name__)


class DuckDuckGoBackend(SearchBackend):
    async def find_url(self, tool_name: str, context: str = "", video_context: str = "") -> str | None:
        query = build_query(tool_name, context, video_context)
        try:
            from duckduckgo_search import DDGS

            loop = asyncio.get_event_loop()

            # For Google-context tools try site-restricted search first.
            if is_google_context(video_context):
                google_query = f'"{tool_name}" {GOOGLE_SITE_QUERY}'
                results = await loop.run_in_executor(
                    None,
                    lambda: list(DDGS().text(google_query, max_results=5)),
                )
                url = pick_best_url([r["href"] for r in results])
                if url:
                    return url
                await asyncio.sleep(0.5)

            results = await loop.run_in_executor(
                None,
                lambda: list(DDGS().text(query, max_results=5)),
            )
            url = pick_best_url([r["href"] for r in results])
            if url:
                return url

            # Retry without quotes around tool name
            fallback_query = build_query(tool_name, context, video_context).replace(
                f'"{tool_name}"', tool_name
            )
            await asyncio.sleep(0.5)
            results = await loop.run_in_executor(
                None,
                lambda: list(DDGS().text(fallback_query, max_results=5)),
            )
            return pick_best_url([r["href"] for r in results])
        except Exception as e:
            logger.warning("DuckDuckGo search failed for '%s': %s", tool_name, e)
        return None
