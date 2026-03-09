"""
infrastructure/io/csv_exporter.py

CSV export utilities for conformity outputs.
"""

from __future__ import annotations

import csv
from pathlib import Path


CSV_COLUMNS = [
    "processo_id",
    "agreement_level",
    "R001",
    "R002",
    "R003",
    "R004",
    "conformity_score",
    "overall_status",
    "flags",
]


def write_conformity_csv(rows: list[dict], csv_path: Path) -> Path:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in CSV_COLUMNS})
    return csv_path
