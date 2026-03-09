"""application/workflows/full_pipeline.py

Minimal pipeline runner for late-stage deterministic workflows.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from application.workflows.stage5_conformity import run_stage5_conformity
from application.workflows.stage6_alerts import run_stage6_alerts


def _build_cli() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(description="Run deterministic late pipeline stages")
	parser.add_argument("--pid", type=str, default=None, help="Process single processo_id")
	parser.add_argument(
		"--run-stage5",
		action="store_true",
		help="Run Stage 5 before Stage 6 (optional due to performance)",
	)
	return parser


def run_full_pipeline(pid: str | None = None, run_stage5: bool = False) -> dict:
	results: dict = {}
	if run_stage5:
		results["stage5"] = run_stage5_conformity(pid=pid)
	results["stage6"] = run_stage6_alerts(pid=pid)
	return results


if __name__ == "__main__":
	args = _build_cli().parse_args()
	run_full_pipeline(pid=args.pid, run_stage5=args.run_stage5)

