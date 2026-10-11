"""Pydantic models matching docs/API.md.

Input and output models are separate on purpose: no output model has a `contact` or
`private_details` field, so those values cannot leak through a response.
"""

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator

ReportType = Literal["lost", "found"]
Category = Literal["bag", "electronics", "wallet", "keys", "id_card", "clothing",
                   "jewelry", "bottle", "umbrella", "book", "other"]
ReportStatus = Literal["open", "matched", "closed"]
Assessment = Literal["likely_match", "possible_match", "unlikely_match", "insufficient_information"]
FeedbackStatus = Literal["pending", "confirmed", "rejected", "uncertain"]
EvidenceAttribute = Literal["category", "color", "location", "time", "features", "other"]
ScoreAttribute = Literal["category", "color", "location", "time", "features"]

# Small allowance for clocks that are slightly ahead of the server.
FUTURE_TOLERANCE = timedelta(minutes=5)


def to_utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    value = value.astimezone(timezone.utc).replace(microsecond=0)
    return value.isoformat().replace("+00:00", "Z")


# ---------- reports ----------

class ReportCreate(BaseModel):
    type: ReportType
    description: str = Field(min_length=10, max_length=2000)
    category: Category | None = None
    color: str | None = Field(default=None, max_length=50)
    location: str | None = Field(default=None, max_length=200)
    occurred_at: datetime | None = None
    private_details: str | None = Field(default=None, max_length=500)
    contact: str | None = Field(default=None, max_length=200)

    @field_validator("description", "color", "location", "private_details", "contact", mode="before")
    @classmethod
    def strip_text(cls, value):
        if isinstance(value, str):
            value = value.strip()
        return value

    @field_validator("color", "location", "private_details", "contact")
    @classmethod
    def empty_to_none(cls, value: str | None) -> str | None:
        return value or None

    @field_validator("occurred_at")
    @classmethod
    def not_in_future(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        aware = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if aware > datetime.now(timezone.utc) + FUTURE_TOLERANCE:
            raise ValueError("occurred_at must not be in the future")
        return aware


class AIAttributesOut(BaseModel):
    extraction_status: Literal["ok", "pending", "failed"] = "pending"
    item_type: str | None = None
    category: str | None = None
    color_family: list[str] = []
    brand: str | None = None
    features: list[str] = []
    location_normalized: str | None = None


class ReportOut(BaseModel):
    id: int
    type: ReportType
    description: str
    category: Category | None
    color: str | None
    location: str | None
    occurred_at: str | None
    has_photo: bool
    photo_url: str | None
    has_private_details: bool
    status: ReportStatus
    created_at: str
    ai_attributes: AIAttributesOut


class ReportList(BaseModel):
    items: list[ReportOut]
    total: int


def parse_ai_attributes(raw: str | None) -> AIAttributesOut:
    if not raw:
        return AIAttributesOut()
    try:
        attrs = AIAttributesOut.model_validate(json.loads(raw))
    except ValueError:
        return AIAttributesOut(extraction_status="failed")
    if attrs.extraction_status != "ok":
        # Contract: when not "ok", the other fields are null/empty.
        return AIAttributesOut(extraction_status=attrs.extraction_status)
    return attrs


def row_to_report_out(row: sqlite3.Row) -> ReportOut:
    has_photo = row["photo_path"] is not None
    return ReportOut(
        id=row["id"],
        type=row["type"],
        description=row["description"],
        category=row["category"],
        color=row["color"],
        location=row["location"],
        occurred_at=row["occurred_at"],
        has_photo=has_photo,
        photo_url=f"/reports/{row['id']}/photo" if has_photo else None,
        has_private_details=bool(row["private_details"]),
        status=row["status"],
        created_at=row["created_at"],
        ai_attributes=parse_ai_attributes(row["ai_attributes_json"]),
    )


# ---------- matches ----------

class MatchRequest(BaseModel):
    limit: int = Field(default=5, ge=1, le=10)


class CandidateReport(BaseModel):
    """Public view of the other report inside a match (no id, contact or private details)."""
    type: ReportType
    description: str
    category: Category | None
    color: str | None
    location: str | None
    occurred_at: str | None
    has_photo: bool
    photo_url: str | None


def row_to_candidate(row: sqlite3.Row) -> CandidateReport:
    public = row_to_report_out(row)
    return CandidateReport(**public.model_dump(include=set(CandidateReport.model_fields)))


class ScoreEntry(BaseModel):
    attribute: ScoreAttribute
    points: int
    max: int
    result: Literal["agree", "partial", "conflict", "unknown"]


class Evidence(BaseModel):
    attribute: EvidenceAttribute
    this_report: str | None
    candidate: str | None
    source: Literal["text", "photo", "rule"]
    note: str


class MatchCandidate(BaseModel):
    match_id: int
    candidate_report_id: int
    candidate: CandidateReport
    assessment: Assessment
    ranking_score: int = Field(ge=0, le=100)
    score_breakdown: list[ScoreEntry]
    matching_evidence: list[Evidence]
    conflicting_evidence: list[Evidence]
    missing_information: list[str]
    next_step: str
    feedback_status: FeedbackStatus


class MatchResponse(BaseModel):
    report_id: int
    generated_at: str | None
    degraded: bool
    degraded_reason: str | None
    candidates_considered: int
    candidates: list[MatchCandidate]


# ---------- feedback ----------

class FeedbackIn(BaseModel):
    status: Literal["confirmed", "rejected", "uncertain"]
    note: str | None = Field(default=None, max_length=500)


class FeedbackOut(BaseModel):
    match_id: int
    feedback_status: FeedbackStatus
    updated_at: str
