from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from bot.auth import is_authenticated
from bot.settings_db import (
    add_history_entry,
    delete_history_entry,
    get_all_settings,
    get_history_entry,
    get_recent_history,
    set_setting,
)

if TYPE_CHECKING:
    from bot.state import BotState

logger = logging.getLogger(__name__)

_CMD_RE = re.compile(r"^/\w+(@\w+)?$")


class SetupState(StatesGroup):
    waiting_llm_openai_key = State()
    waiting_llm_anthropic_key = State()
    waiting_llm_ollama_url = State()
    waiting_storage_notion_key = State()
    waiting_storage_notion_db_id = State()
    waiting_storage_obsidian_path = State()


# ---------- keyboard helpers ----------


def _main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🤖 LLM", callback_data="su:l"),
                InlineKeyboardButton(text="💾 Хранилище", callback_data="su:s"),
            ],
            [
                InlineKeyboardButton(text="👁 Vision", callback_data="su:v"),
                InlineKeyboardButton(text="📊 Статус", callback_data="su:st"),
            ],
            [InlineKeyboardButton(text="❌ Закрыть", callback_data="su:x")],
        ]
    )


def _llm_menu_kb(current: str) -> InlineKeyboardMarkup:
    def _b(label: str, key: str, cb: str) -> InlineKeyboardButton:
        text = f"✅ {label}" if current == key else label
        return InlineKeyboardButton(text=text, callback_data=cb)

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _b("Ollama", "ollama", "su:l:ol"),
                _b("OpenAI", "openai", "su:l:oa"),
                _b("Anthropic", "anthropic", "su:l:an"),
            ],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="su:m")],
        ]
    )


def _storage_menu_kb(current: str) -> InlineKeyboardMarkup:
    def _b(label: str, key: str, cb: str) -> InlineKeyboardButton:
        text = f"✅ {label}" if current == key else label
        return InlineKeyboardButton(text=text, callback_data=cb)

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _b("Notion", "notion", "su:s:no"),
                _b("Obsidian", "obsidian", "su:s:ob"),
            ],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="su:m")],
        ]
    )


def _vision_menu_kb(enabled: bool, backend: str) -> InlineKeyboardMarkup:
    openai_label = "✅ OpenAI" if (enabled and backend == "openai") else "Включить OpenAI"
    anthropic_label = "✅ Anthropic" if (enabled and backend == "anthropic") else "Включить Anthropic"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=openai_label, callback_data="su:v:oa"),
                InlineKeyboardButton(text=anthropic_label, callback_data="su:v:an"),
            ],
            [InlineKeyboardButton(text="Выключить", callback_data="su:v:off")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="su:m")],
        ]
    )


def _mask(value: str) -> str:
    if not value:
        return "не задан"
    if len(value) <= 4:
        return "****"
    return f"...{value[-4:]}"


def _is_command(text: str) -> bool:
    return bool(_CMD_RE.match(text))


# ---------- status text helper ----------


async def _status_text(bot_state: BotState) -> str:
    settings = await get_all_settings()
    cfg = bot_state.config

    llm_backend = settings.get("llm.backend", cfg.llm.backend)
    openai_key = settings.get("llm.openai.api_key") or cfg.llm.openai.api_key
    anthropic_key = settings.get("llm.anthropic.api_key") or cfg.llm.anthropic.api_key
    ollama_url = settings.get("llm.ollama.url") or cfg.llm.ollama.url

    storage_backend = settings.get("storage.backend", cfg.storage.backend)
    notion_key = settings.get("storage.notion.api_key") or cfg.storage.notion.api_key
    notion_db = settings.get("storage.notion.database_id") or cfg.storage.notion.database_id
    obsidian_path = settings.get("storage.obsidian.vault_path") or cfg.storage.obsidian.vault_path

    vision_enabled = cfg.vision.enabled or settings.get("vision.enabled", "").lower() in ("true", "1", "yes")
    vision_backend = settings.get("vision.backend", cfg.vision.backend)

    return (
        "📊 <b>Текущий статус</b>\n\n"
        f"🤖 <b>LLM:</b> {llm_backend}\n"
        f"  OpenAI key: {_mask(openai_key)}\n"
        f"  Anthropic key: {_mask(anthropic_key)}\n"
        f"  Ollama URL: {ollama_url or 'не задан'}\n\n"
        f"💾 <b>Хранилище:</b> {storage_backend}\n"
        f"  Notion key: {_mask(notion_key)}\n"
        f"  Notion DB: {_mask(notion_db)}\n"
        f"  Obsidian path: {obsidian_path or 'не задан'}\n\n"
        f"👁 <b>Vision:</b> {'включен (' + vision_backend + ')' if vision_enabled else 'выключен'}"
    )


# ---------- entry inline keyboard ----------


def entry_inline_kb(entry_id: int, source_url: str) -> InlineKeyboardMarkup:
    buttons = []
    if source_url:
        buttons.append(InlineKeyboardButton(text="🔗 Открыть источник", url=source_url))
    buttons.append(InlineKeyboardButton(text="🗑 Удалить", callback_data=f"en:d:{entry_id}"))
    return InlineKeyboardMarkup(inline_keyboard=[buttons])


def _delete_confirm_kb(entry_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"en:dc:{entry_id}"),
                InlineKeyboardButton(text="❌ Отмена", callback_data=f"en:dx:{entry_id}"),
            ]
        ]
    )


# ---------- router factory ----------


def create_setup_router(bot_state: BotState) -> Router:
    router = Router()

    async def _guard(user_id: int) -> bool:
        return await is_authenticated(user_id)

    # ---- /setup ----

    @router.message(Command("setup"))
    async def cmd_setup(message: Message, state: FSMContext) -> None:
        if not await _guard(message.from_user.id):  # type: ignore[union-attr]
            return
        await state.clear()
        settings = await get_all_settings()
        backend = settings.get("llm.backend", bot_state.config.llm.backend)
        await message.answer(
            f"⚙️ <b>Настройки бота</b>\n\nLLM: {backend}",
            reply_markup=_main_menu_kb(),
            parse_mode="HTML",
        )

    # ---- /status ----

    @router.message(Command("status"))
    async def cmd_status(message: Message) -> None:
        if not await _guard(message.from_user.id):  # type: ignore[union-attr]
            return
        await message.answer(await _status_text(bot_state), parse_mode="HTML")

    # ---- /history ----

    @router.message(Command("history"))
    async def cmd_history(message: Message) -> None:
        if not await _guard(message.from_user.id):  # type: ignore[union-attr]
            return
        entries = await get_recent_history(5)
        if not entries:
            await message.answer("История пуста. Отправь YouTube Shorts URL чтобы начать.")
            return

        rows = []
        for e in entries:
            eid = e["id"]
            title = (e["title"] or "Без названия")[:40]
            rows.append(
                [InlineKeyboardButton(text=f"📌 {title}", callback_data=f"en:v:{eid}")]
            )

        kb = InlineKeyboardMarkup(inline_keyboard=rows)
        await message.answer("🕘 <b>Последние 5 записей:</b>", reply_markup=kb, parse_mode="HTML")

    # ---- main menu callbacks ----

    @router.callback_query(lambda c: c.data == "su:m")
    async def cb_main_menu(callback: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        settings = await get_all_settings()
        backend = settings.get("llm.backend", bot_state.config.llm.backend)
        await callback.message.edit_text(  # type: ignore[union-attr]
            f"⚙️ <b>Настройки бота</b>\n\nLLM: {backend}",
            reply_markup=_main_menu_kb(),
            parse_mode="HTML",
        )
        await callback.answer()

    @router.callback_query(lambda c: c.data == "su:x")
    async def cb_close(callback: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        await callback.message.edit_text("✅ Настройки закрыты.")  # type: ignore[union-attr]
        await callback.answer()

    @router.callback_query(lambda c: c.data == "su:st")
    async def cb_status(callback: CallbackQuery) -> None:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="su:m")]]
        )
        await callback.message.edit_text(  # type: ignore[union-attr]
            await _status_text(bot_state),
            reply_markup=kb,
            parse_mode="HTML",
        )
        await callback.answer()

    # ---- LLM submenu ----

    @router.callback_query(lambda c: c.data == "su:l")
    async def cb_llm_menu(callback: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        settings = await get_all_settings()
        backend = settings.get("llm.backend", bot_state.config.llm.backend)
        await callback.message.edit_text(  # type: ignore[union-attr]
            f"🤖 <b>LLM Backend: {backend}</b>\n\nВыбери бэкенд:",
            reply_markup=_llm_menu_kb(backend),
            parse_mode="HTML",
        )
        await callback.answer()

    @router.callback_query(lambda c: c.data == "su:l:ol")
    async def cb_llm_ollama(callback: CallbackQuery, state: FSMContext) -> None:
        await set_setting("llm.backend", "ollama")
        bot_state.config.llm.backend = "ollama"
        settings = await get_all_settings()
        current_url = settings.get("llm.ollama.url") or bot_state.config.llm.ollama.url
        await state.set_state(SetupState.waiting_llm_ollama_url)
        await callback.message.edit_text(  # type: ignore[union-attr]
            f"🦙 <b>Ollama</b> выбран.\n\nТекущий URL: <code>{current_url}</code>\n\n"
            "Введи новый URL или /skip для сохранения текущего:",
            parse_mode="HTML",
        )
        await callback.answer()

    @router.callback_query(lambda c: c.data == "su:l:oa")
    async def cb_llm_openai(callback: CallbackQuery, state: FSMContext) -> None:
        await set_setting("llm.backend", "openai")
        bot_state.config.llm.backend = "openai"
        await state.set_state(SetupState.waiting_llm_openai_key)
        await callback.message.edit_text(  # type: ignore[union-attr]
            "🔑 Введи <b>OpenAI API key</b>:",
            parse_mode="HTML",
        )
        await callback.answer()

    @router.callback_query(lambda c: c.data == "su:l:an")
    async def cb_llm_anthropic(callback: CallbackQuery, state: FSMContext) -> None:
        await set_setting("llm.backend", "anthropic")
        bot_state.config.llm.backend = "anthropic"
        await state.set_state(SetupState.waiting_llm_anthropic_key)
        await callback.message.edit_text(  # type: ignore[union-attr]
            "🔑 Введи <b>Anthropic API key</b>:",
            parse_mode="HTML",
        )
        await callback.answer()

    # ---- LLM state handlers ----

    @router.message(SetupState.waiting_llm_openai_key)
    async def recv_openai_key(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        if text and not _is_command(text):
            await set_setting("llm.openai.api_key", text)
            bot_state.config.llm.openai.api_key = text
            bot_state.rebuild_backends()
            await message.answer(f"✅ OpenAI key сохранён: {_mask(text)}")
        await state.clear()
        settings = await get_all_settings()
        backend = settings.get("llm.backend", bot_state.config.llm.backend)
        await message.answer(
            f"🤖 <b>LLM Backend: {backend}</b>",
            reply_markup=_llm_menu_kb(backend),
            parse_mode="HTML",
        )

    @router.message(SetupState.waiting_llm_anthropic_key)
    async def recv_anthropic_key(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        if text and not _is_command(text):
            await set_setting("llm.anthropic.api_key", text)
            bot_state.config.llm.anthropic.api_key = text
            bot_state.rebuild_backends()
            await message.answer(f"✅ Anthropic key сохранён: {_mask(text)}")
        await state.clear()
        settings = await get_all_settings()
        backend = settings.get("llm.backend", bot_state.config.llm.backend)
        await message.answer(
            f"🤖 <b>LLM Backend: {backend}</b>",
            reply_markup=_llm_menu_kb(backend),
            parse_mode="HTML",
        )

    @router.message(SetupState.waiting_llm_ollama_url)
    async def recv_ollama_url(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        if text and not _is_command(text):
            await set_setting("llm.ollama.url", text)
            bot_state.config.llm.ollama.url = text
            bot_state.rebuild_backends()
            await message.answer(
                f"✅ Ollama URL сохранён: <code>{text}</code>", parse_mode="HTML"
            )
        await state.clear()
        settings = await get_all_settings()
        backend = settings.get("llm.backend", bot_state.config.llm.backend)
        await message.answer(
            f"🤖 <b>LLM Backend: {backend}</b>",
            reply_markup=_llm_menu_kb(backend),
            parse_mode="HTML",
        )

    # ---- Storage submenu ----

    @router.callback_query(lambda c: c.data == "su:s")
    async def cb_storage_menu(callback: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        settings = await get_all_settings()
        backend = settings.get("storage.backend", bot_state.config.storage.backend)
        await callback.message.edit_text(  # type: ignore[union-attr]
            f"💾 <b>Хранилище: {backend}</b>\n\nВыбери бэкенд:",
            reply_markup=_storage_menu_kb(backend),
            parse_mode="HTML",
        )
        await callback.answer()

    @router.callback_query(lambda c: c.data == "su:s:no")
    async def cb_storage_notion(callback: CallbackQuery, state: FSMContext) -> None:
        await set_setting("storage.backend", "notion")
        bot_state.config.storage.backend = "notion"
        await state.set_state(SetupState.waiting_storage_notion_key)
        await callback.message.edit_text(  # type: ignore[union-attr]
            "🔑 Введи <b>Notion API key</b>:",
            parse_mode="HTML",
        )
        await callback.answer()

    @router.callback_query(lambda c: c.data == "su:s:ob")
    async def cb_storage_obsidian(callback: CallbackQuery, state: FSMContext) -> None:
        await set_setting("storage.backend", "obsidian")
        bot_state.config.storage.backend = "obsidian"
        await state.set_state(SetupState.waiting_storage_obsidian_path)
        await callback.message.edit_text(  # type: ignore[union-attr]
            "📁 Введи путь к <b>Obsidian vault</b>:",
            parse_mode="HTML",
        )
        await callback.answer()

    @router.message(SetupState.waiting_storage_notion_key)
    async def recv_notion_key(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        if text and not _is_command(text):
            await set_setting("storage.notion.api_key", text)
            bot_state.config.storage.notion.api_key = text
            await message.answer(f"✅ Notion key сохранён: {_mask(text)}")
        settings = await get_all_settings()
        current_db = settings.get("storage.notion.database_id") or bot_state.config.storage.notion.database_id
        await state.set_state(SetupState.waiting_storage_notion_db_id)
        await message.answer(
            f"📋 Теперь введи <b>Notion Database ID</b>:\nТекущий: <code>{current_db or 'не задан'}</code>",
            parse_mode="HTML",
        )

    @router.message(SetupState.waiting_storage_notion_db_id)
    async def recv_notion_db_id(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        if text and not _is_command(text):
            await set_setting("storage.notion.database_id", text)
            bot_state.config.storage.notion.database_id = text
            bot_state.rebuild_backends()
            await message.answer(f"✅ Notion Database ID сохранён: {_mask(text)}")
        await state.clear()
        settings = await get_all_settings()
        backend = settings.get("storage.backend", bot_state.config.storage.backend)
        await message.answer(
            f"💾 <b>Хранилище: {backend}</b>",
            reply_markup=_storage_menu_kb(backend),
            parse_mode="HTML",
        )

    @router.message(SetupState.waiting_storage_obsidian_path)
    async def recv_obsidian_path(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        if text and not _is_command(text):
            await set_setting("storage.obsidian.vault_path", text)
            bot_state.config.storage.obsidian.vault_path = text
            bot_state.rebuild_backends()
            await message.answer(
                f"✅ Obsidian vault path сохранён: <code>{text}</code>", parse_mode="HTML"
            )
        await state.clear()
        settings = await get_all_settings()
        backend = settings.get("storage.backend", bot_state.config.storage.backend)
        await message.answer(
            f"💾 <b>Хранилище: {backend}</b>",
            reply_markup=_storage_menu_kb(backend),
            parse_mode="HTML",
        )

    # ---- Vision submenu ----

    @router.callback_query(lambda c: c.data == "su:v")
    async def cb_vision_menu(callback: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        settings = await get_all_settings()
        enabled = bot_state.config.vision.enabled or settings.get("vision.enabled", "").lower() in ("true", "1", "yes")
        backend = settings.get("vision.backend", bot_state.config.vision.backend)
        status = f"включен ({backend})" if enabled else "выключен"
        await callback.message.edit_text(  # type: ignore[union-attr]
            f"👁 <b>Vision: {status}</b>",
            reply_markup=_vision_menu_kb(enabled, backend),
            parse_mode="HTML",
        )
        await callback.answer()

    @router.callback_query(lambda c: c.data == "su:v:oa")
    async def cb_vision_openai(callback: CallbackQuery) -> None:
        await set_setting("vision.enabled", "true")
        await set_setting("vision.backend", "openai")
        bot_state.config.vision.enabled = True
        bot_state.config.vision.backend = "openai"
        bot_state.rebuild_backends()
        await callback.message.edit_text(  # type: ignore[union-attr]
            "👁 <b>Vision: включен (openai)</b>",
            reply_markup=_vision_menu_kb(True, "openai"),
            parse_mode="HTML",
        )
        await callback.answer("✅ Vision OpenAI включён")

    @router.callback_query(lambda c: c.data == "su:v:an")
    async def cb_vision_anthropic(callback: CallbackQuery) -> None:
        await set_setting("vision.enabled", "true")
        await set_setting("vision.backend", "anthropic")
        bot_state.config.vision.enabled = True
        bot_state.config.vision.backend = "anthropic"
        bot_state.rebuild_backends()
        await callback.message.edit_text(  # type: ignore[union-attr]
            "👁 <b>Vision: включен (anthropic)</b>",
            reply_markup=_vision_menu_kb(True, "anthropic"),
            parse_mode="HTML",
        )
        await callback.answer("✅ Vision Anthropic включён")

    @router.callback_query(lambda c: c.data == "su:v:off")
    async def cb_vision_off(callback: CallbackQuery) -> None:
        await set_setting("vision.enabled", "false")
        bot_state.config.vision.enabled = False
        bot_state.rebuild_backends()
        settings = await get_all_settings()
        backend = settings.get("vision.backend", bot_state.config.vision.backend)
        await callback.message.edit_text(  # type: ignore[union-attr]
            "👁 <b>Vision: выключен</b>",
            reply_markup=_vision_menu_kb(False, backend),
            parse_mode="HTML",
        )
        await callback.answer("Vision выключен")

    # ---- Entry callbacks (view / delete) ----

    @router.callback_query(lambda c: c.data and c.data.startswith("en:v:"))
    async def cb_entry_view(callback: CallbackQuery) -> None:
        entry_id = int(callback.data.split(":")[-1])  # type: ignore[index]
        entry = await get_history_entry(entry_id)
        if not entry:
            await callback.answer("Запись не найдена", show_alert=True)
            return

        title = entry.get("title", "Без названия")
        category = entry.get("category", "")
        summary = entry.get("summary", "")
        source_url = entry.get("source_url", "")
        tags_raw = entry.get("tags", "")
        tags = [t for t in tags_raw.split(",") if t] if tags_raw else []
        tag_str = " ".join(f"#{t}" for t in tags) if tags else ""

        lines = [
            f"📌 <b>{title}</b>",
            f"📁 Категория: <code>{category}</code>",
        ]
        if tag_str:
            lines.append(f"🏷 {tag_str}")
        if summary:
            lines.append(f"\n<i>{summary[:300]}</i>")

        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="🔗 Открыть источник", url=source_url),
                    InlineKeyboardButton(text="🗑 Удалить", callback_data=f"en:d:{entry_id}"),
                ],
                [InlineKeyboardButton(text="◀️ К истории", callback_data="en:hist")],
            ]
        ) if source_url else InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"en:d:{entry_id}")],
                [InlineKeyboardButton(text="◀️ К истории", callback_data="en:hist")],
            ]
        )

        await callback.message.edit_text(  # type: ignore[union-attr]
            "\n".join(lines), reply_markup=kb, parse_mode="HTML"
        )
        await callback.answer()

    @router.callback_query(lambda c: c.data == "en:hist")
    async def cb_history_back(callback: CallbackQuery) -> None:
        entries = await get_recent_history(5)
        if not entries:
            await callback.message.edit_text("История пуста.")  # type: ignore[union-attr]
            await callback.answer()
            return

        rows = []
        for e in entries:
            eid = e["id"]
            title = (e["title"] or "Без названия")[:40]
            rows.append([InlineKeyboardButton(text=f"📌 {title}", callback_data=f"en:v:{eid}")])

        await callback.message.edit_text(  # type: ignore[union-attr]
            "🕘 <b>Последние 5 записей:</b>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
            parse_mode="HTML",
        )
        await callback.answer()

    @router.callback_query(lambda c: c.data and c.data.startswith("en:d:"))
    async def cb_entry_delete(callback: CallbackQuery) -> None:
        entry_id = int(callback.data.split(":")[-1])  # type: ignore[index]
        entry = await get_history_entry(entry_id)
        if not entry:
            await callback.answer("Запись не найдена", show_alert=True)
            return
        title = (entry.get("title") or "Без названия")[:40]
        await callback.message.edit_text(  # type: ignore[union-attr]
            f"🗑 Удалить <b>{title}</b>?\n\nЭто также удалит запись из хранилища, если возможно.",
            reply_markup=_delete_confirm_kb(entry_id),
            parse_mode="HTML",
        )
        await callback.answer()

    @router.callback_query(lambda c: c.data and c.data.startswith("en:dc:"))
    async def cb_entry_delete_confirm(callback: CallbackQuery) -> None:
        entry_id = int(callback.data.split(":")[-1])  # type: ignore[index]
        entry = await get_history_entry(entry_id)
        if not entry:
            await callback.answer("Запись не найдена", show_alert=True)
            return

        storage_ref = entry.get("storage_ref", "")
        remote_deleted = False
        if storage_ref and bot_state.storage_backend is not None:
            remote_deleted = await bot_state.storage_backend.delete_by_ref(storage_ref)

        await delete_history_entry(entry_id)

        msg = "✅ Запись удалена"
        if remote_deleted:
            msg += " (в том числе из хранилища)"
        await callback.message.edit_text(msg)  # type: ignore[union-attr]
        await callback.answer()

    @router.callback_query(lambda c: c.data and c.data.startswith("en:dx:"))
    async def cb_entry_delete_cancel(callback: CallbackQuery) -> None:
        entry_id = int(callback.data.split(":")[-1])  # type: ignore[index]
        entry = await get_history_entry(entry_id)
        if not entry:
            await callback.answer("Запись не найдена", show_alert=True)
            return

        source_url = entry.get("source_url", "")
        title = (entry.get("title") or "Без названия")
        category = entry.get("category", "")
        summary = entry.get("summary", "")
        tags_raw = entry.get("tags", "")
        tags = [t for t in tags_raw.split(",") if t] if tags_raw else []
        tag_str = " ".join(f"#{t}" for t in tags) if tags else ""

        lines = [f"📌 <b>{title}</b>", f"📁 Категория: <code>{category}</code>"]
        if tag_str:
            lines.append(f"🏷 {tag_str}")
        if summary:
            lines.append(f"\n<i>{summary[:300]}</i>")

        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="🔗 Открыть источник", url=source_url),
                    InlineKeyboardButton(text="🗑 Удалить", callback_data=f"en:d:{entry_id}"),
                ],
                [InlineKeyboardButton(text="◀️ К истории", callback_data="en:hist")],
            ]
        ) if source_url else InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"en:d:{entry_id}")],
                [InlineKeyboardButton(text="◀️ К истории", callback_data="en:hist")],
            ]
        )

        await callback.message.edit_text(  # type: ignore[union-attr]
            "\n".join(lines), reply_markup=kb, parse_mode="HTML"
        )
        await callback.answer("Отменено")

    return router
