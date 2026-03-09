from __future__ import annotations

import glob
import json
import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

from config.settings import DATA_DIR, OUTPUTS_DIR
from application.workflows.stage4_compliance import run_stage4_compliance
from application.workflows.stage5_conformity import run_stage5_conformity
from application.workflows.stage6_alerts import run_stage6_alerts
from application.workflows.stage6_report import run_stage6_report

logger = logging.getLogger(__name__)

_RUNNING_STAGE: str | None = None
_RUNNING_PROC: subprocess.Popen | None = None
_RUNNING_THREAD: threading.Thread | None = None
_STOP_EVENT = threading.Event()
_LOCK = threading.Lock()

STAGE_SCRIPTS: dict[str, str] = {
    "stage1": "application/main.py",
    "stage2": "application/workflows/stage2_extraction.py",
    "stage3": "application/workflows/stage3_publication.py",
}

STAGE_PROGRESS_FILES: dict[str, Any] = {
    "stage1": DATA_DIR / "discovery" / "processo_links.json",
    "stage2": DATA_DIR / "extraction_progress.json",
    "stage3": DATA_DIR / "publication_extraction_progress.json",
    "stage4": DATA_DIR / "compliance_progress.json",
    "stage5": DATA_DIR / "conformity_summary.json",
    "stage6_alerts": DATA_DIR / "alerts_summary.json",
    "stage6_report": OUTPUTS_DIR,
}


def get_running_stage() -> str | None:
    try:
        with _LOCK:
            return _RUNNING_STAGE
    except Exception as exc:
        logger.warning("Failed to get running stage: %s", exc)
        return None


def is_any_running() -> bool:
    try:
        return get_running_stage() is not None
    except Exception as exc:
        logger.warning("Failed to check running stage: %s", exc)
        return False


def _set_running(stage: str | None) -> None:
    try:
        with _LOCK:
            global _RUNNING_STAGE
            _RUNNING_STAGE = stage
    except Exception as exc:
        logger.warning("Failed to set running stage '%s': %s", stage, exc)


def _parse_stage_progress(stage_name: str, data: dict) -> tuple[int, int, int]:
    try:
        if not isinstance(data, dict):
            return 0, 0, 0

        if stage_name == "stage1":
            total = int(data.get("total_processos", 0) or 0)
            completed = total if total > 0 else 0
            failed = 0
            return total, completed, failed

        if stage_name in ("stage2", "stage3"):
            completed_list = data.get("completed", [])
            completed_list = completed_list if isinstance(completed_list, list) else []
            stats = data.get("stats", {}) if isinstance(data.get("stats", {}), dict) else {}
            total = int(stats.get("total", len(completed_list)) or 0)
            completed = len(completed_list) if completed_list else int(stats.get("success", 0) or 0)
            failed_list = data.get("failed", [])
            failed_list = failed_list if isinstance(failed_list, list) else []
            failed = len(failed_list)
            return int(total), int(completed), int(failed)

        if stage_name == "stage4":
            stats = data.get("stats", {}) if isinstance(data.get("stats", {}), dict) else {}
            total = int(stats.get("total", 0) or 0)
            completed = int(stats.get("completed", 0) or 0)
            failed = int(stats.get("failed", 0) or 0)
            return total, completed, failed

        if stage_name in ("stage5", "stage6_alerts"):
            total = int(data.get("total_contracts", 0) or 0)
            completed = total
            failed = 0
            return total, completed, failed

        if stage_name == "stage6_report":
            coverage = data.get("coverage", {}) if isinstance(data.get("coverage", {}), dict) else {}
            total = int(coverage.get("total_analyzed", 0) or 0)
            completed = total
            failed = 0
            return total, completed, failed

        return 0, 0, 0
    except Exception as exc:
        logger.warning("Failed parsing progress for '%s': %s", stage_name, exc)
        return 0, 0, 0


def get_stage_status(stage_name: str) -> dict:
    base = {
        "stage": stage_name,
        "status": "NOT_STARTED",
        "total": 0,
        "completed": 0,
        "failed_count": 0,
        "last_run": None,
        "progress_pct": 0.0,
    }

    try:
        with _LOCK:
            running_now = _RUNNING_STAGE == stage_name
        if running_now:
            base["status"] = "IN_PROGRESS"

        progress_path: Path | None = None
        if stage_name == "stage6_report":
            pattern = str(OUTPUTS_DIR / "conformity_aggregate_*.json")
            candidates = glob.glob(pattern)
            if candidates:
                latest = max(candidates, key=lambda p: Path(p).stat().st_mtime)
                progress_path = Path(latest)
        else:
            value = STAGE_PROGRESS_FILES.get(stage_name)
            progress_path = value if isinstance(value, Path) else None

        if progress_path is None or not progress_path.exists():
            return base

        try:
            data = json.loads(progress_path.read_text(encoding="utf-8"))
        except Exception:
            return base

        total, completed, failed_count = _parse_stage_progress(stage_name, data if isinstance(data, dict) else {})

        last_run = None
        if isinstance(data, dict):
            last_run = data.get("updated_at") or data.get("built_at") or data.get("generated_at") or None

        with _LOCK:
            running_now = _RUNNING_STAGE == stage_name

        if running_now:
            status = "IN_PROGRESS"
        elif failed_count > 0 and completed == 0:
            status = "FAILED"
        elif total > 0 and completed >= total:
            status = "COMPLETE"
        elif completed > 0:
            status = "IN_PROGRESS"
        else:
            status = "NOT_STARTED"

        progress_pct = round((completed / total) * 100, 1) if total > 0 else 0.0

        base["status"] = status
        base["total"] = int(total)
        base["completed"] = int(completed)
        base["failed_count"] = int(failed_count)
        base["last_run"] = last_run
        base["progress_pct"] = float(progress_pct)
        return base
    except Exception as exc:
        logger.warning("Failed to get stage status for '%s': %s", stage_name, exc)
        return base


def _run_subprocess_stage(stage_name: str, headless: bool) -> None:
    global _RUNNING_PROC
    try:
        cmd = [sys.executable, STAGE_SCRIPTS[stage_name]]
        if headless:
            cmd.append("--headless")
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        _RUNNING_PROC = subprocess.Popen(cmd, env=env)
        _RUNNING_PROC.wait()
    except Exception as exc:
        logger.warning("Failed running subprocess stage '%s': %s", stage_name, exc)
    finally:
        _RUNNING_PROC = None
        _set_running(None)


def _run_thread_stage(stage_name: str, pid_filter: str | None, rerun_failed: bool, analyst_name: str) -> None:
    try:
        if stage_name == "stage4":
            run_stage4_compliance(pid_filter=pid_filter, dry_run=False, rerun_failed=rerun_failed)
        elif stage_name == "stage5":
            run_stage5_conformity(pid=pid_filter)
        elif stage_name == "stage6_alerts":
            run_stage6_alerts(pid=pid_filter)
        elif stage_name == "stage6_report":
            run_stage6_report(analyst_name=analyst_name)
        elif stage_name == "full":
            run_stage4_compliance(rerun_failed=rerun_failed)
            run_stage5_conformity()
            run_stage6_alerts()
            run_stage6_report(analyst_name=analyst_name)
    except Exception as exc:
        logger.warning("Failed running thread stage '%s': %s", stage_name, exc)
    finally:
        _set_running(None)


def launch_stage(
    stage_name: str,
    headless: bool = True,
    pid_filter: str | None = None,
    rerun_failed: bool = False,
    analyst_name: str = "",
) -> bool:
    global _RUNNING_THREAD
    try:
        with _LOCK:
            global _RUNNING_STAGE
            if _RUNNING_STAGE is not None:
                return False
            _RUNNING_STAGE = stage_name

        _STOP_EVENT.clear()

        if stage_name in STAGE_SCRIPTS:
            thread = threading.Thread(target=_run_subprocess_stage, args=(stage_name, headless), daemon=True)
        else:
            thread = threading.Thread(
                target=_run_thread_stage,
                args=(stage_name, pid_filter, rerun_failed, analyst_name),
                daemon=True,
            )

        _RUNNING_THREAD = thread
        thread.start()
        return True
    except Exception as exc:
        logger.warning("Failed to launch stage '%s': %s", stage_name, exc)
        _set_running(None)
        return False


def stop_running_stage() -> bool:
    try:
        with _LOCK:
            global _RUNNING_STAGE
            if _RUNNING_STAGE is None:
                return False
            _STOP_EVENT.set()
            if _RUNNING_PROC is not None:
                try:
                    _RUNNING_PROC.terminate()
                except Exception:
                    pass
            _RUNNING_STAGE = None
        return True
    except Exception as exc:
        logger.warning("Failed to stop running stage: %s", exc)
        return False
