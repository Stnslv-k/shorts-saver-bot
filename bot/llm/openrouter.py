from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field

import httpx

from bot.llm.base import EXTRACTION_PROMPT, LLMBackend
from bot.models import ExtractionResult

logger = logging.getLogger(__name__)

TOP_MODELS_URL = "https://shir-man.com/api/free-llm/top-models"
CACHE_TTL_SECONDS = 3600
OPENROUTER_BASE = "https://openrouter.ai/api/v1"


@dataclass
class _ModelCache:
    models: list[str] = field(default_factory=list)
    fallback_id: str = "openrouter/free"
    fetched_at: float = 0.0


_cache = _ModelCache()


class _RateLimitError(Exception):
    pass


async def _fetch_top_models(api_key: str, max_models: int = 3) -> list[str]:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(TOP_MODELS_URL)
            resp.raise_for_status()
            data = resp.json()

        suitable = [
            m["id"] for m in data.get("models", [])
            if m.get("healthStatus") == "passed"
            and m.get("supportsResponseFormat") is True
        ]

        _cache.fallback_id = data.get("fallback", {}).get("id", "openrouter/free")
        _cache.models = suitable[:max_models]
        _cache.fetched_at = time.monotonic()

        logger.info("OpenRouter: loaded %d free models: %s", len(_cache.models), _cache.models)
        return _cache.models

    except Exception as e:
        logger.warning("Failed to fetch top models: %s. Using openrouter/free fallback.", e)
        return []


async def _get_models(api_key: str, max_models: int) -> tuple[list[str], str]:
    if time.monotonic() - _cache.fetched_at > CACHE_TTL_SECONDS:
        await _fetch_top_models(api_key, max_models)
    return _cache.models, _cache.fallback_id


async def _call_openrouter(api_key: str, model_id: str, prompt: str) -> ExtractionResult:
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{OPENROUTER_BASE}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "HTTP-Referer": "https://github.com/Stnslv-k/shorts-saver-bot",
                "X-Title": "Shorts Saver Bot",
                "Content-Type": "application/json",
            },
            json={
                "model": model_id,
                "messages": [{"role": "user", "content": prompt}],
                "response_format": {"type": "json_object"},
                "temperature": 0.1,
            },
        )

        if resp.status_code == 429:
            raise _RateLimitError(f"Rate limited on {model_id}")
        resp.raise_for_status()

        content = resp.json()["choices"][0]["message"]["content"]
        return ExtractionResult.from_dict(json.loads(content))


class OpenRouterSmartBackend(LLMBackend):
    """Tries ranked free OpenRouter models before falling back to the configured fallback backend."""

    def __init__(self, api_key: str, fallback: LLMBackend, max_free_models: int = 3) -> None:
        self._api_key = api_key
        self._fallback = fallback
        self._max = max_free_models

    async def extract(self, transcript: str) -> ExtractionResult:
        prompt = EXTRACTION_PROMPT.replace("{transcript}", transcript)
        models, managed_fallback = await _get_models(self._api_key, self._max)

        for model_id in models:
            try:
                result = await _call_openrouter(self._api_key, model_id, prompt)
                logger.info("OpenRouter: success with %s", model_id)
                return result
            except _RateLimitError:
                logger.warning("OpenRouter: rate limited on %s, trying next", model_id)
            except Exception as e:
                logger.warning("OpenRouter: %s failed (%s), trying next", model_id, e)

        try:
            result = await _call_openrouter(self._api_key, managed_fallback, prompt)
            logger.info("OpenRouter: success with managed fallback %s", managed_fallback)
            return result
        except Exception as e:
            logger.warning("OpenRouter: managed fallback failed (%s), using configured fallback", e)

        logger.info("OpenRouter: all free models exhausted, using configured fallback")
        return await self._fallback.extract(transcript)
