from bot.config import LLMConfig
from bot.llm.anthropic import AnthropicAdapter
from bot.llm.base import LLMBackend
from bot.llm.ollama import OllamaAdapter
from bot.llm.openai import OpenAIAdapter
from bot.llm.openrouter import OpenRouterSmartBackend


def build_llm_backend(config: LLMConfig) -> LLMBackend:
    if config.backend == "openrouter":
        if not config.openrouter.api_key:
            raise ValueError("openrouter.api_key is required when backend is 'openrouter'")
        fallback_name = config.fallback or "openai"
        fallback = _make_backend(fallback_name, config)
        return OpenRouterSmartBackend(
            api_key=config.openrouter.api_key,
            fallback=fallback,
            max_free_models=config.openrouter.max_free_models,
        )

    primary = _make_backend(config.backend, config)
    if config.fallback:
        fallback = _make_backend(config.fallback, config)
        return FallbackLLMBackend(primary, fallback)
    return primary


def _make_backend(name: str, config: LLMConfig) -> LLMBackend:
    if name == "ollama":
        return OllamaAdapter(config.ollama)
    if name == "openai":
        return OpenAIAdapter(config.openai)
    if name == "anthropic":
        return AnthropicAdapter(config.anthropic)
    raise ValueError(f"Unknown LLM backend: {name!r}")


class FallbackLLMBackend(LLMBackend):
    def __init__(self, primary: LLMBackend, fallback: LLMBackend) -> None:
        self._primary = primary
        self._fallback = fallback

    async def extract(self, transcript: str):
        import logging
        logger = logging.getLogger(__name__)
        try:
            return await self._primary.extract(transcript)
        except Exception as e:
            logger.warning("Primary LLM backend failed (%s), trying fallback", e)
            return await self._fallback.extract(transcript)
