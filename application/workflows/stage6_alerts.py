"""
application/workflows/stage6_alerts.py

Stage 6 — Deterministic alert generation from Stage 5 conformity outputs.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from config.settings import ALERTS_DIR, COMPLIANCE_DIR, CONFORMITY_DIR, DATA_DIR
from domain.services.alert_classifier import classify_alert
from domain.services.alert_queue import build_alert_queue
from domain.services.alert_report import build_alert_executive_summary
from infrastructure.io.alert_exporter import (
    write_alert_queue_csv,
    write_alerts_csv,
    write_alerts_xlsx,
)
from infrastructure.io.alert_writer import write_alert_result, write_alert_summary
from infrastructure.logging_config import setup_logging

logger = logging.getLogger(__name__)
SUMMARY_PATH = DATA_DIR / "alerts_summary.json"
EXPORT_CSV_PATH = DATA_DIR / "alerts_export.csv"
EXPORT_XLSX_PATH = DATA_DIR / "alerts_export.xlsx"
QUEUE_JSON_PATH = DATA_DIR / "alerts_queue.json"
QUEUE_CSV_PATH = DATA_DIR / "alerts_queue.csv"


def _load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Failed to load JSON %s: %s", path, exc)
        return None


def run_stage6_alerts(pid: str | None = None) -> dict:
    t_start = time.monotonic()
    setup_logging("alerts")

    files = sorted(CONFORMITY_DIR.glob("*_conformity.json")) if CONFORMITY_DIR.exists() else []
    if pid:
        safe_pid = pid.replace("/", "_").replace("\\", "_")
        files = [f for f in files if f.name == f"{safe_pid}_conformity.json"]

    logger.info("Stage 6 starting with %d conformity file(s).", len(files))

    summary = {
        "total_contracts": 0,
        "ok": 0,
        "review": 0,
        "failed": 0,
        "processing_time_seconds": 0.0,
    }
    alert_results: list[dict] = []

    for conformity_file in files:
        conformity_json = _load_json(conformity_file)
        if not conformity_json:
            continue

        safe_pid = str(conformity_json.get("processo_id", "UNKNOWN")).replace("/", "_").replace("\\", "_")
        compliance_file = COMPLIANCE_DIR / f"{safe_pid}_compliance.json"
        compliance_json = _load_json(compliance_file) if compliance_file.exists() else None

        alert = classify_alert(conformity_json, compliance_json=compliance_json)
        alert_results.append(alert)
        write_alert_result(alert.get("processo_id", "UNKNOWN"), alert, ALERTS_DIR)

        summary["total_contracts"] += 1
        if alert["alert_level"] == "OK":
            summary["ok"] += 1
        elif alert["alert_level"] == "REVIEW":
            summary["review"] += 1
        else:
            summary["failed"] += 1

    summary["processing_time_seconds"] = round(time.monotonic() - t_start, 2)
    executive = build_alert_executive_summary(alert_results)
    queue = build_alert_queue(alert_results)
    summary.update({
        "by_reason": executive.get("by_reason", {}),
        "failed_rules": executive.get("failed_rules", {}),
        "rates": executive.get("rates", {}),
        "queue_size": len(queue),
        "top_priority": queue[:5],
    })

    write_alert_summary(summary, SUMMARY_PATH)
    write_alerts_csv(alert_results, EXPORT_CSV_PATH)
    write_alerts_xlsx(alert_results, EXPORT_XLSX_PATH)
    write_alert_summary({"items": queue}, QUEUE_JSON_PATH)
    write_alert_queue_csv(queue, QUEUE_CSV_PATH)
    logger.info("Stage 6 complete: %s", summary)
    return summary


def _build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Stage 6 — Alert Generation")
    parser.add_argument("--pid", type=str, default=None, help="Process single processo_id")
    return parser


if __name__ == "__main__":
    args = _build_cli().parse_args()
    run_stage6_alerts(pid=args.pid)
