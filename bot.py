import asyncio
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

from analyzer import analyze_report, extract_summary, format_cost, synthesize_bmw_equipment
from bmw_lookup import fetch_bimmer_equipment, is_bmw
from config import TELEGRAM_BOT_TOKEN
from database import AsyncSessionLocal, CarfaxReport, init_db
from sqlalchemy import func

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

SITE = "https://amigo-usa-car-helper-production.up.railway.app"

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


def _build_card(summary, vin: str, lang: Lang, bmw_equipment_text: str = "") -> str:
    """Build the short Telegram reply card with links."""
    site_url  = f"{SITE}/search?lang={lang}&vin={vin}"
    pdf_url   = f"{SITE}/pdf/{vin}"
    equip_url = f"{SITE}/bmw/{vin}"

    acc_icon = "✅" if summary.accidents == 0 else "💥"
    acc_label = {
        "ro": f"{summary.accidents} accident(e)",
        "ru": f"{summary.accidents} авари{'й' if summary.accidents != 1 else 'я'}",
        "en": f"{summary.accidents} accident{'s' if summary.accidents != 1 else ''}",
    }.get(lang, f"{summary.accidents}")

    owners_label = {
        "ro": f"{summary.owners} proprietar{'i' if summary.owners != 1 else ''}",
        "ru": f"{summary.owners} владел{'ец' if summary.owners == 1 else 'ьцев'}",
        "en": f"{summary.owners} owner{'s' if summary.owners != 1 else ''}",
    }.get(lang, f"{summary.owners}")

    analysis_label = {"ro": "📊 Analiza Feduk", "ru": "📊 Анализ Feduk",  "en": "📊 Feduk Analysis"}.get(lang, "📊 Analysis")
    pdf_label      = {"ro": "📄 Raport PDF",    "ru": "📄 PDF Отчёт",     "en": "📄 PDF Report"}.get(lang, "📄 PDF")
    equip_label    = {"ro": "⚙️ Echipare BMW",  "ru": "⚙️ Комплектация BMW", "en": "⚙️ BMW Equipment"}.get(lang, "⚙️ BMW Equipment")

    card = (
        f"🚗 *{summary.make} {summary.model} ({summary.year})*\n"
        f"📍 {summary.location}\n"
        f"👤 {owners_label}\n"
        f"{acc_icon} {acc_label}\n"
        f"🔑 VIN: `{vin}`\n\n"
        f"[{analysis_label}]({site_url})\n"
        f"[{pdf_label}]({pdf_url})"
    )
    if bmw_equipment_text:
        card += f"\n[{equip_label}]({equip_url})"
    return card


async def _run_analysis_and_save(
    vin: str,
    pdf_bytes: bytes,
    raw_text: str,
    telegram_user_id: int,
    lang: Lang,
) -> tuple[str, str]:
    """
    Full pipeline: Gemini analysis → BMW equipment → DB upsert.
    Returns (card_text, cost_note).
    """
    # 1. Generate full analyses + short summary concurrently
    analyses, summary = await asyncio.gather(
        analyze_report(raw_text),
        extract_summary(raw_text),
    )

    # 2. BMW equipment (optional)
    bmw_equipment_text = ""
    if is_bmw(summary.make):
        logger.info("BMW detected (%s) — fetching bimmer.work equipment", summary.make)
        bimmer = await fetch_bimmer_equipment(vin)
        if bimmer.found:
            bmw_equipment_text = await synthesize_bmw_equipment(bimmer.raw_html_text, lang)

    usage = analyses["usage"]

    # 3. Upsert into DB
    async with AsyncSessionLocal() as session:
        existing = await session.scalar(
            select(CarfaxReport).where(CarfaxReport.vin == vin)
        )
        # Preserve existing BMW data if fresh fetch returned nothing
        prev_bmw = (existing.bmw_equipment or "") if existing else ""
        effective_bmw = bmw_equipment_text or prev_bmw

        if existing:
            existing.telegram_user_id = telegram_user_id
            existing.raw_text         = raw_text
            existing.pdf_file         = pdf_bytes
            existing.ai_analysis_ro   = analyses["ro"]
            existing.ai_analysis_ru   = analyses["ru"]
            existing.ai_analysis_en   = analyses["en"]
            existing.tokens_in        = usage.tokens_in
            existing.tokens_out       = usage.tokens_out
            existing.bmw_equipment    = effective_bmw or None
            existing.created_at       = datetime.now(timezone.utc)
            await session.commit()
        else:
            report = CarfaxReport(
                vin=vin,
                telegram_user_id=telegram_user_id,
                raw_text=raw_text,
                pdf_file=pdf_bytes,
                ai_analysis_ro=analyses["ro"],
                ai_analysis_ru=analyses["ru"],
                ai_analysis_en=analyses["en"],
                tokens_in=usage.tokens_in,
                tokens_out=usage.tokens_out,
                bmw_equipment=effective_bmw or None,
            )
            session.add(report)
            await session.commit()

        cum_in  = await session.scalar(func.sum(CarfaxReport.tokens_in))  or 0
        cum_out = await session.scalar(func.sum(CarfaxReport.tokens_out)) or 0

    card      = _build_card(summary, vin, lang, effective_bmw)
    cost_note = format_cost(usage, cum_in, cum_out, lang)
    return card, cost_note


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
    doc  = update.message.document

    if not doc.mime_type == "application/pdf":
        await update.message.reply_text(t("not_carfax", lang))
        return

    status_msg = await update.message.reply_text(t("processing", lang))

    try:
        # 1. Download PDF bytes
        tg_file   = await context.bot.get_file(doc.file_id)
        pdf_bytes = bytes(await tg_file.download_as_bytearray())

        # 2. Parse — extract text + VIN
        vin, raw_text, is_carfax = parse_pdf(pdf_bytes)

        if not is_carfax:
            await status_msg.edit_text(t("not_carfax", lang))
            return

        if not vin:
            await status_msg.edit_text(t("no_vin", lang))
            return

        # 3. Check if VIN already exists in DB
        async with AsyncSessionLocal() as session:
            already_exists = await session.scalar(
                select(CarfaxReport.id).where(CarfaxReport.vin == vin)
            )

        if already_exists:
            # Store pending data for the "update" path
            context.user_data[f"pending_{vin}"] = {
                "pdf_bytes": pdf_bytes,
                "raw_text":  raw_text,
            }
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton(t("btn_show_existing", lang), callback_data=f"vin:show:{vin}"),
                InlineKeyboardButton(t("btn_update",        lang), callback_data=f"vin:update:{vin}"),
            ]])
            await status_msg.edit_text(
                t("vin_exists", lang, vin=vin),
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        # 4. New VIN — run full analysis
        card, cost_note = await _run_analysis_and_save(
            vin, pdf_bytes, raw_text, update.effective_user.id, lang
        )
        await status_msg.edit_text(t("saved", lang, vin=vin))
        await update.message.reply_text(
            card + cost_note,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True,
        )

    except Exception as exc:
        logger.exception("Error processing document")
        await status_msg.edit_text(t("error", lang, error=str(exc)))


async def cb_vin_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    lang = _get_lang(context)

    _, action, vin = query.data.split(":", 2)

    if action == "show":
        # Fetch existing record and re-extract summary via Gemini (fast, 1 call)
        async with AsyncSessionLocal() as session:
            record = await session.scalar(
                select(CarfaxReport).where(CarfaxReport.vin == vin)
            )

        if not record:
            await query.edit_message_text(t("error", lang, error="Record not found"))
            return

        summary            = await extract_summary(record.raw_text or "")
        bmw_equipment_text = record.bmw_equipment or ""
        card               = _build_card(summary, vin, lang, bmw_equipment_text)

        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(
            card,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True,
        )

    elif action == "update":
        pending = context.user_data.pop(f"pending_{vin}", None)
        if not pending:
            await query.answer(t("session_expired", lang), show_alert=True)
            return

        await query.edit_message_text(t("processing", lang))
        try:
            card, cost_note = await _run_analysis_and_save(
                vin,
                pending["pdf_bytes"],
                pending["raw_text"],
                query.from_user.id,
                lang,
            )
            await query.edit_message_text(t("updated", lang, vin=vin))
            await query.message.reply_text(
                card + cost_note,
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=True,
            )
        except Exception as exc:
            logger.exception("Error updating report")
            await query.edit_message_text(t("error", lang, error=str(exc)))


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
    app.add_handler(CallbackQueryHandler(cb_language,   pattern=r"^lang:"))
    app.add_handler(CallbackQueryHandler(cb_vin_action, pattern=r"^vin:"))
    app.add_handler(MessageHandler(filters.Document.PDF, handle_document))

    logger.info("AMIGO bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
