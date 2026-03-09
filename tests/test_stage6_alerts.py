"""tests/test_stage6_alerts.py

Focused tests for Stage 6 deterministic alert classification.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from domain.services.alert_classifier import classify_alert
from domain.services.alert_queue import build_alert_queue
from domain.services.alert_report import build_alert_executive_summary


def _base_conformity(overall_status="CONFORME", score=100.0, flags=None, requires_review=False):
    return {
        "processo_id": "TEST-PID/ALERT-001",
        "overall_status": overall_status,
        "conformity_score": score,
        "flags": flags or [],
        "requires_review": requires_review,
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

    # Test 1 — Conformity with no flags => OK
    result = classify_alert(_base_conformity("CONFORME", 100.0))
    check("Test 1: conforme is OK", result["alert_level"] == "OK")

    # Test 2 — PARCIAL => REVIEW
    result = classify_alert(_base_conformity("PARCIAL", 85.0))
    check("Test 2: parcial is REVIEW", result["alert_level"] == "REVIEW")

    # Test 3 — INCOMPLETE => REVIEW
    result = classify_alert(_base_conformity("INCOMPLETE", 0.0))
    check("Test 3: incomplete is REVIEW", result["alert_level"] == "REVIEW")

    # Test 4 — Missing publication flag precedence => FAILED
    result = classify_alert(
        _base_conformity("CONFORME", 100.0, flags=["MISSING_PUBLICATION"])
    )
    check("Test 4: missing publication is FAILED", result["alert_level"] == "FAILED")
    check("Test 4b: missing publication reason", result["reason"] == "MISSING_PUBLICATION")
    check("Test 4c: has reason details", isinstance(result.get("reason_details"), dict))

    # Test 5 — Divergence flag precedence => FAILED
    result = classify_alert(
        _base_conformity("PARCIAL", 80.0, flags=["DIAGNOSTIC_DIVERGENCE"])
    )
    check("Test 5: diagnostic divergence is FAILED", result["alert_level"] == "FAILED")

    # Test 6 — Não conforme => FAILED
    non_conforme = _base_conformity("NÃO CONFORME", 20.0)
    non_conforme["score_breakdown"] = {
        "R001": {"verdict": "PASS"},
        "R002": {"verdict": "FAIL"},
        "R003": {"verdict": "FAIL"},
        "R004": {"verdict": "INCOMPLETE"},
    }
    result = classify_alert(non_conforme)
    check("Test 6: nao conforme is FAILED", result["alert_level"] == "FAILED")
    check("Test 6b: failed rules extracted", result["failed_rules"] == ["R002", "R003"])

    # Test 7 — requires_review => REVIEW even if CONFORME
    result = classify_alert(_base_conformity("CONFORME", 95.0, requires_review=True))
    check("Test 7: requires_review forces REVIEW", result["alert_level"] == "REVIEW")

    # Test 8 — Executive summary aggregation
    alerts = [
        {"alert_level": "OK", "reason": "CONFORME", "failed_rules": []},
        {"alert_level": "REVIEW", "reason": "NEEDS_REVIEW", "failed_rules": ["R003"]},
        {"alert_level": "FAILED", "reason": "NON_CONFORME", "failed_rules": ["R002", "R003"]},
    ]
    summary = build_alert_executive_summary(alerts)
    check("Test 8: summary total", summary["total_contracts"] == 3)
    check("Test 8b: summary counts", summary["counts"] == {"ok": 1, "review": 1, "failed": 1})
    check("Test 8c: summary failed rules", summary["failed_rules"]["R003"] == 2)

    # Test 9 — Queue prioritization excludes OK and sorts failed first
    queue = build_alert_queue(
        [
            {
                "processo_id": "PID-OK",
                "alert_level": "OK",
                "reason": "CONFORME",
                "conformity_score": 100.0,
                "failed_rules": [],
                "flags": [],
                "reason_details": {"action": "no_action"},
            },
            {
                "processo_id": "PID-REVIEW",
                "alert_level": "REVIEW",
                "reason": "NEEDS_REVIEW",
                "conformity_score": 70.0,
                "failed_rules": ["R003"],
                "flags": ["DIAGNOSTIC_PARTIAL"],
                "reason_details": {"action": "review_before_approval"},
            },
            {
                "processo_id": "PID-FAILED",
                "alert_level": "FAILED",
                "reason": "NON_CONFORME",
                "conformity_score": 20.0,
                "failed_rules": ["R002"],
                "flags": [],
                "reason_details": {"action": "investigate_rule_failures"},
            },
        ]
    )
    check("Test 9: queue excludes OK", len(queue) == 2)
    check("Test 9b: queue failed first", queue[0]["processo_id"] == "PID-FAILED")
    check("Test 9c: queue includes action", queue[0]["action"] == "investigate_rule_failures")

    print(f"\nPassed: {passed}")
    print(f"Failed: {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(run_tests())
