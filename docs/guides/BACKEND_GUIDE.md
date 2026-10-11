# Backend beginner's guide — Person B

Branch `feature/backend` · Folders `backend/app/`, `backend/tests/api/` · Detailed spec:
[`docs/tasks/BACKEND.md`](../tasks/BACKEND.md) · Contract: [`docs/API.md`](../API.md)
· First read: [How to build with AI](HOW_TO_BUILD_WITH_AI.md)

---

## Big picture (read first)

You build the **server**: it receives requests from the website, stores reports in a
database, and asks the AI module for matches.

```
Frontend (Person A) ──HTTP/JSON──▶  YOUR FastAPI app  ──▶  SQLite file (foundit.db)
                                         │
                                         └─Python call──▶  foundit_ai (Person C)
```

You don't need the AI to start: `/matches` returns `sample_data/mock_matches.json` until
Person C merges their module. Then you replace one line with a real function call.

### Concepts you need

| Concept | Plain explanation |
|---|---|
| **HTTP request** | A message from the browser: a **method** (GET = read, POST = create/do) + a **path** (`/reports/1`) + optional JSON body. |
| **Endpoint** | One method+path your server answers, e.g. `POST /reports`. |
| **Status code** | Number in the reply: 200 OK, 201 Created, 404 Not found, 422 Invalid input, 500 Server error. |
| **FastAPI** | Python framework: you write a function, add `@app.post("/reports")` above it, and it becomes an endpoint. It also generates a test page at `/docs`. |
| **Pydantic model** | A Python class describing the shape of data. FastAPI uses it to **validate** input automatically and to **control what goes out** (if a field isn't in the response model, it can't leak). |
| **SQLite** | A database stored in one file. No server to install; Python has `sqlite3` built in. |
| **SQL** | The language to talk to the database: `INSERT`, `SELECT`, `UPDATE`. |
| **CORS** | Browser security: the website (port 5173) may only call your API (port 8000) if your API says it's allowed. |
| **Environment variable** | A setting outside the code (like the Groq key in `.env`) so secrets never go into Git. |
| **TestClient** | Lets tests call your endpoints without starting a real server. |

---

## Context Prompt — paste at the start of EVERY new AI chat

```
I'm a beginner building the BACKEND of "FoundIt", a one-day hackathon project.

FoundIt: people submit lost or found item reports; an AI module suggests which reports
describe the same item and explains the evidence. Frontend is React (teammate), the AI
module backend/foundit_ai/ is written by another teammate.

My role: backend API with Python 3.11+, FastAPI, Pydantic v2, and the standard-library
sqlite3 module (no ORM). My files: backend/app/, backend/tests/api/, backend/requirements.txt,
scripts/seed_db.py. I must NOT edit backend/foundit_ai/ or frontend/.
The API contract is docs/API.md — endpoints, field names, status codes and the error format
are FIXED; never rename or invent fields. My step-by-step spec is docs/tasks/BACKEND.md.

Hard rules:
- `contact` and `private_details` are stored but NEVER returned by any endpoint. Use separate
  Pydantic models for input and output so leaking is impossible.
- Use parameterized SQL queries (?) only — never build SQL with f-strings.
- DB path from env var FOUNDIT_DB_PATH (default backend/foundit.db).
- The app runs from the repo root with: uvicorn app.main:app --reload --app-dir backend

Rules for you: small steps, only the step I ask for; no new dependencies without asking;
explain what each part does in simple words; after the code tell me how to test it with
curl or the /docs page.
Reply "Ready" and wait for my first task.
```
*(Browser-chat users: paste `docs/API.md` and `docs/tasks/BACKEND.md` after this.)*

---

## Part 1 — Setup (no AI needed, 15 min)

```bash
git switch feature/backend
git pull
python -m venv .venv
.venv\Scripts\activate                 # macOS/Linux: source .venv/bin/activate
pip install "fastapi[standard]" python-multipart pytest
```
Create `backend/requirements.txt` with the lines from step 0 of `docs/tasks/BACKEND.md`.
**Commit:** `chore(api): add backend requirements`

---

## Part 2 — App skeleton + health check (20 min)

**What:** the smallest working server.
**Concepts:** what `uvicorn` is (the program that runs your app), what a decorator `@app.get` does, CORS.

**Prompt:**
```
Task: step 1 of docs/tasks/BACKEND.md. Create backend/app/__init__.py (empty) and
backend/app/main.py with a FastAPI app titled "FoundIt API", CORS allowing
http://localhost:5173, and GET /health returning {"status": "ok", "ai_available": false}.
Explain each line.
```
**Check:** run `uvicorn app.main:app --reload --app-dir backend`, open http://localhost:8000/health and http://localhost:8000/docs.
**Commit:** `feat(api): app skeleton with health check`

---

## Part 3 — Database layer (45 min)

**What:** `db.py` creates the tables and holds all SQL in one place.
**Concepts:** tables and columns, primary key, `UNIQUE`, why parameterized queries prevent **SQL injection**, why we store JSON text in some columns.

**Prompt:**
```
Task: step 2 of docs/tasks/BACKEND.md. Create backend/app/db.py using sqlite3:
- get_connection(): opens FOUNDIT_DB_PATH (default backend/foundit.db), row_factory =
  sqlite3.Row, foreign keys on.
- init_db(): creates the three tables exactly as written in docs/tasks/BACKEND.md
  (reports, match_runs, matches).
- Small functions: insert_report(data) -> id, get_report(id) -> row | None,
  list_reports(type, status, limit) -> rows newest first.
Call init_db() on app startup in main.py (lifespan). Use only parameterized queries.
Explain SQL injection and how "?" placeholders prevent it.
```
**Check:** start the server → a `backend/foundit.db` file appears. `git status` must NOT show it (it's ignored).
**Commit:** `feat(api): sqlite database layer`

---

## Part 4 — Pydantic models (30 min)

**What:** `models.py` — the data shapes from API.md.
**Concepts:** input model vs output model; `Literal` for allowed values; `Field(min_length=…)`; validators.

**Prompt:**
```
Task: create backend/app/models.py with Pydantic v2 models matching docs/API.md exactly:
ReportCreate (input, with all validation rules from the POST /reports table: description
trimmed 10–2000 chars, length limits, occurred_at not in the future, category from the
Category list), AIAttributesOut, ReportOut (public view: NO contact, NO private_details, has
has_private_details and photo_url), ReportList, FeedbackIn, FeedbackOut.
Also write a function row_to_report_out(row) that builds ReportOut from a DB row (parse
ai_attributes_json; if NULL use extraction_status "pending").
Explain why separate input and output models make leaking private fields impossible.
```
**Commit:** `feat(api): request and response models`

---

## Part 5 — Reports endpoints (1 h)

**What:** create, list and get reports.
**Prompt:**
```
Task: step 3 of docs/tasks/BACKEND.md. In main.py add POST /reports (201, returns
ReportOut), GET /reports (query params type, status, limit default 50 max 200; returns
{"items": [...], "total": n}), GET /reports/{report_id} (404 if missing). Use db.py and
models.py. Set created_at to the current UTC time in ISO format with "Z".
Then show me 3 curl commands to test them (Windows-friendly: use curl.exe and escape quotes,
or tell me to use the /docs page).
```
**Check:** in `/docs`, create a report with `contact` filled → `GET /reports/{id}` does **not** show `contact` or `private_details`.
**Commit:** `feat(api): reports endpoints`

---

## Part 6 — Error format (20 min)

**What:** every error has the same shape so the frontend can show `error.message`.
**Prompt:**
```
Task: step 4 of docs/tasks/BACKEND.md. Add exception handlers so all errors match the
"Errors" section of docs/API.md: RequestValidationError → 422 validation_error with
details [{field, issue}]; 404 → not_found; any unexpected Exception → 500 internal_error
with a generic message (log the real error with the logging module, never return a stack trace).
```
**Check:** `POST /reports` with `"description": "hi"` → 422 with `{"error": {"code": "validation_error", ...}}`.
**Commit:** `feat(api): consistent error responses`

---

## Part 7 — Matches endpoints with mock data (40 min)

**What:** unblocks the frontend before the AI is ready.
**Prompt:**
```
Task: step 5 of docs/tasks/BACKEND.md. Add POST /reports/{report_id}/matches (body
optional {"limit": 1..10, default 5}) and GET /reports/{report_id}/matches. For now both
return sample_data/mock_matches.json (path relative to the repo root via
Path(__file__).resolve().parents[2]) with report_id replaced by the real id; 404 if the
report doesn't exist. Put the mock loading in one function load_mock_matches(report_id) so
it's easy to replace later.
```
**Check:** create a report, POST its `/matches` → mock JSON with your id.
**Tell Person A:** "reports + mock matches are live" so they can switch off mocks.
**Commit:** `feat(api): matches endpoints (mock)`

---

## Part 8 — Feedback (30 min)

**Prompt:**
```
Task: step 6 of docs/tasks/BACKEND.md. POST /matches/{match_id}/feedback with FeedbackIn
{status: confirmed|rejected|uncertain, note optional ≤500}. Update the matches row
(feedback_status, note, updated_at). If confirmed, set status='matched' on both the report
and the candidate report. Return FeedbackOut. 404 not_found if the match doesn't exist.
Since matches are still mocked, also make POST /matches create rows in the matches table
for each mock candidate (upsert on report_id+candidate_report_id, keeping existing
feedback_status) and use the real row id as match_id in the response.
```
**Commit:** `feat(api): match feedback endpoint`

---

## Part 9 — Seed script (20 min)

**Prompt:**
```
Task: step 7 of docs/tasks/BACKEND.md. Create scripts/seed_db.py: delete the DB file,
init_db(), insert every report from sample_data/demo_reports.json if it exists, otherwise
from sample_data/mock_reports.json (fields that are missing become NULL). Print how many
reports were inserted. It must run from the repo root: python scripts/seed_db.py
```
**Commit:** `feat(api): demo seed script`

---

## Part 10 — Tests (30 min)

**Concepts:** a test is code that checks your code; `tmp_path` gives each test a fresh temporary DB.
**Prompt:**
```
Task: step 10 of docs/tasks/BACKEND.md. Write backend/tests/api/test_reports.py with
FastAPI TestClient, using monkeypatch.setenv("FOUNDIT_DB_PATH", tmp file) so each test gets
a fresh DB. Tests: create → 201; short description → 422 in our error format; list and get
never contain "contact" or "private_details"; unknown report → 404 not_found; feedback
confirmed sets both reports to matched; unknown match → 404. Explain each test in one line.
```
**Check:** `python -m pytest` from the repo root → all green.
**Commit:** `test(api): reports and feedback tests`

---

## Part 11 — Plug in the real AI (after Person C merges, 45 min)

```bash
git pull origin main        # brings backend/foundit_ai/
pip install -r backend/requirements.txt
```
Create your own `.env` from `.env.example` with your own Groq key (console.groq.com/keys).

**Prompt:**
```
Task: step 8 of docs/tasks/BACKEND.md. Person C's module provides
foundit_ai.agent.extract_attributes(report: ReportRecord) -> AIAttributes and
foundit_ai.agent.find_matches(query: ReportRecord, pool: list[ReportRecord], limit) -> MatchRun
(see backend/foundit_ai/schemas.py — read it, don't edit it).
1. Write row_to_record(row) -> ReportRecord.
2. In POST /reports, after inserting, call extract_attributes and save
   result.model_dump_json() into ai_attributes_json.
3. Replace load_mock_matches in POST /reports/{id}/matches with find_matches(query, all other
   reports), upsert matches rows (keep existing feedback_status), save run JSON in
   match_runs, and return the run with match_id + feedback_status added per candidate.
4. GET /reports/{id}/matches rebuilds that from match_runs + matches; if no run yet return
   generated_at null and empty candidates.
5. /health: ai_available = bool(os.getenv("GROQ_API_KEY")). Load .env with python-dotenv at startup.
```
**Check:** `python scripts/seed_db.py`, start the server, POST matches for the lost backpack → real AI evidence. Remove the key from `.env`, restart → still 200 with `degraded: true`.
**Commit:** `feat(api): integrate AI matching agent`

---

## Part 12 — Photos (optional, only if time allows)

**Prompt:** paste step 9 of `docs/tasks/BACKEND.md` and add: *"Explain what a path traversal attack is and how a UUID filename prevents it."*
**Commit:** `feat(api): photo upload`

---

## Questions judges may ask you
1. How do you make sure private details never leak? *(separate output models without those fields + tests)*
2. Why SQLite? *(zero setup, one file, enough for a one-day MVP)*
3. How do you prevent SQL injection? *(parameterized queries)*
4. What happens if the AI service is down? *(the AI module returns `degraded: true` rule-based results; the API still answers 200)*
5. How did the frontend work before your API existed? *(API contract + mock JSON)*
