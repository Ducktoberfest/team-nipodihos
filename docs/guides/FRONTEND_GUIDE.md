# Frontend beginner's guide — Person A

Branch `feature/frontend` · Folder `frontend/` · Detailed spec: [`docs/tasks/FRONTEND.md`](../tasks/FRONTEND.md)
· Contract: [`docs/API.md`](../API.md) · First read: [How to build with AI](HOW_TO_BUILD_WITH_AI.md)

---

## Big picture (read first)

FoundIt = a website where people report lost or found items, and an AI suggests which
reports describe the same item and **explains why**. Your job is everything the user sees.

```
Your React app (browser)  ──HTTP requests──▶  Backend (Person B)  ──▶  AI (Person C)
```

You don't need the backend to start: `sample_data/mock_*.json` contain **fake responses
that look exactly like the real ones**. You build with those, then flip one switch.

### Concepts you need

| Concept | Plain explanation |
|---|---|
| **React** | A library for building a page out of small reusable pieces called **components**. |
| **Component** | A JavaScript function that returns what to show (JSX, looks like HTML). `<MatchCard />` is a component. |
| **Props** | Inputs you pass to a component: `<AssessmentBadge value="likely_match" />`. |
| **State (`useState`)** | Data a component remembers that can change — e.g. form fields, "is loading". Changing state re-draws the screen. |
| **Effect (`useEffect`)** | Code that runs after drawing, e.g. "load the reports when this page opens". |
| **fetch / async / await** | How the browser asks the backend for data. `await` waits for the answer. |
| **JSON** | The text format the backend and frontend exchange: `{"id": 1, "type": "lost"}`. |
| **Vite** | The tool that runs your app locally at `http://localhost:5173` and reloads when you save. |
| **Mock** | Fake data used until the real thing exists. |

---

## Context Prompt — paste at the start of EVERY new AI chat

```
I'm a beginner building the FRONTEND of "FoundIt", a one-day hackathon project.

FoundIt: people submit lost or found item reports; an AI (open-weight model) suggests which
reports describe the same item and explains the evidence for and against each suggestion.

My role: frontend only, React + Vite (plain JavaScript, no TypeScript), plain CSS.
My folder: frontend/. I must NOT edit anything outside frontend/.
The API contract is docs/API.md — field names, endpoints and shapes are FIXED; never rename
or invent fields. Until the backend is ready I use mock JSON copied from sample_data/ into
frontend/src/mocks/. All network calls go through frontend/src/api.js.
My step-by-step spec is docs/tasks/FRONTEND.md.

Rules for you:
- Work in small steps; only do the step I ask for.
- No new npm packages unless you ask me first and explain why (no router, no UI kit, no Redux).
- Keep components small and readable; explain what each new file does in simple words.
- After the code, tell me exactly how to test it in the browser.
- Use the wording "ranking score", never "% match" or "probability".
Reply "Ready" and wait for my first task.
```
*(Browser-chat users: paste the contents of `docs/API.md` and `docs/tasks/FRONTEND.md` after this.)*

---

## Part 1 — Setup (no AI needed, 15 min)

**What:** create the empty React app and copy the mock data in.

```bash
git switch feature/frontend
git pull
npm create vite@latest frontend -- --template react
cd frontend
npm install
mkdir -p src/mocks
cp ../sample_data/mock_*.json src/mocks/
npm run dev
```
**Check:** http://localhost:5173 shows the Vite welcome page.
**Commit:** `feat(ui): scaffold Vite React app with mock data`

---

## Part 2 — The API layer (`api.js`, 30 min)

**What:** one file with a function per backend endpoint. It returns mock data now and real
data later — the rest of the app never knows the difference.
**Concepts:** `async` functions, `fetch`, error handling, why a single switch (`USE_MOCKS`) makes integration painless.

**Prompt:**
```
Task: create frontend/src/api.js as described in step 1 of docs/tasks/FRONTEND.md.
Functions: listReports(type), getReport(id), createReport(data), findMatches(reportId),
getMatches(reportId), sendFeedback(matchId, status, note).
- USE_MOCKS = true at the top. In mock mode, wait 800–1500 ms, then return data from
  src/mocks/*.json (createReport returns a fake report with a new id; sendFeedback returns
  {match_id, feedback_status, updated_at}). Keep created reports in a module-level array so
  they appear in listReports during the session.
- Real mode: fetch from import.meta.env.VITE_API_URL (default http://localhost:8000) using the
  paths in docs/API.md. If the response is not ok, throw an Error with body.error.message.
Explain how USE_MOCKS works and how I'll switch to the real backend later.
```
**Check:** in `App.jsx` temporarily add `listReports().then(console.log)` → browser console (F12) shows 6 reports.
**Commit:** `feat(ui): add API client with mock mode`

---

## Part 3 — App shell + landing page (40 min)

**What:** the frame of the app: a header with navigation and a landing section explaining FoundIt.
**Concepts:** a `page` state in `App.jsx` decides which component is shown (simple navigation without a router).

**Prompt:**
```
Task: build the app shell (step 2 of docs/tasks/FRONTEND.md).
- App.jsx keeps state: page ("home" | "new" | "list" | "matches"), plus selectedReportId
  and newReportType ("lost" | "found").
- Header: "FoundIt" logo text + links Home / Report an item / Browse reports.
- components/Landing.jsx: headline, 2–3 sentences explaining FoundIt for non-technical
  people, a 3-step "how it works" row (Describe it → AI compares → Verify and recover), and
  buttons "I lost something", "I found something", "Browse reports".
- Clean modern look in index.css: system font, max-width container, soft shadows, rounded
  cards, one accent color; must look fine at 375px phone width. No animations.
Replace the Vite demo content completely.
```
**Check:** buttons switch between pages (other pages can show a placeholder for now).
**Commit:** `feat(ui): app shell and landing page`

---

## Part 4 — Report form (60 min)

**What:** the form to submit a lost or found report.
**Concepts:** *controlled inputs* (each field's value lives in state), validation before
sending, disabling the button while sending, showing server errors.

**Prompt:**
```
Task: build components/ReportForm.jsx (step 3 of docs/tasks/FRONTEND.md, fields from
"POST /reports" in docs/API.md).
- Props: initialType, onCreated(report).
- Lost/Found toggle at the top. Fields: description (textarea, required, 10–2000 chars,
  live character count), category (<select> with the Category values from API.md, plus an
  empty "Not sure" option), color, location, when (datetime-local, optional, not in the
  future), private details (textarea) with the hint "Only used by the AI to verify ownership.
  Never shown to anyone.", contact (optional).
- Validate on submit; show messages under fields. Convert datetime-local to an ISO UTC
  string. Send null for empty optional fields.
- While sending: disable the button and show "Submitting…". On error show the message.
- On success call onCreated(report); App then opens the matches page for that report.
```
**Check:** a 5-character description shows an error and nothing is sent; a valid report opens the matches page.
**Commit:** `feat(ui): report submission form with validation`

---

## Part 5 — Reports list (30 min)

**What:** browse all reports, filter lost/found, open matches for one.
**Concepts:** `useEffect` to load data when the page opens; rendering a list with `.map()` and a `key`.

**Prompt:**
```
Task: build components/ReportList.jsx (step 4 of docs/tasks/FRONTEND.md).
- On mount call listReports(filter). Filter buttons: All / Lost / Found.
- Card per report: type badge (lost = orange, found = green), description, then small
  muted lines for category, color, location, date (formatted nicely; show "—" when null),
  a small "📷 photo" marker if has_photo, and a "Find matches" button → onOpenMatches(id).
- Loading state, empty state ("No reports yet."), error state with a Retry button.
```
**Check:** 6 mock reports appear; filters work; "Find matches" opens the matches page.
**Commit:** `feat(ui): reports list with filter`

---

## Part 6 — Matches view (the most important screen, 2 h, two prompts)

**What:** the AI's ranked suggestions with clear evidence. Judges decide here whether the AI is real.
**Concepts:** splitting a big screen into small components; mapping data values to colors/labels.
Open `sample_data/mock_matches.json` and look at one candidate before starting.

**Prompt 6a — structure:**
```
Task: build the matches page (step 5 of docs/tasks/FRONTEND.md, response shape in
"POST /reports/{report_id}/matches" in docs/API.md and sample_data/mock_matches.json).
- components/MatchesView.jsx: props reportId. Shows a short summary of the report
  (getReport), a "Find matches" button calling findMatches(reportId), and on open loads
  getMatches(reportId) to show previous results.
- While matching: spinner + "AI is comparing reports… (this takes a few seconds)".
- If degraded is true: yellow banner with degraded_reason.
- If candidates is empty: "No similar reports yet. We'll keep your report open."
- Render one components/MatchCard.jsx per candidate (just description + assessment text for now).
- Footer note: "Suggestions are not proof. Always verify before handing over an item."
```

**Prompt 6b — the card:**
```
Task: complete MatchCard.jsx using small components:
- AssessmentBadge.jsx: likely_match → green "Likely match", possible_match → amber
  "Possible match", unlikely_match → grey "Unlikely", insufficient_information → blue
  "Not enough info".
- ScoreBreakdown.jsx: a horizontal bar for ranking_score (0–100) labelled "Ranking score",
  with a tooltip/hint "Points from matching details — not a probability". Below: one row per
  score_breakdown item: attribute name, points/max, and an icon for result
  (agree ✓ green, partial ~ amber, conflict ✗ red, unknown ? grey).
- The candidate's public report: description, color, location, date, photo if photo_url.
- EvidenceList.jsx used twice: "Why it may match" (matching_evidence, green) and "Why it may
  not" (conflicting_evidence, red). Each item: attribute label, "Your report: <this_report>"
  ↔ "Their report: <candidate>", and the note in small text. If candidate equals
  "[private detail withheld]" show a 🔒 badge "Private detail — describe it to the finder".
- "Still unknown": missing_information as a grey list (hide if empty).
- next_step in a highlighted box.
Keep each component under ~60 lines.
```
**Check:** with the mock, you see 3 cards: green "Likely" (93), blue "Not enough info" (30), grey "Unlikely" (40) with red reasons including "found the day BEFORE". Set `degraded` mock → yellow banner.
**Commit:** `feat(ui): matches view with evidence and ranking score`

---

## Part 7 — Feedback buttons (30 min)

**What:** the user confirms or rejects a suggestion.
**Prompt:**
```
Task: add components/FeedbackButtons.jsx to MatchCard (step 6 of docs/tasks/FRONTEND.md).
Buttons "Confirm — it's mine", "Not mine", "Not sure" call sendFeedback(match_id,
"confirmed" | "rejected" | "uncertain"). While sending disable buttons. After success show
the chosen status as a badge and hide the buttons. If feedback_status is already not
"pending" when the card loads, show the badge instead of buttons. Before confirming, show a
small confirm dialog: "Only confirm after verifying a private detail with the finder."
```
**Check:** clicking "Not mine" shows the status badge; reload keeps working with mocks.
**Commit:** `feat(ui): match feedback actions`

---

## Part 8 — Polish (45 min)

**Prompt:**
```
Review all components for: loading, empty and error states on every page; layout at 375px
width (single column, no horizontal scroll); readable contrast; consistent spacing; buttons
disabled while requests run. List the problems you find first, then fix them one file at a time.
```
**Commit:** `fix(ui): states and responsive polish`

---

## Part 9 — Connect to the real backend (when Person B says "ready")

```bash
# from the repo root, in a second terminal (Person B's instructions):
uvicorn app.main:app --reload --app-dir backend
```
Set `USE_MOCKS = false` in `api.js` and click through every page.
If the browser console says **CORS error**: tell Person B (their CORS setting must allow `http://localhost:5173`).
If a field shows `undefined`: compare the real response (F12 → Network tab) with `docs/API.md` and tell Person B which field differs.
**Commit:** `feat(ui): connect to real backend`

---

## Questions judges may ask you (be ready)
1. How does the frontend talk to the backend? *(api.js, fetch, JSON contract in API.md)*
2. How did you work before the backend existed? *(mock JSON with the same shape)*
3. Why "ranking score" and not "% match"? *(it's a points sum, not a calibrated probability)*
4. Why are some details shown as 🔒? *(the finder's private detail is never revealed — the owner must describe it to prove ownership)*
5. What happens if the AI is down? *(yellow banner — backend returns rule-based results with `degraded: true`)*
