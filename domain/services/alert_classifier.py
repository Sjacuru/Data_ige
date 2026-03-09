"""
Deterministic Stage 6 alert classification from Stage 5 conformity results.
"""

from __future__ import annotations

from datetime import datetime


def _has_flag(conformity_json: dict, flag: str) -> bool:
    flags = conformity_json.get("flags", [])
    return isinstance(flags, list) and flag in flags


def _collect_failed_rules(conformity_json: dict) -> list[str]:
    failed: list[str] = []
    score_breakdown = conformity_json.get("score_breakdown", {})
    if not isinstance(score_breakdown, dict):
        return failed
    for rule_name in ("R001", "R002", "R003", "R004"):
        verdict = str(score_breakdown.get(rule_name, {}).get("verdict", "")).upper()
        if verdict == "FAIL":
            failed.append(rule_name)
    return failed


def _build_reason_details(
    conformity_json: dict,
    compliance_json: dict | None,
    reason: str,
    failed_rules: list[str],
) -> dict:
    details = {
        "failed_rules": failed_rules,
        "recommendations": conformity_json.get("recommendations", []),
    }

    if reason == "MISSING_PUBLICATION":
        details["action"] = "extract_publication"
        details["evidence"] = str(
            (compliance_json or {}).get("overall", {}).get("review_reason", "no_publication_found")
        )
    elif reason == "DIAGNOSTIC_DIVERGENCE":
        details["action"] = "manual_audit"
        details["evidence"] = (compliance_json or {}).get("extraction_diagnostic", {}).get(
            "divergence_detail", {}
        )
    elif reason == "NON_CONFORME":
        details["action"] = "investigate_rule_failures"
        details["evidence"] = {
            "r001": (compliance_json or {}).get("r001_timeliness", {}).get("verdict"),
            "r002": (compliance_json or {}).get("r002_party_match", {}).get("verdict"),
        }
    elif reason == "NEEDS_REVIEW":
        details["action"] = "review_before_approval"
        details["evidence"] = {
            "agreement_level": conformity_json.get("diagnostic", {}).get("agreement_level"),
            "requires_review": bool(conformity_json.get("requires_review", False)),
        }
    else:
        details["action"] = "no_action"
        details["evidence"] = "conforme"

    return details


def classify_alert(conformity_json: dict, compliance_json: dict | None = None) -> dict:
    """
    Classify a contract result into Stage 6 business alert buckets.

    Precedence:
    1) FAILED: missing publication, diagnostic divergence, or NÃO CONFORME
    2) REVIEW: PARCIAL, INCOMPLETE, or requires_review
    3) OK: CONFORME without blocking flags
    """
    processo_id = conformity_json.get("processo_id")
    overall_status = str(conformity_json.get("overall_status", "INCOMPLETE"))
    requires_review = bool(conformity_json.get("requires_review", False))
    failed_rules = _collect_failed_rules(conformity_json)

    if _has_flag(conformity_json, "MISSING_PUBLICATION"):
        level = "FAILED"
        reason = "MISSING_PUBLICATION"
    elif _has_flag(conformity_json, "DIAGNOSTIC_DIVERGENCE"):
        level = "FAILED"
        reason = "DIAGNOSTIC_DIVERGENCE"
    elif overall_status == "NÃO CONFORME":
        level = "FAILED"
        reason = "NON_CONFORME"
    elif overall_status in {"PARCIAL", "INCOMPLETE"} or requires_review:
        level = "REVIEW"
        reason = "NEEDS_REVIEW"
    else:
        level = "OK"
        reason = "CONFORME"

    return {
        "processo_id": processo_id,
        "evaluated_at": datetime.now().isoformat(),
        "alert_level": level,
        "reason": reason,
        "reason_details": _build_reason_details(
            conformity_json,
            compliance_json,
            reason,
            failed_rules,
        ),
        "overall_status": overall_status,
        "conformity_score": float(conformity_json.get("conformity_score", 0.0) or 0.0),
        "flags": conformity_json.get("flags", []),
        "failed_rules": failed_rules,
    }
