"""Deterministic, trusted logic. No AI in this file.

Responsibilities:
1. Time check   - pure date arithmetic (the model never judges time).
2. Grounding    - drop any model evidence whose quotes are not really in the reports.
3. Privacy      - hide the candidate's private details; scrub leaks from model text.
4. Scoring      - fixed points table -> ranking_score (NOT a probability).
5. Assessment   - safety caps on top of the model's suggestion.
6. Fallback     - rule-only evidence when the model is unavailable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import timedelta

from foundit_ai.schemas import (
    SCORED_ATTRIBUTES,
    WITHHELD,
    Assessment,
    CandidateAssessment,
    Evidence,
    LLMVerdict,
    ReportRecord,
    Result,
    ScoredAttribute,
    ScoreItem,
)

# --- 4. points table (documented in docs/API.md) -----------------------------

MAX_POINTS: dict[ScoredAttribute, int] = {
    "category": 30, "color": 20, "location": 20, "time": 15, "features": 15,
}
RESULT_FRACTION: dict[Result, float] = {
    "agree": 1.0, "partial": 0.5, "unknown": 0.0, "conflict": 0.0,
}


def points_for(attribute: ScoredAttribute, result: Result) -> int:
    return int(MAX_POINTS[attribute] * RESULT_FRACTION[result] + 0.5)


# --- 1. time check -----------------------------------------------------------

TIME_TOLERANCE = timedelta(hours=2)   # clocks / guesses are approximate
SAME_PERIOD = timedelta(days=3)


def _fmt(dt) -> str:
    # Stored times are UTC; say so, because the UI shows local time elsewhere.
    return dt.strftime("%Y-%m-%d %H:%M UTC")


def _human(delta: timedelta) -> str:
    hours = abs(delta.total_seconds()) / 3600
    if hours < 48:
        return f"{hours:.1f} hours".replace(".0 ", " ")
    return f"{hours / 24:.0f} days"


def time_check(query: ReportRecord, cand: ReportRecord) -> tuple[Result, Evidence | None]:
    lost, found = (query, cand) if query.type == "lost" else (cand, query)
    if lost.occurred_at is None or found.occurred_at is None:
        return "unknown", None

    delta = found.occurred_at - lost.occurred_at
    if delta < -TIME_TOLERANCE:
        result: Result = "conflict"
        note = f"The item was found {_human(delta)} BEFORE it was reported lost."
    elif delta <= SAME_PERIOD:
        result = "agree"
        note = ("Found around the time it was lost." if delta < timedelta(0)
                else f"Found {_human(delta)} after it was lost.")
    else:
        result = "partial"
        note = f"Found {_human(delta)} after it was lost."

    ev = Evidence(attribute="time", this_report=_fmt(query.occurred_at),
                  candidate=_fmt(cand.occurred_at), source="rule", note=note)
    return result, ev


# --- 2. grounding ------------------------------------------------------------

def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def locate_quote(quote: str, report: ReportRecord) -> str | None:
    """Which part of the report contains this exact quote: 'public', 'private' or None."""
    q = _norm(quote)
    if not q:
        return None
    public = [report.description, report.category, report.color, report.location]
    if any(f and q in _norm(f) for f in public):
        return "public"
    if report.private_details and q in _norm(report.private_details):
        return "private"
    return None


# --- 3. privacy --------------------------------------------------------------

_STOPWORDS = {"with", "that", "this", "there", "have", "from", "they", "their",
              "inside", "attached", "small", "little", "keychain", "keyring"}


def _words(text: str | None) -> set[str]:
    return set(re.findall(r"[a-z]{4,}", (text or "").lower()))


def secret_words(query: ReportRecord, cand: ReportRecord) -> set[str]:
    """Words that only appear in the candidate's private details."""
    known = _words(" ".join(filter(None, [
        cand.description, cand.color, cand.location, cand.category,
        query.description, query.color, query.location, query.private_details,
    ])))
    return _words(cand.private_details) - known - _STOPWORDS


def leaks(text: str, secrets: set[str]) -> bool:
    return bool(_words(text) & secrets)


SAFE_NEXT_STEP = ("Contact the lost-and-found desk and describe your item's unique "
                  "details to the finder to verify ownership before any handover.")
PRIVATE_NOTE: dict[Result, str] = {
    "agree": "A private identifying detail recorded by the finder is consistent with yours. Describe it to the finder to verify.",
    "partial": "A private identifying detail recorded by the finder may be consistent with yours. Describe it to the finder to verify.",
    "conflict": "A private identifying detail recorded by the finder does not match yours.",
    "unknown": "No private detail to compare.",
}


# --- verified evidence -------------------------------------------------------

@dataclass
class CheckedEvidence:
    attribute: ScoredAttribute
    result: Result
    evidence: Evidence
    from_private: bool = False


def verify_llm_evidence(verdict: LLMVerdict, query: ReportRecord,
                        cand: ReportRecord) -> tuple[list[CheckedEvidence], int]:
    """Keep only grounded evidence; return (kept, number_dropped)."""
    secrets = secret_words(query, cand)
    kept: list[CheckedEvidence] = []
    dropped = 0
    for e in verdict.evidence:
        if e.result == "unknown":
            continue  # unknown is the default; nothing to show
        q_where = locate_quote(e.this_quote, query) if e.this_quote else None
        c_where = locate_quote(e.candidate_quote, cand) if e.candidate_quote else None
        if q_where is None or c_where is None:
            dropped += 1  # model claimed something the reports don't say
            continue
        private = c_where == "private" or e.attribute == "private_details"
        attribute: ScoredAttribute = "features" if e.attribute == "private_details" else e.attribute
        if private:
            candidate_text, note = WITHHELD, PRIVATE_NOTE[e.result]
        else:
            candidate_text = e.candidate_quote
            note = e.note if not leaks(e.note, secrets) else "Details compared."
        kept.append(CheckedEvidence(
            attribute=attribute, result=e.result, from_private=private,
            evidence=Evidence(attribute=attribute, this_report=e.this_quote,
                              candidate=candidate_text, source="text", note=note),
        ))
    return kept, dropped


# --- 6. rule-only fallback (model unavailable) --------------------------------

_LOC_STOPWORDS = {"near", "the", "floor", "room", "area", "campus", "university"}


def _category(r: ReportRecord) -> str | None:
    return r.category or (r.ai_attributes.category if r.ai_attributes else None)


_SHADE_WORDS = {"dark", "light", "pale", "bright", "deep"}


def _color_words(r: ReportRecord) -> set[str]:
    """Colour words from the user's text plus the model's colour family (if extracted)."""
    words = set(re.findall(r"[a-z]+", (r.color or "").lower())) - _SHADE_WORDS
    if r.ai_attributes:
        words |= {c.lower() for c in r.ai_attributes.color_family}
    return words


def rule_based_evidence(query: ReportRecord, cand: ReportRecord) -> list[CheckedEvidence]:
    """Conservative checks only. Rules never claim a conflict about wording
    they cannot understand (e.g. 'navy' vs 'dark blue' stays unknown)."""
    out: list[CheckedEvidence] = []

    qc, cc = _category(query), _category(cand)
    if qc and cc and "other" not in (qc, cc):
        result: Result = "agree" if qc == cc else "conflict"
        out.append(CheckedEvidence("category", result, Evidence(
            attribute="category", this_report=qc, candidate=cc, source="rule",
            note="Same category." if result == "agree" else "Different categories.")))

    shared_colors = _color_words(query) & _color_words(cand)
    if shared_colors:
        out.append(CheckedEvidence("color", "agree", Evidence(
            attribute="color", this_report=query.color, candidate=cand.color,
            source="rule", note=f"Both mention: {', '.join(sorted(shared_colors))}.")))

    if query.location and cand.location:
        shared = (_words(query.location) & _words(cand.location)) - _LOC_STOPWORDS
        if shared:
            out.append(CheckedEvidence("location", "agree", Evidence(
                attribute="location", this_report=query.location,
                candidate=cand.location, source="rule",
                note=f"Locations share: {', '.join(sorted(shared))}.")))
    return out


# --- 4 + 5. combine ----------------------------------------------------------

LIKELY_MIN_KNOWN = 4      # of the 5 scored attributes
LIKELY_MIN_SCORE = 70

_PRECEDENCE: dict[Result, int] = {"conflict": 3, "agree": 2, "partial": 1, "unknown": 0}


def combine(evidence: list[CheckedEvidence]) -> dict[ScoredAttribute, Result]:
    """Per attribute: a conflict outweighs agreement; agreement outweighs partial."""
    results: dict[ScoredAttribute, Result] = {a: "unknown" for a in SCORED_ATTRIBUTES}
    for ce in evidence:
        if _PRECEDENCE[ce.result] > _PRECEDENCE[results[ce.attribute]]:
            results[ce.attribute] = ce.result
    return results


def decide_assessment(results: dict[ScoredAttribute, Result], score: int,
                      suggestion: Assessment | None, private_conflict: bool) -> Assessment:
    """Python has the final word; the model's suggestion is only used inside these caps."""
    conflicts = [a for a, r in results.items() if r == "conflict"]
    known = sum(r != "unknown" for r in results.values())

    if (results["category"] == "conflict" or results["time"] == "conflict"
            or private_conflict or len(conflicts) >= 2):
        return "unlikely_match"
    if known < 2:
        return "insufficient_information"
    if suggestion is None:  # degraded mode: never claim "likely" without the model
        return "possible_match" if score >= 50 else "unlikely_match"
    # "likely" needs broad evidence: no conflicts, most attributes known, solid score.
    # (A sparse "grey hoodie" matching on category + colour alone stays "possible".)
    if suggestion == "likely_match" and (conflicts or known < LIKELY_MIN_KNOWN
                                         or score < LIKELY_MIN_SCORE):
        return "possible_match"
    return suggestion


DEGRADED_MISSING = "AI comparison unavailable: wording, colours and features were only checked by simple rules."
DEGRADED_NEXT_STEP = ("Try matching again later for a full AI comparison, or contact "
                      "the lost-and-found desk to verify.")
NEXT_STEP_BY_ASSESSMENT: dict[Assessment, str] = {
    "unlikely_match": "Probably a different item. Only follow up if no other candidate works out.",
    "insufficient_information": "Not enough detail to judge. Ask the lost-and-found desk for more details about this item.",
    "possible_match": SAFE_NEXT_STEP,
    "likely_match": SAFE_NEXT_STEP,
}


def _already_known(item: str, query: ReportRecord, cand: ReportRecord) -> bool:
    """The model never sees photos or times, so it may list them as 'missing'
    even when we have them. Drop those items instead of misleading the user."""
    text = item.lower()
    if "photo" in text and cand.has_photo:
        return True
    if (re.search(r"\b(time|date|when)\b", text)
            and query.occurred_at is not None and cand.occurred_at is not None):
        return True
    return False


def assess_candidate(query: ReportRecord, cand: ReportRecord,
                     verdict: LLMVerdict | None) -> CandidateAssessment:
    """Turn (optional) model verdict + rules into one explainable result."""
    time_result, time_ev = time_check(query, cand)
    secrets = secret_words(query, cand)

    if verdict is not None:
        evidence, _dropped = verify_llm_evidence(verdict, query, cand)
        # Category is a plain equality check on the user's or the extracted category.
        # If the model said nothing usable about it, let the rule decide.
        if not any(ce.attribute == "category" for ce in evidence):
            evidence += [ce for ce in rule_based_evidence(query, cand)
                         if ce.attribute == "category"]
        missing = [m for m in verdict.missing_information
                   if not leaks(m, secrets) and not _already_known(m, query, cand)]
        next_step = verdict.next_step if not leaks(verdict.next_step, secrets) else SAFE_NEXT_STEP
    else:
        evidence = rule_based_evidence(query, cand)
        missing = [DEGRADED_MISSING]
        next_step = DEGRADED_NEXT_STEP

    if time_ev is not None:
        evidence.append(CheckedEvidence("time", time_result, time_ev))

    results = combine(evidence)
    breakdown = [ScoreItem(attribute=a, points=points_for(a, results[a]),
                           max=MAX_POINTS[a], result=results[a])
                 for a in SCORED_ATTRIBUTES]
    score = sum(item.points for item in breakdown)
    private_conflict = any(ce.from_private and ce.result == "conflict" for ce in evidence)
    assessment = decide_assessment(results, score,
                                   verdict.suggested_assessment if verdict else None,
                                   private_conflict)

    # The model's advice must fit the final (possibly capped) assessment.
    if verdict is not None and assessment in ("unlikely_match", "insufficient_information") \
            and assessment != verdict.suggested_assessment:
        next_step = NEXT_STEP_BY_ASSESSMENT[assessment]

    order = {a: i for i, a in enumerate(SCORED_ATTRIBUTES)}
    evidence.sort(key=lambda ce: order[ce.attribute])
    return CandidateAssessment(
        candidate_report_id=cand.id,
        candidate=cand.public_view(),
        assessment=assessment,
        ranking_score=score,
        score_breakdown=breakdown,
        matching_evidence=[ce.evidence for ce in evidence if ce.result in ("agree", "partial")],
        conflicting_evidence=[ce.evidence for ce in evidence if ce.result == "conflict"],
        missing_information=missing,
        next_step=next_step,
    )
