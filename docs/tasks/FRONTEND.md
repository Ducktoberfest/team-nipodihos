# Frontend tasks — Person A

**Branch:** `feature/frontend` · **Your folder:** `frontend/` (don't edit anything else)
**Contract:** [`docs/API.md`](../API.md) · **Fake data until the backend is ready:** `sample_data/mock_*.json`

**Goal:** a judge who has never seen FoundIt can submit a report, click *Find matches*,
understand **why** each match was suggested, and confirm or reject it.

---

## 0. Setup (15 min)

Needs Node 18+ (`node --version`).

```bash
git switch feature/frontend
npm create vite@latest frontend -- --template react
cd frontend
npm install
npm run dev
```
Open http://localhost:5173 → you should see the Vite page.

Copy the mock data into your app (keep these copies in sync if `sample_data/` changes):
```bash
mkdir -p src/mocks
cp ../sample_data/mock_*.json src/mocks/
```

First commit: `feat(ui): scaffold Vite React app`.

---

## Suggested structure (no router needed — one `page` state in App.jsx)

```
frontend/src/
  api.js                  ← ALL network calls live here (mock switch)
  App.jsx                 ← page state: "home" | "new" | "list" | "matches"
  index.css               ← plain CSS is fine
  mocks/                  ← copied JSON
  components/
    Landing.jsx
    ReportForm.jsx
    ReportList.jsx
    MatchesView.jsx
    MatchCard.jsx
    AssessmentBadge.jsx
    ScoreBreakdown.jsx
    EvidenceList.jsx
    FeedbackButtons.jsx
```

---

## 1. `api.js` with a mock switch (30 min)

Every component calls these functions, never `fetch` directly. Then switching from mock
to real backend is a one-line change.

```js
import mockReports from "./mocks/mock_reports.json";
import mockMatches from "./mocks/mock_matches.json";

const USE_MOCKS = true;   // set false when the backend is running
const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

async function request(path, options = {}) {
  const res = await fetch(BASE + path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const body = await res.json().catch(() => null);
  if (!res.ok) throw new Error(body?.error?.message ?? `Request failed (${res.status})`);
  return body;
}

export async function listReports(type) { /* GET /reports?type=... */ }
export async function createReport(data) { /* POST /reports */ }
export async function findMatches(reportId) { /* POST /reports/{id}/matches */ }
export async function getMatches(reportId) { /* GET /reports/{id}/matches */ }
export async function sendFeedback(matchId, status, note) { /* POST /matches/{id}/feedback */ }
```
In mock mode, `await wait(1500)` before returning mock data so you can see loading states.

✅ **Check:** `console.log(await listReports())` prints 6 reports.

---

## 2. Landing (20 min)

Headline + 2–3 sentences: *"Lost something on campus? FoundIt's AI compares your
description with found items, even when people describe them differently, and explains
every suggestion."* Buttons: **I lost something** / **I found something** / **Browse reports**.

---

## 3. Report form (60 min)

Fields (see API.md §2): type (lost/found toggle), **description (required, 10–2000 chars)**,
category (select from the `Category` list), color, location, date & time
(`<input type="datetime-local">` → convert to ISO UTC), private details, contact.

- Under private details write: *"Only used by the AI to verify ownership. Never shown to anyone."*
- Show validation messages next to fields; disable submit while sending.
- On success → go to the matches page for the new report.
- On error → show `error.message` (the backend sends `{"error": {"message": ...}}`).

✅ **Check:** submitting with a 5-character description shows an error without calling the API.

---

## 4. Reports list (30 min)

Cards with type badge (lost = orange, found = green), description, category, color,
location, date. Filter buttons: All / Lost / Found. Button **Find matches** on each card.
Empty state: *"No reports yet."*

---

## 5. Matches view — the screen judges will remember (2 h)

Top: the report you're matching (short summary) + **Find matches** button.
While loading (real AI takes ~5 s): *"AI is comparing reports…"* spinner.

For each candidate (`MatchCard`), use `sample_data/mock_matches.json`:

| Element | Field | How to show it |
|---|---|---|
| Badge | `assessment` | likely_match = green "Likely match", possible_match = amber "Possible match", unlikely_match = grey "Unlikely", insufficient_information = blue "Not enough info" |
| Score | `ranking_score` + `score_breakdown` | horizontal bar 0–100 labelled **"Ranking score"** (never "% match" or "probability"); below it 5 small rows: category 30/30 ✓, color 20/20 ✓, time 0/15 ✗ … |
| Their report | `candidate` | description, color, location, date; photo if `photo_url` |
| Why it matches | `matching_evidence` | **green** list: `this_report` ↔ `candidate` + `note` |
| Why it might not | `conflicting_evidence` | **red** list, same layout |
| Hidden detail | candidate == `"[private detail withheld]"` | 🔒 lock badge "Private detail — describe it to the finder" |
| Still unknown | `missing_information` | grey bullet list |
| What to do | `next_step` | highlighted box |
| AI offline | `degraded: true` | yellow banner with `degraded_reason` at the top |
| Nothing found | `candidates: []` | *"No similar reports yet. We'll keep your report open."* |

Small footer note: *"Suggestions are not proof. Always verify before handing over an item."*

---

## 6. Feedback buttons (30 min)

**Confirm** / **Not mine** / **Not sure** → `sendFeedback(match_id, "confirmed" | "rejected" | "uncertain")`.
Afterwards show the chosen status on the card and disable the buttons.

---

## 7. States & polish (45 min)

- Loading, empty, error states on every page.
- Works at phone width (single column).
- Keep animations minimal.

---

## 8. Switch to the real backend (when Person B says it's ready)

Set `USE_MOCKS = false`, run the backend (`uvicorn app.main:app --reload --app-dir backend`
from the repo root), and click through everything. Report any mismatch with API.md to B.

---

## Rules
- Commit after every numbered step (`feat(ui): report form`, …) and `git push`.
- Never change field names — if something in API.md is unclear or wrong, ask the team.
- Before committing: `git status` → only files in `frontend/`. `node_modules/` is ignored.
