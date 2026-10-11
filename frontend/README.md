# FoundIt — frontend (Person A)

React + Vite, plain JavaScript, plain CSS. No router, no UI kit, no state library.

## Run it

Needs Node 18+ (`.nvmrc` pins 22.23.3 — `nvm use` picks it up).

```bash
npm install
npm run dev     # http://localhost:5173
```

## Mock mode

`src/api.js` has two switches at the top:

| Flag | Default | What it does |
|---|---|---|
| `USE_MOCKS` | `false` | `true` serves `src/mocks/*.json` with an artificial delay instead of calling the backend — use it to work offline when the API is down. |
| `MOCK_DEGRADED` | `false` | In mock mode, returns `mock_matches_degraded.json` so the "AI unavailable" banner can be demoed. |

Reports created while `USE_MOCKS` is on are kept in memory for the session, so a
submitted report shows up in the list and has its own matches page. Feedback is
remembered the same way. Everything resets on reload.

## Running against the backend

The app talks to the real API by default. From the repo root:

```bash
python3.11 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt
.venv/bin/python scripts/seed_db.py
.venv/bin/uvicorn app.main:app --reload --app-dir backend
```

Optional: `VITE_API_URL=http://localhost:8000` in `frontend/.env` (that default is built in).

Without a `GROQ_API_KEY` in the repo-root `.env`, the API answers with `degraded: true`
and the UI shows the yellow "AI unavailable" banner — matching still works on rules alone.

Nothing else changes — every network call goes through `src/api.js`.

## Structure

```
src/
  api.js          every network call + the mock switch
  format.js       category/attribute labels, date formatting, ISO conversion
  App.jsx         page state: "home" | "new" | "list" | "matches"
  index.css       design tokens and all styling
  mocks/          copies of sample_data/mock_*.json
  components/
    Landing.jsx         headline, 3-step explainer, entry buttons
    ReportForm.jsx      lost/found toggle, validation, ISO UTC conversion
    ReportList.jsx      cards + All/Lost/Found filter
    MatchesView.jsx     your report, Find matches, degraded banner, states
    MatchCard.jsx       one candidate, composed from the four below
    AssessmentBadge.jsx assessment → label + colour
    ScoreBreakdown.jsx  ranking score bar + the 5 attribute rows
    EvidenceList.jsx    green matching / red conflicting evidence
    FeedbackButtons.jsx confirm / not mine / not sure
```

## Wording rules

- The number is a **ranking score**, never a "% match" or a "probability".
- A candidate's private detail is never shown — it renders as a 🔒 badge asking
  the user to describe it to the finder.
- Every matches page ends with "Suggestions are not proof."

If the mocks in `sample_data/` change, re-copy them:

```bash
cp ../sample_data/mock_*.json src/mocks/
```
