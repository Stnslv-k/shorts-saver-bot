from __future__ import annotations

import json
import logging
from typing import Any

from openai import AsyncOpenAI

from bot.config import OpenAIConfig
from bot.llm.base import EXTRACTION_PROMPT, LLMBackend
from bot.models import ExtractionResult

logger = logging.getLogger(__name__)


class OpenAIAdapter(LLMBackend):
    def __init__(self, config: OpenAIConfig) -> None:
        self._client = AsyncOpenAI(api_key=config.api_key)
        self._model = config.model

    async def extract(self, transcript: str) -> tuple[ExtractionResult, str]:
        prompt = EXTRACTION_PROMPT.replace("{transcript}", transcript)

        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.1,
        )

        raw_text = response.choices[0].message.content or ""
        logger.debug("OpenAI raw response: %s", raw_text[:200])

        parsed: dict[str, Any] = json.loads(raw_text)
        return ExtractionResult.from_dict(parsed), self._model
