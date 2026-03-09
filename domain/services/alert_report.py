"""Stage 6 executive alert report aggregation."""

from __future__ import annotations

from datetime import datetime


def _percent(count: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round((count / total) * 100.0, 2)


def build_alert_executive_summary(alerts: list[dict]) -> dict:
    total = len(alerts)
    ok = sum(1 for a in alerts if a.get("alert_level") == "OK")
    review = sum(1 for a in alerts if a.get("alert_level") == "REVIEW")
    failed = sum(1 for a in alerts if a.get("alert_level") == "FAILED")

    by_reason: dict[str, int] = {}
    failed_rules: dict[str, int] = {"R001": 0, "R002": 0, "R003": 0, "R004": 0}

    for alert in alerts:
        reason = str(alert.get("reason", "UNKNOWN"))
        by_reason[reason] = by_reason.get(reason, 0) + 1

        for rule in alert.get("failed_rules", []) or []:
            if rule in failed_rules:
                failed_rules[rule] += 1

    return {
        "generated_at": datetime.now().isoformat(),
        "total_contracts": total,
        "counts": {
            "ok": ok,
            "review": review,
            "failed": failed,
        },
        "rates": {
            "ok_pct": _percent(ok, total),
            "review_pct": _percent(review, total),
            "failed_pct": _percent(failed, total),
        },
        "by_reason": dict(sorted(by_reason.items(), key=lambda item: item[0])),
        "failed_rules": failed_rules,
    }
