from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import sys
from typing import Any

from bot.config import apply_db_settings, load_config
from bot.models import KnowledgeEntry
from bot.processor import NoTranscriptError, process_url
from bot.settings_db import add_history_entry, get_all_settings, init_settings_db
from bot.state import BotState

logger = logging.getLogger(__name__)

YOUTUBE_SHORTS_RE = re.compile(
    r"^https?://(?:www\.)?(?:youtube\.com/shorts/|youtu\.be/)[A-Za-z0-9_?=&%-]+$"
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the full YouTube Shorts pipeline locally without Telegram."
    )
    parser.add_argument("url", help="YouTube Shorts URL to process")
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to config file (default: config.yaml)",
    )
    parser.add_argument(
        "--no-history",
        action="store_true",
        help="Do not write the result to local history.db",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the final result as JSON instead of a formatted summary",
    )
    parser.add_argument(
        "--cookies-from-browser",
        help="Pass browser cookies to yt-dlp, for example: brave, chrome, safari",
    )
    parser.add_argument(
        "--cookies",
        help="Path to a Netscape-format cookies.txt file for yt-dlp",
    )
    return parser.parse_args(argv)


def validate_url(url: str) -> str:
    value = url.strip()
    if not YOUTUBE_SHORTS_RE.match(value):
        raise ValueError("Expected a YouTube Shorts URL.")
    return value


def build_result_payload(
    entry: KnowledgeEntry,
    model_name: str,
    storage_ref: str,
    history_id: int | None,
) -> dict[str, Any]:
    return {
        "title": entry.title,
        "category": entry.category,
        "summary": entry.summary,
        "source_url": entry.source_url,
        "tags": entry.tags,
        "tools": entry.tools,
        "github_repos": entry.github_repos,
        "recipe": entry.recipe,
        "model": model_name,
        "storage_ref": storage_ref,
        "history_id": history_id,
    }


def print_human_summary(payload: dict[str, Any]) -> None:
    print(f"Title: {payload['title']}")
    print(f"Category: {payload['category']}")
    print(f"Model: {payload['model']}")
    print(f"Storage ref: {payload['storage_ref']}")

    history_id = payload.get("history_id")
    if history_id is not None:
        print(f"History ID: {history_id}")

    tags = payload.get("tags") or []
    if tags:
        print(f"Tags: {', '.join(tags)}")

    summary = (payload.get("summary") or "").strip()
    if summary:
        print("")
        print(summary)


async def run_live(args: argparse.Namespace) -> int:
    url = validate_url(args.url)
    _apply_runtime_overrides(args)

    config = load_config(args.config)
    await init_settings_db()
    db_settings = await get_all_settings()
    apply_db_settings(config, db_settings)

    bot_state = BotState(config=config)
    bot_state.rebuild_backends()

    if not bot_state.is_ready():
        logger.error(
            "Backends are not ready. Configure LLM and storage in %s or via the local settings DB.",
            args.config,
        )
        return 2

    entry, _, storage_ref, model_name = await process_url(
        url,
        bot_state.llm_backend,  # type: ignore[arg-type]
        bot_state.storage_backend,  # type: ignore[arg-type]
        bot_state.vision_backend,
        bot_state.search_backend,
    )

    history_id: int | None = None
    if not args.no_history:
        history_id = await add_history_entry(
            title=entry.title,
            category=entry.category,
            summary=entry.summary,
            source_url=entry.source_url,
            tags=entry.tags,
            storage_ref=storage_ref,
        )

    payload = build_result_payload(entry, model_name, storage_ref, history_id)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print_human_summary(payload)
    return 0


def _apply_runtime_overrides(args: argparse.Namespace) -> None:
    import os

    if args.cookies_from_browser:
        os.environ["YTDLP_COOKIES_FROM_BROWSER"] = args.cookies_from_browser
    if args.cookies:
        os.environ["YTDLP_COOKIES_FILE"] = args.cookies


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
        stream=sys.stderr,
    )

    try:
        return asyncio.run(run_live(args))
    except ValueError as exc:
        logger.error("%s", exc)
        return 2
    except NoTranscriptError as exc:
        logger.error("%s", exc)
        return 3
    except KeyboardInterrupt:
        logger.error("Interrupted")
        return 130
    except Exception:
        logger.exception("Live run failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
