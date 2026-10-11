"""Run the real extraction model once over the demo dataset and store the results.

Run from the repo root:  .venv/Scripts/python scripts/precompute_demo_attributes.py

Writes "ai_attributes" into each report of sample_data/demo_reports.json, so
scripts/seed_db.py can load a ready-to-match database instantly and without
API calls (exactly what POST /reports would have stored for each report).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from foundit_ai.agent import default_client, extract_attributes  # noqa: E402
from foundit_ai.schemas import ReportRecord  # noqa: E402

PATH = ROOT / "sample_data" / "demo_reports.json"


def main() -> None:
    data = json.loads(PATH.read_text(encoding="utf-8"))
    print(f"Extraction chain: {default_client('extract').chain}")
    failed = 0
    for item in data["reports"]:
        record = ReportRecord.model_validate({k: v for k, v in item.items()
                                             if k != "ai_attributes"})
        attrs = extract_attributes(record)
        failed += attrs.extraction_status != "ok"
        item["ai_attributes"] = attrs.model_dump()
        print(f"  #{record.id:<2} {attrs.extraction_status:6} {attrs.item_type!s:14} "
              f"{attrs.color_family} {attrs.features}")
    PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Saved {len(data['reports'])} reports ({failed} failed) to {PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
