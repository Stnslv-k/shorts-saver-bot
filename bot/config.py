from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class OllamaConfig:
    url: str = "http://localhost:11434"
    model: str = "llama3.1:8b"


@dataclass
class OpenAIConfig:
    api_key: str = ""
    model: str = "gpt-4o-mini"


@dataclass
class AnthropicConfig:
    api_key: str = ""
    model: str = "claude-haiku-4-5-20251001"


@dataclass
class LLMConfig:
    backend: str = "ollama"
    fallback: str | None = None
    ollama: OllamaConfig = field(default_factory=OllamaConfig)
    openai: OpenAIConfig = field(default_factory=OpenAIConfig)
    anthropic: AnthropicConfig = field(default_factory=AnthropicConfig)


@dataclass
class NotionConfig:
    api_key: str = ""
    database_id: str = ""


@dataclass
class ObsidianConfig:
    vault_path: str = ""


@dataclass
class StorageConfig:
    backend: str = "notion"
    notion: NotionConfig = field(default_factory=NotionConfig)
    obsidian: ObsidianConfig = field(default_factory=ObsidianConfig)


@dataclass
class OpenAIVisionConfig:
    api_key: str = ""
    model: str = "gpt-4o"


@dataclass
class AnthropicVisionConfig:
    api_key: str = ""
    model: str = "claude-haiku-4-5-20251001"


@dataclass
class VisionConfig:
    enabled: bool = False
    backend: str = "openai"
    openai: OpenAIVisionConfig = field(default_factory=OpenAIVisionConfig)
    anthropic: AnthropicVisionConfig = field(default_factory=AnthropicVisionConfig)


@dataclass
class BotConfig:
    token: str = ""
    password: str = ""


@dataclass
class AppConfig:
    bot: BotConfig = field(default_factory=BotConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    vision: VisionConfig = field(default_factory=VisionConfig)


def _parse_llm(raw: dict[str, Any]) -> LLMConfig:
    ollama_raw = raw.get("ollama", {})
    openai_raw = raw.get("openai", {})
    anthropic_raw = raw.get("anthropic", {})
    return LLMConfig(
        backend=raw.get("backend", "ollama"),
        fallback=raw.get("fallback"),
        ollama=OllamaConfig(
            url=ollama_raw.get("url", "http://localhost:11434"),
            model=ollama_raw.get("model", "llama3.1:8b"),
        ),
        openai=OpenAIConfig(
            api_key=openai_raw.get("api_key", os.getenv("OPENAI_API_KEY", "")),
            model=openai_raw.get("model", "gpt-4o-mini"),
        ),
        anthropic=AnthropicConfig(
            api_key=anthropic_raw.get("api_key", os.getenv("ANTHROPIC_API_KEY", "")),
            model=anthropic_raw.get("model", "claude-haiku-4-5-20251001"),
        ),
    )


def _parse_storage(raw: dict[str, Any]) -> StorageConfig:
    notion_raw = raw.get("notion", {})
    obsidian_raw = raw.get("obsidian", {})
    return StorageConfig(
        backend=raw.get("backend", "notion"),
        notion=NotionConfig(
            api_key=notion_raw.get("api_key", os.getenv("NOTION_API_KEY", "")),
            database_id=notion_raw.get("database_id", ""),
        ),
        obsidian=ObsidianConfig(
            vault_path=obsidian_raw.get("vault_path", ""),
        ),
    )


def _parse_vision(raw: dict[str, Any], llm_raw: dict[str, Any]) -> VisionConfig:
    openai_raw = raw.get("openai", {})
    anthropic_raw = raw.get("anthropic", {})

    # Allow vision to reuse llm api keys as fallback
    llm_openai_key = llm_raw.get("openai", {}).get("api_key", os.getenv("OPENAI_API_KEY", ""))
    llm_anthropic_key = llm_raw.get("anthropic", {}).get("api_key", os.getenv("ANTHROPIC_API_KEY", ""))

    return VisionConfig(
        enabled=bool(raw.get("enabled", False)),
        backend=raw.get("backend", "openai"),
        openai=OpenAIVisionConfig(
            api_key=openai_raw.get("api_key", llm_openai_key),
            model=openai_raw.get("model", "gpt-4o"),
        ),
        anthropic=AnthropicVisionConfig(
            api_key=anthropic_raw.get("api_key", llm_anthropic_key),
            model=anthropic_raw.get("model", "claude-haiku-4-5-20251001"),
        ),
    )


def load_config(path: str | Path = "config.yaml") -> AppConfig:
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path) as f:
        raw = yaml.safe_load(f) or {}

    bot_raw = raw.get("bot", {})
    llm_raw = raw.get("llm", {})
    return AppConfig(
        bot=BotConfig(
            token=bot_raw.get("token", os.getenv("BOT_TOKEN", "")),
            password=bot_raw.get("password", os.getenv("BOT_PASSWORD", "")),
        ),
        llm=_parse_llm(llm_raw),
        storage=_parse_storage(raw.get("storage", {})),
        vision=_parse_vision(raw.get("vision", {}), llm_raw),
    )
