from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def write_aggregate_json(aggregate: dict, output_path: Path) -> Path:
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(aggregate, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return output_path
    except Exception as exc:
        logger.warning("Failed to write aggregate json '%s': %s", output_path, exc)
        return output_path
