from __future__ import annotations

import base64
import logging
from pathlib import Path

from openai import AsyncOpenAI

from bot.config import OpenAIVisionConfig
from bot.vision.base import VISION_PROMPT, VisionBackend

logger = logging.getLogger(__name__)


class OpenAIVisionAdapter(VisionBackend):
    def __init__(self, config: OpenAIVisionConfig) -> None:
        self._client = AsyncOpenAI(api_key=config.api_key)
        self._model = config.model

    async def analyze_frames(self, frame_paths: list[str]) -> str:
        content: list[dict] = [{"type": "text", "text": VISION_PROMPT}]

        for path in frame_paths:
            b64 = _encode_image(path)
            content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{b64}",
                        "detail": "high",
                    },
                }
            )

        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": content}],
            max_tokens=1024,
        )

        result = response.choices[0].message.content or ""
        logger.debug("OpenAI vision response (%d chars)", len(result))
        return result


def _encode_image(path: str) -> str:
    with open(path, "rb") as f:
        return base64.standard_b64encode(f.read()).decode("utf-8")
