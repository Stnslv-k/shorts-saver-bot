from __future__ import annotations

LANG_EN = "en"
LANG_RU = "ru"

STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "welcome": "👋 Welcome! Send the password to get started.",
        "wrong_password": "❌ Wrong password. Try again.",
        "auth_success": "✅ Access granted! Send me a YouTube Shorts link.",
        "already_auth": "You're already authenticated. Send me a YouTube Shorts link.",
        "processing": "⏳ Processing...",
        "processing_vision": "⏳ Processing (with visual analysis)...",
        "saved": "✅ Saved!",
        "error": "❌ Failed to process. Please try again.",
        "error_no_transcript": (
            "❌ I couldn't extract usable content from this Short. "
            "Try another link, or enable Vision in /setup for videos with important on-screen text."
        ),
        "settings_menu": "⚙️ Settings",
        "status_title": "📊 Current config",
        "history_title": "📋 Recent entries",
        "history_empty": "No entries yet.",
        "btn_llm": "🤖 LLM",
        "btn_storage": "💾 Storage",
        "btn_vision": "👁 Vision",
        "btn_status": "📊 Status",
        "btn_language": "🌐 Language",
        "btn_close": "❌ Close",
        "btn_back": "◀️ Back",
        "btn_open_source": "🔗 Open source",
        "btn_delete": "🗑 Delete",
        "btn_delete_confirm": "⚠️ Confirm delete",
        "btn_cancel": "Cancel",
        "deleted": "🗑 Entry deleted.",
        "not_a_url": "Please send a YouTube Shorts URL.",
        "setup_incomplete": "⚙️ Setup incomplete. Use /setup to configure the bot.",
        "lang_select": "🌐 Choose language:",
        "lang_set": "✅ Language set to English.",
    },
    "ru": {
        "welcome": "👋 Привет! Отправь пароль чтобы начать.",
        "wrong_password": "❌ Неверный пароль. Попробуй ещё раз.",
        "auth_success": "✅ Доступ открыт! Отправь ссылку на YouTube Shorts.",
        "already_auth": "Ты уже авторизован. Отправь ссылку на YouTube Shorts.",
        "processing": "⏳ Обрабатываю...",
        "processing_vision": "⏳ Обрабатываю (с анализом видео)...",
        "saved": "✅ Сохранено!",
        "error": "❌ Не удалось обработать. Попробуй ещё раз.",
        "error_no_transcript": (
            "❌ Не удалось извлечь содержимое из этого Short. "
            "Попробуй другую ссылку или включи Vision в /setup для видео с важным текстом на экране."
        ),
        "settings_menu": "⚙️ Настройки",
        "status_title": "📊 Текущая конфигурация",
        "history_title": "📋 Последние записи",
        "history_empty": "Записей пока нет.",
        "btn_llm": "🤖 LLM",
        "btn_storage": "💾 Хранилище",
        "btn_vision": "👁 Vision",
        "btn_status": "📊 Статус",
        "btn_language": "🌐 Язык",
        "btn_close": "❌ Закрыть",
        "btn_back": "◀️ Назад",
        "btn_open_source": "🔗 Открыть источник",
        "btn_delete": "🗑 Удалить",
        "btn_delete_confirm": "⚠️ Подтвердить удаление",
        "btn_cancel": "Отмена",
        "deleted": "🗑 Запись удалена.",
        "not_a_url": "Пожалуйста, отправь ссылку на YouTube Shorts.",
        "setup_incomplete": "⚙️ Настройки не завершены. Используй /setup для настройки.",
        "lang_select": "🌐 Выбери язык:",
        "lang_set": "✅ Язык установлен: Русский.",
    },
}


def t(key: str, lang: str = LANG_EN) -> str:
    return STRINGS.get(lang, STRINGS[LANG_EN]).get(key, STRINGS[LANG_EN].get(key, key))
