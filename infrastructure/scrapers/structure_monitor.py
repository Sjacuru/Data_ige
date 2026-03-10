from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from config.settings import DATA_DIR

logger = logging.getLogger(__name__)

BASELINES_PATH: Path = DATA_DIR / "portal_baselines.json"


@dataclass
class DriftResult:
    """
    Output of check_drift().

    drifted:           True if any selector changed state vs baseline.
    changed_selectors: Names of selectors whose presence changed.
    """
    drifted: bool = False
    changed_selectors: list[str] = field(default_factory=list)


def _load_baselines() -> dict:
    """Load portal_baselines.json. Returns {} on any error."""
    try:
        if not BASELINES_PATH.exists():
            return {}
        data = json.loads(BASELINES_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        logger.warning("structure_monitor: could not load baselines: %s", exc)
        return {}


def _save_baselines(baselines: dict) -> None:
    """Write portal_baselines.json atomically. Never raises."""
    try:
        BASELINES_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = BASELINES_PATH.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(baselines, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(BASELINES_PATH)
    except Exception as exc:
        logger.warning("structure_monitor: could not save baselines: %s", exc)


def record_baseline(portal: str, selector_results: dict[str, bool]) -> None:
    """
    Save or update the selector baseline for a portal.
    Call this after a SUCCESSFUL scrape to establish the expected structure.
    Never raises.

    Args:
        portal:           Identifier string, e.g. "contasrio" or "doweb".
        selector_results: Dict mapping selector name → bool (True = found on page).
    """
    try:
        baselines = _load_baselines()
        baselines[str(portal)] = {
            "selectors": {str(k): bool(v) for k, v in selector_results.items()},
            "recorded_at": datetime.now().isoformat(),
        }
        _save_baselines(baselines)
        logger.debug(
            "structure_monitor: baseline recorded for '%s' (%d selectors)",
            portal, len(selector_results),
        )
    except Exception as exc:
        logger.warning("record_baseline error for '%s': %s", portal, exc)


def check_drift(
    portal: str,
    selector_results: dict[str, bool],
) -> DriftResult:
    """
    Compare current selector results against the stored baseline.

    If no baseline exists for this portal, the current results become the
    baseline and DriftResult(drifted=False) is returned.

    FAIL-OPEN: any exception returns DriftResult(drifted=False).
    This function must NEVER block or slow down scraper execution.

    Args:
        portal:           Identifier string, e.g. "contasrio".
        selector_results: Current probe results from the scraper.

    Returns:
        DriftResult — never raises.
    """
    try:
        baselines = _load_baselines()
        portal_key = str(portal)

        if portal_key not in baselines:
            record_baseline(portal, selector_results)
            logger.info(
                "structure_monitor: no baseline for '%s' — saving current as baseline",
                portal,
            )
            return DriftResult(drifted=False)

        stored = baselines[portal_key].get("selectors", {})
        changed: list[str] = []

        for name, current_state in selector_results.items():
            expected = stored.get(str(name))
            if expected is None:
                continue
            if bool(current_state) != bool(expected):
                changed.append(str(name))

        if changed:
            logger.warning(
                "structure_monitor: DRIFT detected on portal '%s' — "
                "changed selectors: %s",
                portal, changed,
            )
            record_baseline(portal, selector_results)
            return DriftResult(drifted=True, changed_selectors=changed)

        logger.debug(
            "structure_monitor: no drift on portal '%s' (%d selectors checked)",
            portal, len(selector_results),
        )
        return DriftResult(drifted=False)

    except Exception as exc:
        logger.warning(
            "structure_monitor: check_drift failed for '%s' (%s) — "
            "returning no-drift (fail-open)",
            portal, exc,
        )
        return DriftResult(drifted=False)