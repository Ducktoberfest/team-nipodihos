"""Tests for the deterministic layer: time, grounding, privacy, score, caps."""

from __future__ import annotations

from foundit_ai.schemas import WITHHELD
from foundit_ai.scoring import (
    assess_candidate,
    decide_assessment,
    locate_quote,
    points_for,
    time_check,
)
from tests.ai.helpers import ev, verdict


# --- points table -----------------------------------------------------------

def test_points_table_matches_api_doc():
    assert [points_for(a, "agree") for a in ("category", "color", "location", "time", "features")] \
        == [30, 20, 20, 15, 15]
    assert points_for("time", "partial") == 8
    assert points_for("color", "unknown") == 0
    assert points_for("color", "conflict") == 0


# --- time -------------------------------------------------------------------

def test_found_shortly_after_lost_agrees(lost_backpack, found_navy_bag):
    result, evidence = time_check(lost_backpack, found_navy_bag)
    assert result == "agree"
    assert "3.5 hours after" in evidence.note


def test_found_before_lost_is_conflict(lost_backpack, found_sports_bag):
    result, evidence = time_check(lost_backpack, found_sports_bag)
    assert result == "conflict"
    assert "BEFORE" in evidence.note


def test_time_check_works_from_found_side(lost_backpack, found_sports_bag):
    """Matching can start from a found report too; lost/found roles must not flip."""
    result, _ = time_check(found_sports_bag, lost_backpack)
    assert result == "conflict"


def test_missing_date_is_unknown_not_match(lost_backpack, found_vague_bag):
    assert time_check(lost_backpack, found_vague_bag) == ("unknown", None)


# --- grounding --------------------------------------------------------------

def test_locate_quote_public_private_and_invented(found_navy_bag):
    assert locate_quote("NAVY school   bag", found_navy_bag) == "public"
    assert locate_quote("metal tower charm", found_navy_bag) == "private"
    assert locate_quote("red stripe", found_navy_bag) is None


def test_invented_evidence_is_dropped(lost_backpack, found_navy_bag):
    v = verdict(2, [
        ev("color", "agree", "dark blue", "navy"),
        ev("features", "agree", "laptop", "laptop inside"),   # finder never said this
    ])
    result = assess_candidate(lost_backpack, found_navy_bag, v)
    quotes = [e.candidate for e in result.matching_evidence]
    assert "navy" in quotes
    assert "laptop inside" not in quotes
    assert result.score_breakdown[4].result == "unknown"   # features not credited


def test_claim_without_both_quotes_is_dropped(lost_backpack, found_navy_bag):
    v = verdict(2, [ev("color", "agree", "dark blue", None)])
    result = assess_candidate(lost_backpack, found_navy_bag, v)
    assert result.score_breakdown[1].result == "unknown"


# --- privacy ----------------------------------------------------------------

def test_candidate_private_detail_is_withheld(lost_backpack, found_navy_bag):
    v = verdict(2, [ev("private_details", "agree", "Eiffel Tower", "metal tower charm",
                       note="Both have a metal tower charm")])
    result = assess_candidate(lost_backpack, found_navy_bag, v)
    shown = next(e for e in result.matching_evidence if e.attribute == "features")
    assert shown.candidate == WITHHELD
    assert "charm" not in shown.note
    assert shown.this_report == "Eiffel Tower"   # the viewer's own detail is fine


def test_leaky_next_step_is_replaced(lost_backpack, found_navy_bag):
    v = verdict(2, [ev("color", "agree", "dark blue", "navy")],
                next_step="Ask whether it has the metal charm.")
    result = assess_candidate(lost_backpack, found_navy_bag, v)
    assert "charm" not in result.next_step


def test_private_conflict_makes_unlikely(lost_backpack, found_decoy_bag):
    v = verdict(7, [
        ev("color", "agree", "dark blue", "Dark blue"),
        ev("private_details", "conflict", "silver Eiffel Tower", "red pom-pom"),
    ], suggestion="possible_match")
    result = assess_candidate(lost_backpack, found_decoy_bag, v)
    assert result.assessment == "unlikely_match"
    assert result.conflicting_evidence[0].candidate == WITHHELD
    assert "pom" not in result.model_dump_json().lower()


# --- score + assessment caps ------------------------------------------------

def test_true_match_scores_high_and_stays_likely(lost_backpack, found_navy_bag):
    v = verdict(2, [
        ev("category", "agree", "backpack", "school bag"),
        ev("color", "agree", "dark blue", "navy"),
        ev("location", "agree", "Main Library", "Main Library, 2nd floor reading room"),
        ev("features", "partial", "small keychain", "keyring attached"),
    ])
    result = assess_candidate(lost_backpack, found_navy_bag, v)
    assert result.ranking_score == 30 + 20 + 20 + 15 + 8
    assert result.assessment == "likely_match"
    assert result.ranking_score == sum(s.points for s in result.score_breakdown)


def test_time_conflict_caps_model_optimism(lost_backpack, found_sports_bag):
    v = verdict(3, [ev("category", "agree", "backpack", "backpack"),
                    ev("color", "partial", "dark blue", "Blue")],
                suggestion="likely_match")
    result = assess_candidate(lost_backpack, found_sports_bag, v)
    assert result.assessment == "unlikely_match"
    assert result.next_step.startswith("Probably a different item")


def test_too_little_known_is_insufficient(lost_backpack, found_vague_bag):
    v = verdict(4, [ev("category", "agree", "backpack", "backpack")],
                suggestion="possible_match")
    assert assess_candidate(lost_backpack, found_vague_bag, v).assessment \
        == "insufficient_information"


def test_likely_with_a_conflict_becomes_possible():
    results = {"category": "agree", "color": "agree", "location": "conflict",
               "time": "agree", "features": "agree"}
    assert decide_assessment(results, 80, "likely_match", False) == "possible_match"


# --- degraded mode ----------------------------------------------------------

def test_degraded_never_says_likely(lost_backpack, found_navy_bag):
    result = assess_candidate(lost_backpack, found_navy_bag, None)
    assert result.assessment == "possible_match"
    assert {e.source for e in result.matching_evidence} == {"rule"}
    # rules cannot tell navy == dark blue, so colour stays unknown (not conflict)
    assert result.score_breakdown[1].result == "unknown"


def test_degraded_colour_rule_ignores_shade_words(lost_backpack, found_decoy_bag):
    found_decoy_bag.color = "dark green"
    result = assess_candidate(lost_backpack, found_decoy_bag, None)
    assert result.score_breakdown[1].result == "unknown"


def test_sparse_report_cannot_be_likely():
    """Category + colour + one vague feature is not enough for 'likely'."""
    results = {"category": "agree", "color": "agree", "location": "unknown",
               "time": "unknown", "features": "agree"}
    assert decide_assessment(results, 65, "likely_match", False) == "possible_match"
    results["location"] = "agree"
    assert decide_assessment(results, 85, "likely_match", False) == "likely_match"
