"""Shared test data for the AI module: the campus backpack scenario."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from foundit_ai.schemas import ReportRecord


@pytest.fixture(autouse=True)
def _no_real_api_key(monkeypatch):
    """Tests must never call a real model: hide every provider key from every test."""
    for key in ("GROQ_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(key, raising=False)


def at(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, day, hour, minute, tzinfo=timezone.utc)


@pytest.fixture
def lost_backpack() -> ReportRecord:
    return ReportRecord(
        id=1, type="lost",
        description="I lost my dark blue backpack near the university library. "
                    "It had a laptop and a small keychain inside.",
        category="bag", color="dark blue", location="Main Library",
        occurred_at=at(9, 14), private_details="Keychain is a small silver Eiffel Tower.",
    )


@pytest.fixture
def found_navy_bag() -> ReportRecord:
    return ReportRecord(
        id=2, type="found",
        description="A navy school bag was left on a chair in the library. "
                    "It has a keyring attached.",
        category="bag", color="navy", location="Main Library, 2nd floor reading room",
        occurred_at=at(9, 17, 30), has_photo=True,
        private_details="The keyring has a little metal tower charm.",
    )


@pytest.fixture
def found_sports_bag() -> ReportRecord:
    return ReportRecord(
        id=3, type="found",
        description="Blue Adidas backpack found in the Sports Centre locker room. "
                    "No keyring, has a water bottle in the side pocket.",
        category="bag", color="blue", location="Sports Centre, locker room",
        occurred_at=at(8, 10),
    )


@pytest.fixture
def found_vague_bag() -> ReportRecord:
    return ReportRecord(id=4, type="found", category="bag",
                        description="Someone handed in a backpack at the security desk.")


@pytest.fixture
def found_decoy_bag() -> ReportRecord:
    return ReportRecord(
        id=7, type="found",
        description="Dark blue backpack found in the library cafe area. "
                    "There is a keychain on the zipper.",
        category="bag", color="dark blue", location="Library cafe",
        occurred_at=at(9, 16), private_details="Keychain is a red pom-pom with the letter K.",
    )

