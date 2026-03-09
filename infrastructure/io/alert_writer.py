"""Writers for Stage 6 alert artifacts."""

from __future__ import annotations

import json
from pathlib import Path


def write_alert_result(processo_id: str, payload: dict, target_dir: Path) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    safe_pid = (processo_id or "UNKNOWN").replace("/", "_").replace("\\", "_")
    output_path = target_dir / f"{safe_pid}_alert.json"
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path


def write_alert_summary(summary: dict, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path
