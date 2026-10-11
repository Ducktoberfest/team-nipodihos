"""The only place that talks to Person C's foundit_ai module.

Until foundit_ai is merged, matching falls back to sample_data/mock_matches.json and
extraction leaves reports as "pending". Once it is merged this switches automatically.
"""

import json
import logging
import os
import sqlite3
from pathlib import Path

from .db import utc_now_iso

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
MOCK_MATCHES = ROOT / "sample_data" / "mock_matches.json"

try:
    from foundit_ai.agent import extract_attributes, find_matches
    from foundit_ai.schemas import AIAttributes, ReportRecord
    AI_MODULE_AVAILABLE = True
except ModuleNotFoundError as exc:
    # Only swallow "foundit_ai is not there yet"; a real bug inside it should still fail loudly.
    if not (exc.name or "").startswith("foundit_ai"):
        raise
    AI_MODULE_AVAILABLE = False


def ai_available() -> bool:
    return AI_MODULE_AVAILABLE and bool(os.getenv("GROQ_API_KEY"))


def row_to_record(row: sqlite3.Row) -> "ReportRecord":
    """DB row -> foundit_ai ReportRecord (same field names, plus ai_attributes and has_photo)."""
    data = dict(row)
    data["has_photo"] = row["photo_path"] is not None
    raw = row["ai_attributes_json"]
    data["ai_attributes"] = AIAttributes.model_validate_json(raw) if raw else None
    allowed = ReportRecord.model_fields
    return ReportRecord(**{k: v for k, v in data.items() if k in allowed})


def extract(row: sqlite3.Row) -> str | None:
    """Return AIAttributes as JSON for the report, or None when the AI module is missing."""
    if not AI_MODULE_AVAILABLE:
        return None
    try:
        result = extract_attributes(row_to_record(row), photo_path=row["photo_path"])
        return result.model_dump_json()
    except Exception:
        # extract_attributes should never raise, but a report must still be saved if it does.
        logger.exception("extract_attributes failed for report %s", row["id"])
        return json.dumps({"extraction_status": "failed"})


def load_mock_matches(report_id: int) -> dict:
    run = json.loads(MOCK_MATCHES.read_text(encoding="utf-8"))
    run["report_id"] = report_id
    run["generated_at"] = utc_now_iso()
    return run


def run_matching(query: sqlite3.Row, pool: list[sqlite3.Row], limit: int) -> dict:
    """Return a MatchRun as a plain dict (candidates without match_id/feedback_status)."""
    if not AI_MODULE_AVAILABLE:
        run = load_mock_matches(query["id"])
        existing = {row["id"] for row in pool}
        # Mock candidates point at fixed ids; keep only the ones that exist in this DB.
        run["candidates"] = [c for c in run["candidates"]
                             if c["candidate_report_id"] in existing][:limit]
        return run

    result = find_matches(row_to_record(query), [row_to_record(r) for r in pool], limit=limit)
    run = result.model_dump(mode="json")
    run["report_id"] = query["id"]
    run.setdefault("generated_at", utc_now_iso())
    return run
