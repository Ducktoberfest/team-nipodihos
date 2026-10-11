"""Step 2 of matching: ONE model call compares the query with all candidates.

Why one call: the free tier allows ~8K tokens/minute; one batched call uses
~3-4K tokens, five separate calls would use far more.

The model's answer is untrusted. It is validated against LLMComparison here
(schema) and then checked quote-by-quote in scoring.py (grounding).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Literal

from pydantic import BaseModel

from foundit_ai.extract import COLOR_WORDS
from foundit_ai.llm_client import LLMClient
from foundit_ai.schemas import (
    Assessment,
    LLMComparison,
    LLMEvidence,
    LLMVerdict,
    ReportRecord,
    Result,
)
from foundit_ai.scoring import NEXT_STEP_BY_ASSESSMENT

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You compare lost-and-found reports on a university campus.
You receive one QUERY report and several CANDIDATE reports of the opposite type
(lost vs found). For EACH candidate, collect evidence for and against the idea
that both reports describe the same physical item.

Evidence rules:
- Use ONLY facts written in the reports. Never guess, assume or invent details.
- this_quote must be copied EXACTLY (a verbatim substring) from one field of the
  QUERY report; candidate_quote EXACTLY from one field of that CANDIDATE.
- Give one evidence item for each of: category, color, location, features.
  If either report does not mention it, use result "unknown" with null quotes.
  Missing information is NEVER evidence of a match.
- If BOTH reports have private_details, add one "private_details" item that compares
  those two private details directly with each other.
- "agree" = clearly the same (synonyms and shades count: "school bag" ~ "backpack",
  "navy" ~ "dark blue", "keyring" ~ "keychain").
  "partial" = compatible but vague or only partly overlapping ("blue" vs "dark blue",
  "library" vs "library cafe").
  "conflict" = the reports contradict each other ("no keyring" vs "keychain",
  different buildings, different private details).
- Each note is one short sentence (at most 15 words). Quotes should be short.
- Do not judge dates or times; a separate system checks timing.
- No probabilities or percentages anywhere.

Output rules:
- suggested_assessment: likely_match, possible_match, unlikely_match, or
  insufficient_information (too little is known on either side to judge).
- missing_information: short phrases naming details that would help confirm,
  mostly what the CANDIDATE report does not say.
- next_step: one sentence of advice to the QUERY report's author. Encourage
  verification before any handover. NEVER reveal the candidate's private_details;
  ask the author to describe their own detail to the other person instead.
- Return exactly one verdict per candidate, using its id as candidate_id."""


def _report_payload(r: ReportRecord) -> dict:
    """What the model sees. No contact info, no timestamps (timing is checked in Python)."""
    return {
        "id": r.id,
        "type": r.type,
        "description": r.description,
        "category": r.category,
        "color": r.color,
        "location": r.location,
        "private_details": r.private_details,
    }


def build_user_prompt(query: ReportRecord, candidates: list[ReportRecord]) -> str:
    return json.dumps({
        "query_report": _report_payload(query),
        "candidate_reports": [_report_payload(c) for c in candidates],
    }, ensure_ascii=False, indent=1)


def _index_verdicts(candidates: list[ReportRecord],
                    verdicts_in: list[LLMVerdict]) -> dict[int, LLMVerdict]:
    wanted = {c.id for c in candidates}
    verdicts: dict[int, LLMVerdict] = {}
    for v in verdicts_in:
        if v.candidate_id not in wanted:
            log.warning("model_returned_unknown_candidate id=%s", v.candidate_id)
            continue
        verdicts.setdefault(v.candidate_id, v)   # keep the first if duplicated
    missing = wanted - verdicts.keys()
    if missing:
        log.warning("model_skipped_candidates ids=%s", sorted(missing))
    return verdicts


def compare_reports(query: ReportRecord, candidates: list[ReportRecord],
                    llm: LLMClient) -> dict[int, LLMVerdict]:
    """QUOTE MODE (gpt-oss): the model quotes the evidence verbatim.
    Return {candidate_id: verdict}. Raises AIUnavailable if the model fails."""
    if not candidates:
        return {}
    result = llm.complete_json(SYSTEM_PROMPT, build_user_prompt(query, candidates),
                               LLMComparison, effort="medium")
    return _index_verdicts(candidates, result.candidates)


# --- FIELD MODE (Gemma on Google AI Studio) -----------------------------------
# Google's hosted models run a "recitation" filter that blocks answers repeating
# input text word-for-word, so quote mode fails there. In field mode the model
# only says WHICH FIELD supports each judgement; Python copies the words from
# the report itself. Evidence text therefore cannot be invented by the model.

SourceField = Literal["description", "category", "color", "location",
                      "private_details", "none"]


class FieldEvidence(BaseModel):
    attribute: Literal["category", "color", "location", "features", "private_details"]
    result: Result
    query_field: SourceField
    candidate_field: SourceField


class FieldVerdict(BaseModel):
    candidate_id: int
    evidence: list[FieldEvidence]
    suggested_assessment: Assessment


class FieldComparison(BaseModel):
    candidates: list[FieldVerdict]


FIELD_SYSTEM_PROMPT = """You compare lost-and-found reports on a university campus.
You receive one QUERY report and several CANDIDATE reports of the opposite type.
For EACH candidate and EACH attribute (category, color, location, features, and
private_details when both reports have private details) decide:
  agree    = clearly the same (synonyms/shades count: "school bag" ~ "backpack", "navy" ~ "dark blue")
  partial  = compatible but vague or partly overlapping
  conflict = the reports contradict each other
  unknown  = either report does not mention it (missing information is NEVER a match)
and name WHICH FIELD of each report supports it, or "none".
Use only facts written in the reports. Do not copy any text from the reports.
Do not judge dates or times. Then give suggested_assessment: likely_match,
possible_match, unlikely_match, or insufficient_information.
Return one entry per candidate, using its id as candidate_id."""

_NOTES: dict[tuple[str, str], str] = {
    ("category", "agree"): "Same kind of item.",
    ("category", "partial"): "Similar kind of item.",
    ("category", "conflict"): "Different kinds of item.",
    ("color", "agree"): "Same colour.",
    ("color", "partial"): "Similar colours.",
    ("color", "conflict"): "Different colours.",
    ("location", "agree"): "Same place.",
    ("location", "partial"): "Nearby or overlapping places.",
    ("location", "conflict"): "Different places.",
    ("features", "agree"): "Distinguishing details match.",
    ("features", "partial"): "Some details match.",
    ("features", "conflict"): "Distinguishing details contradict each other.",
}
_LABELS = {"category": "type of item", "color": "colour", "location": "place",
           "features": "distinguishing details"}
_SHADES = r"(?:(?:dark|light|pale|bright|deep)\s+)?"


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower())) - {"the", "a", "an", "it", "in", "on", "at", "of", "and", "my", "was"}


def _snippet(description: str, attribute: str, other: ReportRecord) -> str:
    """A short verbatim piece of the description relevant to `attribute`."""
    if attribute == "color":
        colors = "|".join(sorted(COLOR_WORDS, key=len, reverse=True))
        m = re.search(rf"\b{_SHADES}(?:{colors})\b", description, re.IGNORECASE)
        if m:
            return m.group(0)
    other_words = _words(" ".join(filter(None, [other.description, other.color,
                                               other.location, other.private_details])))
    clauses = [c.strip() for c in re.split(r"[.,;]", description) if c.strip()]
    best = max(clauses, key=lambda c: len(_words(c) & other_words), default=description)
    m = re.match(r"\s*((?:\S+\s+){0,9}\S+)", best)      # first ≤10 words, still verbatim
    return m.group(1) if m else best


def _field_text(r: ReportRecord, field: str, attribute: str,
                other: ReportRecord) -> str | None:
    if field == "none":
        return None
    value = getattr(r, field)
    if not value:
        return None                      # model cited an empty field -> no evidence
    return _snippet(value, attribute, other) if field == "description" else value


def compare_reports_by_field(query: ReportRecord, candidates: list[ReportRecord],
                             llm: LLMClient) -> dict[int, LLMVerdict]:
    """FIELD MODE: same output as compare_reports, but evidence text comes from Python."""
    if not candidates:
        return {}
    result = llm.complete_json(FIELD_SYSTEM_PROMPT, build_user_prompt(query, candidates),
                               FieldComparison, effort="medium")
    field_verdicts = list(result.candidates)
    # Gemma sometimes answers for only some candidates; ask once more for the rest.
    answered = {fv.candidate_id for fv in field_verdicts}
    skipped = [c for c in candidates if c.id not in answered]
    if skipped:
        log.info("field_mode_retry_skipped ids=%s", [c.id for c in skipped])
        retry = llm.complete_json(FIELD_SYSTEM_PROMPT, build_user_prompt(query, skipped),
                                  FieldComparison, effort="medium")
        field_verdicts += retry.candidates

    by_id = {c.id: c for c in candidates}
    verdicts = []
    for fv in field_verdicts:
        cand = by_id.get(fv.candidate_id)
        if cand is None:
            log.warning("model_returned_unknown_candidate id=%s", fv.candidate_id)
            continue
        evidence, known = [], set()
        for e in fv.evidence:
            this_q = _field_text(query, e.query_field, e.attribute, cand)
            cand_q = _field_text(cand, e.candidate_field, e.attribute, query)
            if e.result != "unknown" and this_q and cand_q:
                known.add(e.attribute)
            evidence.append(LLMEvidence(
                attribute=e.attribute, result=e.result, this_quote=this_q,
                candidate_quote=cand_q,
                note=_NOTES.get((e.attribute, e.result), "Details compared.")))
        missing = [f"The other report doesn't mention the {label}."
                   for attr, label in _LABELS.items() if attr not in known]
        verdicts.append(LLMVerdict(
            candidate_id=fv.candidate_id, evidence=evidence,
            suggested_assessment=fv.suggested_assessment,
            missing_information=missing,
            next_step=NEXT_STEP_BY_ASSESSMENT[fv.suggested_assessment]))
    return _index_verdicts(candidates, verdicts)
