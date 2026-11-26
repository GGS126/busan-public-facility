"""Evaluate the real query API, or replay fixtures without calling Gemini."""
import argparse
from collections import Counter
from contextlib import nullcontext
from datetime import datetime, timedelta
import getpass
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
from time import perf_counter, sleep

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
FIELDS = ("sport", "districts", "date", "start_time", "end_time", "headcount", "discount_types")


def materialize(case, today):
    tokens = {"tomorrow": (today + timedelta(days=1)).isoformat(),
              "day_after": (today + timedelta(days=2)).isoformat()}
    return json.loads(json.dumps(case, ensure_ascii=False).replace(
        "{tomorrow}", tokens["tomorrow"]).replace("{day_after}", tokens["day_after"]))


def evaluate(case, result):
    expected = case["expected"]
    actual = result.get("conditions", {})
    matches = {}
    for field in FIELDS if expected["status"] != "llm_failed" else ():
        wanted, found = expected["conditions"].get(field), actual.get(field)
        # Region/discount order does not change a search condition.
        if field in {"districts", "discount_types"} and isinstance(wanted, list) and isinstance(found, list):
            wanted, found = sorted(wanted), sorted(found)
        matches[field] = wanted == found
    status_match = result.get("status") == expected["status"]
    missing_match = set(result.get("missing_fields", [])) == set(expected["missing_fields"])
    return {"id": case["id"], "status": result.get("status"),
            "status_match": status_match, "missing_fields_match": missing_match,
            "field_matches": matches, "passed": status_match and missing_match and all(matches.values())}


def percentile(values, fraction):
    return sorted(values)[max(0, math.ceil(len(values) * fraction) - 1)] if values else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Call Gemini using the real API path (may consume quota).")
    parser.add_argument("--limit", type=int, help="Run only the first N fixtures; omitted means all.")
    parser.add_argument("--pause", type=float, default=9, help="Seconds between live queries; minimum 9.")
    parser.add_argument("--output", type=Path, help="Optional JSON report; no queries, keys or provider response text.")
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    if args.pause < 9:
        parser.error("--pause must be at least 9 seconds")
    if not (ROOT / "database" / "facilities.sqlite3").is_file():
        parser.error("Build the DB first: python database/build_db.py")
    # Evaluate the actual SQLite catalog, independent of shell settings.
    os.environ["RULE_DATA_SOURCE"] = "sqlite"
    if args.live and not os.environ.get("GEMINI_API_KEY", "").strip():
        os.environ["GEMINI_API_KEY"] = getpass.getpass("Gemini API key: ").strip()
        if not os.environ["GEMINI_API_KEY"]:
            parser.error("A Gemini key is required for --live")
    from fastapi.testclient import TestClient
    from app import main as service
    from app.models import KST
    from app.query_parser import parse_query

    today = datetime.now(KST).date()
    fixtures = json.loads((ROOT / "backend" / "evaluation" / "query_cases.json").read_text(encoding="utf-8"))
    cases = fixtures[:args.limit]
    rows = []
    with TestClient(service.app) if args.live else nullcontext() as client:
        for index, original in enumerate(cases):
            if args.live and index:
                sleep(args.pause)
            case = materialize(original, today)
            started = perf_counter()
            if args.live:
                response = client.post("/api/query/parse", json={"query": case["query"]})
                result = response.json() if response.status_code == 200 else {}
            else:
                calls = []
                def extract(query, day):
                    calls.append(True)
                    if "raw" not in case:
                        raise AssertionError("Privacy fixture must not reach the provider")
                    return case["raw"]
                result = parse_query(case["query"], today=today, extract=extract, catalog=service.available_options)
            row = evaluate(case, result)
            if not args.live:
                row["provider_calls"] = len(calls)
                if "raw" not in case:
                    row["passed"] = row["passed"] and not calls
            row["elapsed_ms"] = round((perf_counter() - started) * 1000, 2)
            rows.append(row)
            print(f'{row["id"]}: {"PASS" if row["passed"] else "FAIL"} ({row["elapsed_ms"]} ms)')
            # Do not keep issuing requests when credentials/quota/service are unavailable.
            if args.live and result.get("status") == "llm_failed" and case["expected"]["status"] != "llm_failed":
                print("Stopped after an API failure; remaining fixtures were not run.")
                break

    fields = Counter(field for row in rows for field, matches in row["field_matches"].items() if matches)
    field_totals = Counter(field for row in rows for field in row["field_matches"])
    passed = sum(row["passed"] for row in rows)
    times = [row["elapsed_ms"] for row in rows]
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
                              capture_output=True, check=True).stdout.strip()
    report = {
        "mode": "live_gemini" if args.live else "fixture_replay_not_model_accuracy",
        "created_at": datetime.now(KST).isoformat(), "commit": revision,
        "working_tree_dirty": bool(subprocess.run(
            ["git", "status", "--porcelain"], cwd=ROOT, text=True, capture_output=True, check=True).stdout),
        "python": platform.python_version(), "platform": platform.platform(),
        "model": (os.environ.get("GEMINI_MODEL", "").strip() or service.DEFAULT_MODEL) if args.live else None,
        "planned": len(cases), "executed": len(rows), "passed": passed,
        "complete": len(rows) == len(cases),
        "field_scores": {field: {"matched": fields[field], "total": field_totals[field],
                                "rate": fields[field] / field_totals[field] if field_totals[field] else None}
                         for field in FIELDS},
        "latency_ms": {"median": percentile(times, .5), "p95": percentile(times, .95), "max": max(times)},
        "acceptance": "not_determined: team target and browser checks remain separate",
        "results": rows,
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f'{report["mode"]}: {passed}/{len(rows)} passed; {len(rows)}/{len(cases)} executed')
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())
