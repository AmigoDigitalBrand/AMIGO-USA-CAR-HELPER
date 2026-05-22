import asyncio
import logging
from typing import TypedDict

from google import genai
from google.genai import types

from config import GEMINI_API_KEY

logger = logging.getLogger(__name__)

_client = genai.Client(api_key=GEMINI_API_KEY)

# Preference order — newest / fastest first.
# We sort discovered models by this order; anything not listed goes to the end.
_MODEL_PREFERENCE = [
    "gemini-2.5-flash-preview-05-20",
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-2.5-pro-preview-05-06",
    "gemini-2.0-flash",
    "gemini-2.0-flash-001",
    "gemini-2.0-flash-lite",
    "gemini-2.0-flash-exp",
    "gemini-1.5-flash",
    "gemini-1.5-flash-001",
    "gemini-1.5-pro",
]

_cached_model: str | None = None          # first model that actually worked
_available_models: list[str] | None = None  # from list_models(), populated once


def _fetch_available_models() -> list[str]:
    """Call ListModels and return short model names for this API key."""
    try:
        names = []
        for m in _client.models.list():
            short = m.name.replace("models/", "")
            if "gemini" in short:
                names.append(short)
        logger.info("ListModels returned %d Gemini models: %s", len(names), names)
        return names
    except Exception as exc:
        logger.warning("ListModels failed: %s — will try preference list directly.", exc)
        return []


def _sorted_models() -> list[str]:
    """
    Return models sorted by preference.
    Discovered (via ListModels) takes priority; falls back to full preference list.
    """
    global _available_models
    if _available_models is None:
        _available_models = _fetch_available_models()

    if _available_models:
        # sort by preference index; unlisted models go to the end
        pref_index = {m: i for i, m in enumerate(_MODEL_PREFERENCE)}
        ordered = sorted(
            _available_models,
            key=lambda m: pref_index.get(m, len(_MODEL_PREFERENCE)),
        )
        return ordered

    # ListModels gave nothing — try the full preference list directly
    return _MODEL_PREFERENCE


# ── Prompt ───────────────────────────────────────────────────────────────────

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


def _is_unavailable(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(k in msg for k in (
        "not found", "404", "no longer available", "deprecated",
        "not_found", "does not exist", "not supported", "is not found",
        "new users",
    ))


async def _generate_single(raw_text: str, language: str) -> str:
    global _cached_model
    prompt = _build_prompt(raw_text, language)

    # If we already found a working model, start with it
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
                    max_output_tokens=2048,
                ),
            )
            logger.info("✅ Gemini model used: %s (lang=%s)", model, language)
            _cached_model = model  # remember for next call
            return response.text.strip()
        except Exception as exc:
            if _is_unavailable(exc):
                logger.warning("⚠️  Model %s unavailable, trying next.", model)
                last_exc = exc
                continue
            raise

    raise RuntimeError(
        f"All Gemini models exhausted. Tried: {models}. Last error: {last_exc}"
    )


async def analyze_report(raw_text: str) -> AnalysisResult:
    """Generate AMIGO One-Sheet in RO, RU, EN concurrently."""
    ro, ru, en = await asyncio.gather(
        _generate_single(raw_text, "ro"),
        _generate_single(raw_text, "ru"),
        _generate_single(raw_text, "en"),
    )
    return AnalysisResult(ro=ro, ru=ru, en=en)
