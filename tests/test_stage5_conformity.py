"""
tests/test_stage5_conformity.py

Validation tests for Stage 5 Conformity Scoring & Reporting Engine.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from domain.services.conformity_engine import compute_conformity


def _base_compliance(r001="PASS", r002="PASS", agreement="CONFIRMED"):
    return {
        "processo_id": "TEST-PID/001",
        "extraction_diagnostic": {"agreement_level": agreement},
        "r001_timeliness": {"verdict": r001, "inconclusive_reason": None},
        "r002_party_match": {"verdict": r002, "inconclusive_reason": None},
        "overall": {"status": "PASS", "review_reason": None},
    }


def run_tests():
    passed = 0
    failed = 0

    def check(label, condition):
        nonlocal passed, failed
        if condition:
            print(f"✓ {label}")
            passed += 1
        else:
            print(f"✗ {label}")
            failed += 1

    # Test 1 — All PASS scenario → 100 score
    r = compute_conformity(
        _base_compliance("PASS", "PASS", "CONFIRMED"),
        {"header": {"contract_number": "001/2026", "value": "1000,00"}},
        {"contract_number": "001/2026", "value": "1000,00"},
    )
    check("Test 1: all pass gives 100", r["conformity_score"] == 100.0)

    # Test 2 — Mixed PASS/FAIL
    r = compute_conformity(
        _base_compliance("PASS", "FAIL", "CONFIRMED"),
        {"header": {"contract_number": "001/2026", "value": "1000,00"}},
        {"contract_number": "001/2026", "value": "1000,00"},
    )
    check("Test 2: mixed pass/fail score < 100", r["conformity_score"] < 100.0)

    # Test 3 — Diagnostic DIVERGENT → score 0
    r = compute_conformity(
        _base_compliance("PASS", "PASS", "DIVERGENT"),
        {"header": {"contract_number": "001/2026", "value": "1000,00"}},
        {"contract_number": "001/2026", "value": "1000,00"},
    )
    check("Test 3: divergent diagnostic forces zero", r["conformity_score"] == 0.0)
    check("Test 3b: divergent diagnostic skips R003", r["rule_details"]["R003"]["verdict"] == "SKIPPED")
    check("Test 3c: divergent diagnostic skips R004", r["rule_details"]["R004"]["verdict"] == "SKIPPED")

    # Test 4 — Diagnostic PARTIAL → cap 85
    r = compute_conformity(
        _base_compliance("PASS", "PASS", "PARTIAL"),
        {"header": {"contract_number": "001/2026", "value": "1000,00"}},
        {"contract_number": "001/2026", "value": "1000,00"},
    )
    check("Test 4: partial diagnostic caps at 85", r["conformity_score"] == 85.0)

    # Test 5 — Missing publication → forced INCOMPLETE
    no_pub = _base_compliance("INCONCLUSIVE", "INCONCLUSIVE", "SKIPPED")
    no_pub["overall"] = {"status": "INCONCLUSIVE", "review_reason": "no_publication_found"}
    r = compute_conformity(no_pub, {"header": {"contract_number": "001/2026"}}, None)
    check("Test 5: missing publication forces incomplete", r["overall_status"] == "INCOMPLETE")
    check("Test 5b: missing publication score is zero", r["conformity_score"] == 0.0)

    # Test 6 — R004 ≤1% → PARTIAL
    r = compute_conformity(
        _base_compliance("PASS", "PASS", "CONFIRMED"),
        {"header": {"contract_number": "001/2026", "value": "1000,00"}},
        {"contract_number": "001/2026", "value": "1009,00"},
    )
    check("Test 6: R004 <=1% is partial", r["rule_details"]["R004"]["verdict"] == "PARTIAL")

    # Test 7 — Division by zero protection
    r = compute_conformity(
        _base_compliance("PASS", "PASS", "CONFIRMED"),
        {"header": {"contract_number": "001/2026", "value": "0,00"}},
        {"contract_number": "001/2026", "value": "100,00"},
    )
    check("Test 7: division by zero handled", r["rule_details"]["R004"]["verdict"] == "FAIL")

    print(f"\nPassed: {passed}")
    print(f"Failed: {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(run_tests())
