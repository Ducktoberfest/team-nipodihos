"""Tests for the comparison step (fake model, no network)."""

from __future__ import annotations

import json

import pytest

from foundit_ai.compare import SYSTEM_PROMPT, build_user_prompt, compare_reports
from foundit_ai.llm_client import AIUnavailable
from foundit_ai.schemas import LLMComparison
from tests.ai.fakes import FakeLLM
from tests.ai.helpers import ev, verdict


def test_prompt_contains_reports_but_no_timestamps(lost_backpack, found_navy_bag):
    payload = json.loads(build_user_prompt(lost_backpack, [found_navy_bag]))
    assert payload["query_report"]["id"] == 1
    assert payload["candidate_reports"][0]["description"].startswith("A navy school bag")
    assert payload["candidate_reports"][0]["private_details"]   # needed for comparison
    assert "occurred_at" not in json.dumps(payload)              # Python judges time


def test_system_prompt_states_the_safety_rules():
    for rule in ("verbatim", "NEVER evidence of a match", "NEVER reveal",
                 "No probabilities", "private_details"):
        assert rule in SYSTEM_PROMPT


def test_returns_verdicts_by_candidate_id(lost_backpack, found_navy_bag, found_sports_bag):
    answer = LLMComparison(candidates=[
        verdict(3, [ev("location", "conflict", "Main Library", "Sports Centre, locker room")],
                suggestion="unlikely_match"),
        verdict(2, [ev("color", "agree", "dark blue", "navy")]),
    ])
    llm = FakeLLM(answer)
    result = compare_reports(lost_backpack, [found_navy_bag, found_sports_bag], llm)
    assert set(result) == {2, 3}
    assert result[3].suggested_assessment == "unlikely_match"
    assert llm.calls[0]["output_model"] is LLMComparison
    assert len(llm.calls) == 1                                  # one batched call


def test_unknown_and_duplicate_ids_are_ignored(lost_backpack, found_navy_bag):
    answer = LLMComparison(candidates=[
        verdict(99, []),                                         # not a candidate
        verdict(2, [], suggestion="possible_match"),
        verdict(2, [], suggestion="unlikely_match"),             # duplicate
    ])
    result = compare_reports(lost_backpack, [found_navy_bag], FakeLLM(answer))
    assert list(result) == [2]
    assert result[2].suggested_assessment == "possible_match"


def test_no_candidates_means_no_model_call(lost_backpack):
    llm = FakeLLM()
    assert compare_reports(lost_backpack, [], llm) == {}
    assert llm.calls == []


def test_model_failure_propagates(lost_backpack, found_navy_bag):
    with pytest.raises(AIUnavailable):
        compare_reports(lost_backpack, [found_navy_bag], FakeLLM(AIUnavailable("down")))


# --- field mode (Gemma) -------------------------------------------------------

from foundit_ai.compare import (  # noqa: E402
    FieldComparison,
    FieldEvidence,
    FieldVerdict,
    compare_reports_by_field,
)
from foundit_ai.schemas import WITHHELD  # noqa: E402
from foundit_ai.scoring import assess_candidate  # noqa: E402


def field_answer(cid, items, suggestion="likely_match"):
    return FieldComparison(candidates=[FieldVerdict(
        candidate_id=cid, suggested_assessment=suggestion,
        evidence=[FieldEvidence(attribute=a, result=r, query_field=q, candidate_field=c)
                  for a, r, q, c in items])])


def test_field_mode_fills_evidence_from_the_reports(lost_backpack, found_navy_bag):
    answer = field_answer(2, [("color", "agree", "color", "color"),
                              ("category", "agree", "description", "description")])
    v = compare_reports_by_field(lost_backpack, [found_navy_bag], FakeLLM(answer))[2]
    color = next(e for e in v.evidence if e.attribute == "color")
    assert (color.this_quote, color.candidate_quote) == ("dark blue", "navy")
    category = next(e for e in v.evidence if e.attribute == "category")
    assert category.candidate_quote in found_navy_bag.description     # verbatim snippet
    assert len(category.candidate_quote.split()) <= 10


def test_field_mode_never_sends_copy_instructions_that_trigger_recitation():
    from foundit_ai.compare import FIELD_SYSTEM_PROMPT
    assert "Do not copy any text" in FIELD_SYSTEM_PROMPT


def test_field_mode_empty_field_gives_no_evidence(lost_backpack, found_vague_bag):
    answer = field_answer(4, [("color", "agree", "color", "color")])   # vague bag has no color
    v = compare_reports_by_field(lost_backpack, [found_vague_bag], FakeLLM(answer))[4]
    result = assess_candidate(lost_backpack, found_vague_bag, v)
    assert result.score_breakdown[1].result == "unknown"               # claim dropped


def test_field_mode_private_details_stay_hidden(lost_backpack, found_decoy_bag):
    answer = field_answer(7, [("private_details", "conflict", "private_details", "private_details")],
                          suggestion="possible_match")
    v = compare_reports_by_field(lost_backpack, [found_decoy_bag], FakeLLM(answer))[7]
    result = assess_candidate(lost_backpack, found_decoy_bag, v)
    assert result.assessment == "unlikely_match"
    assert result.conflicting_evidence[0].candidate == WITHHELD
    assert "pom" not in result.model_dump_json().lower()


def test_field_mode_lists_missing_information(lost_backpack, found_vague_bag):
    answer = field_answer(4, [("category", "agree", "category", "category")],
                          suggestion="insufficient_information")
    v = compare_reports_by_field(lost_backpack, [found_vague_bag], FakeLLM(answer))[4]
    assert any("colour" in m for m in v.missing_information)
    assert v.next_step.startswith("Not enough detail")


def test_field_mode_asks_again_for_skipped_candidates(lost_backpack, found_navy_bag, found_decoy_bag):
    first = field_answer(7, [("color", "agree", "color", "color")], suggestion="possible_match")
    second = field_answer(2, [("color", "agree", "color", "color")])
    answers = iter([first, second])
    llm = FakeLLM(lambda system, user, model: next(answers))
    result = compare_reports_by_field(lost_backpack, [found_navy_bag, found_decoy_bag], llm)
    assert set(result) == {2, 7}
    assert len(llm.calls) == 2
    assert '"id": 7' not in llm.calls[1]["user"]          # retry only sends the skipped one
