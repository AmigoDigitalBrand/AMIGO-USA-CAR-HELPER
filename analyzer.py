import asyncio
import logging
from dataclasses import dataclass, field
from typing import TypedDict

from google import genai
from google.genai import types

from config import GEMINI_API_KEY

logger = logging.getLogger(__name__)

_client = genai.Client(api_key=GEMINI_API_KEY)

# ── Gemini pricing (USD per 1M tokens) ──────────────────────────────────────
# Gemini 2.5 Flash (non-thinking):  input $0.075 / output $0.30
# Gemini 2.5 Pro:                   input $1.25  / output $10.00
# We use Flash rates as default; adjust if a Pro model wins.
_PRICE_IN  = 0.075 / 1_000_000   # $ per input token
_PRICE_OUT = 0.300 / 1_000_000   # $ per output token

# ── Model preference order ───────────────────────────────────────────────────
_MODEL_PREFERENCE = [
    # Newest / best first
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite",
    "gemini-3.1-flash-lite-preview",
    "gemini-3-flash-preview",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-flash-latest",
    "gemini-flash-lite-latest",
    "gemini-2.5-pro",
    "gemini-pro-latest",
    "gemini-2.5-flash-preview-05-20",
    "gemini-2.5-pro-preview-05-06",
    "gemini-2.0-flash",
    "gemini-2.0-flash-001",
    "gemini-2.0-flash-lite",
    "gemini-2.0-flash-lite-001",
]

_cached_model: str | None = None
_available_models: list[str] | None = None


def _fetch_available_models() -> list[str]:
    try:
        names = [
            m.name.replace("models/", "")
            for m in _client.models.list()
            if "gemini" in m.name
        ]
        logger.info("ListModels → %d models: %s", len(names), names)
        return names
    except Exception as exc:
        logger.warning("ListModels failed: %s", exc)
        return []


def _sorted_models() -> list[str]:
    global _available_models
    if _available_models is None:
        _available_models = _fetch_available_models()
    if _available_models:
        pref = {m: i for i, m in enumerate(_MODEL_PREFERENCE)}
        return sorted(_available_models, key=lambda m: pref.get(m, len(_MODEL_PREFERENCE)))
    return _MODEL_PREFERENCE


# ── Prompt ───────────────────────────────────────────────────────────────────

_SYSTEM_INSTRUCTION = """
You are a professional automotive analyst with 15+ years of experience evaluating used vehicles.
You write clear, factual, well-structured reports. Your tone is neutral and objective —
not overly dry or robotic, but not sensationalist either. You highlight both positives and red flags
with equal weight. Your goal is to help the buyer make an informed decision.
""".strip()

_PROMPT_TEMPLATE = """
Analyze the following Carfax vehicle history report and generate a structured AMIGO Full Report in **{language}**.

Use EXACTLY these Markdown sections:

## 🚗 Date Generale
- **Marcă / Model / An producție**
- **Prima vânzare**: data și locația (stat, dealer dacă e menționat)
- **Rulaj total** la ultima înregistrare din raport

## 💥 Istoricul Accidentelor
For each accident or damage event found:
- **Data** evenimentului
- **Tip daună**: (structurală / airbag / lovitură ușoară / daună totală / etc.)
- **Severitate**: X/10 (1 = zgârietură, 5 = lovitură medie, 10 = daună totală)
- **Reparații efectuate** după eveniment (dacă sunt menționate)

If no accidents: state clearly "Fără accidente înregistrate."

## 🔧 Deservire Tehnică
- **Număr total vizite service** înregistrate
- **Interval mediu** între schimburi de ulei (în mile sau km)
- **Tip service predominant**: dealer OEM / service independent / mixt
- **Goluri suspecte**: perioade fără nicio înregistrare (> 12 luni)

## 🔩 Piese de Schimb Înregistrate
Bullet list of all parts replaced or repaired as recorded in the report.
If none mentioned: "Nicio piesă specifică înregistrată."

## 👤 Proprietari
| Nr. | De la | Rulaj | Locație |
|-----|-------|-------|---------|
Fill one row per owner. Use data from report.

## ⚖️ Concluzie
2-3 short brutal sentences. Real verdict: buy / negotiate / run away — and at what price.
No fluff. Commit.

---
CARFAX REPORT TEXT:
{raw_text}
"""


def _build_prompt(raw_text: str, language: str) -> str:
    lang_map = {"ro": "Romanian", "ru": "Russian", "en": "English"}
    return _PROMPT_TEMPLATE.format(language=lang_map[language], raw_text=raw_text[:60_000])


def _is_unavailable(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(k in msg for k in (
        "not found", "404", "no longer available", "deprecated",
        "not_found", "does not exist", "not supported", "is not found", "new users",
        "503", "unavailable", "high demand", "overloaded", "try again later",
        "resource exhausted", "429",
    ))


# ── Result types ─────────────────────────────────────────────────────────────

@dataclass
class TokenUsage:
    tokens_in:  int = 0
    tokens_out: int = 0

    def __iadd__(self, other: "TokenUsage") -> "TokenUsage":
        self.tokens_in  += other.tokens_in
        self.tokens_out += other.tokens_out
        return self

    @property
    def cost_usd(self) -> float:
        return self.tokens_in * _PRICE_IN + self.tokens_out * _PRICE_OUT


class AnalysisResult(TypedDict):
    ro:    str
    ru:    str
    en:    str
    usage: TokenUsage


# ── Generation ───────────────────────────────────────────────────────────────

async def _generate_single(raw_text: str, language: str) -> tuple[str, TokenUsage]:
    global _cached_model
    prompt = _build_prompt(raw_text, language)
    models = await asyncio.to_thread(_sorted_models)
    if _cached_model and _cached_model in models:
        models = [_cached_model] + [m for m in models if m != _cached_model]

    last_exc: Exception | None = None
    for model in models:
        try:
            response = await asyncio.to_thread(
                _client.models.generate_content,
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=_SYSTEM_INSTRUCTION,
                    temperature=0.4,
                    max_output_tokens=3000,
                ),
            )
            _cached_model = model
            logger.info("✅ Model used: %s (lang=%s)", model, language)
            usage = TokenUsage(
                tokens_in  = getattr(response.usage_metadata, "prompt_token_count",  0) or 0,
                tokens_out = getattr(response.usage_metadata, "candidates_token_count", 0) or 0,
            )
            return response.text.strip(), usage
        except Exception as exc:
            if _is_unavailable(exc):
                logger.warning("⚠️  Model %s unavailable, trying next.", model)
                last_exc = exc
                continue
            raise

    raise RuntimeError(f"All Gemini models exhausted. Last error: {last_exc}")


async def analyze_report(raw_text: str) -> AnalysisResult:
    """Generate AMIGO Full Report in RO, RU, EN concurrently."""
    results = await asyncio.gather(
        _generate_single(raw_text, "ro"),
        _generate_single(raw_text, "ru"),
        _generate_single(raw_text, "en"),
    )
    (ro, u_ro), (ru, u_ru), (en, u_en) = results
    total = TokenUsage()
    total += u_ro
    total += u_ru
    total += u_en
    return AnalysisResult(ro=ro, ru=ru, en=en, usage=total)


def format_cost(usage: TokenUsage, cumulative_in: int, cumulative_out: int, lang: str = "ro") -> str:
    """Return a hidden cost summary (not shown to users — internal only)."""
    session_cost = usage.cost_usd
    cum_cost = cumulative_in * _PRICE_IN + cumulative_out * _PRICE_OUT
    lines = {
        "ro": (
            f"\n\n💸 Cost sesiune: `${session_cost:.5f}` | Total: `${cum_cost:.5f}`"
            f"\n_({usage.tokens_in:,} in / {usage.tokens_out:,} out tokens)_"
        ),
        "ru": (
            f"\n\n💸 Сессия: `${session_cost:.5f}` | Всего: `${cum_cost:.5f}`"
            f"\n_({usage.tokens_in:,} in / {usage.tokens_out:,} out tokens)_"
        ),
        "en": (
            f"\n\n💸 Session: `${session_cost:.5f}` | Total: `${cum_cost:.5f}`"
            f"\n_({usage.tokens_in:,} in / {usage.tokens_out:,} out tokens)_"
        ),
    }
    return lines.get(lang, lines["ro"])


# ── BMW equipment synthesis ───────────────────────────────────────────────────

_BMW_EQUIPMENT_PROMPT = """
You are given raw text scraped from bimmer.work — a BMW VIN decoder.
The text has two sections: general vehicle data and an OPTIONS / EQUIPMENT CODES section
with 3-digit codes (e.g. 1X8, 552, 6C4) followed by English and German descriptions.

Produce a clean, structured Markdown report of the vehicle's full equipment in {language}.
Use these sections (skip any with no data):

## 🏎️ Model & Producție
Include: model name, engine, drivetrain, transmission, color (code + name), upholstery, plant, country.

## 🎨 Exterior
Wheels (code + description), paint, glass, mirrors, roof, body styling options.

## 🪑 Interior
Seats (adjustment, heating, memory), steering wheel, trim finish, ambient light, floor mats, panoramic roof.

## 🔊 Tehnologie & Confort
Navigation, gesture control, head-up display, ConnectedDrive packages, satellite radio,
comfort access, universal remote, e-drive services.

## 🛡️ Siguranță & Asistență
Adaptive headlights, fog lights, high-beam assist, driving assistant, parking assistant,
active protection, alarm system, tyre pressure indicator, runflat tyres.

## 📋 Coduri Opțiuni Complete
List EVERY option code found as: `CODE` — Description (English)
Format as a compact bulleted list. Include ALL codes, even those with only German descriptions.

Be factual. No fluff. Use the language: {language}.

BIMMER.WORK DATA:
{raw_text}
"""


async def synthesize_bmw_equipment(raw_text: str, language: str = "ro") -> str:
    """Synthesize BMW equipment from bimmer.work scraped text."""
    lang_map = {"ro": "Romanian", "ru": "Russian", "en": "English"}
    prompt = _BMW_EQUIPMENT_PROMPT.format(
        language=lang_map.get(language, "Romanian"),
        raw_text=raw_text[:12_000],
    )
    models = await asyncio.to_thread(_sorted_models)
    global _cached_model
    if _cached_model and _cached_model in models:
        models = [_cached_model] + [m for m in models if m != _cached_model]

    for model in models:
        try:
            response = await asyncio.to_thread(
                _client.models.generate_content,
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0.2, max_output_tokens=4000),
            )
            logger.info("✅ BMW equipment synthesized via %s", model)
            return response.text.strip()
        except Exception as exc:
            if _is_unavailable(exc):
                continue
            raise
    return ""


# ── Short summary extraction ──────────────────────────────────────────────────

import json as _json

_SUMMARY_PROMPT = """You are a data extractor. Read the Carfax report below and return a single JSON object.

Extract these exact fields:
- make: car brand (e.g. "BMW")
- model: model and trim (e.g. "X3 xDrive28i")
- year: production year as integer (e.g. 2021)
- location: last known US state (e.g. "California")
- owners: total number of owners as integer
- accidents: total number of accident or damage events as integer (0 if none)

Return ONLY the raw JSON. No markdown fences, no explanation, nothing else.
Example: {{"make":"BMW","model":"X3 xDrive28i","year":2021,"location":"California","owners":2,"accidents":1}}

CARFAX REPORT:
{raw_text}"""


@dataclass
class VehicleSummary:
    make: str = "Unknown"
    model: str = "Unknown"
    year: str = "N/A"
    location: str = "N/A"
    owners: int = 0
    accidents: int = 0


def _parse_summary_json(text: str) -> VehicleSummary:
    """Extract JSON from model response, tolerating markdown fences."""
    import re
    # strip markdown code fences if present
    clean = re.sub(r"```[a-z]*\n?", "", text).strip()
    # find first {...} block
    match = re.search(r"\{.*?\}", clean, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON found in: {text[:200]}")
    data = _json.loads(match.group())
    return VehicleSummary(
        make      = str(data.get("make", "Unknown")).strip(),
        model     = str(data.get("model", "Unknown")).strip(),
        year      = str(data.get("year", "N/A")).strip(),
        location  = str(data.get("location", "N/A")).strip(),
        owners    = int(data.get("owners", 0)),
        accidents = int(data.get("accidents", 0)),
    )


async def extract_summary(raw_text: str) -> VehicleSummary:
    """Quick structured extraction — single Gemini call, JSON output."""
    prompt = _SUMMARY_PROMPT.format(raw_text=raw_text[:25_000])
    models = await asyncio.to_thread(_sorted_models)
    global _cached_model
    if _cached_model and _cached_model in models:
        models = [_cached_model] + [m for m in models if m != _cached_model]

    for model in models:
        try:
            response = await asyncio.to_thread(
                _client.models.generate_content,
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0.0, max_output_tokens=300),
            )
            result = _parse_summary_json(response.text)
            logger.info("✅ Summary extracted via %s: %s", model, result)
            return result
        except Exception as exc:
            if _is_unavailable(exc):
                continue
            logger.warning("Summary extraction failed (%s): %s — raw: %s",
                           model, exc, getattr(exc, '__context__', ''))
            continue   # try next model rather than giving up
    return VehicleSummary()
