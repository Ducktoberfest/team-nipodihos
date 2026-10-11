# FoundIt API Contract (v0.1)

This is the agreed contract between **frontend**, **backend**, and **AI**.
Build against it now; the backend can serve the mock files in `sample_data/`
until the real AI matching is wired in.

**Change rule:** any change to a field name, type, or endpoint must be agreed
by all three of us and recorded in the changelog at the bottom.

- Base URL (dev): `http://localhost:8000`
- Frontend dev origin (CORS allow): `http://localhost:5173`
- All bodies are JSON (`Content-Type: application/json`) except photo upload.
- All timestamps are ISO 8601 strings, UTC, e.g. `"2026-10-09T14:00:00Z"`.
- IDs are integers.

---

## Endpoints at a glance

| Method | Path | Purpose |
|---|---|---|
| GET  | `/health` | Is the API up? Is the AI reachable? |
| POST | `/reports` | Create a lost or found report |
| POST | `/reports/{report_id}/photo` | Attach an optional photo (multipart) |
| GET  | `/reports/{report_id}/photo` | Fetch the photo (image bytes) |
| GET  | `/reports` | List reports (public view) |
| GET  | `/reports/{report_id}` | One report (public view) |
| POST | `/reports/{report_id}/matches` | Run the AI agent and return ranked candidates |
| GET  | `/reports/{report_id}/matches` | Return the last saved candidates (no AI call) |
| POST | `/matches/{match_id}/feedback` | Confirm / reject / mark uncertain |

---

## Shared types

### `ReportType`
`"lost" | "found"`

### `Category`
`"bag" | "electronics" | "wallet" | "keys" | "id_card" | "clothing" | "jewelry" | "bottle" | "umbrella" | "book" | "other"`

### `ReportStatus`
`"open" | "matched" | "closed"`

### `Assessment`
| Value | Meaning shown to user |
|---|---|
| `likely_match` | Strong agreement, no serious conflicts. Still needs verification. |
| `possible_match` | Some agreement, some gaps or minor conflicts. |
| `unlikely_match` | A serious conflict (different category, impossible timing, contradicting features). |
| `insufficient_information` | Too little is known to judge either way. |

### `FeedbackStatus`
`"pending" | "confirmed" | "rejected" | "uncertain"`

---

## Privacy rules (everyone must respect these)

1. `contact` is **never** returned by any endpoint.
2. `private_details` (e.g. "keychain shaped like the Eiffel Tower", "sticker
   on the back") is **never** returned by any endpoint. Only the AI sees it.
   It exists so the true owner can prove ownership.
3. In match results, evidence that comes from the *candidate's* private details
   is shown as `"[private detail withheld]"`. The user is asked to describe the
   detail to the finder instead of being shown it.

---

## 1. `GET /health`

**200**
```json
{ "status": "ok", "ai_available": true }
```
`ai_available: false` means matching will run in degraded (non-AI) mode.

---

## 2. `POST /reports`

**Request** (only `type` and `description` are required; everything else may be omitted or `null`)
```json
{
  "type": "lost",
  "description": "I lost my dark blue backpack near the university library. It had a laptop and a small keychain inside.",
  "category": "bag",
  "color": "dark blue",
  "location": "Main Library",
  "occurred_at": "2026-10-09T14:00:00Z",
  "private_details": "Keychain is a small silver Eiffel Tower.",
  "contact": "student@example.edu"
}
```

| Field | Type | Rules |
|---|---|---|
| `type` | ReportType | required |
| `description` | string | required, 10–2000 chars after trimming |
| `category` | Category \| null | optional |
| `color` | string \| null | optional, ≤ 50 chars |
| `location` | string \| null | optional, ≤ 200 chars |
| `occurred_at` | string \| null | optional, approximate time is fine; must not be in the future |
| `private_details` | string \| null | optional, ≤ 500 chars, never returned |
| `contact` | string \| null | optional, ≤ 200 chars, never returned |

**201** → a `Report` (public view, see below).

**422** → validation error (see Errors).

---

## 3. `POST /reports/{report_id}/photo`  (optional feature)

`multipart/form-data` with one field `file`.
- Allowed: `image/jpeg`, `image/png`, `image/webp`
- Max size: 5 MB
- Stored under a server-generated filename (never the user's filename).

**200** → the updated `Report` (`has_photo: true`).
**404** report not found · **415** wrong type · **413** too large.

`GET /reports/{report_id}/photo` returns the image bytes, or **404**.

---

## 4. `Report` (public view) — returned by create / get / list

```json
{
  "id": 1,
  "type": "lost",
  "description": "I lost my dark blue backpack near the university library. It had a laptop and a small keychain inside.",
  "category": "bag",
  "color": "dark blue",
  "location": "Main Library",
  "occurred_at": "2026-10-09T14:00:00Z",
  "has_photo": false,
  "photo_url": null,
  "has_private_details": true,
  "status": "open",
  "created_at": "2026-10-09T15:10:00Z",
  "ai_attributes": {
    "extraction_status": "ok",
    "item_type": "backpack",
    "category": "bag",
    "color_family": ["blue"],
    "brand": null,
    "features": ["contains laptop", "small keychain"],
    "location_normalized": "main library"
  }
}
```

- `photo_url` is `"/reports/{id}/photo"` when `has_photo` is true, else `null`.
- `ai_attributes` is filled by the AI at submit time (normalises wording such as
  "navy school bag" → item_type `backpack`, color_family `["blue"]`).
  - `extraction_status`: `"ok" | "pending" | "failed"`.
  - If `"pending"` or `"failed"`, the other `ai_attributes` fields are `null`/`[]`
    and the UI should simply not show them. The report is still valid.

---

## 5. `GET /reports`

Query params (all optional): `type=lost|found`, `status=open|matched|closed`, `limit` (default 50, max 200).

**200**
```json
{ "items": [ /* Report, newest first */ ], "total": 6 }
```

## 6. `GET /reports/{report_id}`

**200** → `Report` · **404** → not found.

---

## 7. `POST /reports/{report_id}/matches` — the AI agent

Runs: retrieve candidates of the **opposite** type → AI compares each pair →
grounding check → deterministic score → save → return.
Can take several seconds; show a loading state.

**Request** (body optional)
```json
{ "limit": 5 }
```
`limit`: 1–10, default 5.

**200** → `MatchResponse`. Full example: `sample_data/mock_matches.json`.

```json
{
  "report_id": 1,
  "generated_at": "2026-10-10T09:00:00Z",
  "degraded": false,
  "degraded_reason": null,
  "candidates_considered": 4,
  "candidates": [ /* MatchCandidate, sorted by ranking_score desc */ ]
}
```

- `candidates_considered`: how many opposite-type reports the cheap retrieval
  step looked at before the AI compared the top ones.
- `degraded: true` means the AI model was unavailable; results come from the
  deterministic score only, `assessment` is at most `possible_match`, and
  evidence lists contain only rule-based checks. `degraded_reason` is a short
  human-readable string, e.g. `"AI model timed out"`.
- Empty result is valid: `"candidates": []` (UI shows an empty state).

### `MatchCandidate`

```json
{
  "match_id": 101,
  "candidate_report_id": 2,
  "candidate": {
    "type": "found",
    "description": "A navy school bag was left on a chair in the library. It has a keyring attached.",
    "category": "bag",
    "color": "navy",
    "location": "Main Library, 2nd floor reading room",
    "occurred_at": "2026-10-09T17:30:00Z",
    "has_photo": true,
    "photo_url": "/reports/2/photo"
  },
  "assessment": "likely_match",
  "ranking_score": 93,
  "score_breakdown": [
    { "attribute": "category", "points": 30, "max": 30, "result": "agree" }
  ],
  "matching_evidence": [
    { "attribute": "color", "this_report": "dark blue", "candidate": "navy",
      "source": "text", "note": "Navy is a shade of dark blue." }
  ],
  "conflicting_evidence": [],
  "missing_information": ["Whether the found bag contains a laptop."],
  "next_step": "Contact the finder through the lost-and-found desk and describe your keychain to verify ownership before any handover.",
  "feedback_status": "pending"
}
```

| Field | Type | Notes |
|---|---|---|
| `match_id` | int | use for feedback |
| `candidate_report_id` | int | |
| `candidate` | object | public view of the other report (no contact, no private details) |
| `assessment` | Assessment | |
| `ranking_score` | int 0–100 | **a ranking score, not a probability** (see below) |
| `score_breakdown` | list | one entry per attribute, always all 5 in fixed order |
| `matching_evidence` | list of Evidence | may be empty |
| `conflicting_evidence` | list of Evidence | may be empty |
| `missing_information` | list of string | what would help confirm |
| `next_step` | string | always encourages verification before handover |
| `feedback_status` | FeedbackStatus | |

### `Evidence`

| Field | Type | Notes |
|---|---|---|
| `attribute` | `"category" \| "color" \| "location" \| "time" \| "features" \| "other"` | |
| `this_report` | string \| null | what the report you are viewing says |
| `candidate` | string \| null | what the candidate says, or `"[private detail withheld]"` |
| `source` | `"text" \| "photo" \| "rule"` | `photo` = from image analysis, `rule` = deterministic check |
| `note` | string | one-sentence explanation |

### `score_breakdown` entry

| Field | Type |
|---|---|
| `attribute` | `"category" \| "color" \| "location" \| "time" \| "features"` |
| `points` | int |
| `max` | int |
| `result` | `"agree" \| "partial" \| "conflict" \| "unknown"` |

### How `ranking_score` is calculated

A fixed, explainable sum — **not** a model-generated percentage and **not** a
calibrated probability. It only orders candidates.

| Attribute | Max | agree | partial | unknown | conflict |
|---|---|---|---|---|---|
| category | 30 | 30 | 15 | 0 | 0 |
| color | 20 | 20 | 10 | 0 | 0 |
| location | 20 | 20 | 10 | 0 | 0 |
| time | 15 | 15 | 8 | 0 | 0 |
| features | 15 | 15 | 8 | 0 | 0 |

- **Missing information scores 0**, never counts as agreement.
- Time `conflict` includes impossible ordering (item *found before* it was *lost*,
  beyond a small tolerance).
- The AI decides `agree/partial/conflict/unknown` for language-heavy attributes
  (color shades, item synonyms, features); Python decides time and applies the
  points. Python also caps the `assessment`:
  - any `conflict` on category or time → at most `unlikely_match`
  - fewer than 2 attributes known on both sides → `insufficient_information`

---

## 8. `GET /reports/{report_id}/matches`

Returns the last saved `MatchResponse` without calling the AI (fast; use when
re-opening a page). **404** if the report doesn't exist. If matching was never
run: `200` with `"candidates": []` and `"generated_at": null`.

---

## 9. `POST /matches/{match_id}/feedback`

**Request**
```json
{ "status": "confirmed", "note": "Keychain matched when we met at the desk." }
```
`status`: `"confirmed" | "rejected" | "uncertain"` · `note`: optional, ≤ 500 chars.

**200**
```json
{ "match_id": 101, "feedback_status": "confirmed", "updated_at": "2026-10-10T09:05:00Z" }
```
Side effect: `confirmed` sets both reports' `status` to `"matched"`.
**404** match not found · **422** invalid status.

---

## Errors

All errors use one shape:
```json
{
  "error": {
    "code": "validation_error",
    "message": "description must be at least 10 characters",
    "details": [ { "field": "description", "issue": "too_short" } ]
  }
}
```

| HTTP | `code` |
|---|---|
| 404 | `not_found` |
| 413 | `file_too_large` |
| 415 | `unsupported_media_type` |
| 422 | `validation_error` |
| 500 | `internal_error` (never includes stack traces) |

Note: the AI being down is **not** an error — matching returns `200` with
`degraded: true`.

(Backend: FastAPI's default 422 body differs; add an exception handler that
converts it to this shape.)

---

## Mock files for parallel work

| File | Use |
|---|---|
| `sample_data/mock_reports.json` | response of `GET /reports` |
| `sample_data/mock_matches.json` | response of `POST /reports/1/matches` (normal mode) |
| `sample_data/mock_matches_degraded.json` | same, when the AI is unavailable |

---

## Changelog

- v0.1 (2026-10-10): initial contract.
