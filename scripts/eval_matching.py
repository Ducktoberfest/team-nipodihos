"""Live evaluation of the matching agent on sample_data/demo_reports.json.

Calls the REAL models in MODEL_CHAIN (needs GEMINI_API_KEY and/or GROQ_API_KEY in .env). Run from the repo root:

    .venv/Scripts/python scripts/eval_matching.py

1. Extracts attributes for every report (like the backend does at submit time).
2. Runs find_matches for every lost report.
3. Compares the results with the dataset's "expected" section.

Stays under free-tier limits (~8K tokens/minute on Groq) by pausing when needed.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from foundit_ai import agent  # noqa: E402
from foundit_ai.agent import default_client, extract_attributes, find_matches  # noqa: E402
from foundit_ai.llm_client import AIUnavailable  # noqa: E402
from foundit_ai.llm_client import ModelClient  # noqa: E402
from foundit_ai.schemas import ReportRecord  # noqa: E402

TOKENS_PER_MINUTE = 7000          # stay a little under Groq's 8K free-tier limit
SHORT = {"likely_match": "LIKELY", "possible_match": "possible",
         "unlikely_match": "unlikely", "insufficient_information": "not-enough-info"}


def wait_for_budget(client: ModelClient, next_call_tokens: int) -> None:
    while True:
        now = time.time()
        used = sum(t for ts, t in client.usage_log if now - ts < 60)
        if used + next_call_tokens <= TOKENS_PER_MINUTE:
            return
        oldest = min(ts for ts, _ in client.usage_log if now - ts < 60)
        pause = 60 - (now - oldest) + 1
        print(f"   (rate limit: pausing {pause:.0f}s)", flush=True)
        time.sleep(pause)


def main() -> None:
    data = json.loads((ROOT / "sample_data" / "demo_reports.json").read_text(encoding="utf-8"))
    reports = [ReportRecord.model_validate(r) for r in data["reports"]]
    expected = data["expected"]
    extractor = default_client("extract")
    compare_clients = []
    for task in ("compare", "compare_fields"):
        try:
            compare_clients.append(default_client(task))
            print(f"{task:15} chain: {compare_clients[-1].chain}")
        except AIUnavailable as e:
            print(f"{task:15} unavailable: {e}")
    print(f"{'extract':15} chain: {extractor.chain}")
    client = compare_clients[0]

    print(f"1) Extracting attributes for {len(reports)} reports...")
    for r in reports:
        wait_for_budget(extractor, 700)
        r.ai_attributes = extract_attributes(r)
        a = r.ai_attributes
        print(f"   #{r.id:<2} {a.extraction_status:6} item={a.item_type!s:14} "
              f"colors={a.color_family} features={a.features}")

    print("\n2) Matching every lost report...")
    runs = {}
    for q in [r for r in reports if r.type == "lost"]:
        wait_for_budget(client, 4500)
        started = time.perf_counter()
        run = find_matches(q, reports, limit=5)
        runs[q.id] = run
        flag = "  [DEGRADED]" if run.degraded else f"  [{agent.last_compare_source}]"
        print(f"\n   LOST #{q.id}: {q.description[:70]}...  ({time.perf_counter() - started:.1f}s){flag}")
        for c in run.candidates:
            conflicts = ", ".join(e.attribute for e in c.conflicting_evidence) or "-"
            print(f"     -> #{c.candidate_report_id:<2} {SHORT[c.assessment]:16} "
                  f"score={c.ranking_score:3}  conflicts: {conflicts}")

    print("\n3) Checks against expected results")
    passed = total = 0

    def check(ok: bool, text: str) -> None:
        nonlocal passed, total
        total += 1
        passed += ok
        print(f"   [{'PASS' if ok else 'FAIL'}] {text}")

    for lost_id, found_id, why in expected["true_pairs"]:
        run = runs[lost_id]
        top = run.candidates[0] if run.candidates else None
        check(bool(top and top.candidate_report_id == found_id
                   and top.assessment in ("likely_match", "possible_match")),
              f"#{lost_id} -> #{found_id} ranked first as likely/possible ({why})")
    for lost_id, found_id, why in expected["decoys"]:
        found = {c.candidate_report_id: c for c in runs[lost_id].candidates}.get(found_id)
        check(found is None or found.assessment in ("unlikely_match", "insufficient_information"),
              f"decoy #{lost_id} vs #{found_id} not suggested ({why})")
    for lost_id in expected["no_true_match"]:
        check(all(c.assessment != "likely_match" for c in runs[lost_id].candidates),
              f"#{lost_id} has no 'likely' match (there is none)")
    leaks = [r for r in reports if r.private_details]
    dumped = " ".join(run.model_dump_json() for run in runs.values()).lower()
    leaked = [r.id for r in leaks if r.type == "found" and r.private_details.lower() in dumped]
    check(not leaked, f"no found-report private details appear in any result (leaked: {leaked})")

    calls = extractor.usage_log + [u for c in compare_clients for u in c.usage_log]
    tokens = sum(t for _, t in calls)
    print(f"\nResult: {passed}/{total} checks passed · {len(calls)} model calls · {tokens} tokens")


if __name__ == "__main__":
    main()
