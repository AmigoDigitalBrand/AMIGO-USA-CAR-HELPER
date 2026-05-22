import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from analyzer import analyze_report
from config import TELEGRAM_BOT_TOKEN
from database import AsyncSessionLocal, CarfaxReport, init_db

# Local Telegram Bot API server — removes the 20 MB file size limit
LOCAL_API_BASE_URL = "http://localhost:8081/bot"
LOCAL_API_FILE_URL = "http://localhost:8081/file/bot"
from locales import DEFAULT_LANG, Lang, t
from pdf_parser import parse_pdf

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _lang_keyboard(lang: Lang) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(t("lang_btn_ro", lang), callback_data="lang:ro"),
            InlineKeyboardButton(t("lang_btn_ru", lang), callback_data="lang:ru"),
            InlineKeyboardButton(t("lang_btn_en", lang), callback_data="lang:en"),
        ]
    ])


def _get_lang(context: ContextTypes.DEFAULT_TYPE) -> Lang:
    return context.user_data.get("lang", DEFAULT_LANG)


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = _get_lang(context)
    await update.message.reply_text(
        t("welcome", lang) + f"\n\n{t('choose_lang', lang)}",
        reply_markup=_lang_keyboard(lang),
    )


async def cb_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    lang: Lang = query.data.split(":")[1]  # type: ignore[assignment]
    context.user_data["lang"] = lang
    await query.edit_message_reply_markup(reply_markup=None)
    await query.message.reply_text(f"✅ Language set to: {lang.upper()}")


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = _get_lang(context)
    doc = update.message.document

    if not doc.mime_type == "application/pdf":
        await update.message.reply_text(t("not_carfax", lang))
        return

    status_msg = await update.message.reply_text(t("processing", lang))

    try:
        # 1. Download PDF bytes
        tg_file = await context.bot.get_file(doc.file_id)
        pdf_bytes = bytes(await tg_file.download_as_bytearray())

        # 2. Parse — extract text + VIN
        vin, raw_text, is_carfax = parse_pdf(pdf_bytes)

        if not is_carfax:
            await status_msg.edit_text(t("not_carfax", lang))
            return

        if not vin:
            await status_msg.edit_text(t("no_vin", lang))
            return

        # 3. Generate Gemini analyses (RO, RU, EN)
        analyses = await analyze_report(raw_text)

        # 4. Upsert into DB
        async with AsyncSessionLocal() as session:
            existing = await session.scalar(
                select(CarfaxReport).where(CarfaxReport.vin == vin)
            )
            if existing:
                existing.telegram_user_id = update.effective_user.id
                existing.raw_text = raw_text
                existing.pdf_file = pdf_bytes
                existing.ai_analysis_ro = analyses["ro"]
                existing.ai_analysis_ru = analyses["ru"]
                existing.ai_analysis_en = analyses["en"]
                existing.created_at = datetime.now(timezone.utc)
                await session.commit()
                status_key = "updated"
            else:
                report = CarfaxReport(
                    vin=vin,
                    telegram_user_id=update.effective_user.id,
                    raw_text=raw_text,
                    pdf_file=pdf_bytes,
                    ai_analysis_ro=analyses["ro"],
                    ai_analysis_ru=analyses["ru"],
                    ai_analysis_en=analyses["en"],
                )
                session.add(report)
                await session.commit()
                status_key = "saved"

        # 5. Reply with analysis in user's language
        lang_key = f"ai_analysis_{lang}"
        analysis_text = analyses[lang]

        await status_msg.edit_text(t(status_key, lang, vin=vin))
        # Telegram message limit is 4096 chars — split if needed
        chunk_size = 4000
        for i in range(0, len(analysis_text), chunk_size):
            await update.message.reply_text(
                analysis_text[i : i + chunk_size],
                parse_mode=ParseMode.MARKDOWN,
            )

    except Exception as exc:
        logger.exception("Error processing document")
        await status_msg.edit_text(t("error", lang, error=str(exc)))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def post_init(app: Application) -> None:
    await init_db()
    logger.info("Database tables ensured.")


def main() -> None:
    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .local_mode(True)
        .base_url(LOCAL_API_BASE_URL)
        .base_file_url(LOCAL_API_FILE_URL)
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(cb_language, pattern=r"^lang:"))
    app.add_handler(MessageHandler(filters.Document.PDF, handle_document))

    logger.info("AMIGO bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
