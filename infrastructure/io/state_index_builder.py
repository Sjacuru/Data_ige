from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from config.settings import (
    ALERTS_DIR,
    COMPLIANCE_DIR,
    CONFORMITY_DIR,
    DATA_DIR,
    EXTRACTIONS_DIR,
    PREPROCESSED_DIR,
)

logger = logging.getLogger(__name__)

DISCOVERY_FILE = DATA_DIR / "discovery" / "processo_links.json"
STATE_INDEX_PATH = DATA_DIR / "dashboard_state_index.json"

# Ordered evaluation — first match wins
_STAGE_ORDER = [
    "SCORED",
    "COMPLIANCE",
    "PREPROCESSED",
    "PUB_FOUND",
    "EXTRACTED",
    "DISCOVERED",
]


def _empty_index_skeleton() -> dict:
    return {
        "built_at": "",
        "total_pids": 0,
        "stage_counts": {
            "SCORED": 0,
            "COMPLIANCE": 0,
            "PREPROCESSED": 0,
            "PUB_FOUND": 0,
            "EXTRACTED": 0,
            "DISCOVERED": 0,
        },
        "contracts": {},
    }


def _empty_load_skeleton() -> dict:
    return {
        "contracts": {},
        "stage_counts": {},
        "total_pids": 0,
    }


def _sanitize(pid: str) -> str:
    try:
        return str(pid).replace("/", "_").replace("\\", "_")
    except Exception as exc:
        logger.warning("Failed to sanitize pid '%s': %s", pid, exc)
        return ""


def _has_error_flag(json_path: Path) -> bool:
    try:
        if not json_path.exists():
            return False
        data = json.loads(json_path.read_text(encoding="utf-8"))

        if isinstance(data, dict) and "error" in data:
            return True

        if str(json_path).endswith("_compliance.json") and isinstance(data, dict):
            overall = data.get("overall", {}) if isinstance(data.get("overall", {}), dict) else {}
            status = str(overall.get("status", ""))
            review_reason = str(overall.get("review_reason", ""))
            if status == "INCONCLUSIVE" and "error" in review_reason.lower():
                return True

        return False
    except Exception as exc:
        logger.warning("Failed to inspect error flag in %s: %s", json_path, exc)
        return False


def _compute_stage(pid_safe: str) -> str:
    try:
        conformity_path = CONFORMITY_DIR / f"{pid_safe}_conformity.json"
        compliance_path = COMPLIANCE_DIR / f"{pid_safe}_compliance.json"
        preprocessed_path = PREPROCESSED_DIR / f"{pid_safe}_preprocessed.json"
        publication_structured_path = PREPROCESSED_DIR / f"{pid_safe}_publication_structured.json"
        publication_raw_path = EXTRACTIONS_DIR / f"{pid_safe}_publications_raw.json"
        raw_path = EXTRACTIONS_DIR / f"{pid_safe}_raw.json"

        if conformity_path.exists():
            return "SCORED"
        if compliance_path.exists():
            return "COMPLIANCE"
        if preprocessed_path.exists() and publication_structured_path.exists():
            return "PREPROCESSED"
        if publication_raw_path.exists():
            return "PUB_FOUND"
        if raw_path.exists():
            return "EXTRACTED"
        return "DISCOVERED"
    except Exception as exc:
        logger.warning("Failed to compute stage for '%s': %s", pid_safe, exc)
        return "DISCOVERED"


def build_state_index(discovery_file: Path = DISCOVERY_FILE) -> dict:
    try:
        skeleton = _empty_index_skeleton()

        if not discovery_file.exists():
            logger.warning("Discovery file not found: %s", discovery_file)
            return skeleton

        try:
            discovery_data = json.loads(discovery_file.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Failed to load discovery file %s: %s", discovery_file, exc)
            return skeleton

        processos = discovery_data.get("processos", []) if isinstance(discovery_data, dict) else []
        if not isinstance(processos, list):
            logger.warning("Invalid discovery schema in %s: 'processos' is not a list", discovery_file)
            return skeleton

        contracts: dict = {}
        stage_counts = {
            "SCORED": 0,
            "COMPLIANCE": 0,
            "PREPROCESSED": 0,
            "PUB_FOUND": 0,
            "EXTRACTED": 0,
            "DISCOVERED": 0,
        }

        for item in processos:
            if not isinstance(item, dict):
                continue
            pid = str(item.get("processo_id", ""))
            if not pid:
                continue

            pid_safe = _sanitize(pid)
            if not pid_safe:
                continue

            stage = _compute_stage(pid_safe)

            raw_path = EXTRACTIONS_DIR / f"{pid_safe}_raw.json"
            pub_raw_path = EXTRACTIONS_DIR / f"{pid_safe}_publications_raw.json"
            preprocessed_path = PREPROCESSED_DIR / f"{pid_safe}_preprocessed.json"
            pub_structured_path = PREPROCESSED_DIR / f"{pid_safe}_publication_structured.json"
            compliance_path = COMPLIANCE_DIR / f"{pid_safe}_compliance.json"
            conformity_path = CONFORMITY_DIR / f"{pid_safe}_conformity.json"

            error_flag = False
            if conformity_path.exists():
                error_flag = _has_error_flag(conformity_path)
            elif compliance_path.exists():
                error_flag = _has_error_flag(compliance_path)
            elif preprocessed_path.exists():
                error_flag = _has_error_flag(preprocessed_path)
            elif pub_raw_path.exists():
                error_flag = _has_error_flag(pub_raw_path)
            elif raw_path.exists():
                error_flag = _has_error_flag(raw_path)

            contracts[pid_safe] = {
                "processo_id": pid,
                "pipeline_stage": stage,
                "has_raw": raw_path.exists(),
                "has_pub_raw": pub_raw_path.exists(),
                "has_preprocessed": preprocessed_path.exists(),
                "has_pub_structured": pub_structured_path.exists(),
                "has_compliance": compliance_path.exists(),
                "has_conformity": conformity_path.exists(),
                "error_flag": bool(error_flag),
            }

            if stage in stage_counts:
                stage_counts[stage] += 1

        return {
            "built_at": datetime.now().isoformat(),
            "total_pids": len(contracts),
            "stage_counts": stage_counts,
            "contracts": contracts,
        }
    except Exception as exc:
        logger.warning("Failed to build state index: %s", exc)
        return _empty_index_skeleton()


def save_state_index(index: dict, output_path: Path = STATE_INDEX_PATH) -> Path:
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = index if isinstance(index, dict) else {}
        output_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return output_path
    except Exception as exc:
        logger.warning("Failed to save state index to %s: %s", output_path, exc)
        return output_path


def load_state_index(path: Path = STATE_INDEX_PATH) -> dict:
    try:
        if not path.exists():
            return _empty_load_skeleton()
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else _empty_load_skeleton()
    except Exception as exc:
        logger.warning("Failed to load state index from %s: %s", path, exc)
        return _empty_load_skeleton()
