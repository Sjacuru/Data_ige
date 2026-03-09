from __future__ import annotations

import csv
import io
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

REPORT_CSV_COLUMNS = [
    "processo_id",
    "agreement_level",
    "R001",
    "R002",
    "R003",
    "R004",
    "conformity_score",
    "overall_status",
    "flags",
    "pipeline_stage",
    "company_name",
    "contract_value",
    "contract_date",
    "publication_date",
    "days_to_publish",
    "primary_violation",
    "severity",
    "requires_review",
    "report_generated_at",
]


def _safe_str(value: object) -> str:
    try:
        if value is None:
            return ""
        return str(value)
    except Exception:
        return ""


def _safe_list(value: object) -> list:
    try:
        return value if isinstance(value, list) else []
    except Exception:
        return []


def _row(contract: dict, generated_at: str) -> dict:
    try:
        data = contract if isinstance(contract, dict) else {}
        days_value = data.get("days_to_publish", None)
        if days_value is None:
            days_to_publish = ""
        else:
            try:
                days_to_publish = int(days_value)
            except Exception:
                days_to_publish = ""

        requires_review = "TRUE" if bool(data.get("requires_review", False)) else "FALSE"
        flags = "|".join(_safe_str(item) for item in _safe_list(data.get("flags", [])))

        mapped = {
            "processo_id": _safe_str(data.get("processo_id", "")),
            "agreement_level": _safe_str(data.get("agreement_level", "")),
            "R001": _safe_str(data.get("R001_verdict", "")),
            "R002": _safe_str(data.get("R002_verdict", "")),
            "R003": _safe_str(data.get("R003_verdict", "")),
            "R004": _safe_str(data.get("R004_verdict", "")),
            "conformity_score": _safe_str(data.get("conformity_score", "")),
            "overall_status": _safe_str(data.get("overall_status", "")),
            "flags": flags,
            "pipeline_stage": _safe_str(data.get("pipeline_stage", "")),
            "company_name": _safe_str(data.get("company_name", "")),
            "contract_value": _safe_str(data.get("contract_value", "")),
            "contract_date": _safe_str(data.get("contract_date", "")),
            "publication_date": _safe_str(data.get("publication_date", "")),
            "days_to_publish": days_to_publish,
            "primary_violation": _safe_str(data.get("primary_violation", "")),
            "severity": _safe_str(data.get("severity", "")),
            "requires_review": requires_review,
            "report_generated_at": _safe_str(generated_at),
        }

        return {column: mapped.get(column, "") for column in REPORT_CSV_COLUMNS}
    except Exception as exc:
        logger.warning("Failed to build CSV row: %s", exc)
        fallback = {column: "" for column in REPORT_CSV_COLUMNS}
        fallback["requires_review"] = "FALSE"
        fallback["report_generated_at"] = _safe_str(generated_at)
        return fallback


def write_report_csv(contracts: list[dict], output_path: Path, generated_at: str) -> Path:
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        rows = contracts if isinstance(contracts, list) else []

        with output_path.open("w", encoding="utf-8-sig", newline="") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=REPORT_CSV_COLUMNS)
            writer.writeheader()
            for contract in rows:
                writer.writerow(_row(contract if isinstance(contract, dict) else {}, generated_at))

        return output_path
    except Exception as exc:
        logger.warning("Failed to write report CSV '%s': %s", output_path, exc)
        return output_path


def build_report_csv_bytes(contracts: list[dict], generated_at: str) -> bytes:
    try:
        rows = contracts if isinstance(contracts, list) else []
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=REPORT_CSV_COLUMNS)
        writer.writeheader()
        for contract in rows:
            writer.writerow(_row(contract if isinstance(contract, dict) else {}, generated_at))
        return buffer.getvalue().encode("utf-8-sig")
    except Exception as exc:
        logger.warning("Failed to build report CSV bytes: %s", exc)
        fallback_buffer = io.StringIO()
        writer = csv.DictWriter(fallback_buffer, fieldnames=REPORT_CSV_COLUMNS)
        writer.writeheader()
        return fallback_buffer.getvalue().encode("utf-8-sig")
