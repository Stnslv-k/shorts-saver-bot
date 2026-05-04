from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class ExtractionResult:
    title: str
    category: str  # "github", "recipe", "tool", "article", "general"
    summary: str
    github_repos: list[dict[str, str]] = field(default_factory=list)
    recipe: dict[str, Any] | None = None
    tools: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExtractionResult":
        return cls(
            title=data.get("title", "Untitled"),
            category=data.get("category", "general"),
            summary=data.get("summary", ""),
            github_repos=data.get("github_repos", []),
            recipe=data.get("recipe"),
            tools=data.get("tools", []),
            tags=data.get("tags", []),
        )


@dataclass
class KnowledgeEntry:
    title: str
    category: str
    summary: str
    source_url: str
    extracted_at: datetime
    github_repos: list[dict[str, str]] = field(default_factory=list)
    recipe: dict[str, Any] | None = None
    tools: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    raw_transcript: str = ""

    @classmethod
    def from_extraction(
        cls,
        result: ExtractionResult,
        source_url: str,
        raw_transcript: str,
    ) -> "KnowledgeEntry":
        return cls(
            title=result.title,
            category=result.category,
            summary=result.summary,
            source_url=source_url,
            extracted_at=datetime.utcnow(),
            github_repos=result.github_repos,
            recipe=result.recipe,
            tools=result.tools,
            tags=result.tags,
            raw_transcript=raw_transcript,
        )
