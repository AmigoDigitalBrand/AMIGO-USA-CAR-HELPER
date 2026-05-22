import asyncio
from typing import TypedDict

from google import genai
from google.genai import types

from config import GEMINI_API_KEY

_client = genai.Client(api_key=GEMINI_API_KEY)

# Preferred models tried first (newest → fastest → most capable)
_PREFERRED_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-2.0-flash",
    "gemini-2.0-flash-001",
    "gemini-2.0-flash-lite",
    "gemini-2.0-flash-exp",
    "gemini-1.5-flash",
    "gemini-1.5-flash-001",
    "gemini-1.5-pro",
]

_discovered_models: list[str] = []  # populated at first call


def _list_available_models() -> list[str]:
    """Ask the API which models actually exist for this key."""
    try:
        result = []
        for m in _client.models.list():
            name = m.name  # e.g. "models/gemini-1.5-flash"
            # keep only generateContent-capable Gemini models
            short = name.replace("models/", "")
            if "gemini" in short:
                result.append(short)
        return result
    except Exception as exc:
        logger.warning("Could not list models: %s", exc)
        return []

_SYSTEM_INSTRUCTION = """
You are a cynical, seasoned auto dealer with 20+ years on the floor.
You have zero patience for fluff. You speak plainly, call out red flags bluntly,
and give real-world dollar verdicts. You write the "AMIGO One-Sheet Benchmark" —
a structured, no-BS vehicle history summary used by car buyers to make fast decisions.
""".strip()

_PROMPT_TEMPLATE = """
Given the following Carfax vehicle history report text, produce the **AMIGO One-Sheet Benchmark** in {language}.

Structure your output with these four sections using Markdown headers:

## 💰 Financial Value
Assess real market value vs. asking price risk. Factor in mileage, age, ownership count.
Be blunt about whether this car is worth money or a money pit.

## 🔧 Service Pedigree
Classify service history: OEM dealership vs. independent shops vs. gaps.
Note oil change frequency, recall completions, and general maintenance discipline.

## 💥 Damage Chronology
Timeline of all incidents: airbag deployments, structural damage, post-accident dealer repairs.
Call out any "cleaned up by dealer" patterns — these are the red flags.

## ⚖️ Executive Verdict
One ruthless paragraph. Buy it, walk away, or negotiate hard — and at what price offset.
No hedge words. Commit to a verdict.

---
CARFAX REPORT TEXT:
{raw_text}
"""


class AnalysisResult(TypedDict):
    ro: str
    ru: str
    en: str


def _build_prompt(raw_text: str, language: str) -> str:
    lang_map = {"ro": "Romanian", "ru": "Russian", "en": "English"}
    return _PROMPT_TEMPLATE.format(language=lang_map[language], raw_text=raw_text[:60_000])


import logging
logger = logging.getLogger(__name__)


def _get_model_list() -> list[str]:
    """Return preferred models + any discovered ones not already in the list."""
    global _discovered_models
    if not _discovered_models:
        _discovered_models = _list_available_models()
        logger.info("Discovered %d Gemini models: %s", len(_discovered_models), _discovered_models)
    # preferred first, then anything discovered that isn't already listed
    extra = [m for m in _discovered_models if m not in _PREFERRED_MODELS]
    return _PREFERRED_MODELS + extra


def _is_availability_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(k in msg for k in (
        "not found", "404", "no longer available", "deprecated",
        "not_found", "does not exist", "not supported", "is not found",
        "new users",
    ))


async def _generate_single(raw_text: str, language: str) -> str:
    prompt = _build_prompt(raw_text, language)
    models = await asyncio.to_thread(_get_model_list)
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
                    max_output_tokens=2048,
                ),
            )
            logger.info("Gemini model used: %s (lang=%s)", model, language)
            return response.text.strip()
        except Exception as exc:
            if _is_availability_error(exc):
                logger.warning("Model %s unavailable, trying next. (%s)", model, exc)
                last_exc = exc
                continue
            raise  # quota, auth, network — surface immediately

    raise RuntimeError(f"All Gemini models failed. Last error: {last_exc}")


async def analyze_report(raw_text: str) -> AnalysisResult:
    """Generate AMIGO One-Sheet in RO, RU, EN concurrently."""
    ro, ru, en = await asyncio.gather(
        _generate_single(raw_text, "ro"),
        _generate_single(raw_text, "ru"),
        _generate_single(raw_text, "en"),
    )
    return AnalysisResult(ro=ro, ru=ru, en=en)
