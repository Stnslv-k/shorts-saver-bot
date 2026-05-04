from __future__ import annotations

from bot.config import VisionConfig
from bot.vision.anthropic import AnthropicVisionAdapter
from bot.vision.base import VisionBackend
from bot.vision.openai import OpenAIVisionAdapter


def build_vision_backend(config: VisionConfig) -> VisionBackend:
    if config.backend == "openai":
        return OpenAIVisionAdapter(config.openai)
    if config.backend == "anthropic":
        return AnthropicVisionAdapter(config.anthropic)
    raise ValueError(f"Unknown vision backend: {config.backend!r}")
