"""CSV/XLSX exporters for Stage 6 alerts."""

from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd


ALERT_CSV_COLUMNS = [
    "processo_id",
    "alert_level",
    "reason",
    "overall_status",
    "conformity_score",
    "flags",
    "failed_rules",
]

QUEUE_CSV_COLUMNS = [
    "processo_id",
    "alert_level",
    "reason",
    "conformity_score",
    "failed_rules",
    "flags",
    "action",
    "priority_score",
]


def _row_from_alert(alert: dict) -> dict:
    return {
        "processo_id": alert.get("processo_id"),
        "alert_level": alert.get("alert_level"),
        "reason": alert.get("reason"),
        "overall_status": alert.get("overall_status"),
        "conformity_score": alert.get("conformity_score"),
        "flags": "|".join(alert.get("flags", []) or []),
        "failed_rules": "|".join(alert.get("failed_rules", []) or []),
    }


def write_alerts_csv(alerts: list[dict], csv_path: Path) -> Path:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=ALERT_CSV_COLUMNS)
        writer.writeheader()
        for alert in alerts:
            row = _row_from_alert(alert)
            writer.writerow({k: row.get(k, "") for k in ALERT_CSV_COLUMNS})
    return csv_path


def write_alerts_xlsx(alerts: list[dict], xlsx_path: Path) -> Path:
    xlsx_path.parent.mkdir(parents=True, exist_ok=True)
    rows = [_row_from_alert(alert) for alert in alerts]
    frame = pd.DataFrame(rows, columns=ALERT_CSV_COLUMNS)
    frame.to_excel(xlsx_path, index=False)
    return xlsx_path

def write_alert_queue_csv(queue: list[dict], csv_path: Path) -> Path:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=QUEUE_CSV_COLUMNS)
        writer.writeheader()
        for item in queue:
            row = {
                "processo_id": item.get("processo_id"),
                "alert_level": item.get("alert_level"),
                "reason": item.get("reason"),
                "conformity_score": item.get("conformity_score"),
                "failed_rules": "|".join(item.get("failed_rules", []) or []),
                "flags": "|".join(item.get("flags", []) or []),
                "action": item.get("action"),
                "priority_score": item.get("priority_score"),
            }
            writer.writerow({k: row.get(k, "") for k in QUEUE_CSV_COLUMNS})
    return csv_path
