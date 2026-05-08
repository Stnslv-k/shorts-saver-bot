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
from bot.i18n import LANG_EN, LANG_RU, t
from bot.settings_db import (
    add_history_entry,
    delete_history_entry,
    get_all_settings,
    get_history_entry,
    get_recent_history,
    get_ui_lang,
    set_setting,
    set_ui_lang,
)

if TYPE_CHECKING:
    from bot.state import BotState

logger = logging.getLogger(__name__)

_CMD_RE = re.compile(r"^/\w+(@\w+)?$")


class SetupState(StatesGroup):
    waiting_llm_openai_key = State()
    waiting_llm_anthropic_key = State()
    waiting_llm_openrouter_key = State()
    waiting_llm_ollama_url = State()
    waiting_storage_notion_key = State()
    waiting_storage_notion_db_id = State()
    waiting_storage_obsidian_path = State()


# ---------- keyboard helpers ----------


def _main_menu_kb(lang: str = LANG_EN) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=t("btn_llm", lang), callback_data="su:l"),
                InlineKeyboardButton(text=t("btn_storage", lang), callback_data="su:s"),
            ],
            [
                InlineKeyboardButton(text=t("btn_vision", lang), callback_data="su:v"),
                InlineKeyboardButton(text=t("btn_status", lang), callback_data="su:st"),
            ],
            [InlineKeyboardButton(text=t("btn_language", lang), callback_data="su:lang")],
            [InlineKeyboardButton(text=t("btn_close", lang), callback_data="su:x")],
        ]
    )


def _llm_menu_kb(current: str, lang: str = LANG_EN) -> InlineKeyboardMarkup:
    def _b(label: str, key: str, cb: str) -> InlineKeyboardButton:
        text = f"✅ {label}" if current == key else label
        return InlineKeyboardButton(text=text, callback_data=cb)

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _b("Ollama", "ollama", "su:l:ol"),
                _b("OpenAI", "openai", "su:l:oa"),
            ],
            [
                _b("Anthropic", "anthropic", "su:l:an"),
                _b("OpenRouter", "openrouter", "su:l:or"),
            ],
            [InlineKeyboardButton(text=t("btn_back", lang), callback_data="su:m")],
        ]
    )


def _storage_menu_kb(current: str, lang: str = LANG_EN) -> InlineKeyboardMarkup:
    def _b(label: str, key: str, cb: str) -> InlineKeyboardButton:
        text = f"✅ {label}" if current == key else label
        return InlineKeyboardButton(text=text, callback_data=cb)

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _b("Notion", "notion", "su:s:no"),
                _b("Obsidian", "obsidian", "su:s:ob"),
            ],
            [InlineKeyboardButton(text=t("btn_back", lang), callback_data="su:m")],
        ]
    )


def _vision_menu_kb(enabled: bool, backend: str, lang: str = LANG_EN) -> InlineKeyboardMarkup:
    openai_label = "✅ OpenAI" if (enabled and backend == "openai") else "Enable OpenAI" if lang == LANG_EN else "Включить OpenAI"
    anthropic_label = "✅ Anthropic" if (enabled and backend == "anthropic") else "Enable Anthropic" if lang == LANG_EN else "Включить Anthropic"
    disable_label = "Disable" if lang == LANG_EN else "Выключить"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=openai_label, callback_data="su:v:oa"),
                InlineKeyboardButton(text=anthropic_label, callback_data="su:v:an"),
            ],
            [InlineKeyboardButton(text=disable_label, callback_data="su:v:off")],
            [InlineKeyboardButton(text=t("btn_back", lang), callback_data="su:m")],
        ]
    )


def _lang_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🇬🇧 English", callback_data="su:lang:en"),
                InlineKeyboardButton(text="🇷🇺 Русский", callback_data="su:lang:ru"),
            ],
        ]
    )


def _mask(value: str) -> str:
    if not value:
        return "—"
    if len(value) <= 4:
        return "****"
    return f"...{value[-4:]}"


def _is_command(text: str) -> bool:
    return bool(_CMD_RE.match(text))


# ---------- status text helper ----------


async def _status_text(bot_state: BotState, lang: str = LANG_EN) -> str:
    settings = await get_all_settings()
    cfg = bot_state.config

    llm_backend = settings.get("llm.backend", cfg.llm.backend)
    openai_key = settings.get("llm.openai.api_key") or cfg.llm.openai.api_key
    anthropic_key = settings.get("llm.anthropic.api_key") or cfg.llm.anthropic.api_key
    openrouter_key = settings.get("llm.openrouter.api_key") or cfg.llm.openrouter.api_key
    ollama_url = settings.get("llm.ollama.url") or cfg.llm.ollama.url

    storage_backend = settings.get("storage.backend", cfg.storage.backend)
    notion_key = settings.get("storage.notion.api_key") or cfg.storage.notion.api_key
    notion_db = settings.get("storage.notion.database_id") or cfg.storage.notion.database_id
    obsidian_path = settings.get("storage.obsidian.vault_path") or cfg.storage.obsidian.vault_path

    vision_enabled = cfg.vision.enabled or settings.get("vision.enabled", "").lower() in ("true", "1", "yes")
    vision_backend = settings.get("vision.backend", cfg.vision.backend)

    if lang == LANG_RU:
        not_set = "не задан"
        vision_status = f"включен ({vision_backend})" if vision_enabled else "выключен"
        return (
            f"📊 <b>Текущий статус</b>\n\n"
            f"🤖 <b>LLM:</b> {llm_backend}\n"
            f"  OpenAI key: {_mask(openai_key)}\n"
            f"  Anthropic key: {_mask(anthropic_key)}\n"
            f"  OpenRouter key: {_mask(openrouter_key)}\n"
            f"  Ollama URL: {ollama_url or not_set}\n\n"
            f"💾 <b>Хранилище:</b> {storage_backend}\n"
            f"  Notion key: {_mask(notion_key)}\n"
            f"  Notion DB: {_mask(notion_db)}\n"
            f"  Obsidian path: {obsidian_path or not_set}\n\n"
            f"👁 <b>Vision:</b> {vision_status}"
        )
    else:
        not_set = "not set"
        vision_status = f"enabled ({vision_backend})" if vision_enabled else "disabled"
        return (
            f"📊 <b>Current status</b>\n\n"
            f"🤖 <b>LLM:</b> {llm_backend}\n"
            f"  OpenAI key: {_mask(openai_key)}\n"
            f"  Anthropic key: {_mask(anthropic_key)}\n"
            f"  OpenRouter key: {_mask(openrouter_key)}\n"
            f"  Ollama URL: {ollama_url or not_set}\n\n"
            f"💾 <b>Storage:</b> {storage_backend}\n"
            f"  Notion key: {_mask(notion_key)}\n"
            f"  Notion DB: {_mask(notion_db)}\n"
            f"  Obsidian path: {obsidian_path or not_set}\n\n"
            f"👁 <b>Vision:</b> {vision_status}"
        )


# ---------- entry inline keyboard ----------


def entry_inline_kb(entry_id: int, source_url: str, lang: str = LANG_EN) -> InlineKeyboardMarkup:
    buttons = []
    if source_url:
        buttons.append(InlineKeyboardButton(text=t("btn_open_source", lang), url=source_url))
    buttons.append(InlineKeyboardButton(text=t("btn_delete", lang), callback_data=f"en:d:{entry_id}"))
    return InlineKeyboardMarkup(inline_keyboard=[buttons])


def _delete_confirm_kb(entry_id: int, lang: str = LANG_EN) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=t("btn_delete_confirm", lang), callback_data=f"en:dc:{entry_id}"),
                InlineKeyboardButton(text=t("btn_cancel", lang), callback_data=f"en:dx:{entry_id}"),
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
        lang = await get_ui_lang()
        await state.clear()
        settings = await get_all_settings()
        backend = settings.get("llm.backend", bot_state.config.llm.backend)
        await message.answer(
            f"⚙️ <b>{t('settings_menu', lang)}</b>\n\nLLM: {backend}",
            reply_markup=_main_menu_kb(lang),
            parse_mode="HTML",
        )

    # ---- /status ----

    @router.message(Command("status"))
    async def cmd_status(message: Message) -> None:
        if not await _guard(message.from_user.id):  # type: ignore[union-attr]
            return
        lang = await get_ui_lang()
        await message.answer(await _status_text(bot_state, lang), parse_mode="HTML")

    # ---- /history ----

    @router.message(Command("history"))
    async def cmd_history(message: Message) -> None:
        if not await _guard(message.from_user.id):  # type: ignore[union-attr]
            return
        lang = await get_ui_lang()
        entries = await get_recent_history(5)
        if not entries:
            await message.answer(t("history_empty", lang))
            return

        rows = []
        for e in entries:
            eid = e["id"]
            title = (e["title"] or "—")[:40]
            rows.append(
                [InlineKeyboardButton(text=f"📌 {title}", callback_data=f"en:v:{eid}")]
            )

        kb = InlineKeyboardMarkup(inline_keyboard=rows)
        await message.answer(
            f"🕘 <b>{t('history_title', lang)}:</b>", reply_markup=kb, parse_mode="HTML"
        )

    # ---- main menu callbacks ----

    @router.callback_query(lambda c: c.data == "su:m")
    async def cb_main_menu(callback: CallbackQuery, state: FSMContext) -> None:
        lang = await get_ui_lang()
        await state.clear()
        settings = await get_all_settings()
        backend = settings.get("llm.backend", bot_state.config.llm.backend)
        await callback.message.edit_text(  # type: ignore[union-attr]
            f"⚙️ <b>{t('settings_menu', lang)}</b>\n\nLLM: {backend}",
            reply_markup=_main_menu_kb(lang),
            parse_mode="HTML",
        )
        await callback.answer()

    @router.callback_query(lambda c: c.data == "su:x")
    async def cb_close(callback: CallbackQuery, state: FSMContext) -> None:
        lang = await get_ui_lang()
        await state.clear()
        await callback.message.edit_text(t("settings_menu", lang) + " — closed.")  # type: ignore[union-attr]
        await callback.answer()

    @router.callback_query(lambda c: c.data == "su:st")
    async def cb_status(callback: CallbackQuery) -> None:
        lang = await get_ui_lang()
        kb = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text=t("btn_back", lang), callback_data="su:m")]]
        )
        await callback.message.edit_text(  # type: ignore[union-attr]
            await _status_text(bot_state, lang),
            reply_markup=kb,
            parse_mode="HTML",
        )
        await callback.answer()

    # ---- Language submenu ----

    @router.callback_query(lambda c: c.data == "su:lang")
    async def cb_lang_menu(callback: CallbackQuery) -> None:
        lang = await get_ui_lang()
        await callback.message.edit_text(  # type: ignore[union-attr]
            t("lang_select", lang),
            reply_markup=_lang_menu_kb(),
        )
        await callback.answer()

    @router.callback_query(lambda c: c.data in ("su:lang:en", "su:lang:ru"))
    async def cb_lang_set(callback: CallbackQuery) -> None:
        new_lang = callback.data.split(":")[-1]  # type: ignore[union-attr]
        await set_ui_lang(new_lang)
        await callback.message.edit_text(t("lang_set", new_lang))  # type: ignore[union-attr]
        await callback.answer()

    # ---- LLM submenu ----

    @router.callback_query(lambda c: c.data == "su:l")
    async def cb_llm_menu(callback: CallbackQuery, state: FSMContext) -> None:
        lang = await get_ui_lang()
        await state.clear()
        settings = await get_all_settings()
        backend = settings.get("llm.backend", bot_state.config.llm.backend)
        await callback.message.edit_text(  # type: ignore[union-attr]
            f"🤖 <b>LLM Backend: {backend}</b>",
            reply_markup=_llm_menu_kb(backend, lang),
            parse_mode="HTML",
        )
        await callback.answer()

    @router.callback_query(lambda c: c.data == "su:l:ol")
    async def cb_llm_ollama(callback: CallbackQuery, state: FSMContext) -> None:
        lang = await get_ui_lang()
        await set_setting("llm.backend", "ollama")
        bot_state.config.llm.backend = "ollama"
        settings = await get_all_settings()
        current_url = settings.get("llm.ollama.url") or bot_state.config.llm.ollama.url
        await state.set_state(SetupState.waiting_llm_ollama_url)
        await callback.message.edit_text(  # type: ignore[union-attr]
            f"🦙 <b>Ollama</b>\n\nURL: <code>{current_url}</code>\n\n"
            + ("Enter new URL or /skip:" if lang == LANG_EN else "Введи новый URL или /skip:"),
            parse_mode="HTML",
        )
        await callback.answer()

    @router.callback_query(lambda c: c.data == "su:l:oa")
    async def cb_llm_openai(callback: CallbackQuery, state: FSMContext) -> None:
        lang = await get_ui_lang()
        await set_setting("llm.backend", "openai")
        bot_state.config.llm.backend = "openai"
        await state.set_state(SetupState.waiting_llm_openai_key)
        prompt = "Enter <b>OpenAI API key</b>:" if lang == LANG_EN else "Введи <b>OpenAI API key</b>:"
        await callback.message.edit_text(f"🔑 {prompt}", parse_mode="HTML")  # type: ignore[union-attr]
        await callback.answer()

    @router.callback_query(lambda c: c.data == "su:l:an")
    async def cb_llm_anthropic(callback: CallbackQuery, state: FSMContext) -> None:
        lang = await get_ui_lang()
        await set_setting("llm.backend", "anthropic")
        bot_state.config.llm.backend = "anthropic"
        await state.set_state(SetupState.waiting_llm_anthropic_key)
        prompt = "Enter <b>Anthropic API key</b>:" if lang == LANG_EN else "Введи <b>Anthropic API key</b>:"
        await callback.message.edit_text(f"🔑 {prompt}", parse_mode="HTML")  # type: ignore[union-attr]
        await callback.answer()

    @router.callback_query(lambda c: c.data == "su:l:or")
    async def cb_llm_openrouter(callback: CallbackQuery, state: FSMContext) -> None:
        lang = await get_ui_lang()
        await set_setting("llm.backend", "openrouter")
        bot_state.config.llm.backend = "openrouter"
        await state.set_state(SetupState.waiting_llm_openrouter_key)
        prompt = (
            "Enter <b>OpenRouter API key</b>:"
            if lang == LANG_EN
            else "Введи <b>OpenRouter API key</b>:"
        )
        await callback.message.edit_text(f"🔑 {prompt}", parse_mode="HTML")  # type: ignore[union-attr]
        await callback.answer()

    # ---- LLM state handlers ----

    @router.message(SetupState.waiting_llm_openai_key)
    async def recv_openai_key(message: Message, state: FSMContext) -> None:
        lang = await get_ui_lang()
        text = (message.text or "").strip()
        if text and not _is_command(text):
            await set_setting("llm.openai.api_key", text)
            bot_state.config.llm.openai.api_key = text
            bot_state.rebuild_backends()
            saved_msg = f"✅ OpenAI key saved: {_mask(text)}" if lang == LANG_EN else f"✅ OpenAI key сохранён: {_mask(text)}"
            await message.answer(saved_msg)
        await state.clear()
        settings = await get_all_settings()
        backend = settings.get("llm.backend", bot_state.config.llm.backend)
        await message.answer(
            f"🤖 <b>LLM Backend: {backend}</b>",
            reply_markup=_llm_menu_kb(backend, lang),
            parse_mode="HTML",
        )

    @router.message(SetupState.waiting_llm_anthropic_key)
    async def recv_anthropic_key(message: Message, state: FSMContext) -> None:
        lang = await get_ui_lang()
        text = (message.text or "").strip()
        if text and not _is_command(text):
            await set_setting("llm.anthropic.api_key", text)
            bot_state.config.llm.anthropic.api_key = text
            bot_state.rebuild_backends()
            saved_msg = f"✅ Anthropic key saved: {_mask(text)}" if lang == LANG_EN else f"✅ Anthropic key сохранён: {_mask(text)}"
            await message.answer(saved_msg)
        await state.clear()
        settings = await get_all_settings()
        backend = settings.get("llm.backend", bot_state.config.llm.backend)
        await message.answer(
            f"🤖 <b>LLM Backend: {backend}</b>",
            reply_markup=_llm_menu_kb(backend, lang),
            parse_mode="HTML",
        )

    @router.message(SetupState.waiting_llm_openrouter_key)
    async def recv_openrouter_key(message: Message, state: FSMContext) -> None:
        lang = await get_ui_lang()
        text = (message.text or "").strip()
        if text and not _is_command(text):
            await set_setting("llm.openrouter.api_key", text)
            bot_state.config.llm.openrouter.api_key = text
            bot_state.rebuild_backends()
            saved_msg = (
                f"✅ OpenRouter key saved: {_mask(text)}"
                if lang == LANG_EN
                else f"✅ OpenRouter key сохранён: {_mask(text)}"
            )
            await message.answer(saved_msg)
        await state.clear()
        settings = await get_all_settings()
        backend = settings.get("llm.backend", bot_state.config.llm.backend)
        await message.answer(
            f"🤖 <b>LLM Backend: {backend}</b>",
            reply_markup=_llm_menu_kb(backend, lang),
            parse_mode="HTML",
        )

    @router.message(SetupState.waiting_llm_ollama_url)
    async def recv_ollama_url(message: Message, state: FSMContext) -> None:
        lang = await get_ui_lang()
        text = (message.text or "").strip()
        if text and not _is_command(text):
            await set_setting("llm.ollama.url", text)
            bot_state.config.llm.ollama.url = text
            bot_state.rebuild_backends()
            saved_msg = f"✅ Ollama URL saved: <code>{text}</code>" if lang == LANG_EN else f"✅ Ollama URL сохранён: <code>{text}</code>"
            await message.answer(saved_msg, parse_mode="HTML")
        await state.clear()
        settings = await get_all_settings()
        backend = settings.get("llm.backend", bot_state.config.llm.backend)
        await message.answer(
            f"🤖 <b>LLM Backend: {backend}</b>",
            reply_markup=_llm_menu_kb(backend, lang),
            parse_mode="HTML",
        )

    # ---- Storage submenu ----

    @router.callback_query(lambda c: c.data == "su:s")
    async def cb_storage_menu(callback: CallbackQuery, state: FSMContext) -> None:
        lang = await get_ui_lang()
        await state.clear()
        settings = await get_all_settings()
        backend = settings.get("storage.backend", bot_state.config.storage.backend)
        await callback.message.edit_text(  # type: ignore[union-attr]
            f"💾 <b>Storage: {backend}</b>",
            reply_markup=_storage_menu_kb(backend, lang),
            parse_mode="HTML",
        )
        await callback.answer()

    @router.callback_query(lambda c: c.data == "su:s:no")
    async def cb_storage_notion(callback: CallbackQuery, state: FSMContext) -> None:
        lang = await get_ui_lang()
        await set_setting("storage.backend", "notion")
        bot_state.config.storage.backend = "notion"
        await state.set_state(SetupState.waiting_storage_notion_key)
        prompt = "Enter <b>Notion API key</b>:" if lang == LANG_EN else "Введи <b>Notion API key</b>:"
        await callback.message.edit_text(f"🔑 {prompt}", parse_mode="HTML")  # type: ignore[union-attr]
        await callback.answer()

    @router.callback_query(lambda c: c.data == "su:s:ob")
    async def cb_storage_obsidian(callback: CallbackQuery, state: FSMContext) -> None:
        lang = await get_ui_lang()
        await set_setting("storage.backend", "obsidian")
        bot_state.config.storage.backend = "obsidian"
        await state.set_state(SetupState.waiting_storage_obsidian_path)
        prompt = "Enter path to <b>Obsidian vault</b>:" if lang == LANG_EN else "Введи путь к <b>Obsidian vault</b>:"
        await callback.message.edit_text(f"📁 {prompt}", parse_mode="HTML")  # type: ignore[union-attr]
        await callback.answer()

    @router.message(SetupState.waiting_storage_notion_key)
    async def recv_notion_key(message: Message, state: FSMContext) -> None:
        lang = await get_ui_lang()
        text = (message.text or "").strip()
        if text and not _is_command(text):
            await set_setting("storage.notion.api_key", text)
            bot_state.config.storage.notion.api_key = text
            saved_msg = f"✅ Notion key saved: {_mask(text)}" if lang == LANG_EN else f"✅ Notion key сохранён: {_mask(text)}"
            await message.answer(saved_msg)
        settings = await get_all_settings()
        current_db = settings.get("storage.notion.database_id") or bot_state.config.storage.notion.database_id
        await state.set_state(SetupState.waiting_storage_notion_db_id)
        db_prompt = (
            f"Now enter <b>Notion Database ID</b>:\nCurrent: <code>{current_db or 'not set'}</code>"
            if lang == LANG_EN else
            f"Теперь введи <b>Notion Database ID</b>:\nТекущий: <code>{current_db or 'не задан'}</code>"
        )
        await message.answer(db_prompt, parse_mode="HTML")

    @router.message(SetupState.waiting_storage_notion_db_id)
    async def recv_notion_db_id(message: Message, state: FSMContext) -> None:
        lang = await get_ui_lang()
        text = (message.text or "").strip()
        if text and not _is_command(text):
            await set_setting("storage.notion.database_id", text)
            bot_state.config.storage.notion.database_id = text
            bot_state.rebuild_backends()
            saved_msg = f"✅ Notion Database ID saved: {_mask(text)}" if lang == LANG_EN else f"✅ Notion Database ID сохранён: {_mask(text)}"
            await message.answer(saved_msg)
        await state.clear()
        settings = await get_all_settings()
        backend = settings.get("storage.backend", bot_state.config.storage.backend)
        await message.answer(
            f"💾 <b>Storage: {backend}</b>",
            reply_markup=_storage_menu_kb(backend, lang),
            parse_mode="HTML",
        )

    @router.message(SetupState.waiting_storage_obsidian_path)
    async def recv_obsidian_path(message: Message, state: FSMContext) -> None:
        lang = await get_ui_lang()
        text = (message.text or "").strip()
        if text and not _is_command(text):
            await set_setting("storage.obsidian.vault_path", text)
            bot_state.config.storage.obsidian.vault_path = text
            bot_state.rebuild_backends()
            saved_msg = f"✅ Obsidian vault path saved: <code>{text}</code>" if lang == LANG_EN else f"✅ Obsidian vault path сохранён: <code>{text}</code>"
            await message.answer(saved_msg, parse_mode="HTML")
        await state.clear()
        settings = await get_all_settings()
        backend = settings.get("storage.backend", bot_state.config.storage.backend)
        await message.answer(
            f"💾 <b>Storage: {backend}</b>",
            reply_markup=_storage_menu_kb(backend, lang),
            parse_mode="HTML",
        )

    # ---- Vision submenu ----

    @router.callback_query(lambda c: c.data == "su:v")
    async def cb_vision_menu(callback: CallbackQuery, state: FSMContext) -> None:
        lang = await get_ui_lang()
        await state.clear()
        settings = await get_all_settings()
        enabled = bot_state.config.vision.enabled or settings.get("vision.enabled", "").lower() in ("true", "1", "yes")
        backend = settings.get("vision.backend", bot_state.config.vision.backend)
        if lang == LANG_RU:
            status = f"включен ({backend})" if enabled else "выключен"
        else:
            status = f"enabled ({backend})" if enabled else "disabled"
        await callback.message.edit_text(  # type: ignore[union-attr]
            f"👁 <b>Vision: {status}</b>",
            reply_markup=_vision_menu_kb(enabled, backend, lang),
            parse_mode="HTML",
        )
        await callback.answer()

    @router.callback_query(lambda c: c.data == "su:v:oa")
    async def cb_vision_openai(callback: CallbackQuery) -> None:
        lang = await get_ui_lang()
        await set_setting("vision.enabled", "true")
        await set_setting("vision.backend", "openai")
        bot_state.config.vision.enabled = True
        bot_state.config.vision.backend = "openai"
        bot_state.rebuild_backends()
        status = "enabled (openai)" if lang == LANG_EN else "включен (openai)"
        await callback.message.edit_text(  # type: ignore[union-attr]
            f"👁 <b>Vision: {status}</b>",
            reply_markup=_vision_menu_kb(True, "openai", lang),
            parse_mode="HTML",
        )
        await callback.answer("✅ Vision OpenAI enabled" if lang == LANG_EN else "✅ Vision OpenAI включён")

    @router.callback_query(lambda c: c.data == "su:v:an")
    async def cb_vision_anthropic(callback: CallbackQuery) -> None:
        lang = await get_ui_lang()
        await set_setting("vision.enabled", "true")
        await set_setting("vision.backend", "anthropic")
        bot_state.config.vision.enabled = True
        bot_state.config.vision.backend = "anthropic"
        bot_state.rebuild_backends()
        status = "enabled (anthropic)" if lang == LANG_EN else "включен (anthropic)"
        await callback.message.edit_text(  # type: ignore[union-attr]
            f"👁 <b>Vision: {status}</b>",
            reply_markup=_vision_menu_kb(True, "anthropic", lang),
            parse_mode="HTML",
        )
        await callback.answer("✅ Vision Anthropic enabled" if lang == LANG_EN else "✅ Vision Anthropic включён")

    @router.callback_query(lambda c: c.data == "su:v:off")
    async def cb_vision_off(callback: CallbackQuery) -> None:
        lang = await get_ui_lang()
        await set_setting("vision.enabled", "false")
        bot_state.config.vision.enabled = False
        bot_state.rebuild_backends()
        settings = await get_all_settings()
        backend = settings.get("vision.backend", bot_state.config.vision.backend)
        status = "disabled" if lang == LANG_EN else "выключен"
        await callback.message.edit_text(  # type: ignore[union-attr]
            f"👁 <b>Vision: {status}</b>",
            reply_markup=_vision_menu_kb(False, backend, lang),
            parse_mode="HTML",
        )
        await callback.answer("Vision disabled" if lang == LANG_EN else "Vision выключен")

    # ---- Entry callbacks (view / delete) ----

    @router.callback_query(lambda c: c.data and c.data.startswith("en:v:"))
    async def cb_entry_view(callback: CallbackQuery) -> None:
        lang = await get_ui_lang()
        entry_id = int(callback.data.split(":")[-1])  # type: ignore[index]
        entry = await get_history_entry(entry_id)
        if not entry:
            await callback.answer("Entry not found" if lang == LANG_EN else "Запись не найдена", show_alert=True)
            return

        title = entry.get("title", "—")
        category = entry.get("category", "")
        summary = entry.get("summary", "")
        source_url = entry.get("source_url", "")
        tags_raw = entry.get("tags", "")
        tags = [tg for tg in tags_raw.split(",") if tg] if tags_raw else []
        tag_str = " ".join(f"#{tg}" for tg in tags) if tags else ""

        lines = [
            f"📌 <b>{title}</b>",
            f"📁 <code>{category}</code>",
        ]
        if tag_str:
            lines.append(f"🏷 {tag_str}")
        if summary:
            lines.append(f"\n<i>{summary[:300]}</i>")

        back_label = "◀️ Back" if lang == LANG_EN else "◀️ К истории"
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text=t("btn_open_source", lang), url=source_url),
                    InlineKeyboardButton(text=t("btn_delete", lang), callback_data=f"en:d:{entry_id}"),
                ],
                [InlineKeyboardButton(text=back_label, callback_data="en:hist")],
            ]
        ) if source_url else InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=t("btn_delete", lang), callback_data=f"en:d:{entry_id}")],
                [InlineKeyboardButton(text=back_label, callback_data="en:hist")],
            ]
        )

        await callback.message.edit_text(  # type: ignore[union-attr]
            "\n".join(lines), reply_markup=kb, parse_mode="HTML"
        )
        await callback.answer()

    @router.callback_query(lambda c: c.data == "en:hist")
    async def cb_history_back(callback: CallbackQuery) -> None:
        lang = await get_ui_lang()
        entries = await get_recent_history(5)
        if not entries:
            await callback.message.edit_text(t("history_empty", lang))  # type: ignore[union-attr]
            await callback.answer()
            return

        rows = []
        for e in entries:
            eid = e["id"]
            title = (e["title"] or "—")[:40]
            rows.append([InlineKeyboardButton(text=f"📌 {title}", callback_data=f"en:v:{eid}")])

        await callback.message.edit_text(  # type: ignore[union-attr]
            f"🕘 <b>{t('history_title', lang)}:</b>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
            parse_mode="HTML",
        )
        await callback.answer()

    @router.callback_query(lambda c: c.data and c.data.startswith("en:d:"))
    async def cb_entry_delete(callback: CallbackQuery) -> None:
        lang = await get_ui_lang()
        entry_id = int(callback.data.split(":")[-1])  # type: ignore[index]
        entry = await get_history_entry(entry_id)
        if not entry:
            await callback.answer("Entry not found" if lang == LANG_EN else "Запись не найдена", show_alert=True)
            return
        title = (entry.get("title") or "—")[:40]
        confirm_text = (
            f"🗑 Delete <b>{title}</b>?" if lang == LANG_EN
            else f"🗑 Удалить <b>{title}</b>?"
        )
        await callback.message.edit_text(  # type: ignore[union-attr]
            confirm_text,
            reply_markup=_delete_confirm_kb(entry_id, lang),
            parse_mode="HTML",
        )
        await callback.answer()

    @router.callback_query(lambda c: c.data and c.data.startswith("en:dc:"))
    async def cb_entry_delete_confirm(callback: CallbackQuery) -> None:
        lang = await get_ui_lang()
        entry_id = int(callback.data.split(":")[-1])  # type: ignore[index]
        entry = await get_history_entry(entry_id)
        if not entry:
            await callback.answer("Entry not found" if lang == LANG_EN else "Запись не найдена", show_alert=True)
            return

        storage_ref = entry.get("storage_ref", "")
        remote_deleted = False
        if storage_ref and bot_state.storage_backend is not None:
            remote_deleted = await bot_state.storage_backend.delete_by_ref(storage_ref)

        await delete_history_entry(entry_id)

        if lang == LANG_RU:
            msg = "✅ Запись удалена"
            if remote_deleted:
                msg += " (в том числе из хранилища)"
        else:
            msg = "✅ Entry deleted"
            if remote_deleted:
                msg += " (including from storage)"
        await callback.message.edit_text(msg)  # type: ignore[union-attr]
        await callback.answer()

    @router.callback_query(lambda c: c.data and c.data.startswith("en:dx:"))
    async def cb_entry_delete_cancel(callback: CallbackQuery) -> None:
        lang = await get_ui_lang()
        entry_id = int(callback.data.split(":")[-1])  # type: ignore[index]
        entry = await get_history_entry(entry_id)
        if not entry:
            await callback.answer("Entry not found" if lang == LANG_EN else "Запись не найдена", show_alert=True)
            return

        source_url = entry.get("source_url", "")
        title = (entry.get("title") or "—")
        category = entry.get("category", "")
        summary = entry.get("summary", "")
        tags_raw = entry.get("tags", "")
        tags = [tg for tg in tags_raw.split(",") if tg] if tags_raw else []
        tag_str = " ".join(f"#{tg}" for tg in tags) if tags else ""

        lines = [f"📌 <b>{title}</b>", f"📁 <code>{category}</code>"]
        if tag_str:
            lines.append(f"🏷 {tag_str}")
        if summary:
            lines.append(f"\n<i>{summary[:300]}</i>")

        back_label = "◀️ Back" if lang == LANG_EN else "◀️ К истории"
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text=t("btn_open_source", lang), url=source_url),
                    InlineKeyboardButton(text=t("btn_delete", lang), callback_data=f"en:d:{entry_id}"),
                ],
                [InlineKeyboardButton(text=back_label, callback_data="en:hist")],
            ]
        ) if source_url else InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=t("btn_delete", lang), callback_data=f"en:d:{entry_id}")],
                [InlineKeyboardButton(text=back_label, callback_data="en:hist")],
            ]
        )

        await callback.message.edit_text(  # type: ignore[union-attr]
            "\n".join(lines), reply_markup=kb, parse_mode="HTML"
        )
        await callback.answer("Cancelled" if lang == LANG_EN else "Отменено")

    return router
