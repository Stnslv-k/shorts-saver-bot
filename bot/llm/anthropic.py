from __future__ import annotations

import json
import logging
from typing import Any

import anthropic

from bot.config import AnthropicConfig
from bot.llm.base import EXTRACTION_PROMPT, LLMBackend
from bot.models import ExtractionResult

logger = logging.getLogger(__name__)


class AnthropicAdapter(LLMBackend):
    def __init__(self, config: AnthropicConfig) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=config.api_key)
        self._model = config.model

    async def extract(self, transcript: str) -> ExtractionResult:
        prompt = EXTRACTION_PROMPT.replace("{transcript}", transcript)

        message = await self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
        )

        raw_text = message.content[0].text if message.content else ""
        logger.debug("Anthropic raw response: %s", raw_text[:200])

        parsed = _parse_json_response(raw_text)
        return ExtractionResult.from_dict(parsed)


def _parse_json_response(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.error("Failed to parse LLM JSON response: %s\nText: %s", e, text[:500])
        raise ValueError(f"LLM returned invalid JSON: {e}") from e
