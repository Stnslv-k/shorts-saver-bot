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
class SearchConfig:
    enabled: bool = True
    backend: str = "duckduckgo"  # duckduckgo | brave
    brave_api_key: str = ""


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
    search: SearchConfig = field(default_factory=SearchConfig)


def _parse_llm(raw: dict[str, Any]) -> LLMConfig:
    ollama_raw = raw.get("ollama", {})
    openai_raw = raw.get("openai", {})
    anthropic_raw = raw.get("anthropic", {})
    return LLMConfig(
        backend=os.getenv("LLM_BACKEND", raw.get("backend", "ollama")),
        fallback=raw.get("fallback"),
        ollama=OllamaConfig(
            url=os.getenv("OLLAMA_URL", ollama_raw.get("url", "http://localhost:11434")),
            model=ollama_raw.get("model", "llama3.1:8b"),
        ),
        openai=OpenAIConfig(
            api_key=os.getenv("OPENAI_API_KEY", openai_raw.get("api_key", "")),
            model=openai_raw.get("model", "gpt-4o-mini"),
        ),
        anthropic=AnthropicConfig(
            api_key=os.getenv("ANTHROPIC_API_KEY", anthropic_raw.get("api_key", "")),
            model=anthropic_raw.get("model", "claude-haiku-4-5-20251001"),
        ),
    )


def _parse_storage(raw: dict[str, Any]) -> StorageConfig:
    notion_raw = raw.get("notion", {})
    obsidian_raw = raw.get("obsidian", {})
    return StorageConfig(
        backend=os.getenv("STORAGE_BACKEND", raw.get("backend", "notion")),
        notion=NotionConfig(
            api_key=os.getenv("NOTION_API_KEY", notion_raw.get("api_key", "")),
            database_id=os.getenv("NOTION_DATABASE_ID", notion_raw.get("database_id", "")),
        ),
        obsidian=ObsidianConfig(
            vault_path=os.getenv("OBSIDIAN_VAULT_PATH", obsidian_raw.get("vault_path", "")),
        ),
    )


def _parse_vision(raw: dict[str, Any], llm_raw: dict[str, Any]) -> VisionConfig:
    openai_raw = raw.get("openai", {})
    anthropic_raw = raw.get("anthropic", {})

    llm_openai_key = os.getenv("OPENAI_API_KEY", llm_raw.get("openai", {}).get("api_key", ""))
    llm_anthropic_key = os.getenv("ANTHROPIC_API_KEY", llm_raw.get("anthropic", {}).get("api_key", ""))

    vision_enabled_env = os.getenv("VISION_ENABLED", "").lower()
    if vision_enabled_env in ("true", "1", "yes"):
        enabled = True
    elif vision_enabled_env in ("false", "0", "no"):
        enabled = False
    else:
        enabled = bool(raw.get("enabled", False))

    return VisionConfig(
        enabled=enabled,
        backend=os.getenv("VISION_BACKEND", raw.get("backend", "openai")),
        openai=OpenAIVisionConfig(
            api_key=openai_raw.get("api_key", llm_openai_key),
            model=openai_raw.get("model", "gpt-4o"),
        ),
        anthropic=AnthropicVisionConfig(
            api_key=anthropic_raw.get("api_key", llm_anthropic_key),
            model=anthropic_raw.get("model", "claude-haiku-4-5-20251001"),
        ),
    )


def _parse_search(raw: dict[str, Any]) -> SearchConfig:
    search_enabled_env = os.getenv("SEARCH_ENABLED", "").lower()
    if search_enabled_env in ("true", "1", "yes"):
        enabled = True
    elif search_enabled_env in ("false", "0", "no"):
        enabled = False
    else:
        enabled = bool(raw.get("enabled", True))

    brave_raw = raw.get("brave", {})
    return SearchConfig(
        enabled=enabled,
        backend=os.getenv("SEARCH_BACKEND", raw.get("backend", "duckduckgo")),
        brave_api_key=os.getenv("BRAVE_API_KEY", brave_raw.get("api_key", "")),
    )


def load_config(path: str | Path = "config.yaml") -> AppConfig:
    """Load config from env vars and optional YAML file.

    Priority: env vars > config.yaml > defaults.
    config.yaml is optional — only BOT_TOKEN and BOT_PASSWORD are required (via env or yaml).
    """
    config_path = Path(path)
    raw: dict[str, Any] = {}

    if config_path.exists():
        with open(config_path) as f:
            raw = yaml.safe_load(f) or {}

    bot_raw = raw.get("bot", {})
    llm_raw = raw.get("llm", {})
    return AppConfig(
        bot=BotConfig(
            token=os.getenv("BOT_TOKEN", bot_raw.get("token", "")),
            password=os.getenv("BOT_PASSWORD", bot_raw.get("password", "")),
        ),
        llm=_parse_llm(llm_raw),
        storage=_parse_storage(raw.get("storage", {})),
        vision=_parse_vision(raw.get("vision", {}), llm_raw),
        search=_parse_search(raw.get("search", {})),
    )


def apply_db_settings(config: AppConfig, settings: dict[str, str]) -> None:
    """Overlay DB-stored settings onto config for values not provided by env vars or yaml."""

    def _s(key: str) -> str:
        return settings.get(key, "")

    # LLM — only override if env var not set
    if not os.getenv("LLM_BACKEND") and "llm.backend" in settings:
        config.llm.backend = settings["llm.backend"]
    if not config.llm.openai.api_key:
        config.llm.openai.api_key = _s("llm.openai.api_key")
    if not config.llm.anthropic.api_key:
        config.llm.anthropic.api_key = _s("llm.anthropic.api_key")
    if not os.getenv("OLLAMA_URL") and "llm.ollama.url" in settings:
        config.llm.ollama.url = settings["llm.ollama.url"]

    # Storage
    if not os.getenv("STORAGE_BACKEND") and "storage.backend" in settings:
        config.storage.backend = settings["storage.backend"]
    if not config.storage.notion.api_key:
        config.storage.notion.api_key = _s("storage.notion.api_key")
    if not config.storage.notion.database_id:
        config.storage.notion.database_id = _s("storage.notion.database_id")
    if not config.storage.obsidian.vault_path:
        config.storage.obsidian.vault_path = _s("storage.obsidian.vault_path")

    # Vision
    if not os.getenv("VISION_ENABLED") and not config.vision.enabled and "vision.enabled" in settings:
        config.vision.enabled = settings["vision.enabled"].lower() in ("true", "1", "yes")
    if not os.getenv("VISION_BACKEND") and "vision.backend" in settings:
        config.vision.backend = settings["vision.backend"]
