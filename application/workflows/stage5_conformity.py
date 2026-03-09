"""
application/workflows/stage5_conformity.py

Stage 5 — Conformity Scoring & Reporting Engine.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from domain.services.conformity_engine import compute_conformity
from infrastructure.io.conformity_writer import (
    write_conformity_result,
    write_conformity_summary,
)
from infrastructure.io.csv_exporter import write_conformity_csv
from infrastructure.logging_config import setup_logging

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
COMPLIANCE_DIR = BASE_DIR / "data" / "compliance"
CONFORMITY_DIR = BASE_DIR / "data" / "conformity"
SUMMARY_PATH = BASE_DIR / "data" / "conformity_summary.json"
CSV_PATH = BASE_DIR / "data" / "conformity_export.csv"


def _load_json(path: Path) -> dict | None:
    if not path or not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Failed to load JSON %s: %s", path, exc)
        return None


def _resolve_fallback_sources(compliance_json: dict) -> tuple[dict | None, dict | None, bool]:
    inputs = compliance_json.get("inputs", {})
    contract_file = inputs.get("contract_file")
    publication_file = inputs.get("publication_file")

    contract_data = _load_json(BASE_DIR / contract_file) if contract_file else None
    publication_data = _load_json(BASE_DIR / publication_file) if publication_file else None

    used = bool(contract_data or publication_data)
    return contract_data, publication_data, used


def _build_csv_row(result: dict) -> dict:
    flags = "|".join(result.get("flags", []))
    breakdown = result.get("score_breakdown", {})
    return {
        "processo_id": result.get("processo_id"),
        "agreement_level": result.get("diagnostic", {}).get("agreement_level"),
        "R001": breakdown.get("R001", {}).get("verdict"),
        "R002": breakdown.get("R002", {}).get("verdict"),
        "R003": breakdown.get("R003", {}).get("verdict"),
        "R004": breakdown.get("R004", {}).get("verdict"),
        "conformity_score": result.get("conformity_score"),
        "overall_status": result.get("overall_status"),
        "flags": flags,
    }


def run_stage5_conformity(pid: str | None = None) -> dict:
    """Run Stage 5 conformity processing over compliance outputs."""
    t_start = time.monotonic()
    setup_logging("conformity")

    if not COMPLIANCE_DIR.exists():
        logger.warning("Compliance directory not found: %s", COMPLIANCE_DIR)
        return {
            "total_contracts": 0,
            "conformes": 0,
            "parciais": 0,
            "nao_conformes": 0,
            "incomplete": 0,
            "average_score": 0.0,
            "flagged_count": 0,
            "processing_time_seconds": round(time.monotonic() - t_start, 2),
        }

    files = sorted(COMPLIANCE_DIR.glob("*_compliance.json"))
    if pid:
        safe_pid = pid.replace("/", "_").replace("\\", "_")
        files = [f for f in files if f.name == f"{safe_pid}_compliance.json"]

    logger.info("Stage 5 starting with %d compliance file(s).", len(files))

    csv_rows: list[dict] = []
    summary = {
        "total_contracts": 0,
        "conformes": 0,
        "parciais": 0,
        "nao_conformes": 0,
        "incomplete": 0,
        "average_score": 0.0,
        "flagged_count": 0,
    }

    score_sum = 0.0
    fallback_usage = 0

    for file_path in files:
        compliance_json = _load_json(file_path)
        if not compliance_json:
            continue

        contract_data, publication_data, used_fallback = _resolve_fallback_sources(compliance_json)
        if used_fallback:
            fallback_usage += 1
            logger.info("Fallback source loaded for %s", compliance_json.get("processo_id"))

        result = compute_conformity(
            compliance_json,
            contract_preprocessed=contract_data,
            publication_structured=publication_data,
        )

        write_conformity_result(result.get("processo_id", "UNKNOWN"), result, CONFORMITY_DIR)
        csv_rows.append(_build_csv_row(result))

        summary["total_contracts"] += 1
        status = result.get("overall_status")
        if status == "CONFORME":
            summary["conformes"] += 1
        elif status == "PARCIAL":
            summary["parciais"] += 1
        elif status == "NÃO CONFORME":
            summary["nao_conformes"] += 1
        else:
            summary["incomplete"] += 1

        if result.get("flags"):
            summary["flagged_count"] += 1
        score_sum += float(result.get("conformity_score", 0.0))

        if result.get("diagnostic", {}).get("agreement_level") == "DIVERGENT":
            logger.warning("Diagnostic divergence for %s", result.get("processo_id"))
        if "MISSING_PUBLICATION" in result.get("flags", []):
            logger.warning("Missing publication case for %s", result.get("processo_id"))

    if summary["total_contracts"]:
        summary["average_score"] = round(score_sum / summary["total_contracts"], 2)

    summary["fallback_usage"] = fallback_usage
    summary["processing_time_seconds"] = round(time.monotonic() - t_start, 2)

    write_conformity_summary(summary, SUMMARY_PATH)
    write_conformity_csv(csv_rows, CSV_PATH)

    logger.info("Conformity stage complete: %s", summary)
    return summary


def _build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Stage 5 — Conformity Scoring & Reporting")
    parser.add_argument("--pid", type=str, default=None, help="Process single processo_id")
    return parser


if __name__ == "__main__":
    args = _build_cli().parse_args()
    run_stage5_conformity(pid=args.pid)
