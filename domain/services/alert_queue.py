"""Stage 6 alert queue builder for auditor operations."""

from __future__ import annotations


PRIORITY_BY_LEVEL = {
    "FAILED": 1,
    "REVIEW": 2,
    "OK": 3,
}


def _priority_score(alert: dict) -> float:
    base = PRIORITY_BY_LEVEL.get(str(alert.get("alert_level", "OK")), 3)
    score = float(alert.get("conformity_score", 0.0) or 0.0)
    return (base * 1000.0) - score


def build_alert_queue(alerts: list[dict]) -> list[dict]:
    """
    Build sorted operational queue for non-OK alerts.

    Sorting:
    1) alert level severity (FAILED before REVIEW)
    2) lower conformity score first
    3) processo_id lexical tiebreak
    """
    queue: list[dict] = []
    for alert in alerts:
        level = str(alert.get("alert_level", "OK"))
        if level == "OK":
            continue

        item = {
            "processo_id": alert.get("processo_id"),
            "alert_level": level,
            "reason": alert.get("reason"),
            "conformity_score": float(alert.get("conformity_score", 0.0) or 0.0),
            "failed_rules": alert.get("failed_rules", []),
            "flags": alert.get("flags", []),
            "action": (alert.get("reason_details") or {}).get("action"),
            "priority_score": _priority_score(alert),
        }
        queue.append(item)

    queue.sort(
        key=lambda item: (
            PRIORITY_BY_LEVEL.get(item["alert_level"], 3),
            item["conformity_score"],
            str(item.get("processo_id", "")),
        )
    )
    return queue
