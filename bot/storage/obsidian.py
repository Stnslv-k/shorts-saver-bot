from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path

import aiofiles

from bot.config import ObsidianConfig
from bot.models import KnowledgeEntry
from bot.storage.base import StorageBackend

logger = logging.getLogger(__name__)


class ObsidianAdapter(StorageBackend):
    def __init__(self, config: ObsidianConfig) -> None:
        self._vault_path = Path(config.vault_path)

    async def save(self, entry: KnowledgeEntry) -> tuple[str, str]:
        self._vault_path.mkdir(parents=True, exist_ok=True)

        filename = _sanitize_filename(entry.title) + ".md"
        # Avoid collisions by appending a timestamp suffix if file exists
        filepath = self._vault_path / filename
        if filepath.exists():
            ts = entry.extracted_at.strftime("%Y%m%d%H%M%S")
            filename = _sanitize_filename(entry.title) + f"_{ts}.md"
            filepath = self._vault_path / filename

        content = _render_markdown(entry)

        async with aiofiles.open(filepath, "w", encoding="utf-8") as f:
            await f.write(content)

        logger.info("Obsidian note saved: %s", filepath)
        return f"Saved to Obsidian: {filepath.name}", str(filepath)

    async def delete_by_ref(self, ref: str) -> bool:
        try:
            path = Path(ref)
            if path.exists():
                path.unlink()
                logger.info("Obsidian note deleted: %s", ref)
                return True
            return False
        except Exception as e:
            logger.warning("Failed to delete Obsidian note %s: %s", ref, e)
            return False

    async def list_recent(self, n: int = 5) -> list[KnowledgeEntry]:
        if not self._vault_path.exists():
            return []

        md_files = sorted(
            self._vault_path.glob("*.md"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[:n]

        entries: list[KnowledgeEntry] = []
        for path in md_files:
            entry = await _parse_markdown_file(path)
            if entry:
                entries.append(entry)
        return entries


def _sanitize_filename(title: str) -> str:
    # Replace characters that are invalid in most filesystems
    sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", title)
    sanitized = re.sub(r"\s+", " ", sanitized).strip()
    sanitized = sanitized[:100]  # Limit length
    return sanitized or "untitled"


def _render_markdown(entry: KnowledgeEntry) -> str:
    lines: list[str] = []

    # YAML frontmatter
    lines.append("---")
    lines.append(f"title: {_yaml_str(entry.title)}")
    lines.append(f"category: {entry.category}")
    lines.append(f"source_url: {entry.source_url}")
    lines.append(f"extracted_at: {entry.extracted_at.isoformat()}")
    if entry.tags:
        tags_str = ", ".join(f'"{t}"' for t in entry.tags)
        lines.append(f"tags: [{tags_str}]")
    if entry.tools:
        tools_str = ", ".join(f'"{t}"' for t in entry.tools)
        lines.append(f"tools: [{tools_str}]")
    lines.append("---")
    lines.append("")

    # Title
    lines.append(f"# {entry.title}")
    lines.append("")

    # Summary
    lines.append("## Summary")
    lines.append("")
    lines.append(entry.summary)
    lines.append("")

    # GitHub repos
    if entry.github_repos:
        lines.append("## GitHub Repositories")
        lines.append("")
        for repo in entry.github_repos:
            name = repo.get("name", "")
            url = repo.get("url", "")
            desc = repo.get("description", "")
            if url:
                lines.append(f"- **[{name}]({url})** — {desc}")
            else:
                lines.append(f"- **{name}** — {desc}")
        lines.append("")

    # Recipe
    if entry.recipe:
        lines.append("## Recipe")
        lines.append("")
        recipe_name = entry.recipe.get("name", "")
        if recipe_name:
            lines.append(f"**{recipe_name}**")
            lines.append("")

        ingredients = entry.recipe.get("ingredients", [])
        if ingredients:
            lines.append("### Ingredients")
            lines.append("")
            for item in ingredients:
                lines.append(f"- {item}")
            lines.append("")

        steps = entry.recipe.get("steps", [])
        if steps:
            lines.append("### Steps")
            lines.append("")
            for i, step in enumerate(steps, 1):
                lines.append(f"{i}. {step}")
            lines.append("")

    # Tools
    if entry.tools:
        lines.append("## Tools Mentioned")
        lines.append("")
        for tool in entry.tools:
            lines.append(f"- {tool}")
        lines.append("")

    # Source
    lines.append("## Source")
    lines.append("")
    lines.append(f"[{entry.source_url}]({entry.source_url})")
    lines.append("")

    # Transcript
    if entry.raw_transcript:
        lines.append("## Raw Transcript")
        lines.append("")
        lines.append(entry.raw_transcript)
        lines.append("")

    return "\n".join(lines)


def _yaml_str(value: str) -> str:
    if any(c in value for c in ('"', "'", ":", "#", "[", "]", "{", "}")):
        escaped = value.replace('"', '\\"')
        return f'"{escaped}"'
    return value


async def _parse_markdown_file(path: Path) -> KnowledgeEntry | None:
    try:
        async with aiofiles.open(path, encoding="utf-8") as f:
            content = await f.read()

        import yaml

        if not content.startswith("---"):
            return None

        end = content.find("---", 3)
        if end == -1:
            return None

        frontmatter_str = content[3:end].strip()
        frontmatter = yaml.safe_load(frontmatter_str) or {}

        return KnowledgeEntry(
            title=frontmatter.get("title", path.stem),
            category=frontmatter.get("category", "general"),
            summary="",
            source_url=frontmatter.get("source_url", ""),
            extracted_at=_parse_dt(frontmatter.get("extracted_at")),
            tags=frontmatter.get("tags", []),
            tools=frontmatter.get("tools", []),
        )
    except Exception as e:
        logger.warning("Failed to parse Obsidian note %s: %s", path, e)
        return None


def _parse_dt(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            pass
    return datetime.utcnow()
