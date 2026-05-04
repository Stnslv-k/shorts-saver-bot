from __future__ import annotations

import logging

import httpx

from bot.search.base import SearchBackend

logger = logging.getLogger(__name__)


class BraveSearchBackend(SearchBackend):
    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def find_url(self, tool_name: str, context: str = "") -> str | None:
        query = f"{tool_name} official site"
        if context:
            query = f"{tool_name} {context} official site"
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    params={"q": query, "count": 3},
                    headers={
                        "Accept": "application/json",
                        "X-Subscription-Token": self._api_key,
                    },
                    timeout=10,
                )
                data = resp.json()
                results = data.get("web", {}).get("results", [])
                if results:
                    return results[0]["url"]
        except Exception as e:
            logger.warning("Brave search failed for '%s': %s", tool_name, e)
        return None
