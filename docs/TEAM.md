# FoundIt — Team Plan

Three people, three branches, one shared contract.
**The contract is [`docs/API.md`](API.md).** Build against it; don't change it alone.

**Step-by-step task sheets:** [Frontend](tasks/FRONTEND.md) · [Backend](tasks/BACKEND.md) · [AI](tasks/AI.md)

**Beginner's guides with ready-to-paste AI prompts** (start here): [How to build with AI](guides/HOW_TO_BUILD_WITH_AI.md) · [Frontend](guides/FRONTEND_GUIDE.md) · [Backend](guides/BACKEND_GUIDE.md) · [AI agent](guides/AI_GUIDE.md)

| Person | Role | Branch | Owns (only you edit these) |
|---|---|---|---|
| **A** | Frontend | `feature/frontend` | `frontend/` |
| **B** | Backend | `feature/backend` | `backend/app/`, `backend/tests/api/`, `backend/requirements.txt`, `scripts/seed_db.py` |
| **C** | AI agent | `feature/ai` | `backend/foundit_ai/`, `backend/tests/ai/`, `backend/requirements-ai.txt`, `scripts/spike_model.py`, `scripts/eval_matching.py`, `sample_data/demo_reports.json`, `sample_data/photos/` |

**Shared files** (on `main`; change only after telling the other two):
`docs/API.md`, `docs/TEAM.md`, `sample_data/mock_*.json`, `.gitignore`, `.env.example`, `pytest.ini`, `README.md`.

---

## How the three parts connect

```
 Browser (A)  ──HTTP, docs/API.md──▶  FastAPI + SQLite (B)  ──Python call──▶  foundit_ai (C)  ──▶  Groq (gpt-oss-120b)
```

- **A ↔ B:** HTTP + JSON exactly as in `docs/API.md`. Until B is ready, A uses `sample_data/mock_*.json`.
- **B ↔ C:** two Python functions. Until C is merged, B returns `sample_data/mock_matches.json` from `/matches`.

```python
# backend/foundit_ai/agent.py   (C provides, B calls)
from foundit_ai.schemas import ReportRecord, AIAttributes, MatchRun

def extract_attributes(report: ReportRecord, photo_path: str | None = None) -> AIAttributes:
    """Call once when a report is created. Store the result as JSON in the report row.
    Never raises because of the AI: on failure returns extraction_status='failed'."""

def find_matches(query: ReportRecord, pool: list[ReportRecord], *, limit: int = 5) -> MatchRun:
    """Call for POST /reports/{id}/matches. `pool` = all other reports.
    Never raises because of the AI: on failure returns degraded=True with rule-based results."""
```

B's job around `find_matches`: load reports from the DB as `ReportRecord`s, call it, save
each candidate as a `matches` row (this creates `match_id`, `feedback_status="pending"`),
and return the API shape.

---

## A — Frontend (React + Vite) · `frontend/`

Priority order. Ship each step working before starting the next.

- [ ] **1.** `npm create vite@latest frontend -- --template react`; runs on `http://localhost:5173`.
- [ ] **2.** `src/api.js`: one function per endpoint. A `USE_MOCKS` switch returns the mock JSON files; otherwise calls `import.meta.env.VITE_API_URL` (default `http://localhost:8000`).
- [ ] **3.** Landing section: what FoundIt does in 2–3 sentences + "Report lost" / "Report found" buttons.
- [ ] **4.** Report form: lost/found toggle, description (required), category select, color, location, date-time, private details (explain: *"only used to verify ownership, never shown"*), optional photo. Client-side validation messages.
- [ ] **5.** Reports list: cards, filter by lost/found.
- [ ] **6.** Matches view for a report — the most important screen for judges:
  - candidate card with **assessment badge** (likely / possible / unlikely / not enough info)
  - `ranking_score` as a bar + the 5-row `score_breakdown` (label it "ranking score", **not** "% match")
  - **green** matching evidence, **red** conflicting evidence, side by side "your report" vs "their report"
  - `[private detail withheld]` styled as a lock badge
  - missing information list and `next_step`
  - yellow banner when `degraded: true`
- [ ] **7.** Confirm / Reject / Not sure buttons → `POST /matches/{id}/feedback`.
- [ ] **8.** Loading (matching takes ~5 s: show "AI is comparing reports…"), empty, and error states. Mobile-friendly layout.
- [ ] **9.** Switch `USE_MOCKS` off and test against B's real backend.

**Done when:** a judge can submit a report, click "Find matches", understand *why* each result is shown, and confirm one.

---

## B — Backend (FastAPI + SQLite) · `backend/app/`

- [ ] **1.** `backend/app/main.py`: FastAPI app, CORS for `http://localhost:5173`, `GET /health`. Run: `uvicorn app.main:app --reload --app-dir backend`.
- [ ] **2.** SQLite (stdlib `sqlite3` or SQLModel), file `backend/foundit.db` (git-ignored). Tables: `reports` (all fields in API.md + `private_details`, `contact`, `photo_path`, `ai_attributes_json`, `status`, `created_at`) and `matches` (`id`, `report_id`, `candidate_report_id`, `result_json`, `feedback_status`, `note`, `updated_at`).
- [ ] **3.** `POST /reports`, `GET /reports`, `GET /reports/{id}` with validation from API.md. **Never return `contact` or `private_details`.**
- [ ] **4.** Error format from API.md (custom handler so 422s look like `{"error": {...}}`).
- [ ] **5.** `POST /reports/{id}/matches` returning `sample_data/mock_matches.json` (temporary), and `GET /reports/{id}/matches`.
- [ ] **6.** `POST /matches/{id}/feedback`; `confirmed` sets both reports to `matched`.
- [ ] **7.** `scripts/seed_db.py`: loads `sample_data/demo_reports.json` (C provides) into a fresh DB.
- [ ] **8.** After C merges: call `extract_attributes` in `POST /reports`, `find_matches` in `/matches`.
- [ ] **9.** Photo upload/serve (`POST/GET /reports/{id}/photo`): JPEG/PNG/WebP, ≤ 5 MB, server-generated UUID filename in `backend/uploads/` (git-ignored). Lower priority.
- [ ] **10.** Tests in `backend/tests/api/` with FastAPI `TestClient` (create, validate, list hides private fields, feedback).

`backend/requirements.txt` should start with `-r requirements-ai.txt` so C's dependencies are included.

**Done when:** every endpoint in API.md works with `curl`, and data survives a server restart.

---

## C — AI agent · `backend/foundit_ai/`

- [x] **1.** `schemas.py` + `scoring.py` (deterministic: time check, grounding, privacy, points, caps) + tests.
- [ ] **2.** `retrieve.py`: cheap candidate search (opposite type, compatible category, word similarity) → top 5. No model call.
- [ ] **3.** `llm_client.py`: Groq client, timeout, fallback `gpt-oss-120b` → `gpt-oss-20b`, never crashes the caller.
- [ ] **4.** `compare.py`: one model call compares the query with all candidates (strict JSON schema), including private-detail vs private-detail.
- [ ] **5.** `extract.py`: normalise a report into `AIAttributes` at submit time.
- [ ] **6.** `agent.py`: `find_matches` + `extract_attributes` (interface above), degraded fallback. Tests with a fake model client (offline).
- [ ] **7.** `sample_data/demo_reports.json`: ~15 campus reports covering the hard cases (synonyms, look-alike decoys, wrong location, missing dates/colors, one report much richer than the other).
- [ ] **8.** `scripts/eval_matching.py`: runs the demo set against the live model, prints which expected pairs were found.
- [ ] **9.** Vision: test `qwen/qwen3.8-27b` on a **real** photo; add photo attributes only if it is reliable.
- [ ] **10.** README section: model, why it qualifies (gpt-oss-120b, Apache 2.0), how the agent works, limitations.

**Done when:** `find_matches` on the demo set ranks the true matches first, flags the decoys, and still answers when the API key is removed.

---

## Integration checkpoints

| When | Checkpoint |
|---|---|
| Start | Everyone has cloned `main`, read `docs/API.md`, created their branch |
| +2 h | B's backend runs with mock `/matches`; A's UI shows mock data |
| +3 h | **Merge 1:** A's UI talks to B's real backend (reports CRUD) |
| +5 h | **Merge 2:** C's `foundit_ai` merged; B wires in `find_matches` |
| +6 h | Full flow works end to end on the demo dataset |
| +7 h | **Feature freeze.** Only bug fixes, README, demo rehearsal, backup recording |

---

## Git rules

1. Work **only on your branch**. Commit small and often: `git add <your files>` (avoid `git add .` until you've checked `git status`).
2. Merge into `main` through a **Pull Request**; one teammate glances at it before merging.
3. Before a PR: `git pull origin main` into your branch and make sure tests pass.
4. **Never commit `.env`**. Each person creates their own `.env` from `.env.example` with their own Groq key.
5. No `git push --force`, no rewriting `main`.
6. Need a change in someone else's files or in a shared file? Ask them in chat first.

### Commit message style

`feat(ai): add candidate retrieval` · `feat(api): add feedback endpoint` · `feat(ui): matches view` · `fix(...)` · `docs: ...` · `test(...)`
