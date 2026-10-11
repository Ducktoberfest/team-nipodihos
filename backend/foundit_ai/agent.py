"""The FoundIt matching agent — the two functions the backend calls.

A controlled pipeline with explicit steps (reliability over autonomy):

    extract_attributes:  Gemma 4 normalises the report (fallback: gpt-oss)
    find_matches:        retrieve (Python)
                         -> compare: gpt-oss quotes evidence; if unavailable,
                            Gemma 4 names the supporting fields (field mode)
                         -> verify + score (Python)

Neither function raises because of the AI. If the model is unavailable,
extraction returns status "failed" and matching returns degraded=True with
rule-based results.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from foundit_ai import extract as _extract
from foundit_ai.compare import compare_reports, compare_reports_by_field
from foundit_ai.llm_client import AIUnavailable, LLMClient, ModelClient, chain_for
from foundit_ai.retrieve import search_candidate_reports
from foundit_ai.schemas import AIAttributes, MatchRun, ReportRecord
from foundit_ai.scoring import assess_candidate

log = logging.getLogger(__name__)

MAX_LIMIT = 10
DEGRADED_REASON = "AI model unavailable. Showing rule-based results only."

_default_clients: dict[str, LLMClient] = {}


def default_client(task: str) -> LLMClient:
    """Shared ModelClient per task ("extract" | "compare"), created on first use.
    Raises AIUnavailable if no provider key is configured for that task."""
    if task not in _default_clients:
        _default_clients[task] = ModelClient(chain_for(task))
    return _default_clients[task]


def _get_llm(llm: LLMClient | None, task: str) -> LLMClient:
    return llm if llm is not None else default_client(task)


# Which model produced the last comparison (for logs and the eval script only).
last_compare_source: str = "none"


def _compare(query: ReportRecord, candidates: list[ReportRecord],
             llm: LLMClient | None):
    """gpt-oss in quote mode first; if unavailable, Gemma in field mode."""
    global last_compare_source
    if llm is not None:                                  # explicit client (tests)
        last_compare_source = "given client"
        return compare_reports(query, candidates, llm)
    errors = []
    for task, compare_fn in (("compare", compare_reports),
                             ("compare_fields", compare_reports_by_field)):
        try:
            client = default_client(task)
            verdicts = compare_fn(query, candidates, client)
            last_compare_source = f"{getattr(client, 'last_model', task)} ({task})"
            return verdicts
        except AIUnavailable as e:
            errors.append(f"{task}: {e}")
            log.warning("compare_step_unavailable task=%s reason=%s", task, e)
    last_compare_source = "rules only"
    raise AIUnavailable("; ".join(errors))


def extract_attributes(report: ReportRecord, photo_path: str | None = None, *,
                       llm: LLMClient | None = None) -> AIAttributes:
    """Call once when a report is created; store the result with the report.

    photo_path is accepted for the agreed interface; photo analysis is not
    enabled yet (vision model still being evaluated).
    """
    try:
        client = _get_llm(llm, "extract")
    except AIUnavailable as e:
        log.warning("extraction_skipped report_id=%s reason=%s", report.id, e)
        return AIAttributes(extraction_status="failed")
    return _extract.extract_attributes(report, client)


_ASSESSMENT_ORDER = {"likely_match": 0, "possible_match": 1,
                     "insufficient_information": 2, "unlikely_match": 3}


def find_matches(query: ReportRecord, pool: list[ReportRecord], *, limit: int = 5,
                 llm: LLMClient | None = None,
                 now: datetime | None = None) -> MatchRun:
    """Rank candidate reports of the opposite type for `query`, with evidence."""
    limit = max(1, min(limit, MAX_LIMIT))
    generated_at = now or datetime.now(timezone.utc)

    # Step 1: cheap retrieval (Python).
    candidates, considered = search_candidate_reports(query, pool, k=limit)
    if not candidates:
        return MatchRun(report_id=query.id, generated_at=generated_at, degraded=False,
                        degraded_reason=None, candidates_considered=considered,
                        candidates=[])

    # Step 2: one model call compares all candidates.
    degraded, reason, verdicts = False, None, {}
    try:
        verdicts = _compare(query, candidates, llm)
    except AIUnavailable as e:
        degraded, reason = True, DEGRADED_REASON
        log.warning("matching_degraded report_id=%s reason=%s", query.id, e)

    # Steps 3+4: verify evidence and score (Python has the final word).
    # A candidate the model skipped falls back to rule-based assessment.
    results = [assess_candidate(query, c, verdicts.get(c.id)) for c in candidates]
    results.sort(key=lambda r: (-r.ranking_score, _ASSESSMENT_ORDER[r.assessment],
                                r.candidate_report_id))

    return MatchRun(report_id=query.id, generated_at=generated_at, degraded=degraded,
                    degraded_reason=reason, candidates_considered=considered,
                    candidates=results)
