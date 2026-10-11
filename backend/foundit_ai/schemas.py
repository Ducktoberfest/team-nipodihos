"""Data shapes used by the FoundIt AI module.

These mirror docs/API.md. Two groups:
- Input:  ReportRecord (what the backend passes us, INCLUDING private fields).
- Output: MatchRun / CandidateAssessment (what we return; never contains
  contact info or the candidate's private details).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

ReportType = Literal["lost", "found"]
Category = Literal[
    "bag", "electronics", "wallet", "keys", "id_card", "clothing",
    "jewelry", "bottle", "umbrella", "book", "other",
]
ScoredAttribute = Literal["category", "color", "location", "time", "features"]
Result = Literal["agree", "partial", "conflict", "unknown"]
Assessment = Literal[
    "likely_match", "possible_match", "unlikely_match", "insufficient_information",
]

SCORED_ATTRIBUTES: tuple[ScoredAttribute, ...] = (
    "category", "color", "location", "time", "features",
)
WITHHELD = "[private detail withheld]"


# --- input ------------------------------------------------------------------

class AIAttributes(BaseModel):
    """Normalised attributes the model extracts when a report is submitted."""

    extraction_status: Literal["ok", "pending", "failed"] = "pending"
    item_type: str | None = None
    category: Category | None = None
    color_family: list[str] = Field(default_factory=list)
    brand: str | None = None
    features: list[str] = Field(default_factory=list)
    location_normalized: str | None = None


class ReportRecord(BaseModel):
    """A stored report, as the backend hands it to the AI module."""

    id: int
    type: ReportType
    description: str
    category: Category | None = None
    color: str | None = None
    location: str | None = None
    occurred_at: datetime | None = None
    private_details: str | None = None
    has_photo: bool = False
    status: Literal["open", "matched", "closed"] = "open"
    ai_attributes: AIAttributes | None = None

    def public_view(self) -> "CandidatePublic":
        return CandidatePublic(
            type=self.type,
            description=self.description,
            category=self.category,
            color=self.color,
            location=self.location,
            occurred_at=self.occurred_at,
            has_photo=self.has_photo,
            photo_url=f"/reports/{self.id}/photo" if self.has_photo else None,
        )


# --- output -----------------------------------------------------------------

class CandidatePublic(BaseModel):
    """What the user may see about another person's report."""

    type: ReportType
    description: str
    category: Category | None
    color: str | None
    location: str | None
    occurred_at: datetime | None
    has_photo: bool
    photo_url: str | None


class Evidence(BaseModel):
    attribute: Literal["category", "color", "location", "time", "features", "other"]
    this_report: str | None
    candidate: str | None
    source: Literal["text", "photo", "rule"]
    note: str


class ScoreItem(BaseModel):
    attribute: ScoredAttribute
    points: int
    max: int
    result: Result


class CandidateAssessment(BaseModel):
    """One ranked candidate. The backend adds match_id + feedback_status."""

    candidate_report_id: int
    candidate: CandidatePublic
    assessment: Assessment
    ranking_score: int = Field(ge=0, le=100)
    score_breakdown: list[ScoreItem]
    matching_evidence: list[Evidence]
    conflicting_evidence: list[Evidence]
    missing_information: list[str]
    next_step: str


class MatchRun(BaseModel):
    report_id: int
    generated_at: datetime
    degraded: bool
    degraded_reason: str | None
    candidates_considered: int
    candidates: list[CandidateAssessment]


# --- what we ask the language model to return --------------------------------
# Raw model output is UNTRUSTED. scoring.py verifies every quote before use.

class LLMEvidence(BaseModel):
    attribute: Literal["category", "color", "location", "features", "private_details"]
    result: Result
    this_quote: str | None
    candidate_quote: str | None
    note: str


class LLMVerdict(BaseModel):
    candidate_id: int
    evidence: list[LLMEvidence]
    suggested_assessment: Assessment
    missing_information: list[str]
    next_step: str


class LLMComparison(BaseModel):
    candidates: list[LLMVerdict]
