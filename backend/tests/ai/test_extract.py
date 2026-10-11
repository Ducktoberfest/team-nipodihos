"""Tests for attribute extraction (fake model, no network)."""

from __future__ import annotations

from foundit_ai.extract import ExtractionOut, build_user_prompt, extract_attributes
from foundit_ai.llm_client import AIUnavailable
from tests.ai.fakes import FakeLLM


def good_answer(**overrides) -> ExtractionOut:
    data = dict(item_type="Backpack", category="bag", color_family=["blue", "blue"],
                brand=None, features=["keyring attached"],
                location_normalized="main library, 2nd floor reading room")
    data.update(overrides)
    return ExtractionOut(**data)


def test_success_normalises_attributes(found_navy_bag):
    attrs = extract_attributes(found_navy_bag, FakeLLM(good_answer()))
    assert attrs.extraction_status == "ok"
    assert attrs.item_type == "backpack"
    assert attrs.color_family == ["blue"]           # de-duplicated
    assert attrs.features == ["keyring attached"]


def test_private_details_never_sent_to_model(found_navy_bag):
    llm = FakeLLM(good_answer())
    extract_attributes(found_navy_bag, llm)
    assert "tower charm" not in llm.calls[0]["user"]
    assert "tower charm" not in build_user_prompt(found_navy_bag)


def test_invented_brand_and_features_are_dropped(found_navy_bag):
    answer = good_answer(brand="JanSport",
                         features=["keyring attached", "laptop sleeve", "red stripe"])
    attrs = extract_attributes(found_navy_bag, FakeLLM(answer))
    assert attrs.brand is None                      # "JanSport" is not in the report
    assert attrs.features == ["keyring attached"]


def test_stated_brand_is_kept(found_sports_bag):
    attrs = extract_attributes(found_sports_bag, FakeLLM(good_answer(brand="Adidas")))
    assert attrs.brand == "Adidas"


def test_model_failure_returns_failed_status(found_navy_bag):
    attrs = extract_attributes(found_navy_bag, FakeLLM(AIUnavailable("down")))
    assert attrs.extraction_status == "failed"
    assert attrs.item_type is None and attrs.features == []


def test_uses_low_reasoning_effort(found_navy_bag):
    llm = FakeLLM(good_answer())
    extract_attributes(found_navy_bag, llm)
    assert llm.calls[0]["effort"] == "low"          # simple task, save tokens


def test_colour_family_comes_from_users_words_not_the_model(found_navy_bag):
    """Gemma once labelled a brown wallet 'blue'; code must override such mistakes."""
    attrs = extract_attributes(found_navy_bag, FakeLLM(good_answer(color_family=["red"])))
    assert attrs.color_family == ["blue"]           # "navy" -> blue, model's "red" ignored


def test_model_colour_used_only_when_user_named_none(found_vague_bag):
    attrs = extract_attributes(found_vague_bag, FakeLLM(good_answer(color_family=["green"])))
    assert attrs.color_family == ["green"]
