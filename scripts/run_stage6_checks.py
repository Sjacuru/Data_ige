"""Run Stage 6 checks and emit a compact completion report."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import OUTPUTS_DIR


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _run_test(test_path: str) -> dict:
    command = [sys.executable, test_path]
    started_at = datetime.now().isoformat()
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(PROJECT_ROOT),
        env=env,
    )
    ended_at = datetime.now().isoformat()
    return {
        "test": test_path,
        "command": " ".join(command),
        "started_at": started_at,
        "ended_at": ended_at,
        "exit_code": completed.returncode,
        "passed": completed.returncode == 0,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def run_stage6_checks() -> dict:
    test_targets = [
        "tests/test_stage6_alerts.py",
        "tests/test_stage6_integration.py",
    ]
    results = [_run_test(test_path) for test_path in test_targets]

    passed = all(result["passed"] for result in results)
    report = {
        "epic": "Epic 6",
        "generated_at": datetime.now().isoformat(),
        "overall_passed": passed,
        "tests_total": len(results),
        "tests_passed": sum(1 for result in results if result["passed"]),
        "results": results,
    }

    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = OUTPUTS_DIR / "epic6_completion_report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return report


if __name__ == "__main__":
    summary = run_stage6_checks()
    print(json.dumps({
        "overall_passed": summary["overall_passed"],
        "tests_total": summary["tests_total"],
        "tests_passed": summary["tests_passed"],
        "report": str(OUTPUTS_DIR / "epic6_completion_report.json"),
    }, ensure_ascii=False, indent=2))
