from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from dateutil import parser as date_parser

from config.settings import (
    ALERTS_DIR,
    COMPLIANCE_DIR,
    CONFORMITY_DIR,
    DATA_DIR,
    EXTRACTIONS_DIR,
    PREPROCESSED_DIR,
)
from infrastructure.io.state_index_builder import build_state_index, DISCOVERY_FILE

logger = logging.getLogger(__name__)


def _load_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _sanitize(pid: str) -> str:
    try:
        return str(pid).replace("/", "_").replace("\\", "_")
    except Exception as exc:
        logger.warning("Failed to sanitize pid '%s': %s", pid, exc)
        return ""


def _load_raw_metadata(pid_safe: str) -> dict:
    try:
        path = EXTRACTIONS_DIR / f"{pid_safe}_raw.json"
        data = _load_json(path) or {}
        return {
            "company_name": str(data.get("company_name", "")) if isinstance(data, dict) else "",
            "contract_value": str(data.get("contract_value", "")) if isinstance(data, dict) else "",
        }
    except Exception as exc:
        logger.warning("Failed loading raw metadata for %s: %s", pid_safe, exc)
        return {"company_name": "", "contract_value": ""}


def _load_publication_date(pid_safe: str) -> str:
    try:
        path = PREPROCESSED_DIR / f"{pid_safe}_publication_structured.json"
        data = _load_json(path) or {}
        return str(data.get("publication_date", "")) if isinstance(data, dict) else ""
    except Exception as exc:
        logger.warning("Failed loading publication date for %s: %s", pid_safe, exc)
        return ""


def _load_contract_date(pid_safe: str) -> str:
    try:
        path = PREPROCESSED_DIR / f"{pid_safe}_preprocessed.json"
        data = _load_json(path) or {}
        return str(data.get("signing_date", "")) if isinstance(data, dict) else ""
    except Exception as exc:
        logger.warning("Failed loading contract date for %s: %s", pid_safe, exc)
        return ""


def _compute_days_to_publish(contract_date: str, pub_date: str) -> int | None:
    try:
        if not contract_date or not pub_date:
            return None
        contract_dt = date_parser.parse(contract_date)
        publication_dt = date_parser.parse(pub_date)
        return int((publication_dt - contract_dt).days)
    except Exception:
        return None


def _derive_primary_violation(score_breakdown: dict) -> str:
    try:
        if not isinstance(score_breakdown, dict):
            return ""
        for rule_name in ("R001", "R002", "R003", "R004"):
            verdict = str(score_breakdown.get(rule_name, {}).get("verdict", ""))
            if verdict == "FAIL":
                return rule_name
        return ""
    except Exception as exc:
        logger.warning("Failed deriving primary violation: %s", exc)
        return ""


def _derive_severity(score: float) -> str:
    try:
        if float(score) >= 90.0:
            return "BAIXA"
        if float(score) >= 60.0:
            return "MÉDIA"
        return "ALTA"
    except Exception as exc:
        logger.warning("Failed deriving severity from score '%s': %s", score, exc)
        return "ALTA"


def _load_conformity_files() -> list[dict]:
    try:
        if not CONFORMITY_DIR.exists():
            return []
        rows: list[dict] = []
        for path in sorted(CONFORMITY_DIR.glob("*_conformity.json")):
            data = _load_json(path)
            if isinstance(data, dict):
                rows.append(data)
        return rows
    except Exception as exc:
        logger.warning("Failed loading conformity files: %s", exc)
        return []


def build_aggregate_report(discovery_file: Path = DISCOVERY_FILE, state_index: dict | None = None) -> dict:
    try:
        if not isinstance(state_index, dict):
            state_index = build_state_index(discovery_file=discovery_file)

        contracts_index = state_index.get("contracts", {}) if isinstance(state_index, dict) else {}
        if not isinstance(contracts_index, dict):
            contracts_index = {}

        conformity_rows = _load_conformity_files()
        conformity_by_safe: dict[str, dict] = {}
        for row in conformity_rows:
            try:
                pid = str(row.get("processo_id", ""))
                pid_safe = _sanitize(pid)
                if pid_safe:
                    conformity_by_safe[pid_safe] = row
            except Exception:
                continue

        contract_rows: list[dict] = []
        flag_counts: dict[str, int] = {}

        analyzed_count = 0
        sum_scores = 0.0
        status_counts = {
            "CONFORME": 0,
            "PARCIAL": 0,
            "NÃO CONFORME": 0,
            "INCOMPLETE": 0,
        }

        rule_totals = {"R001": 0.0, "R002": 0.0, "R003": 0.0, "R004": 0.0}

        for pid_safe, state_meta in contracts_index.items():
            try:
                if not isinstance(state_meta, dict):
                    state_meta = {}

                conformity = conformity_by_safe.get(pid_safe)
                compliance = _load_json(COMPLIANCE_DIR / f"{pid_safe}_compliance.json") or None
                raw_meta = _load_raw_metadata(pid_safe)
                publication_date = _load_publication_date(pid_safe)
                contract_date = _load_contract_date(pid_safe)

                score_breakdown = {}
                diagnostic = {}
                overall_status = ""
                conformity_score = 0.0
                flags: list[str] = []
                recommendations: list[str] = []
                requires_review = False

                if isinstance(conformity, dict):
                    score_breakdown = conformity.get("score_breakdown", {}) if isinstance(conformity.get("score_breakdown", {}), dict) else {}
                    diagnostic = conformity.get("diagnostic", {}) if isinstance(conformity.get("diagnostic", {}), dict) else {}
                    overall_status = str(conformity.get("overall_status", ""))
                    try:
                        conformity_score = float(conformity.get("conformity_score", 0.0) or 0.0)
                    except Exception:
                        conformity_score = 0.0
                    flags = conformity.get("flags", []) if isinstance(conformity.get("flags", []), list) else []
                    recommendations = conformity.get("recommendations", []) if isinstance(conformity.get("recommendations", []), list) else []
                    requires_review = bool(conformity.get("requires_review", False))

                    analyzed_count += 1
                    sum_scores += conformity_score
                    if overall_status in status_counts:
                        status_counts[overall_status] += 1

                r001_score = float(score_breakdown.get("R001", {}).get("score", 0.0) or 0.0)
                r002_score = float(score_breakdown.get("R002", {}).get("score", 0.0) or 0.0)
                r003_score = float(score_breakdown.get("R003", {}).get("score", 0.0) or 0.0)
                r004_score = float(score_breakdown.get("R004", {}).get("score", 0.0) or 0.0)

                if conformity is not None:
                    rule_totals["R001"] += r001_score
                    rule_totals["R002"] += r002_score
                    rule_totals["R003"] += r003_score
                    rule_totals["R004"] += r004_score

                for flag in flags:
                    flag_key = str(flag)
                    flag_counts[flag_key] = flag_counts.get(flag_key, 0) + 1

                row = {
                    "processo_id": str(state_meta.get("processo_id", "")),
                    "pid_safe": str(pid_safe),
                    "pipeline_stage": str(state_meta.get("pipeline_stage", "")),
                    "company_name": str(raw_meta.get("company_name", "")),
                    "contract_value": str(raw_meta.get("contract_value", "")),
                    "contract_date": str(contract_date),
                    "publication_date": str(publication_date),
                    "days_to_publish": _compute_days_to_publish(contract_date, publication_date),
                    "overall_status": overall_status,
                    "conformity_score": float(conformity_score),
                    "agreement_level": str(diagnostic.get("agreement_level", "")),
                    "R001_score": r001_score,
                    "R001_verdict": str(score_breakdown.get("R001", {}).get("verdict", "")),
                    "R002_score": r002_score,
                    "R002_verdict": str(score_breakdown.get("R002", {}).get("verdict", "")),
                    "R003_score": r003_score,
                    "R003_verdict": str(score_breakdown.get("R003", {}).get("verdict", "")),
                    "R004_score": r004_score,
                    "R004_verdict": str(score_breakdown.get("R004", {}).get("verdict", "")),
                    "flags": flags,
                    "recommendations": recommendations,
                    "requires_review": bool(requires_review),
                    "primary_violation": _derive_primary_violation(score_breakdown),
                    "severity": _derive_severity(float(conformity_score)),
                    "error_flag": bool(state_meta.get("error_flag", False)),
                }

                contract_rows.append(row)
            except Exception as exc:
                logger.warning("Failed building row for %s: %s", pid_safe, exc)
                continue

        total_discovered = int(state_index.get("total_pids", 0) if isinstance(state_index, dict) else 0)
        total_extracted = sum(1 for row in contract_rows if bool((contracts_index.get(row.get("pid_safe", ""), {}) or {}).get("has_raw", False)))
        total_pub_found = sum(1 for row in contract_rows if bool((contracts_index.get(row.get("pid_safe", ""), {}) or {}).get("has_pub_raw", False)))
        total_preprocessed = sum(
            1
            for row in contract_rows
            if bool((contracts_index.get(row.get("pid_safe", ""), {}) or {}).get("has_preprocessed", False))
            and bool((contracts_index.get(row.get("pid_safe", ""), {}) or {}).get("has_pub_structured", False))
        )
        total_analyzed = analyzed_count

        coverage_rate = float(total_analyzed / total_discovered) if total_discovered > 0 else 0.0
        overall_conformity_rate = float(status_counts["CONFORME"] / total_analyzed) if total_analyzed > 0 else 0.0
        average_score = float(sum_scores / total_analyzed) if total_analyzed > 0 else 0.0

        rule_averages = {
            "R001": float(rule_totals["R001"] / total_analyzed) if total_analyzed > 0 else 0.0,
            "R002": float(rule_totals["R002"] / total_analyzed) if total_analyzed > 0 else 0.0,
            "R003": float(rule_totals["R003"] / total_analyzed) if total_analyzed > 0 else 0.0,
            "R004": float(rule_totals["R004"] / total_analyzed) if total_analyzed > 0 else 0.0,
        }

        top_flags = [
            item[0]
            for item in sorted(flag_counts.items(), key=lambda kv: kv[1], reverse=True)[:10]
        ]

        return {
            "generated_at": datetime.now().isoformat(),
            "coverage": {
                "total_discovered": int(total_discovered),
                "total_extracted": int(total_extracted),
                "total_pub_found": int(total_pub_found),
                "total_preprocessed": int(total_preprocessed),
                "total_analyzed": int(total_analyzed),
                "coverage_rate": float(coverage_rate),
            },
            "conformity_summary": {
                "CONFORME": int(status_counts["CONFORME"]),
                "PARCIAL": int(status_counts["PARCIAL"]),
                "NÃO CONFORME": int(status_counts["NÃO CONFORME"]),
                "INCOMPLETE": int(status_counts["INCOMPLETE"]),
                "overall_conformity_rate": float(overall_conformity_rate),
                "average_score": float(average_score),
            },
            "rule_averages": rule_averages,
            "top_flags": list(top_flags),
            "contracts": list(contract_rows),
        }
    except Exception as exc:
        logger.warning("Failed to build aggregate report: %s", exc)
        return {
            "generated_at": "",
            "coverage": {
                "total_discovered": 0,
                "total_extracted": 0,
                "total_pub_found": 0,
                "total_preprocessed": 0,
                "total_analyzed": 0,
                "coverage_rate": 0.0,
            },
            "conformity_summary": {
                "CONFORME": 0,
                "PARCIAL": 0,
                "NÃO CONFORME": 0,
                "INCOMPLETE": 0,
                "overall_conformity_rate": 0.0,
                "average_score": 0.0,
            },
            "rule_averages": {"R001": 0.0, "R002": 0.0, "R003": 0.0, "R004": 0.0},
            "top_flags": [],
            "contracts": [],
        }
