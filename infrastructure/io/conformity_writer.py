"""
infrastructure/io/conformity_writer.py

Writers for Epic 5 conformity outputs.
"""

from __future__ import annotations

import json
from pathlib import Path


def write_conformity_result(
    processo_id: str,
    result: dict,
    conformity_dir: Path,
) -> Path:
    conformity_dir.mkdir(parents=True, exist_ok=True)
    safe_pid = processo_id.replace("/", "_").replace("\\", "_")
    out_path = conformity_dir / f"{safe_pid}_conformity.json"
    out_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return out_path


def write_conformity_summary(summary: dict, summary_path: Path) -> Path:
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return summary_path
