"""The only place that talks to language models.

- Providers (Google AI Studio for Gemma, Groq for gpt-oss) all expose an
  OpenAI-compatible API, so one code path serves them all via the `openai` SDK.
- A chain lists models in order of preference (one chain per task). Each call tries them in turn;
  if all fail we raise AIUnavailable and callers switch to degraded (rule-based)
  mode, so a model outage never crashes the app.
- Every call asks for strict JSON matching a Pydantic model, then validates it.
- Open-model guard: on Google only `gemma-*` models are allowed, because the
  same API key also reaches Google's closed Gemini models.
"""

from __future__ import annotations

import copy
import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol, TypeVar

from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

log = logging.getLogger(__name__)

# Load the repo-root .env once (never overrides variables already set).
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

T = TypeVar("T", bound=BaseModel)

# Each task gets the models that measured best for it (see scripts/eval_matching.py):
# - extract:        Gemma 4 is fast and accurate on short structured outputs.
# - compare:        quote mode needs verbatim quotes -> gpt-oss on Groq.
# - compare_fields: field mode (no quotes) -> Gemma 4, used when quote mode is
#                   unavailable. Google's "recitation" filter blocks Gemma in quote mode.
DEFAULT_CHAINS = {
    "extract": "google:gemma-4-26b-a4b-it,groq:openai/gpt-oss-120b",
    "compare": "groq:openai/gpt-oss-120b,groq:openai/gpt-oss-20b",
    "compare_fields": "google:gemma-4-26b-a4b-it",
}
DEFAULT_CHAIN = DEFAULT_CHAINS["compare"]


def chain_for(task: str) -> str:
    """MODEL_CHAIN_EXTRACT / MODEL_CHAIN_COMPARE in .env override the defaults."""
    return os.getenv(f"MODEL_CHAIN_{task.upper()}", DEFAULT_CHAINS[task])


@dataclass(frozen=True)
class Provider:
    base_url: str
    key_env: str
    supports_reasoning_effort: bool      # gpt-oss yes, Gemma no (400 error)
    allowed_prefixes: tuple[str, ...]    # open-weight models only


PROVIDERS: dict[str, Provider] = {
    "google": Provider(
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        key_env="GEMINI_API_KEY", supports_reasoning_effort=False,
        allowed_prefixes=("gemma-",)),
    "groq": Provider(
        base_url=os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
        key_env="GROQ_API_KEY", supports_reasoning_effort=True,
        allowed_prefixes=("openai/gpt-oss", "qwen/", "meta-llama/")),
}


class AIUnavailable(Exception):
    """No model could produce a usable answer (no key, outage, bad output)."""


class LLMClient(Protocol):
    def complete_json(self, system: str, user: str, output_model: type[T], *,
                      effort: str = "medium") -> T: ...


def parse_chain(chain: str) -> list[tuple[str, str]]:
    """'google:gemma-4-26b-a4b-it,groq:openai/gpt-oss-120b' -> [(provider, model), ...]"""
    pairs = []
    for item in filter(None, (part.strip() for part in chain.split(","))):
        provider, sep, model = item.partition(":")
        if not sep or provider not in PROVIDERS or not model:
            raise ValueError(f"Bad MODEL_CHAIN entry {item!r}; expected provider:model "
                             f"with provider in {sorted(PROVIDERS)}")
        if not model.startswith(PROVIDERS[provider].allowed_prefixes):
            raise ValueError(f"{provider}:{model} is not an allowed open-weight model "
                             f"(allowed: {PROVIDERS[provider].allowed_prefixes})")
        pairs.append((provider, model))
    return pairs


def strict_json_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Pydantic's JSON schema, tightened for strict structured-output mode:
    every object lists all its properties as required and forbids extras."""
    schema = copy.deepcopy(model.model_json_schema())

    def tighten(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object" and "properties" in node:
                node["additionalProperties"] = False
                node["required"] = list(node["properties"])
            for value in node.values():
                tighten(value)
        elif isinstance(node, list):
            for value in node:
                tighten(value)

    tighten(schema)
    return schema


_THOUGHT = re.compile(r"<thought>.*?</thought>", re.DOTALL | re.IGNORECASE)


def clean_model_text(raw: str) -> str:
    """Keep only the JSON object: drop 'thinking' blocks, markdown fences and any
    stray text before the first '{' or after the last '}' (Gemma sometimes
    appends a lone closing fence)."""
    text = _THOUGHT.sub("", raw)
    start, end = text.find("{"), text.rfind("}")
    return text[start:end + 1] if start != -1 and end > start else text.strip()


class ModelClient:
    """Tries each (provider, model) in MODEL_CHAIN until one returns valid JSON."""

    def __init__(self, chain: str | None = None, *,
                 sdk_factory: Callable[[str], Any] | None = None,
                 timeout: float | None = None) -> None:
        self.chain = parse_chain(chain or DEFAULT_CHAIN)
        self.max_completion_tokens = int(os.getenv("MAX_COMPLETION_TOKENS", "6000"))
        self.usage_log: list[tuple[float, int]] = []   # (timestamp, total tokens)
        self.last_model: str | None = None
        timeout = timeout or float(os.getenv("AI_TIMEOUT_SECONDS", "20"))

        self._sdks: dict[str, Any] = {}
        skipped = []
        for provider in dict.fromkeys(p for p, _ in self.chain):
            if sdk_factory is not None:
                self._sdks[provider] = sdk_factory(provider)
                continue
            key = os.getenv(PROVIDERS[provider].key_env)
            if not key:
                skipped.append(PROVIDERS[provider].key_env)
                continue
            from openai import OpenAI
            self._sdks[provider] = OpenAI(api_key=key, base_url=PROVIDERS[provider].base_url,
                                          timeout=timeout, max_retries=0)
            # no SDK retries: the next model in the chain is the retry
        self.chain = [(p, m) for p, m in self.chain if p in self._sdks]
        if skipped:
            log.info("model_providers_skipped missing=%s", skipped)
        if not self.chain:
            raise AIUnavailable(f"no model API key configured (need one of: {skipped})")

    def complete_json(self, system: str, user: str, output_model: type[T], *,
                      effort: str = "medium") -> T:
        from openai import OpenAIError

        response_format = {"type": "json_schema", "json_schema": {
            "name": output_model.__name__, "strict": True,
            "schema": strict_json_schema(output_model)}}
        errors: list[str] = []

        for provider, model in self.chain:
            kwargs: dict[str, Any] = {}
            if PROVIDERS[provider].supports_reasoning_effort:
                # gpt-oss "thinks" first; reasoning + JSON must fit in this budget.
                kwargs = {"reasoning_effort": effort,
                          "max_completion_tokens": self.max_completion_tokens}
            started = time.perf_counter()
            try:
                resp = self._sdks[provider].chat.completions.create(
                    model=model,
                    messages=[{"role": "system", "content": system},
                              {"role": "user", "content": user}],
                    response_format=response_format,
                    temperature=0,
                    **kwargs,
                )
            except OpenAIError as e:
                errors.append(f"{model}: {type(e).__name__}")
                log.warning("model_call_failed model=%s error=%s", model, str(e)[:300])
                continue

            elapsed = time.perf_counter() - started
            usage = getattr(resp, "usage", None)
            tokens = getattr(usage, "total_tokens", 0) or 0
            self.usage_log.append((time.time(), tokens))
            log.info("model_call model=%s latency=%.1fs tokens=%s", model, elapsed, tokens)

            raw = resp.choices[0].message.content or ""
            try:
                result = output_model.model_validate_json(clean_model_text(raw))
            except ValidationError as e:
                errors.append(f"{model}: invalid output")
                log.warning("model_output_invalid model=%s errors=%s raw=%r",
                            model, e.error_count(), raw[:200])
                continue
            self.last_model = model
            return result

        raise AIUnavailable("; ".join(errors) or "no model configured")


# Backwards-compatible name used in early docs.
GroqClient = ModelClient
