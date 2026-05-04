from __future__ import annotations

import base64
import logging

import anthropic

from bot.config import AnthropicVisionConfig
from bot.vision.base import VISION_PROMPT, VisionBackend

logger = logging.getLogger(__name__)


class AnthropicVisionAdapter(VisionBackend):
    def __init__(self, config: AnthropicVisionConfig) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=config.api_key)
        self._model = config.model

    async def analyze_frames(self, frame_paths: list[str]) -> str:
        content: list[dict] = []

        for path in frame_paths:
            b64 = _encode_image(path)
            content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": b64,
                    },
                }
            )

        content.append({"type": "text", "text": VISION_PROMPT})

        message = await self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            messages=[{"role": "user", "content": content}],
        )

        result = message.content[0].text if message.content else ""
        logger.debug("Anthropic vision response (%d chars)", len(result))
        return result


def _encode_image(path: str) -> str:
    with open(path, "rb") as f:
        return base64.standard_b64encode(f.read()).decode("utf-8")
