# Backend tasks — Person B

**Branch:** `feature/backend` · **Your files:** `backend/app/`, `backend/tests/api/`,
`backend/requirements.txt`, `scripts/seed_db.py`
**Don't edit:** `backend/foundit_ai/` (Person C), `frontend/` (Person A)
**Contract:** [`docs/API.md`](../API.md) — every response must match it exactly.

**Goal:** every endpoint in API.md works with `curl`, data survives a restart, and private
fields never leave the server.

---

## 0. Setup (15 min)

Needs Python 3.11+.

```bash
git switch feature/backend
python -m venv .venv
.venv\Scripts\activate          # Windows (macOS/Linux: source .venv/bin/activate)
pip install "fastapi[standard]" python-multipart pytest
```

Create `backend/requirements.txt`:
```
-r requirements-ai.txt
fastapi[standard]>=0.115
python-multipart>=0.0.9
pytest>=8
```
(`requirements-ai.txt` comes from Person C. Until it's merged, install from your file
without that first line.)

Run from the **repo root**:
```bash
uvicorn app.main:app --reload --app-dir backend
```
Docs at http://localhost:8000/docs (FastAPI builds this automatically — great for testing).

---

## Suggested structure

```
backend/
  app/
    __init__.py
    main.py        ← FastAPI app, CORS, routes, error handlers
    db.py          ← sqlite3 connection + table creation + queries
    models.py      ← Pydantic request/response models (from API.md)
  tests/api/
    test_reports.py
scripts/seed_db.py
```
`backend/foundit.db` is created at runtime and is git-ignored (`*.db`).

---

## 1. App skeleton (20 min)

```python
# backend/app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="FoundIt API")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"],
                   allow_methods=["*"], allow_headers=["*"])

@app.get("/health")
def health():
    return {"status": "ok", "ai_available": False}   # True once the AI is wired in
```
✅ **Check:** `curl http://localhost:8000/health`

---

## 2. Database (45 min)

Use the standard library `sqlite3` (no extra install). Create tables at startup:

```sql
CREATE TABLE IF NOT EXISTS reports (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  type TEXT NOT NULL CHECK (type IN ('lost','found')),
  description TEXT NOT NULL,
  category TEXT, color TEXT, location TEXT,
  occurred_at TEXT,                 -- ISO 8601 UTC string or NULL
  private_details TEXT,             -- NEVER returned by the API
  contact TEXT,                     -- NEVER returned by the API
  photo_path TEXT,
  ai_attributes_json TEXT,          -- filled by Person C's extract_attributes()
  status TEXT NOT NULL DEFAULT 'open',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS match_runs (      -- last matching run per report
  report_id INTEGER PRIMARY KEY REFERENCES reports(id),
  run_json TEXT NOT NULL                     -- MatchRun JSON from the AI module
);

CREATE TABLE IF NOT EXISTS matches (         -- one row per (report, candidate) pair
  id INTEGER PRIMARY KEY AUTOINCREMENT,      -- this is match_id
  report_id INTEGER NOT NULL REFERENCES reports(id),
  candidate_report_id INTEGER NOT NULL REFERENCES reports(id),
  feedback_status TEXT NOT NULL DEFAULT 'pending',
  note TEXT,
  updated_at TEXT NOT NULL,
  UNIQUE (report_id, candidate_report_id)
);
```
Let the DB path come from an env var so tests can use a temp file:
`DB_PATH = os.getenv("FOUNDIT_DB_PATH", "backend/foundit.db")`.

---

## 3. Reports endpoints (1 h)

`POST /reports`, `GET /reports`, `GET /reports/{id}` — API.md §2, §4–6.

- Validation: `type` and `description` required; description 10–2000 chars after
  trimming; `occurred_at` not in the future; length limits from the table in API.md.
- **The response model must not have `private_details` or `contact` fields.** Return
  `has_private_details: bool` instead. Use separate Pydantic models for create (input)
  and public view (output) so it's impossible to leak by accident.
- `ai_attributes`: parse `ai_attributes_json`; if NULL return `{"extraction_status": "pending"}`
  with the other fields null/empty.
- `photo_url`: `"/reports/{id}/photo"` if `photo_path` else `null`.

✅ **Check:** create a report with `contact` → `GET /reports/{id}` must not show it.

---

## 4. Error format (20 min)

All errors look like `{"error": {"code": ..., "message": ..., "details": [...]}}`.

```python
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError):
    details = [{"field": ".".join(str(p) for p in e["loc"][1:]), "issue": e["type"]}
               for e in exc.errors()]
    return JSONResponse(status_code=422, content={"error": {
        "code": "validation_error", "message": exc.errors()[0]["msg"], "details": details}})
```
Do the same for 404 (`not_found`) and a catch-all 500 (`internal_error`, no stack trace).

---

## 5. Matches endpoints — mock first (40 min)

`POST /reports/{id}/matches` and `GET /reports/{id}/matches` (API.md §7–8).

**For now:** return `sample_data/mock_matches.json` (replace `report_id` with the real id).
This unblocks Person A immediately.

```python
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
MOCK_MATCHES = ROOT / "sample_data" / "mock_matches.json"
```

---

## 6. Feedback (30 min)

`POST /matches/{match_id}/feedback` with `{"status": "confirmed"|"rejected"|"uncertain", "note"?: str}`.
Update the `matches` row; if `confirmed`, set **both** reports' `status` to `matched`.
Return `{"match_id", "feedback_status", "updated_at"}`. 404 if the match doesn't exist.

---

## 7. Seed script (20 min)

`scripts/seed_db.py`: delete the DB, recreate tables, insert every report from
`sample_data/demo_reports.json` (Person C provides it; until then use `mock_reports.json`).
Must work from a clean clone: `python scripts/seed_db.py`.

---

## 8. Wire in the AI (after Person C merges `feature/ai` into `main`) (45 min)

```bash
git pull origin main          # brings in backend/foundit_ai/
```
```python
from foundit_ai.agent import extract_attributes, find_matches
from foundit_ai.schemas import ReportRecord
```

- **In `POST /reports`:** build a `ReportRecord` from the new row, call
  `extract_attributes(record)`, save `result.model_dump_json()` to `ai_attributes_json`.
  It never raises because of the AI (returns `extraction_status="failed"` instead).
- **In `POST /reports/{id}/matches`:**
  1. Load the report and all other reports as `ReportRecord`s (row → ReportRecord: same
     field names; `ai_attributes = AIAttributes.model_validate_json(row["ai_attributes_json"])`
     if set; `has_photo = photo_path is not None`).
  2. `run = find_matches(query, pool, limit=body.limit)` → a `MatchRun`.
  3. For each candidate: upsert into `matches` on `(report_id, candidate_report_id)` —
     keep an existing `feedback_status`, so a re-run doesn't erase a confirmation.
  4. Save `run.model_dump_json()` in `match_runs`.
  5. Return the run with `match_id` and `feedback_status` added to each candidate.
- **`GET /reports/{id}/matches`:** rebuild the same response from `match_runs` + `matches`.
- `/health`: `ai_available = bool(os.getenv("GROQ_API_KEY"))`.

---

## 9. Photos (only if time allows, 45 min)

`POST /reports/{id}/photo` (multipart field `file`): allow `image/jpeg|png|webp`, max 5 MB,
save as `backend/uploads/<uuid4>.<ext>` (**never use the uploaded filename** — path
traversal risk). `GET /reports/{id}/photo` returns it with `FileResponse`. `uploads/` is git-ignored.

---

## 10. Tests (30 min, then add as you go)

`backend/tests/api/test_reports.py` using `fastapi.testclient.TestClient` and
`monkeypatch.setenv("FOUNDIT_DB_PATH", str(tmp_path / "test.db"))`:
- create report → 201; too-short description → 422 in our error format
- list/get never contain `contact` or `private_details`
- feedback `confirmed` sets both reports to `matched`; unknown match → 404

Run all tests from the repo root: `python -m pytest`.

---

## Rules
- Commit after each numbered step (`feat(api): reports endpoints`, …) and `git push`.
- Tell Person A as soon as step 3 + 5 work so they can switch off mocks.
- Never commit `.env` or `*.db`. Check `git status` before every commit.
