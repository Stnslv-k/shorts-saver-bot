from __future__ import annotations

import logging
from typing import Any

from notion_client import AsyncClient

from bot.config import NotionConfig
from bot.models import KnowledgeEntry
from bot.storage.base import StorageBackend

logger = logging.getLogger(__name__)

CATEGORY_TO_NOTION_COLOR: dict[str, str] = {
    "github": "blue",
    "recipe": "green",
    "tool": "orange",
    "article": "purple",
    "general": "default",
}


class NotionAdapter(StorageBackend):
    def __init__(self, config: NotionConfig) -> None:
        self._client = AsyncClient(auth=config.api_key)
        self._db_id = config.database_id

    async def save(self, entry: KnowledgeEntry) -> tuple[str, str]:
        properties = _build_properties(entry)
        children = _build_children(entry)

        response = await self._client.pages.create(
            parent={"database_id": self._db_id},
            properties=properties,
            children=children,
        )

        page_id = response.get("id", "")
        page_url = response.get("url", "")
        logger.info("Notion page created: %s", page_url)
        return f"Notion page created: {page_url}", page_id

    async def delete_by_ref(self, ref: str) -> bool:
        try:
            await self._client.pages.update(page_id=ref, archived=True)
            logger.info("Notion page archived: %s", ref)
            return True
        except Exception as e:
            logger.warning("Failed to archive Notion page %s: %s", ref, e)
            return False

    async def list_recent(self, n: int = 5) -> list[KnowledgeEntry]:
        response = await self._client.databases.query(
            database_id=self._db_id,
            sorts=[{"timestamp": "created_time", "direction": "descending"}],
            page_size=n,
        )

        entries: list[KnowledgeEntry] = []
        for page in response.get("results", []):
            entry = _page_to_entry(page)
            if entry:
                entries.append(entry)
        return entries


def _build_properties(entry: KnowledgeEntry) -> dict[str, Any]:
    props: dict[str, Any] = {
        "Name": {"title": [{"text": {"content": entry.title}}]},
        "Category": {
            "select": {
                "name": entry.category,
                "color": CATEGORY_TO_NOTION_COLOR.get(entry.category, "default"),
            }
        },
        "Summary": {"rich_text": [{"text": {"content": entry.summary[:2000]}}]},
        "Source URL": {"url": entry.source_url},
        "Extracted At": {"date": {"start": entry.extracted_at.isoformat()}},
    }

    if entry.tags:
        props["Tags"] = {"multi_select": [{"name": t} for t in entry.tags[:10]]}

    if entry.tools:
        props["Tools"] = {
            "rich_text": [{"text": {"content": ", ".join(entry.tools[:20])}}]
        }

    return props


def _build_children(entry: KnowledgeEntry) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []

    def heading(text: str, level: int = 2) -> dict[str, Any]:
        key = f"heading_{level}"
        return {
            "object": "block",
            "type": key,
            key: {"rich_text": [{"type": "text", "text": {"content": text}}]},
        }

    def paragraph(text: str) -> dict[str, Any]:
        return {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": text[:2000]}}]
            },
        }

    def bullet(text: str) -> dict[str, Any]:
        return {
            "object": "block",
            "type": "bulleted_list_item",
            "bulleted_list_item": {
                "rich_text": [{"type": "text", "text": {"content": text}}]
            },
        }

    blocks.append(heading("Summary"))
    blocks.append(paragraph(entry.summary))

    if entry.github_repos:
        blocks.append(heading("GitHub Repositories"))
        for repo in entry.github_repos:
            name = repo.get("name", "")
            url = repo.get("url", "")
            desc = repo.get("description", "")
            blocks.append(bullet(f"{name} — {url}\n{desc}".strip()))

    if entry.recipe:
        blocks.append(heading("Recipe"))
        recipe_name = entry.recipe.get("name", "")
        if recipe_name:
            blocks.append(paragraph(recipe_name))

        ingredients = entry.recipe.get("ingredients", [])
        if ingredients:
            blocks.append(heading("Ingredients", level=3))
            for item in ingredients:
                blocks.append(bullet(str(item)))

        steps = entry.recipe.get("steps", [])
        if steps:
            blocks.append(heading("Steps", level=3))
            for i, step in enumerate(steps, 1):
                blocks.append(bullet(f"{i}. {step}"))

    if entry.tools:
        blocks.append(heading("Tools Mentioned"))
        for tool in entry.tools:
            blocks.append(bullet(tool))

    if entry.raw_transcript:
        blocks.append(heading("Transcript"))
        # Notion blocks have a 2000 char limit; chunk the transcript
        transcript = entry.raw_transcript
        for i in range(0, min(len(transcript), 10000), 2000):
            blocks.append(paragraph(transcript[i : i + 2000]))

    return blocks


def _page_to_entry(page: dict[str, Any]) -> KnowledgeEntry | None:
    try:
        props = page.get("properties", {})
        title_prop = props.get("Name", {}).get("title", [])
        title = title_prop[0]["text"]["content"] if title_prop else "Untitled"

        category = props.get("Category", {}).get("select", {})
        category_name = category.get("name", "general") if category else "general"

        summary_prop = props.get("Summary", {}).get("rich_text", [])
        summary = summary_prop[0]["text"]["content"] if summary_prop else ""

        source_url = props.get("Source URL", {}).get("url", "")

        date_prop = props.get("Extracted At", {}).get("date", {})
        from datetime import datetime
        extracted_at = (
            datetime.fromisoformat(date_prop["start"])
            if date_prop and date_prop.get("start")
            else datetime.utcnow()
        )

        tags_prop = props.get("Tags", {}).get("multi_select", [])
        tags = [t["name"] for t in tags_prop]

        return KnowledgeEntry(
            title=title,
            category=category_name,
            summary=summary,
            source_url=source_url,
            extracted_at=extracted_at,
            tags=tags,
        )
    except Exception as e:
        logger.warning("Failed to parse Notion page: %s", e)
        return None
