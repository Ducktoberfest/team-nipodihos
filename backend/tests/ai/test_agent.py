"""End-to-end tests of the agent with a fake model (no network)."""

from __future__ import annotations

import pytest

from foundit_ai import agent
from foundit_ai.llm_client import AIUnavailable
from foundit_ai.schemas import LLMComparison, MatchRun
from tests.ai.fakes import FakeLLM
from tests.ai.helpers import ev, verdict


@pytest.fixture(autouse=True)
def _reset_default_client(monkeypatch):
    monkeypatch.setattr(agent, "_default_clients", {})


@pytest.fixture
def pool(lost_backpack, found_navy_bag, found_sports_bag, found_vague_bag, found_decoy_bag):
    return [lost_backpack, found_navy_bag, found_sports_bag, found_vague_bag, found_decoy_bag]


def realistic_answer() -> LLMComparison:
    """Roughly what gpt-oss returned in the spike, plus a private-detail comparison."""
    return LLMComparison(candidates=[
        verdict(2, [
            ev("category", "agree", "backpack", "school bag"),
            ev("color", "agree", "dark blue", "navy"),
            ev("location", "agree", "Main Library", "Main Library, 2nd floor reading room"),
            ev("features", "agree", "small keychain", "keyring attached"),
            ev("private_details", "agree", "Eiffel Tower", "metal tower charm"),
        ], suggestion="likely_match"),
        verdict(3, [
            ev("category", "agree", "backpack", "backpack"),
            ev("location", "conflict", "Main Library", "Sports Centre, locker room"),
            ev("features", "conflict", "small keychain", "No keyring"),
        ], suggestion="unlikely_match"),
        verdict(4, [ev("category", "agree", "backpack", "backpack")],
                suggestion="insufficient_information"),
        verdict(7, [
            ev("category", "agree", "backpack", "backpack"),
            ev("color", "agree", "dark blue", "Dark blue"),
            ev("location", "partial", "library", "library cafe"),
            ev("private_details", "conflict", "silver Eiffel Tower", "red pom-pom"),
        ], suggestion="possible_match"),
    ])


def test_happy_path_ranks_true_match_first(lost_backpack, pool):
    run = agent.find_matches(lost_backpack, pool, llm=FakeLLM(realistic_answer()))
    assert isinstance(run, MatchRun) and not run.degraded
    assert run.candidates_considered == 4
    by_id = {c.candidate_report_id: c for c in run.candidates}

    assert run.candidates[0].candidate_report_id == 2
    assert by_id[2].assessment == "likely_match" and by_id[2].ranking_score == 100
    assert by_id[3].assessment == "unlikely_match"          # time + location + keyring
    assert by_id[4].assessment == "insufficient_information"
    assert by_id[7].assessment == "unlikely_match"          # private detail contradicts
    assert "pom" not in run.model_dump_json().lower()       # finder's secret never leaks
    assert "charm" not in run.model_dump_json().lower()


def test_model_down_gives_degraded_rule_based_results(lost_backpack, pool):
    run = agent.find_matches(lost_backpack, pool, llm=FakeLLM(AIUnavailable("down")))
    assert run.degraded and run.degraded_reason
    assert run.candidates
    assert all(c.assessment != "likely_match" for c in run.candidates)
    assert all(e.source == "rule" for c in run.candidates for e in c.matching_evidence)


def test_no_api_key_degrades_instead_of_crashing(lost_backpack, pool):
    run = agent.find_matches(lost_backpack, pool)      # no llm, GROQ_API_KEY removed
    assert run.degraded


def test_skipped_candidate_falls_back_to_rules(lost_backpack, pool):
    only_two = LLMComparison(candidates=[c for c in realistic_answer().candidates
                                         if c.candidate_id == 2])
    run = agent.find_matches(lost_backpack, pool, llm=FakeLLM(only_two))
    assert not run.degraded
    others = [c for c in run.candidates if c.candidate_report_id != 2]
    assert all(c.assessment != "likely_match" for c in others)


def test_empty_pool_makes_no_model_call(lost_backpack):
    llm = FakeLLM(realistic_answer())
    run = agent.find_matches(lost_backpack, [lost_backpack], llm=llm)
    assert run.candidates == [] and run.candidates_considered == 0
    assert llm.calls == []


def test_limit_is_clamped(lost_backpack, pool):
    run = agent.find_matches(lost_backpack, pool, limit=1, llm=FakeLLM(realistic_answer()))
    assert len(run.candidates) == 1
    run = agent.find_matches(lost_backpack, pool, limit=0, llm=FakeLLM(realistic_answer()))
    assert len(run.candidates) == 1


def test_extract_without_key_returns_failed(found_navy_bag):
    assert agent.extract_attributes(found_navy_bag).extraction_status == "failed"


def test_output_matches_api_contract_shape(lost_backpack, pool):
    data = agent.find_matches(lost_backpack, pool, llm=FakeLLM(realistic_answer())).model_dump(mode="json")
    assert set(data) == {"report_id", "generated_at", "degraded", "degraded_reason",
                         "candidates_considered", "candidates"}
    c = data["candidates"][0]
    assert set(c) == {"candidate_report_id", "candidate", "assessment", "ranking_score",
                      "score_breakdown", "matching_evidence", "conflicting_evidence",
                      "missing_information", "next_step"}
    assert "private_details" not in c["candidate"]
    assert data["generated_at"].endswith("Z")


def test_gemma_field_mode_takes_over_when_gpt_oss_is_unavailable(lost_backpack, pool, monkeypatch):
    from foundit_ai.compare import FieldComparison, FieldEvidence, FieldVerdict
    gemma_answer = FieldComparison(candidates=[FieldVerdict(
        candidate_id=2, suggested_assessment="likely_match",
        evidence=[FieldEvidence(attribute=a, result="agree", query_field=f, candidate_field=f)
                  for a, f in [("category", "category"), ("color", "color"),
                               ("location", "location")]])])
    fakes = {"compare": FakeLLM(AIUnavailable("groq down")),
             "compare_fields": FakeLLM(gemma_answer)}
    monkeypatch.setattr(agent, "default_client", lambda task: fakes[task])

    run = agent.find_matches(lost_backpack, pool)
    assert not run.degraded                                   # Gemma answered
    assert fakes["compare_fields"].calls                      # field mode was used
    top = run.candidates[0]
    assert top.candidate_report_id == 2
    assert any(e.candidate == "navy" for e in top.matching_evidence)


def test_both_comparison_models_down_means_degraded(lost_backpack, pool, monkeypatch):
    monkeypatch.setattr(agent, "default_client",
                        lambda task: FakeLLM(AIUnavailable(f"{task} down")))
    run = agent.find_matches(lost_backpack, pool)
    assert run.degraded
