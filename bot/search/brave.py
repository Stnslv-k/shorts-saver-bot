from __future__ import annotations

import logging

import httpx

from bot.search._filters import build_query, pick_best_url
from bot.search.base import SearchBackend

logger = logging.getLogger(__name__)


class BraveSearchBackend(SearchBackend):
    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def find_url(self, tool_name: str, context: str = "", video_context: str = "") -> str | None:
        query = build_query(tool_name, context, video_context)
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    params={"q": query, "count": 5},
                    headers={
                        "Accept": "application/json",
                        "X-Subscription-Token": self._api_key,
                    },
                    timeout=10,
                )
                data = resp.json()
                results = data.get("web", {}).get("results", [])
                return pick_best_url([r["url"] for r in results])
        except Exception as e:
            logger.warning("Brave search failed for '%s': %s", tool_name, e)
        return None
