import asyncio
from typing import TypedDict

from google import genai
from google.genai import types

from config import GEMINI_API_KEY

_client = genai.Client(api_key=GEMINI_API_KEY)
_MODEL = "gemini-2.0-flash"

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


async def _generate_single(raw_text: str, language: str) -> str:
    prompt = _build_prompt(raw_text, language)
    response = await asyncio.to_thread(
        _client.models.generate_content,
        model=_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=_SYSTEM_INSTRUCTION,
            temperature=0.4,
            max_output_tokens=2048,
        ),
    )
    return response.text.strip()


async def analyze_report(raw_text: str) -> AnalysisResult:
    """Generate AMIGO One-Sheet in RO, RU, EN concurrently."""
    ro, ru, en = await asyncio.gather(
        _generate_single(raw_text, "ro"),
        _generate_single(raw_text, "ru"),
        _generate_single(raw_text, "en"),
    )
    return AnalysisResult(ro=ro, ru=ru, en=en)
