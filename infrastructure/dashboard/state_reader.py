from __future__ import annotations

import glob
import json
import logging
from collections import deque
from datetime import datetime
from pathlib import Path

from config.settings import ALERTS_DIR, COMPLIANCE_DIR, CONFORMITY_DIR, DATA_DIR, EXTRACTIONS_DIR, LOGS_DIR, PREPROCESSED_DIR
from domain.services.alert_queue import build_alert_queue
from infrastructure.io.state_index_builder import STATE_INDEX_PATH, build_state_index, load_state_index, save_state_index
from infrastructure.io.report_aggregator import build_aggregate_report

logger = logging.getLogger(__name__)


def _cache_data(ttl: int):
    try:
        import streamlit as st

        return st.cache_data(ttl=ttl)
    except Exception:
        def _decorator(func):
            return func

        return _decorator


def _sanitize(pid: str) -> str:
    try:
        return str(pid).replace("/", "_").replace("\\", "_")
    except Exception:
        return ""


def _load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Could not parse %s: %s", path, exc)
        return None


@_cache_data(ttl=30)
def read_state_index() -> dict:
    try:
        idx = load_state_index(path=STATE_INDEX_PATH)
        if not isinstance(idx, dict):
            idx = {"contracts": {}, "stage_counts": {}, "total_pids": 0}

        total_pids = int(idx.get("total_pids", 0) or 0)
        if total_pids == 0:
            idx = build_state_index()
            save_state_index(idx, output_path=STATE_INDEX_PATH)
        return idx if isinstance(idx, dict) else {"contracts": {}, "stage_counts": {}, "total_pids": 0}
    except Exception as exc:
        logger.warning("Failed to read state index: %s", exc)
        return {"contracts": {}, "stage_counts": {}, "total_pids": 0}


@_cache_data(ttl=60)
def read_aggregate_report() -> dict:
    try:
        report = build_aggregate_report()
        return report if isinstance(report, dict) else {
            "generated_at": "",
            "coverage": {},
            "conformity_summary": {},
            "rule_averages": {},
            "contracts": [],
        }
    except Exception as exc:
        logger.warning("Failed to read aggregate report: %s", exc)
        return {
            "generated_at": "",
            "coverage": {},
            "conformity_summary": {},
            "rule_averages": {},
            "contracts": [],
        }


def read_processo_detail(pid: str) -> dict:
    try:
        pid_safe = _sanitize(pid)
        return {
            "raw": _load_json(EXTRACTIONS_DIR / f"{pid_safe}_raw.json"),
            "pub_raw": _load_json(EXTRACTIONS_DIR / f"{pid_safe}_publications_raw.json"),
            "preprocessed": _load_json(PREPROCESSED_DIR / f"{pid_safe}_preprocessed.json"),
            "pub_structured": _load_json(PREPROCESSED_DIR / f"{pid_safe}_publication_structured.json"),
            "compliance": _load_json(COMPLIANCE_DIR / f"{pid_safe}_compliance.json"),
            "conformity": _load_json(CONFORMITY_DIR / f"{pid_safe}_conformity.json"),
            "alert": _load_json(ALERTS_DIR / f"{pid_safe}_alert.json"),
        }
    except Exception as exc:
        logger.warning("Failed to read processo detail for %s: %s", pid, exc)
        return {
            "raw": None,
            "pub_raw": None,
            "preprocessed": None,
            "pub_structured": None,
            "compliance": None,
            "conformity": None,
            "alert": None,
        }


def read_all_alerts() -> list[dict]:
    try:
        import domain.services.alert_queue as alert_queue

        if not ALERTS_DIR.exists():
            return []

        paths = sorted(ALERTS_DIR.glob("*.json"))
        if not paths:
            return []

        alerts: list[dict] = []
        for path in paths:
            data = _load_json(path)
            if isinstance(data, dict):
                alerts.append(data)

        if not alerts:
            return []

        queue_items = alert_queue.build_alert_queue(alerts)
        lookup: dict[str, dict] = {}
        for alert in alerts:
            processo_id = str(alert.get("processo_id", ""))
            if processo_id:
                lookup[processo_id] = alert

        ordered: list[dict] = []
        used_ids: set[str] = set()
        for item in queue_items:
            processo_id = str(item.get("processo_id", ""))
            if processo_id in lookup:
                ordered.append(lookup[processo_id])
                used_ids.add(processo_id)

        ok_tail: list[dict] = []
        for alert in alerts:
            processo_id = str(alert.get("processo_id", ""))
            if processo_id in used_ids:
                continue
            if str(alert.get("alert_level", "")) == "OK":
                ok_tail.append(alert)

        return ordered + ok_tail
    except Exception as exc:
        logger.warning("Failed to read all alerts: %s", exc)
        return []


def read_errors() -> dict:
    result = {"stage2": [], "stage3": [], "stage4": []}
    try:
        stage_specs = {
            "stage2": (DATA_DIR / "extraction_progress.json", "failed"),
            "stage3": (DATA_DIR / "publication_extraction_progress.json", "failed"),
            "stage4": (DATA_DIR / "compliance_progress.json", "failed"),
        }

        for stage_name, (path, failed_key) in stage_specs.items():
            data = _load_json(path)
            if not isinstance(data, dict):
                continue
            failed = data.get(failed_key, [])
            if not isinstance(failed, list):
                continue

            normalized: list[dict] = []
            for entry in failed:
                item = entry if isinstance(entry, dict) else {}
                normalized.append(
                    {
                        "processo_id": str(item.get("processo_id", "") or ""),
                        "error": str(item.get("error", "") or ""),
                        "at": str(item.get("at", "") or ""),
                    }
                )
            result[stage_name] = normalized

        return result
    except Exception as exc:
        logger.warning("Failed to read errors: %s", exc)
        return result


def read_discovery_summary() -> dict:
    try:
        summary_path = DATA_DIR / "discovery" / "discovery_summary.json"
        summary_data = _load_json(summary_path)
        if isinstance(summary_data, dict):
            return summary_data

        fallback_path = DATA_DIR / "discovery" / "processo_links.json"
        fallback_data = _load_json(fallback_path)
        if isinstance(fallback_data, dict):
            return {key: value for key, value in fallback_data.items() if key != "processos"}

        return {}
    except Exception as exc:
        logger.warning("Failed to read discovery summary: %s", exc)
        return {}


def list_output_files() -> list[dict]:
    try:
        outputs_dir = DATA_DIR / "outputs"
        if not outputs_dir.exists():
            return []

        paths: list[Path] = []
        for pattern in ("*.xlsx", "*.csv", "*.json"):
            for raw_path in glob.glob(str(outputs_dir / pattern)):
                paths.append(Path(raw_path))

        if not paths:
            return []

        paths = sorted(paths, key=lambda p: p.stat().st_mtime, reverse=True)
        rows: list[dict] = []
        for path in paths:
            stat = path.stat()
            rows.append(
                {
                    "name": path.name,
                    "path": str(path),
                    "size_kb": round(stat.st_size / 1024, 1),
                    "modified_at": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                }
            )
        return rows
    except Exception as exc:
        logger.warning("Failed to list output files: %s", exc)
        return []


@_cache_data(ttl=5)
def read_log_tail(stage_name: str, lines: int = 50) -> list[str]:
    try:
        max_lines = int(lines) if int(lines) > 0 else 50
        pattern = str(LOGS_DIR / f"{stage_name}_*.log")
        matches = [Path(path) for path in glob.glob(pattern)]
        if not matches:
            return []

        latest = max(matches, key=lambda p: p.stat().st_mtime)
        buffer: deque[str] = deque(maxlen=max_lines)
        with latest.open("r", encoding="utf-8") as log_file:
            for line in log_file:
                buffer.append(line.rstrip("\n"))
        return list(buffer)
    except Exception as exc:
        logger.warning("Failed to read log tail for '%s': %s", stage_name, exc)
        return []
