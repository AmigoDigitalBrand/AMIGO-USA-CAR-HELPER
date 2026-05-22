from typing import Literal

Lang = Literal["ro", "ru", "en"]

STRINGS: dict[str, dict[str, str]] = {
    "ro": {
        "welcome": (
            "👋 Bună! Sunt AMIGO — asistentul tău auto.\n"
            "Trimite-mi un raport Carfax în format PDF și îți fac analiza completă."
        ),
        "processing": "⏳ Procesez raportul... Durează câteva secunde.",
        "not_carfax": (
            "❌ Fișierul nu pare a fi un raport Carfax valid.\n"
            "Te rog trimite un PDF Carfax oficial."
        ),
        "no_vin": (
            "❌ Nu am putut extrage VIN-ul din document.\n"
            "Asigură-te că PDF-ul este un raport Carfax complet."
        ),
        "saved": "✅ Raport salvat pentru VIN: `{vin}`",
        "updated": "🔄 Raport actualizat pentru VIN: `{vin}`",
        "file_too_big": (
            "❌ Fișierul depășește limita de 20 MB a Telegram.\n"
            "Te rog comprimă PDF-ul (ex. smallpdf.com) și trimite-l din nou."
        ),
        "error": "⚠️ A apărut o eroare: {error}",
        "choose_lang": "🌐 Alege limba pentru analiză:",
        "lang_btn_ro": "🇷🇴 Română",
        "lang_btn_ru": "🇷🇺 Русский",
        "lang_btn_en": "🇬🇧 English",
        "vin_exists": (
            "🔎 VIN `{vin}` există deja în platforma *Feduk USA Car*.\n\n"
            "Ce dorești să faci?"
        ),
        "btn_show_existing": "📋 Prezintă informația existentă",
        "btn_update": "🔄 Actualizează",
        "session_expired": "⚠️ Sesiunea a expirat. Te rog re-trimite PDF-ul.",
    },
    "ru": {
        "welcome": (
            "👋 Привет! Я AMIGO — твой автопомощник.\n"
            "Отправь мне отчёт Carfax в формате PDF, и я сделаю полный анализ."
        ),
        "processing": "⏳ Обрабатываю отчёт... Займёт несколько секунд.",
        "not_carfax": (
            "❌ Файл не похож на корректный отчёт Carfax.\n"
            "Пожалуйста, отправь официальный PDF Carfax."
        ),
        "no_vin": (
            "❌ Не удалось извлечь VIN из документа.\n"
            "Убедись, что PDF является полным отчётом Carfax."
        ),
        "saved": "✅ Отчёт сохранён для VIN: `{vin}`",
        "updated": "🔄 Отчёт обновлён для VIN: `{vin}`",
        "file_too_big": (
            "❌ Файл превышает лимит Telegram в 20 МБ.\n"
            "Сожми PDF (например, smallpdf.com) и отправь снова."
        ),
        "error": "⚠️ Произошла ошибка: {error}",
        "choose_lang": "🌐 Выбери язык анализа:",
        "lang_btn_ro": "🇷🇴 Română",
        "lang_btn_ru": "🇷🇺 Русский",
        "lang_btn_en": "🇬🇧 English",
        "vin_exists": (
            "🔎 VIN `{vin}` уже есть в платформе *Feduk USA Car*.\n\n"
            "Что ты хочешь сделать?"
        ),
        "btn_show_existing": "📋 Показать существующую информацию",
        "btn_update": "🔄 Обновить",
        "session_expired": "⚠️ Сессия истекла. Пожалуйста, отправь PDF снова.",
    },
    "en": {
        "welcome": (
            "👋 Hey! I'm AMIGO — your car buying assistant.\n"
            "Send me a Carfax report as a PDF and I'll give you the full breakdown."
        ),
        "processing": "⏳ Processing your report... Give me a few seconds.",
        "not_carfax": (
            "❌ This file doesn't appear to be a valid Carfax report.\n"
            "Please send an official Carfax PDF."
        ),
        "no_vin": (
            "❌ Could not extract a VIN from the document.\n"
            "Make sure the PDF is a complete Carfax report."
        ),
        "saved": "✅ Report saved for VIN: `{vin}`",
        "updated": "🔄 Report updated for VIN: `{vin}`",
        "file_too_big": (
            "❌ File exceeds Telegram's 20 MB limit.\n"
            "Please compress the PDF (e.g. smallpdf.com) and send it again."
        ),
        "error": "⚠️ An error occurred: {error}",
        "choose_lang": "🌐 Choose analysis language:",
        "lang_btn_ro": "🇷🇴 Română",
        "lang_btn_ru": "🇷🇺 Русский",
        "lang_btn_en": "🇬🇧 English",
        "vin_exists": (
            "🔎 VIN `{vin}` already exists in the *Feduk USA Car* platform.\n\n"
            "What would you like to do?"
        ),
        "btn_show_existing": "📋 Show existing info",
        "btn_update": "🔄 Update",
        "session_expired": "⚠️ Session expired. Please re-send the PDF.",
    },
}

DEFAULT_LANG: Lang = "ro"


def t(key: str, lang: Lang = DEFAULT_LANG, **kwargs: str) -> str:
    text = STRINGS.get(lang, STRINGS[DEFAULT_LANG]).get(key, key)
    return text.format(**kwargs) if kwargs else text
