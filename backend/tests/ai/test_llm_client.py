"""Tests for the multi-provider model client — no network (fake SDKs)."""

from __future__ import annotations

import openai
import pytest
from pydantic import BaseModel

from foundit_ai.llm_client import (
    AIUnavailable,
    ModelClient,
    clean_model_text,
    parse_chain,
    strict_json_schema,
)
from foundit_ai.schemas import LLMComparison
from tests.ai.fakes import FakeOpenAISDK

CHAIN = "google:gemma-4-26b-a4b-it,groq:openai/gpt-oss-120b"


class Answer(BaseModel):
    label: str
    note: str | None


def outage() -> openai.OpenAIError:
    """Any OpenAIError subclass (timeout, rate limit, 5xx...) takes the same path."""
    return openai.OpenAIError("simulated outage")


def client_with(google_replies, groq_replies=()):
    sdks = {"google": FakeOpenAISDK(google_replies), "groq": FakeOpenAISDK(groq_replies)}
    return ModelClient(CHAIN, sdk_factory=sdks.__getitem__), sdks


# --- configuration ------------------------------------------------------------

def test_no_keys_means_ai_unavailable(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(AIUnavailable):
        ModelClient(CHAIN)


def test_provider_without_key_is_skipped(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")
    client = ModelClient(CHAIN)                    # no Groq key in tests
    assert client.chain == [("google", "gemma-4-26b-a4b-it")]


def test_closed_gemini_models_are_refused():
    with pytest.raises(ValueError, match="open-weight"):
        parse_chain("google:gemini-3.8-flash")


def test_bad_chain_entry_is_refused():
    with pytest.raises(ValueError):
        parse_chain("gemma-4-26b-a4b-it")          # missing provider


# --- calls ---------------------------------------------------------------------

def test_valid_answer_from_first_model():
    client, sdks = client_with(['{"label": "ok", "note": null}'])
    assert client.complete_json("s", "u", Answer) == Answer(label="ok", note=None)
    assert sdks["google"].models_called == ["gemma-4-26b-a4b-it"]
    assert sdks["groq"].models_called == []
    assert client.last_model == "gemma-4-26b-a4b-it"


def test_gemma_gets_no_reasoning_effort_but_gpt_oss_does():
    client, sdks = client_with([outage()], ['{"label": "ok", "note": null}'])
    client.complete_json("s", "u", Answer, effort="low")
    assert "reasoning_effort" not in sdks["google"].kwargs[0]
    assert sdks["groq"].kwargs[0]["reasoning_effort"] == "low"


def test_outage_falls_back_to_next_provider():
    client, sdks = client_with([outage()], ['{"label": "ok", "note": "x"}'])
    assert client.complete_json("s", "u", Answer).label == "ok"
    assert client.last_model == "openai/gpt-oss-120b"


def test_invalid_json_falls_back_to_next_provider():
    client, _ = client_with(["not json"], ['{"label": "ok", "note": null}'])
    assert client.complete_json("s", "u", Answer).label == "ok"


def test_thought_blocks_are_stripped():
    client, _ = client_with(['<thought>hmm, navy is blue</thought>\n{"label": "ok", "note": null}'])
    assert client.complete_json("s", "u", Answer).label == "ok"


def test_all_models_fail_raises_ai_unavailable():
    client, _ = client_with([outage()], ['{"wrong": "shape"}'])
    with pytest.raises(AIUnavailable) as err:
        client.complete_json("s", "u", Answer)
    assert "gemma" in str(err.value) and "gpt-oss" in str(err.value)


# --- helpers ---------------------------------------------------------------------

def test_clean_model_text_handles_fences_and_thoughts():
    assert clean_model_text('```json\n{"a": 1}\n```') == '{"a": 1}'
    assert clean_model_text('<THOUGHT>x</THOUGHT> {"a": 1}') == '{"a": 1}'
    assert clean_model_text('{"a": {"b": 1}}\n```') == '{"a": {"b": 1}}'   # lone fence, seen live


def test_strict_schema_requires_every_field_and_forbids_extras():
    schema = strict_json_schema(LLMComparison)
    evidence = schema["$defs"]["LLMEvidence"]
    assert evidence["additionalProperties"] is False
    assert set(evidence["required"]) == set(evidence["properties"])


def test_each_task_has_its_own_chain(monkeypatch):
    from foundit_ai.llm_client import chain_for
    assert chain_for("extract").startswith("google:gemma-4")      # Gemma reads reports
    assert chain_for("compare").startswith("groq:openai/gpt-oss")  # gpt-oss compares
    monkeypatch.setenv("MODEL_CHAIN_COMPARE", "google:gemma-4-31b-it")
    assert chain_for("compare") == "google:gemma-4-31b-it"
