# AI tasks — Person C

**Branch:** `feature/ai` · **Your files:** `backend/foundit_ai/`, `backend/tests/ai/`,
`backend/requirements-ai.txt`, `scripts/spike_model.py`, `scripts/eval_matching.py`,
`sample_data/demo_reports.json`, `sample_data/photos/`
**Contract with Person B:** two functions in `backend/foundit_ai/agent.py` (see TEAM.md).

**Goal:** `find_matches` ranks true matches first, flags look-alike decoys, explains every
suggestion with verified evidence, and still answers when the model is unavailable.

---

## How the agent works (the explanation you'll give judges)

```
submit report ──▶ extract_attributes ──[gpt-oss-120b]──▶ normalised attributes saved
                    ("navy school bag" → item_type backpack, color_family blue)

find matches ──▶ 1. retrieve   (Python)   opposite type, compatible category, word similarity → top 5
                 2. compare    (gpt-oss)  ONE call: evidence for/against per candidate, strict JSON
                 3. verify     (Python)   drop quotes not in the reports, hide private details
                 4. score      (Python)   fixed points table + safety caps → ranked MatchRun
                 └─ model fails? → degraded mode: rules only, never "likely"
```
The model **suggests**; Python **verifies and decides**. The model never touches the
database, never runs code, and never sees contact info.

---

## Setup

```bash
git switch feature/ai
python -m venv .venv && .venv\Scripts\activate
pip install -r backend/requirements-ai.txt
copy .env.example .env            # then paste your Groq key into .env
python -m pytest                  # all AI tests must pass offline
```

---

## Tasks

- [x] **1. `schemas.py` + `scoring.py` + tests** — data shapes; deterministic time check,
  grounding, privacy redaction, points table, assessment caps, degraded fallback. 17 tests.
- [x] **Spike** (`scripts/spike_model.py`) — proved gpt-oss-120b returns valid strict-JSON,
  grounded evidence in ~5 s / ~3.2K tokens for 4 candidates. Weakness found: doesn't compare
  private details against each other → fix in `compare.py` prompt.
- [ ] **2. `retrieve.py`** — `search_candidate_reports(query, pool, k)`: opposite type,
  `open` status, drop clear category conflicts, rank by TF-IDF cosine over description +
  extracted attributes. Pure Python, no model call. Tests: never returns same-type
  reports; category conflict removed; synonyms found via extracted attributes.
- [ ] **3. `llm_client.py`** — Groq via the `openai` SDK (`base_url` from `.env`), timeout,
  primary `gpt-oss-120b` → fallback `gpt-oss-20b`, raises one `AIUnavailable` error if both
  fail. A `FakeLLM` in tests so nothing hits the network.
- [ ] **4. `compare.py`** — `compare_reports(query, candidates, llm) -> LLMComparison`:
  one call, strict JSON schema, prompt rules (verbatim quotes, unknown ≠ match, compare
  private details directly, no probabilities, don't judge time). Tests: schema-invalid
  output → `AIUnavailable`; unknown candidate ids ignored.
- [ ] **5. `extract.py`** — `extract_attributes(report) -> AIAttributes` (strict JSON).
  On failure returns `extraction_status="failed"` — never raises.
- [ ] **6. `agent.py`** — `find_matches(query, pool, limit)`: retrieve → compare →
  `assess_candidate` per candidate → sort → `MatchRun`. Any AI failure → `degraded=True`.
  Tests with FakeLLM: happy path, model down, empty pool, model forgets a candidate.
- [ ] **7. `sample_data/demo_reports.json`** — ~15 campus reports + an `expected` section
  listing true pairs and decoys. Hard cases: synonyms, look-alike decoy with different
  private detail, right item wrong place, found before lost, missing date/colour, one rich
  vs one sparse description.
- [ ] **8. `scripts/eval_matching.py`** — runs every lost report in the demo set against the
  live model; prints hit@1 for true pairs and whether decoys were ranked below. Run it
  after any prompt change.
- [ ] **9. Vision** — test `qwen/qwen3.8-27b` on 3 real phone photos. Only add photo
  attributes to extraction if it identifies them correctly; otherwise leave photos as
  "shown to humans, not analysed" and say so in the README.
- [ ] **10. README section** — model + license (gpt-oss-120b, Apache 2.0, hosted on Groq
  because no GPU; same weights could run elsewhere), architecture diagram above, how the
  score is computed, limitations (no calibrated probability, small dataset, English only).

**Merge target:** tasks 2–7 merged into `main` by checkpoint **+5 h** so Person B can wire them in.

---

## Rules
- All tests offline (`FakeLLM`); only `scripts/*` call the real API.
- Never put your key anywhere except `.env`.
- Commit after each task: `feat(ai): add candidate retrieval`, etc.
