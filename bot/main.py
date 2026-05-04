from __future__ import annotations

import logging
import re
import sys

from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message

from bot.auth import authenticate_user, init_db, is_authenticated
from bot.config import apply_db_settings, load_config
from bot.processor import process_url
from bot.settings_db import add_history_entry, get_all_settings, init_settings_db
from bot.setup import create_setup_router, entry_inline_kb
from bot.state import BotState

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


async def handle_url(message: Message, bot_state: BotState) -> None:
    user_id = message.from_user.id  # type: ignore[union-attr]

    if not await is_authenticated(user_id):
        return

    text = message.text or message.caption or ""
    url_match = YOUTUBE_SHORTS_RE.search(text)

    if not url_match:
        await message.answer(
            "Please send a valid YouTube Shorts URL "
            "(e.g. https://youtube.com/shorts/abc123)."
        )
        return

    if not bot_state.is_ready():
        await message.answer(
            "⚙️ Настройки не завершены. Используй /setup для настройки."
        )
        return

    url = url_match.group(0)
    vision_note = escape_md(" (with visual analysis)") if bot_state.vision_backend is not None else ""
    processing_msg = await message.answer(
        f"Processing{vision_note}\\.\\.\\. this may take a moment\\.",
        parse_mode="MarkdownV2",
    )

    try:
        entry, confirmation, storage_ref = await process_url(
            url,
            bot_state.llm_backend,  # type: ignore[arg-type]
            bot_state.storage_backend,  # type: ignore[arg-type]
            bot_state.vision_backend,
            bot_state.search_backend,
        )

        # Save to local history
        history_id = await add_history_entry(
            title=entry.title,
            category=entry.category,
            summary=entry.summary,
            source_url=entry.source_url,
            tags=entry.tags,
            storage_ref=storage_ref,
        )

        tag_str = " ".join(f"#{t}" for t in entry.tags) if entry.tags else ""
        lines = [
            "✅ Сохранено!\n",
            f"📌 <b>{entry.title}</b>",
            f"📁 Категория: <code>{entry.category}</code>",
        ]
        if tag_str:
            lines.append(f"🏷 {tag_str}")
        if entry.summary:
            lines.append(f"\n<i>{entry.summary[:300]}</i>")

        kb = entry_inline_kb(history_id, entry.source_url)
        await processing_msg.edit_text(
            "\n".join(lines),
            reply_markup=kb,
            parse_mode="HTML",
        )

    except Exception as e:
        logger.exception("Failed to process URL %s", url)
        await processing_msg.edit_text(
            f"Error processing URL: {str(e)[:200]}\n\nPlease try again."
        )


async def handle_text(
    message: Message,
    state: FSMContext,
    password: str,
    bot_state: BotState,
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
        await handle_url(message, bot_state)
    else:
        await message.answer(
            "Send me a YouTube Shorts URL to extract knowledge from it."
        )


def escape_md(text: str) -> str:
    special = r"\_*[]()~`>#+-=|{}.!"
    return "".join(f"\\{c}" if c in special else c for c in str(text))


def main() -> None:
    config = load_config("config.yaml")

    if not config.bot.token:
        logger.error(
            "Bot token is not set. Provide BOT_TOKEN env var or set bot.token in config.yaml."
        )
        sys.exit(1)

    if not config.bot.password:
        logger.error(
            "Bot password is not set. Provide BOT_PASSWORD env var or set bot.password in config.yaml."
        )
        sys.exit(1)

    import asyncio

    async def _run() -> None:
        await init_db()
        await init_settings_db()

        # Overlay DB settings (fills in what env vars + yaml didn't cover)
        db_settings = await get_all_settings()
        apply_db_settings(config, db_settings)

        bot_state = BotState(config=config)
        bot_state.rebuild_backends()

        if not bot_state.is_ready():
            logger.warning(
                "Bot started without complete configuration. "
                "Users will be prompted to run /setup."
            )
        else:
            logger.info(
                "Backends ready: LLM=%s storage=%s vision=%s",
                config.llm.backend,
                config.storage.backend,
                "enabled" if config.vision.enabled else "disabled",
            )

        bot = Bot(token=config.bot.token)
        storage = MemoryStorage()
        dp = Dispatcher(storage=storage)

        password = config.bot.password

        # Setup router must be included before the catch-all handler so that
        # its state-filtered handlers take priority.
        setup_router = create_setup_router(bot_state)
        dp.include_router(setup_router)

        @dp.message(CommandStart())
        async def _start(msg: Message, state: FSMContext) -> None:
            await cmd_start(msg, state, password)

        @dp.message(AuthState.waiting_for_password)
        async def _pw(msg: Message, state: FSMContext) -> None:
            await handle_password(msg, state, password)

        @dp.message()
        async def _text(msg: Message, state: FSMContext) -> None:
            await handle_text(msg, state, password, bot_state)

        logger.info("Bot starting...")
        await dp.start_polling(bot, allowed_updates=["message", "callback_query"])

    asyncio.run(_run())


if __name__ == "__main__":
    main()
