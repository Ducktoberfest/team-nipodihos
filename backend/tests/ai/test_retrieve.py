"""Tests for cheap candidate retrieval (no model involved)."""

from __future__ import annotations

import pytest

from foundit_ai.retrieve import search_candidate_reports, tfidf_similarities
from foundit_ai.schemas import AIAttributes, ReportRecord


@pytest.fixture
def found_wallet() -> ReportRecord:
    return ReportRecord(id=9, type="found", category="wallet", color="brown",
                        description="Brown leather wallet found in the cafeteria.",
                        location="Cafeteria")


@pytest.fixture
def pool(lost_backpack, found_navy_bag, found_sports_bag, found_vague_bag,
         found_decoy_bag, found_wallet):
    return [lost_backpack, found_navy_bag, found_sports_bag, found_vague_bag,
            found_decoy_bag, found_wallet]


def test_only_opposite_type_and_never_itself(lost_backpack, pool):
    other_lost = ReportRecord(id=20, type="lost", category="bag",
                              description="Lost a dark blue backpack in the library.")
    candidates, _ = search_candidate_reports(lost_backpack, pool + [other_lost], k=10)
    assert all(c.type == "found" for c in candidates)
    assert lost_backpack.id not in [c.id for c in candidates]


def test_category_conflict_is_removed(lost_backpack, pool):
    candidates, considered = search_candidate_reports(lost_backpack, pool, k=10)
    assert 9 not in [c.id for c in candidates]   # wallet vs bag
    assert considered == 5                       # but it was looked at


def test_closed_reports_are_skipped(lost_backpack, found_navy_bag):
    found_navy_bag.status = "matched"
    assert search_candidate_reports(lost_backpack, [found_navy_bag]) == ([], 0)


def test_extracted_attributes_bridge_synonyms(lost_backpack):
    """'school bag' shares no word with 'backpack' until extraction normalises it."""
    plain = ReportRecord(id=30, type="found", description="A navy school bag on a chair.")
    other = ReportRecord(id=31, type="found", description="Green umbrella on a chair.")
    lost = lost_backpack.model_copy(update={"category": None})

    without, _ = search_candidate_reports(lost, [plain, other], k=1)
    plain.ai_attributes = AIAttributes(extraction_status="ok", item_type="backpack",
                                       category="bag", color_family=["blue"])
    with_attrs, _ = search_candidate_reports(lost, [plain, other], k=1)

    assert without == []            # plain word overlap misses the synonym completely
    assert with_attrs[0].id == 30   # extraction makes it findable
    sims = tfidf_similarities(["backpack", "blue"], [["backpack", "blue"], ["umbrella"]])
    assert sims[0] > sims[1] == 0.0


def test_k_limits_results(lost_backpack, pool):
    candidates, _ = search_candidate_reports(lost_backpack, pool, k=2)
    assert len(candidates) == 2


def test_best_candidates_rank_first(lost_backpack, pool):
    candidates, _ = search_candidate_reports(lost_backpack, pool, k=5)
    top_two = {c.id for c in candidates[:2]}
    assert top_two & {2, 7}        # the library backpacks beat the vague one


def test_works_from_found_side(found_navy_bag, lost_backpack):
    candidates, considered = search_candidate_reports(found_navy_bag, [lost_backpack])
    assert [c.id for c in candidates] == [1] and considered == 1


def test_empty_pool_and_bad_k(lost_backpack):
    assert search_candidate_reports(lost_backpack, []) == ([], 0)
    with pytest.raises(ValueError):
        search_candidate_reports(lost_backpack, [], k=0)
