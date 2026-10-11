"""SQLite storage. All SQL lives here and uses "?" placeholders only (no f-string SQL)."""

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]

SCHEMA = """
CREATE TABLE IF NOT EXISTS reports (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  type TEXT NOT NULL CHECK (type IN ('lost','found')),
  description TEXT NOT NULL,
  category TEXT, color TEXT, location TEXT,
  occurred_at TEXT,                 -- ISO 8601 UTC string or NULL
  private_details TEXT,             -- NEVER returned by the API
  contact TEXT,                     -- NEVER returned by the API
  photo_path TEXT,
  ai_attributes_json TEXT,          -- filled by foundit_ai.extract_attributes()
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
"""

REPORT_COLUMNS = (
    "type", "description", "category", "color", "location", "occurred_at",
    "private_details", "contact", "photo_path", "ai_attributes_json", "status", "created_at",
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def get_db_path() -> Path:
    # Read at call time so tests can point FOUNDIT_DB_PATH at a temp file.
    return Path(os.getenv("FOUNDIT_DB_PATH", str(BACKEND_DIR / "foundit.db")))


@contextmanager
def connect():
    """Open a connection; commit on success, roll back on error, always close."""
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    get_db_path().parent.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        conn.executescript(SCHEMA)


# ---------- reports ----------

def insert_report(conn: sqlite3.Connection, data: dict) -> int:
    """Insert a report. `data` may include an explicit "id" (used by the seed script)."""
    columns = [c for c in REPORT_COLUMNS if c in data]
    if "id" in data:
        columns = ["id", *columns]
    placeholders = ", ".join("?" for _ in columns)
    sql = f"INSERT INTO reports ({', '.join(columns)}) VALUES ({placeholders})"  # column names are fixed above
    cur = conn.execute(sql, [data[c] for c in columns])
    return cur.lastrowid


def get_report(conn: sqlite3.Connection, report_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()


def list_reports(conn: sqlite3.Connection, type_: str | None, status: str | None,
                 limit: int) -> tuple[list[sqlite3.Row], int]:
    """Newest first. Returns (rows, total matching the filters before the limit)."""
    where = "WHERE (? IS NULL OR type = ?) AND (? IS NULL OR status = ?)"
    params = (type_, type_, status, status)
    total = conn.execute(f"SELECT COUNT(*) FROM reports {where}", params).fetchone()[0]
    rows = conn.execute(
        f"SELECT * FROM reports {where} ORDER BY created_at DESC, id DESC LIMIT ?",
        (*params, limit),
    ).fetchall()
    return rows, total


def list_other_reports(conn: sqlite3.Connection, report_id: int) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM reports WHERE id != ? ORDER BY id", (report_id,)).fetchall()


def set_ai_attributes(conn: sqlite3.Connection, report_id: int, attributes_json: str) -> None:
    conn.execute("UPDATE reports SET ai_attributes_json = ? WHERE id = ?", (attributes_json, report_id))


def set_photo_path(conn: sqlite3.Connection, report_id: int, photo_path: str | None) -> None:
    conn.execute("UPDATE reports SET photo_path = ? WHERE id = ?", (photo_path, report_id))


def set_report_status(conn: sqlite3.Connection, report_ids: list[int], status: str) -> None:
    conn.executemany("UPDATE reports SET status = ? WHERE id = ?", [(status, i) for i in report_ids])


# ---------- match runs ----------

def save_match_run(conn: sqlite3.Connection, report_id: int, run: dict) -> None:
    conn.execute(
        "INSERT INTO match_runs (report_id, run_json) VALUES (?, ?) "
        "ON CONFLICT(report_id) DO UPDATE SET run_json = excluded.run_json",
        (report_id, json.dumps(run)),
    )


def get_match_run(conn: sqlite3.Connection, report_id: int) -> dict | None:
    row = conn.execute("SELECT run_json FROM match_runs WHERE report_id = ?", (report_id,)).fetchone()
    return json.loads(row["run_json"]) if row else None


# ---------- matches ----------

def upsert_match(conn: sqlite3.Connection, report_id: int, candidate_report_id: int) -> None:
    """Create the (report, candidate) row if missing. Existing feedback is kept on re-runs."""
    conn.execute(
        "INSERT INTO matches (report_id, candidate_report_id, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT(report_id, candidate_report_id) DO NOTHING",
        (report_id, candidate_report_id, utc_now_iso()),
    )


def get_matches_for_report(conn: sqlite3.Connection, report_id: int) -> dict[int, sqlite3.Row]:
    rows = conn.execute("SELECT * FROM matches WHERE report_id = ?", (report_id,)).fetchall()
    return {row["candidate_report_id"]: row for row in rows}


def get_match(conn: sqlite3.Connection, match_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM matches WHERE id = ?", (match_id,)).fetchone()


def update_match_feedback(conn: sqlite3.Connection, match_id: int, status: str,
                          note: str | None) -> str:
    updated_at = utc_now_iso()
    conn.execute(
        "UPDATE matches SET feedback_status = ?, note = ?, updated_at = ? WHERE id = ?",
        (status, note, updated_at, match_id),
    )
    return updated_at
