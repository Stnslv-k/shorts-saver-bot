from __future__ import annotations

import logging
import re
import sys
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message

from bot.auth import authenticate_user, init_db, is_authenticated
from bot.config import load_config
from bot.llm import build_llm_backend
from bot.processor import process_url
from bot.storage import build_storage_backend
from bot.vision import build_vision_backend

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

YOUTUBE_SHORTS_RE = re.compile(
    r"https?://(?:www\.)?(?:youtube\.com/shorts/|youtu\.be/)[A-Za-z0-9_?=&%-]+"
)


class AuthState(StatesGroup):
    waiting_for_password = State()


async def cmd_start(message: Message, state: FSMContext, password: str) -> None:
    user_id = message.from_user.id  # type: ignore[union-attr]

    if await is_authenticated(user_id):
        await message.answer(
            "You are already authenticated. Send me a YouTube Shorts URL to get started."
        )
        return

    await state.set_state(AuthState.waiting_for_password)
    await message.answer("Welcome! Please enter the bot password to continue.")


async def handle_password(
    message: Message, state: FSMContext, password: str
) -> None:
    user_id = message.from_user.id  # type: ignore[union-attr]
    text = (message.text or "").strip()

    if text == password:
        await authenticate_user(user_id, message.from_user.username)  # type: ignore[union-attr]
        await state.clear()
        await message.answer(
            "Authenticated! Send me a YouTube Shorts URL and I'll extract the knowledge for you."
        )
    else:
        await message.answer("Incorrect password. Try again.")


async def handle_url(
    message: Message,
    llm_backend,
    storage_backend,
    vision_backend=None,
) -> None:
    user_id = message.from_user.id  # type: ignore[union-attr]

    if not await is_authenticated(user_id):
        return  # silently ignore

    text = message.text or message.caption or ""
    url_match = YOUTUBE_SHORTS_RE.search(text)

    if not url_match:
        await message.answer(
            "Please send a valid YouTube Shorts URL "
            "(e.g. https://youtube.com/shorts/abc123)."
        )
        return

    url = url_match.group(0)
    vision_note = escape_md(" (with visual analysis)") if vision_backend is not None else ""
    processing_msg = await message.answer(
        f"Processing{vision_note}\\.\\.\\. this may take a moment\\.",
        parse_mode="MarkdownV2",
    )

    try:
        entry, confirmation = await process_url(url, llm_backend, storage_backend, vision_backend)

        lines = [
            f"*{escape_md(entry.title)}*",
            f"Category: `{escape_md(entry.category)}`",
            "",
            escape_md(entry.summary),
        ]

        if entry.tags:
            # Tags rendered as inline code spans; backticks in tag text would break the
            # span, so strip them before wrapping.
            tag_str = " ".join(f"`{t.replace('`', '')}`" for t in entry.tags)
            lines.append(f"Tags: {tag_str}")

        if entry.tools:
            tools_str = escape_md(", ".join(entry.tools[:5]))
            lines.append(f"Tools: {tools_str}")

        if entry.github_repos:
            repo_lines = []
            for repo in entry.github_repos[:3]:
                name = escape_md(repo.get("name", ""))
                repo_url = _escape_link_url(repo.get("url", ""))
                if repo_url:
                    repo_lines.append(f"[{name}]({repo_url})")
                else:
                    repo_lines.append(name)
            lines.append("GitHub: " + ", ".join(repo_lines))

        lines.append("")
        lines.append(f"_{escape_md(confirmation)}_")

        reply = "\n".join(lines)
        await processing_msg.edit_text(reply, parse_mode="MarkdownV2")

    except Exception as e:
        logger.exception("Failed to process URL %s", url)
        await processing_msg.edit_text(
            f"Error processing URL: {str(e)[:200]}\n\nPlease try again."
        )


async def handle_text(
    message: Message,
    state: FSMContext,
    password: str,
    llm_backend,
    storage_backend,
    vision_backend=None,
) -> None:
    user_id = message.from_user.id  # type: ignore[union-attr]

    current_state = await state.get_state()
    if current_state == AuthState.waiting_for_password.state:
        await handle_password(message, state, password)
        return

    if not await is_authenticated(user_id):
        return

    text = message.text or ""
    if YOUTUBE_SHORTS_RE.search(text):
        await handle_url(message, llm_backend, storage_backend, vision_backend)
    else:
        await message.answer(
            "Send me a YouTube Shorts URL to extract knowledge from it."
        )


def escape_md(text: str) -> str:
    """Escape special characters for Telegram MarkdownV2."""
    special = r"\_*[]()~`>#+-=|{}.!"
    return "".join(f"\\{c}" if c in special else c for c in str(text))


def _escape_link_url(url: str) -> str:
    """Escape characters inside the (...) part of a MarkdownV2 inline link.

    Per Telegram spec, only ')' and '\\' must be escaped inside link URLs.
    """
    return url.replace("\\", "\\\\").replace(")", "\\)")


def main() -> None:
    config_path = Path("config.yaml")
    if not config_path.exists():
        logger.error("config.yaml not found. Copy config.yaml.example and fill in your values.")
        sys.exit(1)

    config = load_config(config_path)

    if not config.bot.token:
        logger.error("Bot token is not set in config.yaml")
        sys.exit(1)

    if not config.bot.password:
        logger.error("Bot password is not set in config.yaml")
        sys.exit(1)

    import asyncio

    async def _run() -> None:
        await init_db()

        llm_backend = build_llm_backend(config.llm)
        storage_backend = build_storage_backend(config.storage)

        vision_backend = None
        if config.vision.enabled:
            vision_backend = build_vision_backend(config.vision)
            logger.info("Vision enabled: backend=%s", config.vision.backend)
        else:
            logger.info("Vision disabled")

        bot = Bot(token=config.bot.token)
        storage = MemoryStorage()
        dp = Dispatcher(storage=storage)

        password = config.bot.password

        # /start handler
        @dp.message(CommandStart())
        async def _start(msg: Message, state: FSMContext) -> None:
            await cmd_start(msg, state, password)

        # Password entry state handler — must be registered before the catch-all
        @dp.message(AuthState.waiting_for_password)
        async def _pw(msg: Message, state: FSMContext) -> None:
            await handle_password(msg, state, password)

        # All other messages
        @dp.message()
        async def _text(msg: Message, state: FSMContext) -> None:
            await handle_text(msg, state, password, llm_backend, storage_backend, vision_backend)

        logger.info("Bot starting...")
        await dp.start_polling(bot, allowed_updates=["message"])

    asyncio.run(_run())


if __name__ == "__main__":
    main()
