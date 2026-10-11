"""Spike: can the open-weight models on Groq do FoundIt's AI jobs reliably?

Tests the riskiest assumption before we build anything on top of it:

  1. TEXT  (openai/gpt-oss-120b): compare one lost report with 4 found
     candidates in ONE call, returning schema-valid JSON whose quotes are
     really present in the reports (no invented evidence).
  2. VISION (qwen/qwen3.8-27b): read a photo and return structured attributes.

Run:  .venv/Scripts/python scripts/spike_model.py
Needs GROQ_API_KEY in .env. This is a throwaway experiment, not app code.
"""

from __future__ import annotations

import base64
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from openai import BadRequestError, OpenAI
from pydantic import BaseModel, ValidationError

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

TEXT_MODEL = os.getenv("TEXT_MODEL", "openai/gpt-oss-120b")
VISION_MODEL = os.getenv("VISION_MODEL", "qwen/qwen3.8-27b")

# --- test data: one lost report, four tricky found candidates --------------

LOST = {
    "id": 1, "type": "lost",
    "description": "I lost my dark blue backpack near the university library. "
                   "It had a laptop and a small keychain inside.",
    "category": "bag", "color": "dark blue", "location": "Main Library",
    "occurred_at": "2026-10-09T14:00:00Z",
    "private_details": "Keychain is a small silver Eiffel Tower.",
}

CANDIDATES = [
    {   # true match, different wording
        "id": 2, "type": "found",
        "description": "A navy school bag was left on a chair in the library. "
                       "It has a keyring attached.",
        "category": "bag", "color": "navy",
        "location": "Main Library, 2nd floor reading room",
        "occurred_at": "2026-10-09T17:30:00Z",
        "private_details": "The keyring has a little metal tower charm.",
    },
    {   # same category/colour family, wrong place, found BEFORE it was lost
        "id": 3, "type": "found",
        "description": "Blue Adidas backpack found in the Sports Centre locker room. "
                       "No keyring, has a water bottle in the side pocket.",
        "category": "bag", "color": "blue",
        "location": "Sports Centre, locker room",
        "occurred_at": "2026-10-08T10:00:00Z",
        "private_details": None,
    },
    {   # almost no information
        "id": 4, "type": "found",
        "description": "Someone handed in a backpack at the security desk.",
        "category": "bag", "color": None, "location": None,
        "occurred_at": None, "private_details": None,
    },
    {   # decoy: looks identical publicly, private detail contradicts
        "id": 7, "type": "found",
        "description": "Dark blue backpack found in the library cafe area. "
                       "There is a keychain on the zipper.",
        "category": "bag", "color": "dark blue", "location": "Library cafe",
        "occurred_at": "2026-10-09T16:00:00Z",
        "private_details": "Keychain is a red pom-pom with the letter K.",
    },
]

# What a sensible human would say. Used only to eyeball the model's answer.
EXPECTED = {2: {"likely_match"}, 3: {"unlikely_match"},
            4: {"insufficient_information"}, 7: {"unlikely_match", "possible_match"}}

# --- output contract --------------------------------------------------------

Result = Literal["agree", "partial", "conflict", "unknown"]
Assessment = Literal["likely_match", "possible_match", "unlikely_match",
                     "insufficient_information"]


class Evidence(BaseModel):
    attribute: Literal["category", "color", "location", "features"]
    result: Result
    lost_quote: str | None
    found_quote: str | None
    note: str


class CandidateVerdict(BaseModel):
    candidate_id: int
    evidence: list[Evidence]
    suggested_assessment: Assessment
    missing_information: list[str]
    next_step: str


class Comparison(BaseModel):
    candidates: list[CandidateVerdict]


def strict_schema() -> dict:
    """Pydantic's schema, tightened for strict structured-output mode."""
    schema = Comparison.model_json_schema()

    def tighten(node):
        if isinstance(node, dict):
            if node.get("type") == "object" and "properties" in node:
                node["additionalProperties"] = False
                node["required"] = list(node["properties"])
            for v in node.values():
                tighten(v)
        elif isinstance(node, list):
            for v in node:
                tighten(v)

    tighten(schema)
    return schema


SYSTEM = """You compare lost-and-found reports for a university campus.

Rules:
- Use ONLY facts written in the reports. Never guess or invent details.
- lost_quote / found_quote must be copied EXACTLY (verbatim substring) from a
  field of the lost / found report. Use null if that report says nothing.
- If either side does not mention an attribute, result is "unknown".
  Missing information is never evidence of a match.
- "partial" = compatible but vague (e.g. "blue" vs "dark blue").
- "conflict" = the reports contradict each other.
- Treat synonyms and shades sensibly ("school bag" ~ "backpack", "navy" ~ "dark blue").
- Compare private_details too, but next_step must NOT reveal the found
  report's private_details; ask the owner to describe the detail instead.
- Do not judge dates/times; a separate system checks timing.
- No probabilities or percentages.
Return one entry per candidate."""


def build_user_prompt() -> str:
    strip = lambda r: {k: v for k, v in r.items() if k != "occurred_at"}
    return json.dumps({"lost_report": strip(LOST),
                       "found_candidates": [strip(c) for c in CANDIDATES]}, indent=1)


# --- checks -----------------------------------------------------------------

def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def report_text(r: dict) -> str:
    return _norm(" ".join(str(v) for k, v in r.items()
                          if v and k not in ("id", "type", "occurred_at")))


def grounding_failures(v: CandidateVerdict) -> list[str]:
    """Quotes that do not appear verbatim in the report they claim to come from."""
    cand = next((c for c in CANDIDATES if c["id"] == v.candidate_id), None)
    if cand is None:
        return [f"unknown candidate_id {v.candidate_id}"]
    bad = []
    for e in v.evidence:
        if e.lost_quote and _norm(e.lost_quote) not in report_text(LOST):
            bad.append(f"lost_quote {e.lost_quote!r}")
        if e.found_quote and _norm(e.found_quote) not in report_text(cand):
            bad.append(f"found_quote {e.found_quote!r}")
        if e.result != "unknown" and not (e.lost_quote and e.found_quote):
            bad.append(f"{e.attribute}={e.result} without both quotes")
    return bad


def privacy_leak(v: CandidateVerdict) -> list[str]:
    """Words from the finder's private details that show up in next_step."""
    cand = next((c for c in CANDIDATES if c["id"] == v.candidate_id), {})
    secret = cand.get("private_details") or ""
    words = {w for w in re.findall(r"[a-z]{4,}", secret.lower())
             if w not in report_text(LOST) and w not in {"keychain", "keyring", "with", "little", "metal", "letter", "charm", "has", "the"}}
    return [w for w in words if w in v.next_step.lower()]


# --- runs -------------------------------------------------------------------

def client() -> OpenAI:
    key = os.getenv("GROQ_API_KEY")
    if not key:
        sys.exit("GROQ_API_KEY missing in .env")
    return OpenAI(api_key=key, base_url=os.getenv("GROQ_BASE_URL",
                  "https://api.groq.com/openai/v1"),
                  timeout=float(os.getenv("AI_TIMEOUT_SECONDS", "30")))


def run_text(c: OpenAI, effort: str) -> None:
    print(f"\n=== TEXT: {TEXT_MODEL}  (reasoning_effort={effort}) ===")
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": build_user_prompt()}]
    modes = [
        ("json_schema strict", {"type": "json_schema", "json_schema":
            {"name": "comparison", "strict": True, "schema": strict_schema()}}),
        ("json_object", {"type": "json_object"}),
    ]
    for mode_name, fmt in modes:
        extra = "" if fmt["type"] == "json_schema" else (
            "\nReturn JSON matching this schema:\n" + json.dumps(Comparison.model_json_schema()))
        msgs = [messages[0], {"role": "user", "content": messages[1]["content"] + extra}]
        t0 = time.perf_counter()
        try:
            resp = c.chat.completions.create(model=TEXT_MODEL, messages=msgs,
                                             response_format=fmt, temperature=0,
                                             reasoning_effort=effort)
        except BadRequestError as e:
            print(f"  mode {mode_name!r} rejected: {str(e)[:200]}")
            continue
        dt = time.perf_counter() - t0
        u = resp.usage
        print(f"  mode={mode_name}  latency={dt:.1f}s  tokens in/out={u.prompt_tokens}/{u.completion_tokens}")
        raw = resp.choices[0].message.content or ""
        try:
            result = Comparison.model_validate_json(raw)
        except ValidationError as e:
            print(f"  SCHEMA INVALID: {e}\n  raw: {raw[:500]}")
            return
        print("  schema valid: yes")
        for v in sorted(result.candidates, key=lambda v: v.candidate_id):
            ok = "OK " if v.suggested_assessment in EXPECTED.get(v.candidate_id, set()) else "?? "
            print(f"\n  [{ok}] candidate {v.candidate_id}: {v.suggested_assessment}"
                  f"   (expected {'/'.join(sorted(EXPECTED.get(v.candidate_id, {'?'})))})")
            for e in v.evidence:
                print(f"       {e.attribute:9} {e.result:9} lost={e.lost_quote!r}  found={e.found_quote!r}")
            bad = grounding_failures(v)
            print(f"       grounding: {'PASS' if not bad else 'FAIL ' + '; '.join(bad)}")
            leak = privacy_leak(v)
            print(f"       privacy:   {'PASS' if not leak else 'LEAK ' + ', '.join(leak)}")
            print(f"       next_step: {v.next_step}")
        return


def run_vision(c: OpenAI) -> None:
    img = ROOT / "sample_data" / "photos" / "found_2_navy_backpack.png"
    print(f"\n=== VISION: {VISION_MODEL}  ({img.name}) ===")
    b64 = base64.b64encode(img.read_bytes()).decode()
    prompt = ('Describe the lost-and-found item in this photo. Return ONLY JSON: '
              '{"item_type": str, "colors": [str], "visible_features": [str], '
              '"text_or_logos": [str], "image_quality": "clear"|"unclear"}. '
              'Only describe what is visible; do not guess brands.')
    msgs = [{"role": "user", "content": [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}]}]
    for extra in ({"reasoning_format": "hidden"}, {}):
        t0 = time.perf_counter()
        try:
            resp = c.chat.completions.create(model=VISION_MODEL, messages=msgs,
                                             response_format={"type": "json_object"},
                                             temperature=0, extra_body=extra or None)
        except BadRequestError as e:
            print(f"  request with {extra} rejected: {str(e)[:200]}")
            continue
        dt = time.perf_counter() - t0
        raw = resp.choices[0].message.content or ""
        print(f"  latency={dt:.1f}s  tokens in/out={resp.usage.prompt_tokens}/{resp.usage.completion_tokens}")
        try:
            print("  parsed:", json.dumps(json.loads(raw)))
        except json.JSONDecodeError:
            print("  NOT JSON:", raw[:400])
        return


if __name__ == "__main__":
    c = client()
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    if which in ("all", "text"):
        run_text(c, effort=os.getenv("SPIKE_EFFORT", "medium"))
    if which in ("all", "vision"):
        run_vision(c)
