# AI agent beginner's guide — Person C

Branch `feature/ai` · Folders `backend/foundit_ai/`, `backend/tests/ai/` · Detailed spec:
[`docs/tasks/AI.md`](../tasks/AI.md) · First read: [How to build with AI](HOW_TO_BUILD_WITH_AI.md)

---

## Big picture (read first)

You build the **brain**: the part that decides which reports might be the same item and
explains why. The backend calls two of your functions; you never touch HTTP or the database.

```
extract_attributes(report)          find_matches(query, pool)
        │                                   │
        ▼                                   ▼
 gpt-oss-120b: "navy school bag"     1. retrieve  (Python)  cheap filter → top 5
  → backpack, color_family blue      2. compare   (model)   one call, evidence as strict JSON
                                     3. verify    (Python)  quotes must exist; hide private details
                                     4. score     (Python)  points table + safety caps
                                     └ model down → degraded: rules only
```

### Concepts you need

| Concept | Plain explanation |
|---|---|
| **LLM** | A language model: text in, text out. Ours is **gpt-oss-120b**. |
| **Open-weight** | The trained model files are public; anyone may download and run them. gpt-oss is Apache 2.0. |
| **Groq** | A company that hosts open models on fast hardware. We call it over the internet because we have no GPU. |
| **Prompt** | The instructions + data we send. The *system prompt* holds the rules. |
| **Structured output / JSON schema** | We force the model to answer in an exact JSON shape so Python can read it — no free-form paragraphs. |
| **Tokens & rate limit** | Text is counted in tokens (~¾ word). Free plan: 8,000 tokens/minute → we compare all candidates in ONE call. |
| **Hallucination** | The model stating something not in the input. We defend with **grounding**: every quote must appear word-for-word in a report, or it's thrown away. |
| **Retrieval** | Cheaply narrowing many reports to a few candidates *before* the expensive model call. |
| **TF-IDF** | Word-overlap similarity where rare words ("Eiffel") count more than common ones ("the"). |
| **Degraded mode** | If the model fails, return safe rule-based results instead of crashing. |
| **Fake client** | A pretend model used in tests, so tests are fast, free and work offline. |

---

## Context Prompt — paste at the start of EVERY new AI chat

```
I'm learning AI engineering and building the AI AGENT of "FoundIt", a one-day hackathon
project: people submit lost/found reports; the agent finds candidate matches and explains
evidence for and against each.

My role: Python 3.11+ module backend/foundit_ai/ and its tests in backend/tests/ai/.
I must NOT edit backend/app/ (backend teammate) or frontend/. Spec: docs/tasks/AI.md.
Existing code (read before writing): schemas.py (data shapes incl. LLMComparison),
scoring.py (deterministic time check, grounding, privacy, points, caps, assess_candidate).

Model: openai/gpt-oss-120b on Groq via the `openai` SDK with base_url from .env
(GROQ_BASE_URL); fallback openai/gpt-oss-20b. Free tier: 8K tokens/min.

Design rules:
- The model only suggests; Python verifies and decides (scoring.py has the final word).
- The model never gets contact info, never runs code/SQL, never touches the database.
- Tests must run offline with a fake LLM client; only scripts/* call the real API.
- No new dependencies without asking; stdlib where possible.
- Explain the AI-engineering reasoning behind each design choice in simple words.
Work in small steps; only the step I ask for. Reply "Ready" and wait.
```

---

## Part 1 — Schemas + scoring ✅ done

Read `backend/foundit_ai/scoring.py` top to bottom. Then use this prompt to check you understand it:
```
Explain backend/foundit_ai/scoring.py to me section by section, then quiz me with 5
questions: why time is checked in Python, what grounding is, why missing info scores 0,
when the assessment is capped, and what degraded mode does.
```

---

## Part 2 — Retrieval (`retrieve.py`, 45 min)

**What:** pick the top-k candidates without calling the model.
**Why:** model calls cost seconds and tokens; Python filtering costs microseconds.

**Prompt:**
```
Task: step 2 of docs/tasks/AI.md. Create backend/foundit_ai/retrieve.py with
search_candidate_reports(query: ReportRecord, pool: list[ReportRecord], k: int = 5)
-> tuple[list[ReportRecord], int]  (candidates, number considered).
- Keep only opposite type, status "open", id != query.id.
- Drop clear category conflicts (both categories known, different, neither "other";
  use ai_attributes.category when the user category is missing).
- Rank by a small pure-Python TF-IDF cosine over: description + color + location +
  ai_attributes (item_type, color_family, features, location_normalized). Lowercase,
  simple tokenizer, small stopword list.
- Return top k. Write backend/tests/ai/test_retrieve.py using the fixtures in conftest.py:
  never returns same type; category conflict removed; navy school bag ranks above an
  unrelated wallet; k respected; empty pool → ([], 0).
Explain TF-IDF in simple words.
```
**Check:** `python -m pytest` all green. **Commit:** `feat(ai): add candidate retrieval`

---

## Part 3 — Model client (`llm_client.py`, 40 min)

**What:** one place that talks to Groq, with timeout and fallback.
**Prompt:**
```
Task: step 3 of docs/tasks/AI.md. Create backend/foundit_ai/llm_client.py:
- class AIUnavailable(Exception).
- class LLMClient (Protocol) with method complete_json(system: str, user: str,
  output_model: type[BaseModel]) -> BaseModel.
- class GroqClient: reads GROQ_API_KEY, GROQ_BASE_URL, TEXT_MODEL, FALLBACK_MODEL
  (default openai/gpt-oss-20b), AI_TIMEOUT_SECONDS from env (python-dotenv). Uses
  response_format json_schema strict built from output_model (all properties required,
  additionalProperties false — reuse the approach in scripts/spike_model.py),
  temperature 0, reasoning_effort "medium". Tries the primary model, then the fallback on
  timeout, rate limit, API error, or invalid JSON. Raises AIUnavailable if both fail or the key is missing.
  Logs model, latency and token usage with the logging module.
- tests/ai/fakes.py: FakeLLM returning a preset object, or raising AIUnavailable.
Tests: missing key → AIUnavailable; invalid JSON from primary triggers fallback (mock the
openai client; no network).
```
**Commit:** `feat(ai): add Groq client with fallback`

---

## Part 4 — Comparison (`compare.py`, 45 min)

**What:** the prompt that makes the model compare reports. Improved from the spike: compare private details directly.
**Prompt:**
```
Task: step 4 of docs/tasks/AI.md. Create backend/foundit_ai/compare.py with
compare_reports(query, candidates, llm) -> dict[int, LLMVerdict].
- Build a compact JSON input: query report + candidates with fields type, description,
  category, color, location, private_details, and ai_attributes (no occurred_at, no contact).
- System prompt rules: use only facts in the reports; this_quote/candidate_quote copied
  verbatim; unknown when either side is silent (missing info is never a match); "partial" =
  compatible but vague; "conflict" = contradiction; synonyms/shades are fine; ALWAYS add a
  private_details evidence item when both reports have private details, comparing them
  directly; next_step must not reveal the candidate's private details and should ask about
  what the CANDIDATE lacks; don't judge time; no probabilities.
- Call llm.complete_json(..., LLMComparison). Ignore verdicts whose candidate_id isn't in
  the candidates. Let AIUnavailable propagate.
Tests with FakeLLM: unknown ids dropped; the prompt never contains a contact value.
Explain each prompt rule and which failure it prevents.
```
**Commit:** `feat(ai): add report comparison prompt`

---

## Part 5 — Extraction (`extract.py`, 30 min)

**Prompt:**
```
Task: step 5 of docs/tasks/AI.md. Create backend/foundit_ai/extract.py with
extract_attributes(report: ReportRecord, llm: LLMClient | None = None) -> AIAttributes.
The model normalizes the report: item_type (short noun, e.g. "backpack"), category (from
the Category list), color_family (basic colors only: black, white, grey, blue, green, red,
yellow, orange, purple, pink, brown, beige, silver, gold, multicolor), brand (only if
stated), features (short phrases from the text), location_normalized (lowercase). Only
use stated facts; null/[] when unknown. Do NOT send private_details or contact.
On AIUnavailable or any validation error return AIAttributes(extraction_status="failed")
— never raise. Tests with FakeLLM for success and failure.
```
**Commit:** `feat(ai): add attribute extraction`

---

## Part 6 — The agent (`agent.py`, 45 min)

**Prompt:**
```
Task: step 6 of docs/tasks/AI.md. Create backend/foundit_ai/agent.py exposing exactly the
two functions in docs/TEAM.md:
- extract_attributes(report, photo_path=None) -> AIAttributes (delegates to extract.py
  with a default GroqClient created lazily).
- find_matches(query, pool, *, limit=5, llm=None) -> MatchRun:
  1. search_candidate_reports → (candidates, considered); none → empty MatchRun.
  2. compare_reports; on AIUnavailable set degraded=True, degraded_reason short and human.
  3. assess_candidate(query, cand, verdict or None) for each; a candidate the model
     forgot gets None (rule-based) — degraded stays False for the others.
  4. Sort by ranking_score desc; return MatchRun with generated_at = now UTC.
  Never raises because of the AI.
Tests with FakeLLM: happy path ranks the navy bag first; model down → degraded True and
no likely_match; empty pool; model omits one candidate.
```
**Commit:** `feat(ai): add matching agent`

---

## Part 7 — Demo dataset (40 min)

**Prompt:**
```
Task: step 7 of docs/tasks/AI.md. Create sample_data/demo_reports.json:
{"reports": [...15 ReportRecord-shaped dicts...], "expected": {"true_pairs": [[lost_id,
found_id], ...], "decoys": [[lost_id, found_id, "why"], ...]}}. University campus,
October 2026, UTC times. Cover: same item different words; look-alike decoy with a
different private detail; right item wrong building; found before lost; missing
date/color; one rich and one sparse description; two different phones; a wallet and a
water bottle. Keep it realistic, no real names or contacts (use contact null).
```
**Commit:** `feat(ai): add demo dataset with hard cases`

---

## Part 8 — Live evaluation (`scripts/eval_matching.py`, 30 min)

**Prompt:**
```
Task: step 8 of docs/tasks/AI.md. scripts/eval_matching.py loads demo_reports.json, runs
extract_attributes on every report (sleeping if needed to respect 8K tokens/min), then
find_matches for every lost report. Print a table: lost id, top candidate, assessment,
score, correct?; then hit@1 for true_pairs and how many decoys ranked below the true match.
```
**Check:** run it with your key. Note the numbers — they go in the README and the pitch.
**Commit:** `feat(ai): add live evaluation script`

---

## Part 9 — Vision (optional)
Take 3 real phone photos (bag, phone, bottle), put them in `sample_data/photos/`, and ask:
```
Extend scripts/spike_model.py run_vision to loop over all images in sample_data/photos and
print the parsed result per photo. Don't change anything else.
```
Only integrate photo attributes if it gets all 3 right.

---

## Part 10 — README section
```
Write the "AI agent" section of README.md: model (gpt-oss-120b, Apache 2.0, why it qualifies
as open-weight, why hosted on Groq), the pipeline diagram from docs/guides/AI_GUIDE.md, how
the ranking score is computed (table from docs/API.md), what the model does vs what Python
does, degraded mode, evaluation numbers from eval_matching.py, and honest limitations.
```

---

## Questions judges may ask you
1. What does the AI actually do that rules couldn't? *(understands "navy school bag" ≈ "dark blue backpack", compares free-text details)*
2. How do you stop hallucinated evidence? *(grounding: quotes must exist verbatim, else dropped)*
3. Is the score a probability? *(no — a transparent points sum; the model can't set it)*
4. Why one model call instead of one per candidate? *(rate limit 8K tokens/min, latency)*
5. Is your model really open? *(gpt-oss-120b weights are public under Apache 2.0; Groq is only hosting)*
6. What if Groq is down? *(fallback model, then degraded rule-based mode; the demo never crashes)*
