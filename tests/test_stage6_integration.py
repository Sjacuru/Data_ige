"""tests/test_stage6_integration.py

Integration test for Stage 6 workflow output artifacts and schemas.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from application.workflows import stage6_alerts


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def run_tests() -> int:
    passed = 0
    failed = 0

    def check(label: str, condition: bool) -> None:
        nonlocal passed, failed
        if condition:
            print(f"✓ {label}")
            passed += 1
        else:
            print(f"✗ {label}")
            failed += 1

    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        conformity_dir = tmp_root / "conformity"
        compliance_dir = tmp_root / "compliance"
        alerts_dir = tmp_root / "alerts"

        pid = "INT-001"

        conformity_payload = {
            "processo_id": pid,
            "diagnostic": {"agreement_level": "PARTIAL"},
            "score_breakdown": {
                "R001": {"verdict": "PASS"},
                "R002": {"verdict": "FAIL"},
                "R003": {"verdict": "INCOMPLETE"},
                "R004": {"verdict": "INCOMPLETE"},
            },
            "conformity_score": 55.0,
            "overall_status": "NÃO CONFORME",
            "flags": ["DIAGNOSTIC_PARTIAL"],
            "requires_review": True,
            "recommendations": ["Review before approval"],
        }
        compliance_payload = {
            "processo_id": pid,
            "overall": {"review_reason": "one_or_more_rules_failed"},
            "r001_timeliness": {"verdict": "PASS"},
            "r002_party_match": {"verdict": "FAIL"},
            "extraction_diagnostic": {"divergence_detail": {}},
        }

        _write_json(conformity_dir / f"{pid}_conformity.json", conformity_payload)
        _write_json(compliance_dir / f"{pid}_compliance.json", compliance_payload)

        stage6_alerts.CONFORMITY_DIR = conformity_dir
        stage6_alerts.COMPLIANCE_DIR = compliance_dir
        stage6_alerts.ALERTS_DIR = alerts_dir
        stage6_alerts.SUMMARY_PATH = tmp_root / "alerts_summary.json"
        stage6_alerts.EXPORT_CSV_PATH = tmp_root / "alerts_export.csv"
        stage6_alerts.EXPORT_XLSX_PATH = tmp_root / "alerts_export.xlsx"
        stage6_alerts.QUEUE_JSON_PATH = tmp_root / "alerts_queue.json"
        stage6_alerts.QUEUE_CSV_PATH = tmp_root / "alerts_queue.csv"

        summary = stage6_alerts.run_stage6_alerts(pid=pid)

        alert_file = alerts_dir / f"{pid}_alert.json"
        summary_file = stage6_alerts.SUMMARY_PATH
        export_csv_file = stage6_alerts.EXPORT_CSV_PATH
        export_xlsx_file = stage6_alerts.EXPORT_XLSX_PATH
        queue_json_file = stage6_alerts.QUEUE_JSON_PATH
        queue_csv_file = stage6_alerts.QUEUE_CSV_PATH

        check("Alert file generated", alert_file.exists())
        check("Summary file generated", summary_file.exists())
        check("Export CSV generated", export_csv_file.exists())
        check("Export XLSX generated", export_xlsx_file.exists())
        check("Queue JSON generated", queue_json_file.exists())
        check("Queue CSV generated", queue_csv_file.exists())

        alert_data = _read_json(alert_file)
        summary_data = _read_json(summary_file)
        queue_data = _read_json(queue_json_file)

        check("Alert schema contains level", "alert_level" in alert_data)
        check("Alert schema contains reason details", "reason_details" in alert_data)
        check("Alert schema contains failed rules", "failed_rules" in alert_data)

        check("Summary has queue size", "queue_size" in summary_data)
        check("Summary has top priority", "top_priority" in summary_data)
        check("Summary total contracts is 1", summary_data.get("total_contracts") == 1)
        check("Runtime summary object total is 1", summary.get("total_contracts") == 1)

        queue_items = queue_data.get("items", []) if isinstance(queue_data, dict) else []
        check("Queue contains one item", len(queue_items) == 1)
        if queue_items:
            check("Queue item action exists", "action" in queue_items[0])

    print(f"\nPassed: {passed}")
    print(f"Failed: {failed}")
    return 0 if failed == 0 else 1


def test_stage6_integration_suite() -> None:
    assert run_tests() == 0


if __name__ == "__main__":
    raise SystemExit(run_tests())
