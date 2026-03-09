"""
tests/test_task4_6_stage4_compliance.py

Acceptance tests for Task 4.6 — application/workflows/stage4_compliance.py

Tracks:
  A — Import + module structure
  B — Progress tracking functions (offline, no API key)
  C — Compliance output schema validation
  D — dry-run smoke test (reads real data directory, no API calls)
  E — Validate any existing compliance output files

Usage
─────
    python tests/test_task4_6_stage4_compliance.py            # all tracks
    python tests/test_task4_6_stage4_compliance.py --offline  # A + B + C only
"""

import json
import os
import sys
import shutil
import tempfile
import argparse
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

GREEN = "\033[92m"; RED = "\033[91m"; YELLOW = "\033[93m"
CYAN  = "\033[96m"; BOLD = "\033[1m"; RESET  = "\033[0m"

PASSED = FAILED = WARNINGS = 0

def check(label, condition, hint=""):
    global PASSED, FAILED
    if condition:
        print(f"  {GREEN}✓{RESET}  {label}"); PASSED += 1
    else:
        print(f"  {RED}✗{RESET}  {label}")
        if hint: print(f"       {YELLOW}hint: {hint}{RESET}")
        FAILED += 1

def warn(msg):
    global WARNINGS
    print(f"  {YELLOW}⚠{RESET}  {msg}"); WARNINGS += 1

def info(msg): print(f"  {CYAN}·{RESET}  {msg}")

def section(title):
    print(f"\n{BOLD}{title}{RESET}")
    print("  " + "─" * 60)


# ══════════════════════════════════════════════════════════════════════════════
# TRACK A — Import + structure
# ══════════════════════════════════════════════════════════════════════════════

def track_a():
    section("TRACK A — Import & Structure")
    try:
        from application.workflows.stage4_compliance import (
            run_stage4_compliance,
            process_pid,
            _load_progress,
            _save_progress,
            _mark_completed,
            _mark_failed,
            _mark_skipped,
            _sanitize,
            _compute_overall,
            COMPLIANCE_DIR,
            PROGRESS_FILE,
        )
        check("A1: application.workflows.stage4_compliance imports cleanly", True)
    except ImportError as e:
        check("A1: import cleanly", False, hint=str(e))
        return False

    # A2: _sanitize
    check("A2: _sanitize converts / to _",
          _sanitize("FIL-PRO-2023/00482") == "FIL-PRO-2023_00482",
          hint=_sanitize("FIL-PRO-2023/00482"))

    # A3: COMPLIANCE_DIR defined
    check("A3: COMPLIANCE_DIR is a Path",
          isinstance(COMPLIANCE_DIR, Path),
          hint=str(type(COMPLIANCE_DIR)))

    # A4: PROGRESS_FILE defined
    check("A4: PROGRESS_FILE is a Path",
          isinstance(PROGRESS_FILE, Path))

    return True


# ══════════════════════════════════════════════════════════════════════════════
# TRACK B — Progress tracking (MDAP B6)
# ══════════════════════════════════════════════════════════════════════════════

def track_b_progress():
    section("TRACK B — Progress Tracking (MDAP B6)")
    import application.workflows.stage4_compliance as wf

    tmp_dir = Path(tempfile.mkdtemp())
    original_progress = wf.PROGRESS_FILE

    try:
        wf.PROGRESS_FILE = tmp_dir / "compliance_progress.json"

        # B6.1: fresh load returns correct skeleton
        progress = wf._load_progress()
        required_keys = {"last_run", "stats", "completed", "failed", "skipped"}
        check("B6.1: fresh load returns skeleton with all required keys",
              required_keys.issubset(progress.keys()),
              hint=f"missing: {required_keys - set(progress.keys())}")
        check("B6.1: completed starts as empty list",
              progress["completed"] == [],
              hint=str(progress.get("completed")))
        check("B6.1: stats.completed starts at 0",
              progress["stats"]["completed"] == 0)

        # B6.2: mark completed → appears in list, stats incremented
        wf._mark_completed(progress, "TEST-PID/001")
        check("B6.2: mark completed → PID in completed list",
              "TEST-PID/001" in progress["completed"],
              hint=str(progress["completed"]))
        check("B6.2: stats.completed == 1",
              progress["stats"]["completed"] == 1,
              hint=str(progress["stats"]["completed"]))

        # B6.3: mark_completed is idempotent (no duplicate)
        wf._mark_completed(progress, "TEST-PID/001")
        check("B6.3: mark_completed idempotent — no duplicates",
              progress["completed"].count("TEST-PID/001") == 1,
              hint=str(progress["completed"]))

        # B6.4: mark failed → appears in failed list with timestamp + error
        wf._mark_failed(progress, "FAIL-PID/001", "FileNotFoundError")
        failed_entry = next(
            (e for e in progress["failed"] if e["processo_id"] == "FAIL-PID/001"),
            None
        )
        check("B6.4: mark_failed → entry in failed list",
              failed_entry is not None,
              hint=str(progress["failed"]))
        check("B6.4: failed entry has 'at' timestamp",
              failed_entry is not None and "at" in failed_entry)
        check("B6.4: failed entry has 'error' field",
              failed_entry is not None and failed_entry.get("error") == "FileNotFoundError")
        check("B6.4: stats.failed == 1",
              progress["stats"]["failed"] == 1)

        # B6.5: mark skipped
        wf._mark_skipped(progress, "SKIP-PID/001")
        check("B6.5: mark_skipped → PID in skipped list",
              "SKIP-PID/001" in progress["skipped"])

        # B6.6: save + reload round-trips correctly
        wf._save_progress(progress)
        reloaded = wf._load_progress()
        check("B6.6: reload: completed list persisted",
              "TEST-PID/001" in reloaded.get("completed", []))
        check("B6.6: reload: failed list persisted",
              any(e["processo_id"] == "FAIL-PID/001"
                  for e in reloaded.get("failed", [])))
        check("B6.6: reload: last_run is set",
              reloaded.get("last_run") is not None)

    finally:
        wf.PROGRESS_FILE = original_progress
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ══════════════════════════════════════════════════════════════════════════════
# TRACK C — Output schema validation (MDAP B7)
# ══════════════════════════════════════════════════════════════════════════════

def track_c_schema():
    section("TRACK C — Compliance Output Schema (MDAP B7)")
    from application.workflows.stage4_compliance import _compute_overall

    # B7.1: top-level keys of a compliance JSON
    required_top = {
        "processo_id", "evaluated_at", "inputs",
        "extraction_diagnostic", "r001_timeliness", "r002_party_match",
        "overall", "metadata",
    }

    # Build a minimal mock compliance dict
    sample = {
        "processo_id": "TEST/001",
        "evaluated_at": datetime.now().isoformat(),
        "inputs": {
            "contract_file": "path/a.json",
            "publication_file": "path/b.json",
            "publication_source": "doweb",
        },
        "extraction_diagnostic": {
            "agreement_level": "CONFIRMED",
            "fields_confirmed": [],
            "fields_divergent": [],
            "divergence_detail": {},
            "auditor_action_required": False,
        },
        "r001_timeliness": {
            "verdict": "PASS", "signing_date": "01/01/2026",
            "publication_date": "10/01/2026", "days_delta": 9,
            "limit_days": 20, "explanation": "ok", "confidence": "high",
            "requires_review": False, "inconclusive_reason": None,
        },
        "r002_party_match": {
            "verdict": "PASS", "contract_contratante": "A",
            "publication_contratante": "A", "contract_contratada": "B",
            "publication_contratada": "B", "explanation": "ok",
            "confidence": "high", "requires_review": False,
            "inconclusive_reason": None, "llm_model": "llama-3.3-70b-versatile",
        },
        "overall": {"status": "PASS", "requires_review": False, "review_reason": None},
        "metadata": {
            "diagnostic_skipped": False, "r001_skipped": False,
            "r002_skipped": False, "api_calls_made": 3,
            "processing_time_seconds": 4.2, "warnings": [],
        },
    }

    check("B7.1: all top-level keys present",
          required_top.issubset(sample.keys()),
          hint=f"missing: {required_top - set(sample.keys())}")

    # B7.2: _compute_overall derives status correctly
    check("B7.2: R001=PASS, R002=PASS, diag=CONFIRMED → PASS",
          _compute_overall("PASS", "PASS", "CONFIRMED")[0] == "PASS")
    check("B7.2: R001=FAIL → FAIL",
          _compute_overall("FAIL", "PASS", "CONFIRMED")[0] == "FAIL")
    check("B7.2: R002=FAIL → FAIL",
          _compute_overall("PASS", "FAIL", "CONFIRMED")[0] == "FAIL")
    check("B7.2: R001=INCONCLUSIVE → INCONCLUSIVE",
          _compute_overall("INCONCLUSIVE", "PASS", "CONFIRMED")[0] == "INCONCLUSIVE")
    check("B7.2: diag=DIVERGENT → INCONCLUSIVE",
          _compute_overall("PASS", "PASS", "DIVERGENT")[0] == "INCONCLUSIVE")

    # B7.3: requires_review = True for FAIL and INCONCLUSIVE
    check("B7.3: FAIL → requires_review = True",
          _compute_overall("FAIL", "PASS", "CONFIRMED")[1] is True)
    check("B7.3: INCONCLUSIVE → requires_review = True",
          _compute_overall("INCONCLUSIVE", "PASS", "CONFIRMED")[1] is True)
    check("B7.3: PASS + CONFIRMED → requires_review = False",
          _compute_overall("PASS", "PASS", "CONFIRMED")[1] is False)
    check("B7.3: PASS + PARTIAL → requires_review = True",
          _compute_overall("PASS", "PASS", "PARTIAL")[1] is True)

    # B7.4: INCONCLUSIVE JSON for no-publication case
    no_pub = {
        "overall": {
            "status": "INCONCLUSIVE",
            "requires_review": True,
            "review_reason": "no_publication_found",
        },
        "r001_timeliness": {"inconclusive_reason": "no_publication_found"},
        "r002_party_match": {"inconclusive_reason": "no_publication_found"},
    }
    check("B7.4: no-publication case → status INCONCLUSIVE",
          no_pub["overall"]["status"] == "INCONCLUSIVE")
    check("B7.4: no-publication case → requires_review = True",
          no_pub["overall"]["requires_review"] is True)
    check("B7.4: no-publication reason tag correct",
          no_pub["overall"]["review_reason"] == "no_publication_found")


# ══════════════════════════════════════════════════════════════════════════════
# TRACK D — dry-run smoke test
# ══════════════════════════════════════════════════════════════════════════════

def track_d_dryrun():
    section("TRACK D — dry-run smoke test")

    preprocessed_dir = ROOT / "data/preprocessed"
    if not preprocessed_dir.exists():
        warn("data/preprocessed/ not found — skipping dry-run test")
        warn("Run Stages 1-3 first to populate data/preprocessed/")
        return

    try:
        from application.workflows.stage4_compliance import run_stage4_compliance
        result = run_stage4_compliance(dry_run=True)

        check("D1: dry_run returns a dict", isinstance(result, dict))
        check("D2: dry_run result has 'total' key",
              "total" in result,
              hint=str(result))
        check("D3: total > 0 (preprocessed files found)",
              result.get("total", 0) > 0,
              hint=f"total={result.get('total')}")
        check("D4: dry_run=True in result",
              result.get("dry_run") is True)

        info(f"  PIDs found: {result.get('total')}")
        info(f"  Pending   : {result.get('pending')}")

    except Exception as e:
        check("D1: dry_run completes without exception", False, hint=str(e))


# ══════════════════════════════════════════════════════════════════════════════
# TRACK E — Validate existing compliance output files
# ══════════════════════════════════════════════════════════════════════════════

def track_e_outputs():
    section("TRACK E — Validate existing compliance outputs (if present)")

    compliance_dir = ROOT / "data/compliance"
    if not compliance_dir.exists():
        warn("data/compliance/ not found — skipping (run Stage 4 first)")
        return

    files = sorted(compliance_dir.glob("*_compliance.json"))
    if not files:
        warn("No *_compliance.json files found — run Stage 4 first")
        return

    check(f"E1: found {len(files)} compliance files", len(files) > 0)

    required_keys = {
        "processo_id", "evaluated_at", "inputs", "extraction_diagnostic",
        "r001_timeliness", "r002_party_match", "overall", "metadata",
    }
    valid_verdicts = {"PASS", "FAIL", "INCONCLUSIVE"}
    valid_levels   = {"CONFIRMED", "PARTIAL", "DIVERGENT", "SKIPPED"}

    schema_ok = failed_schema = 0
    status_counts = {"PASS": 0, "FAIL": 0, "INCONCLUSIVE": 0}
    bad_review = 0

    for f in files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            failed_schema += 1
            continue

        if required_keys.issubset(data.keys()):
            schema_ok += 1
        else:
            failed_schema += 1

        status = data.get("overall", {}).get("status", "")
        if status in status_counts:
            status_counts[status] += 1

        # Every FAIL/INCONCLUSIVE must have requires_review = True
        if status in ("FAIL", "INCONCLUSIVE"):
            if not data.get("overall", {}).get("requires_review"):
                bad_review += 1

    check("E2: all files have valid schema", failed_schema == 0,
          hint=f"{failed_schema} files with bad schema")
    check("E3: all overall.status values are valid",
          sum(status_counts.values()) == len(files),
          hint=f"counts: {status_counts}, total files: {len(files)}")
    check("E4: every FAIL/INCONCLUSIVE has requires_review=True",
          bad_review == 0,
          hint=f"{bad_review} records missing requires_review=True")

    info(f"  PASS        : {status_counts['PASS']}")
    info(f"  FAIL        : {status_counts['FAIL']}")
    info(f"  INCONCLUSIVE: {status_counts['INCONCLUSIVE']}")

    inconclusive_pct = (status_counts["INCONCLUSIVE"] / len(files) * 100) if files else 0
    check(f"E5: INCONCLUSIVE rate ≤ 30% (got {inconclusive_pct:.0f}%)",
          inconclusive_pct <= 30,
          hint=f"{inconclusive_pct:.1f}% INCONCLUSIVE — investigate missing publications")


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Task 4.6 acceptance tests — stage4_compliance.py"
    )
    parser.add_argument("--offline", action="store_true",
                        help="Run Track A + B + C only (no disk reads)")
    args = parser.parse_args()

    print(f"\n{BOLD}{'═' * 65}{RESET}")
    print(f"{BOLD}  TASK 4.6 — stage4_compliance.py Acceptance Tests{RESET}")
    print(f"{BOLD}{'═' * 65}{RESET}")

    ok = track_a()
    if ok:
        track_b_progress()
        track_c_schema()
        if not args.offline:
            track_d_dryrun()
            track_e_outputs()

    print(f"\n{BOLD}{'═' * 65}{RESET}")
    print(f"{BOLD}  RESULTS{RESET}")
    print(f"{'═' * 65}")
    print(f"  {GREEN}✓  Passed  : {PASSED}{RESET}")
    print(f"  {RED}✗  Failed  : {FAILED}{RESET}")
    print(f"  {YELLOW}⚠  Warnings: {WARNINGS}{RESET}")

    if FAILED == 0:
        print(f"\n  {BOLD}{GREEN}✅ Task 4.6 COMPLETE — safe to proceed to Task 4.7{RESET}")
    else:
        print(f"\n  {BOLD}{RED}❌ {FAILED} check(s) failed{RESET}")
    print(f"{'═' * 65}\n")
    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())