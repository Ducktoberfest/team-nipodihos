"""Recreate the database and load demo reports.

Run from the repo root:  python scripts/seed_db.py
Uses sample_data/demo_reports.json (Person C) if present, else sample_data/mock_reports.json.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import db  # noqa: E402

SOURCES = [ROOT / "sample_data" / "demo_reports.json", ROOT / "sample_data" / "mock_reports.json"]
FIELDS = ("type", "description", "category", "color", "location", "occurred_at",
          "private_details", "contact")


def load_reports() -> tuple[Path, list[dict]]:
    for path in SOURCES:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            items = data["items"] if isinstance(data, dict) else data
            return path, items
    raise SystemExit("No demo data found in sample_data/")


def to_row(item: dict) -> dict:
    row = {field: item.get(field) for field in FIELDS}
    row["status"] = item.get("status") or "open"
    row["created_at"] = item.get("created_at") or db.utc_now_iso()
    # Photos referenced by mock data don't exist on disk, so photo_path stays NULL.
    if item.get("ai_attributes"):
        row["ai_attributes_json"] = json.dumps(item["ai_attributes"])
    if "id" in item:
        row["id"] = item["id"]  # keep ids stable so mock_matches.json candidates line up
    return row


def main() -> None:
    db_path = db.get_db_path()
    db_path.unlink(missing_ok=True)
    db.init_db()

    source, items = load_reports()
    items = sorted(items, key=lambda i: i.get("id", 0))
    with db.connect() as conn:
        for item in items:
            db.insert_report(conn, to_row(item))
    print(f"Inserted {len(items)} reports from {source.relative_to(ROOT)} into {db_path}")


if __name__ == "__main__":
    main()
