from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from bot.config import OllamaConfig
from bot.llm.base import EXTRACTION_PROMPT, LLMBackend
from bot.models import ExtractionResult

logger = logging.getLogger(__name__)


class OllamaAdapter(LLMBackend):
    def __init__(self, config: OllamaConfig) -> None:
        self._url = config.url.rstrip("/")
        self._model = config.model

    async def extract(self, transcript: str) -> tuple[ExtractionResult, str]:
        prompt = EXTRACTION_PROMPT.replace("{transcript}", transcript)

        payload: dict[str, Any] = {
            "model": self._model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(f"{self._url}/api/generate", json=payload)
            response.raise_for_status()
            data = response.json()

        raw_text = data.get("response", "")
        logger.debug("Ollama raw response: %s", raw_text[:200])

        parsed = _parse_json_response(raw_text)
        return ExtractionResult.from_dict(parsed), f"{self._model} (local)"


def _parse_json_response(text: str) -> dict[str, Any]:
    text = text.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.error("Failed to parse LLM JSON response: %s\nText: %s", e, text[:500])
        raise ValueError(f"LLM returned invalid JSON: {e}") from e
