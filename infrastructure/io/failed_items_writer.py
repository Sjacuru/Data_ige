from __future__ import annotations

import json
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from config.settings import DATA_DIR

logger = logging.getLogger(__name__)

FAILED_ITEMS_PATH: Path = DATA_DIR / "failed_items.json"
_LOCK = threading.Lock()


def _load_all() -> list[dict]:
    """Load the full failed_items.json as a list. Returns [] on any error."""
    try:
        if not FAILED_ITEMS_PATH.exists():
            return []
        raw = FAILED_ITEMS_PATH.read_text(encoding="utf-8")
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except Exception as exc:
        logger.warning("Failed to load failed_items.json: %s", exc)
        return []


def _save_all(items: list[dict]) -> bool:
    """Write items to failed_items.json atomically. Returns True on success."""
    try:
        FAILED_ITEMS_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = FAILED_ITEMS_PATH.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(items, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(FAILED_ITEMS_PATH)
        return True
    except Exception as exc:
        logger.warning("Failed to save failed_items.json: %s", exc)
        return False


def append_failed_item(
    processo_id: str,
    stage: str,
    error_type: str,
    error_msg: str,
    retry_count: int = 0,
) -> bool:
    """
    Append one failure record to data/failed_items.json.

    Thread-safe. Atomic write. Never raises.
    Returns True if the record was written successfully.

    Args:
        processo_id:  e.g. "FIL-PRO-2023/00482"
        stage:        e.g. "stage3" or "stage4"
        error_type:   class name of the exception, e.g. "TransientError"
        error_msg:    str(exc) or short human description
        retry_count:  number of retries already attempted (default 0)
    """
    record: dict = {
        "processo_id": str(processo_id or ""),
        "stage": str(stage or ""),
        "error_type": str(error_type or ""),
        "error_msg": str(error_msg or ""),
        "failed_at": datetime.now().isoformat(),
        "retry_count": int(retry_count),
        "resolved": False,
    }
    try:
        with _LOCK:
            items = _load_all()
            items.append(record)
            return _save_all(items)
    except Exception as exc:
        logger.warning("append_failed_item error: %s", exc)
        return False


def mark_resolved(processo_id: str, stage: str) -> bool:
    """
    Set resolved=True for all entries matching processo_id + stage.
    Never raises. Returns True if at least one entry was updated.
    """
    try:
        with _LOCK:
            items = _load_all()
            updated = False
            for item in items:
                if (
                    item.get("processo_id") == str(processo_id)
                    and item.get("stage") == str(stage)
                    and not item.get("resolved", False)
                ):
                    item["resolved"] = True
                    updated = True
            if updated:
                _save_all(items)
            return updated
    except Exception as exc:
        logger.warning("mark_resolved error: %s", exc)
        return False


def load_failed_items(stage: Optional[str] = None) -> list[dict]:
    """
    Return all failed items, optionally filtered by stage.
    Never raises. Returns [] on any error.
    """
    try:
        items = _load_all()
        if stage is not None:
            items = [i for i in items if i.get("stage") == str(stage)]
        return items
    except Exception as exc:
        logger.warning("load_failed_items error: %s", exc)
        return []


def count_unresolved(stage: Optional[str] = None) -> int:
    """
    Count unresolved failed items, optionally filtered by stage.
    Never raises. Returns 0 on any error.
    """
    try:
        items = load_failed_items(stage=stage)
        return sum(1 for i in items if not i.get("resolved", False))
    except Exception as exc:
        logger.warning("count_unresolved error: %s", exc)
        return 0
