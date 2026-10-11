"""At submit time: normalise a report into AIAttributes.

The model turns free text into consistent vocabulary ("navy school bag" ->
item_type "backpack", color_family ["blue"]) so retrieval can find synonyms.

These attributes are PUBLIC (returned by GET /reports), so:
- the model never sees private_details or contact info;
- Python drops any brand / feature / location that isn't backed by the text.
Never raises because of the AI: failure -> extraction_status="failed".
"""

from __future__ import annotations

import json
import logging
import re
from typing import Literal

from pydantic import BaseModel

from foundit_ai.llm_client import AIUnavailable, LLMClient
from foundit_ai.schemas import AIAttributes, Category, ReportRecord

log = logging.getLogger(__name__)

ColorFamily = Literal[
    "black", "white", "grey", "blue", "green", "red", "yellow", "orange",
    "purple", "pink", "brown", "beige", "silver", "gold", "multicolor",
]


class ExtractionOut(BaseModel):
    """Exactly what we ask the model for."""

    item_type: str | None
    category: Category | None
    color_family: list[ColorFamily]
    brand: str | None
    features: list[str]
    location_normalized: str | None


SYSTEM_PROMPT = """You normalise lost-and-found reports into structured attributes.
Use ONLY facts stated in the report. If something is not stated, use null or [].
- item_type: a short common noun for the object, e.g. "backpack" for "school bag",
  "smartphone" for "iPhone", "water bottle", "wallet".
- category: one of the allowed categories.
- color_family: basic colour families of the stated colours only
  ("navy" -> "blue", "maroon" -> "red", "charcoal" -> "grey"). [] if no colour is stated.
- brand: only if a brand name is written in the report, else null.
- features: up to 5 short phrases copied or minimally shortened from the report
  (contents, attachments, damage, stickers). No guesses.
- location_normalized: the stated place in lowercase, else null."""


def build_user_prompt(r: ReportRecord) -> str:
    """Public fields only — never private_details or contact."""
    return json.dumps({"type": r.type, "description": r.description,
                       "category": r.category, "color": r.color,
                       "location": r.location}, ensure_ascii=False)


def _words(text: str | None) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(w) > 2}


# Colour words people use -> the basic family we store. Deterministic, so a model
# mistake (e.g. "brown" -> "blue") can never reach the public attributes.
COLOR_WORDS: dict[str, str] = {
    **{c: c for c in ("black", "white", "grey", "blue", "green", "red", "yellow",
                      "orange", "purple", "pink", "brown", "beige", "silver", "gold")},
    "gray": "grey", "charcoal": "grey", "navy": "blue", "teal": "blue",
    "turquoise": "blue", "cyan": "blue", "maroon": "red", "burgundy": "red",
    "crimson": "red", "scarlet": "red", "olive": "green", "lime": "green",
    "khaki": "beige", "cream": "beige", "tan": "brown", "ivory": "white",
    "violet": "purple", "lilac": "purple", "magenta": "pink", "golden": "gold",
    "multicolor": "multicolor", "multicoloured": "multicolor", "multicolored": "multicolor",
}


def color_families(report: ReportRecord) -> list[str]:
    """Families named in the colour field (or, if empty, the description)."""
    text = report.color or report.description
    words = re.findall(r"[a-z]+", text.lower())
    return list(dict.fromkeys(COLOR_WORDS[w] for w in words if w in COLOR_WORDS))


def _grounded(phrase: str, source_words: set[str]) -> bool:
    """At least half of the phrase's meaningful words appear in the report."""
    words = _words(phrase)
    return bool(words) and len(words & source_words) * 2 >= len(words)


def extract_attributes(report: ReportRecord, llm: LLMClient) -> AIAttributes:
    try:
        out = llm.complete_json(SYSTEM_PROMPT, build_user_prompt(report),
                                ExtractionOut, effort="low")
    except AIUnavailable as e:
        log.warning("extraction_failed report_id=%s error=%s", report.id, e)
        return AIAttributes(extraction_status="failed")

    source = _words(" ".join(filter(None, [report.description, report.color,
                                           report.location, report.category])))
    brand = out.brand if out.brand and _grounded(out.brand, source) else None
    features = [f for f in out.features if _grounded(f, source)][:5]
    location = (out.location_normalized
                if out.location_normalized and _grounded(out.location_normalized, source)
                else None)
    return AIAttributes(
        extraction_status="ok",
        item_type=(out.item_type or "").strip().lower() or None,
        category=out.category,
        # Code decides colours when the user named one; the model only fills gaps.
        color_family=color_families(report) or list(dict.fromkeys(out.color_family)),
        brand=brand,
        features=features,
        location_normalized=location,
    )
