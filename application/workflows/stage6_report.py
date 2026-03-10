from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from config.settings import DATA_DIR, LOGS_DIR, OUTPUTS_DIR
from infrastructure.io.state_index_builder import build_state_index, save_state_index
from infrastructure.io.report_aggregator import build_aggregate_report
from infrastructure.io.excel_writer import write_excel_report
from infrastructure.io.report_csv_writer import write_report_csv
from infrastructure.io.aggregate_json_writer import write_aggregate_json
from infrastructure.logging_config import setup_logging, add_error_log_file
from infrastructure.health_check import run_preflight

logger = logging.getLogger(__name__)


# DO NOT import full_pipeline. This module is standalone.


def _build_output_paths(datestamp: str) -> dict:
    try:
        stamp = str(datestamp)
        return {
            "excel": OUTPUTS_DIR / f"conformity_report_{stamp}.xlsx",
            "csv": OUTPUTS_DIR / f"conformity_report_{stamp}.csv",
            "json": OUTPUTS_DIR / f"conformity_aggregate_{stamp}.json",
        }
    except Exception as exc:
        logger.warning("Failed to build output paths: %s", exc)
        return {
            "excel": OUTPUTS_DIR / "conformity_report_.xlsx",
            "csv": OUTPUTS_DIR / "conformity_report_.csv",
            "json": OUTPUTS_DIR / "conformity_aggregate_.json",
        }


def _print_summary_table(summary: dict) -> None:
    try:
        status = str(summary.get("status", "")) if isinstance(summary, dict) else ""
        total_contracts = int((summary.get("total_contracts", 0) if isinstance(summary, dict) else 0) or 0)
        total_analyzed = int((summary.get("total_analyzed", 0) if isinstance(summary, dict) else 0) or 0)
        coverage_rate = float((summary.get("coverage_rate", 0.0) if isinstance(summary, dict) else 0.0) or 0.0)
        conformity_rate = float((summary.get("conformity_rate", 0.0) if isinstance(summary, dict) else 0.0) or 0.0)
        excel_path = summary.get("excel_path", None) if isinstance(summary, dict) else None
        csv_path = summary.get("csv_path", None) if isinstance(summary, dict) else None
        json_path = summary.get("json_path", None) if isinstance(summary, dict) else None
        processing_time_seconds = float(
            (summary.get("processing_time_seconds", 0.0) if isinstance(summary, dict) else 0.0) or 0.0
        )
        errors = summary.get("errors", []) if isinstance(summary, dict) and isinstance(summary.get("errors", []), list) else []

        lines = [
            "═══════════════════════════════════════",
            "  Stage 6 Report — Summary",
            "═══════════════════════════════════════",
            f"  Status          : {status}",
            f"  Contracts       : {total_contracts}",
            f"  Analyzed        : {total_analyzed}",
            f"  Coverage        : {coverage_rate:.1%}",
            f"  Conformity Rate : {conformity_rate:.1%}",
            f"  Excel           : {excel_path or '—'}",
            f"  CSV             : {csv_path or '—'}",
            f"  JSON            : {json_path or '—'}",
            f"  Time (s)        : {processing_time_seconds}",
            f"  Errors          : {len(errors)}",
            "═══════════════════════════════════════",
        ]
        sys.stdout.write("\n".join(lines) + "\n")
        sys.stdout.flush()
    except Exception as exc:
        logger.warning("Failed printing summary table: %s", exc)


def run_stage6_report(state_only: bool = False, report_only: bool = False, analyst_name: str = "") -> dict:
    try:
        t_start = time.monotonic()

        preflight = run_preflight(
            "stage6_report",
            require_discovery=True,
            require_browser=False,
        )
        if not preflight.passed:
            logger.error("Aborting stage6_report — pre-flight failed.")
            return {
                "status": "FAILED",
                "state_index_path": str(DATA_DIR / "dashboard_state_index.json"),
                "excel_path": None,
                "csv_path": None,
                "json_path": None,
                "log_path": str(LOGS_DIR),
                "total_contracts": 0,
                "total_analyzed": 0,
                "coverage_rate": 0.0,
                "conformity_rate": 0.0,
                "processing_time_seconds": round(time.monotonic() - t_start, 2),
                "errors": [],
                "preflight_failed": True,
                "preflight_errors": preflight.errors,
            }

        log_path = setup_logging("report")
        error_log_path = add_error_log_file()
        logger.info("Stage 6 report error log: %s", error_log_path)
        datestamp = datetime.now().strftime("%Y%m%d")
        paths = _build_output_paths(datestamp)
        errors: list[str] = []

        summary = {
            "status": "SUCCESS",
            "state_index_path": str(DATA_DIR / "dashboard_state_index.json"),
            "excel_path": None,
            "csv_path": None,
            "json_path": None,
            "log_path": log_path or str(LOGS_DIR),
            "total_contracts": 0,
            "total_analyzed": 0,
            "coverage_rate": 0.0,
            "conformity_rate": 0.0,
            "processing_time_seconds": 0.0,
            "errors": errors,
        }

        if not report_only:
            try:
                idx = build_state_index()
                save_state_index(idx)
                summary["total_contracts"] = int(idx.get("total_pids", 0) or 0) if isinstance(idx, dict) else 0
            except Exception as exc:
                errors.append(f"state_index: {exc}")
                summary["status"] = "PARTIAL"

        if not state_only:
            try:
                agg = build_aggregate_report()
                coverage = agg.get("coverage", {}) if isinstance(agg, dict) else {}
                conformity = agg.get("conformity_summary", {}) if isinstance(agg, dict) else {}
                summary["total_analyzed"] = int(coverage.get("total_analyzed", 0) or 0)
                summary["coverage_rate"] = float(coverage.get("coverage_rate", 0.0) or 0.0)
                summary["conformity_rate"] = float(conformity.get("overall_conformity_rate", 0.0) or 0.0)
            except Exception as exc:
                errors.append(f"aggregation: {exc}")
                summary["status"] = "FAILED" if not state_only else "PARTIAL"
                summary["processing_time_seconds"] = round(time.monotonic() - t_start, 2)
                return summary

            try:
                excel_path = write_excel_report(agg, paths["excel"], analyst_name=analyst_name)
                summary["excel_path"] = str(excel_path)
            except Exception as exc:
                errors.append(f"excel: {exc}")
                summary["status"] = "PARTIAL"

            try:
                csv_path = write_report_csv(agg.get("contracts", []) if isinstance(agg, dict) else [], paths["csv"], agg.get("generated_at", "") if isinstance(agg, dict) else "")
                summary["csv_path"] = str(csv_path)
            except Exception as exc:
                errors.append(f"csv: {exc}")
                summary["status"] = "PARTIAL"

            try:
                json_path = write_aggregate_json(agg, paths["json"])
                summary["json_path"] = str(json_path)
            except Exception as exc:
                errors.append(f"json: {exc}")
                summary["status"] = "PARTIAL"

        summary["processing_time_seconds"] = round(time.monotonic() - t_start, 2)
        _print_summary_table(summary)
        return summary
    except Exception as exc:
        logger.warning("Stage 6 report failed unexpectedly: %s", exc)
        return {
            "status": "FAILED",
            "state_index_path": str(DATA_DIR / "dashboard_state_index.json"),
            "excel_path": None,
            "csv_path": None,
            "json_path": None,
            "log_path": str(LOGS_DIR),
            "total_contracts": 0,
            "total_analyzed": 0,
            "coverage_rate": 0.0,
            "conformity_rate": 0.0,
            "processing_time_seconds": 0.0,
            "errors": [f"stage6_report: {exc}"],
        }


def _build_cli() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Stage 6 — Report Generation")
    p.add_argument("--state-only", action="store_true")
    p.add_argument("--report-only", action="store_true")
    p.add_argument("--analyst", type=str, default="")
    p.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"], default="INFO")
    p.add_argument("--version", type=str, default="1.0.0")
    return p


if __name__ == "__main__":
    args = _build_cli().parse_args()
    result = run_stage6_report(
        state_only=args.state_only,
        report_only=args.report_only,
        analyst_name=args.analyst,
    )
    sys.exit(0 if result.get("status", "FAILED") != "FAILED" else 1)
