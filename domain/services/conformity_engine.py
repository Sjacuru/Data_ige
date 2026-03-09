"""
domain/services/conformity_engine.py

High-level deterministic conformity scoring engine for Epic 5.
"""

from __future__ import annotations

from datetime import datetime

from domain.services.rule_r003 import evaluate_r003
from domain.services.rule_r004 import evaluate_r004
from domain.services.score_calculator import (
    WEIGHTS,
    apply_diagnostic_gating,
    classify_final_status,
    compute_weighted_score,
)
from domain.services.status_mapper import map_rule_status, map_diagnostic


def _safe_get(d: dict | None, *keys, default=None):
    current = d
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
    return current if current is not None else default


def _extract_fallback_fields(
    contract_preprocessed: dict | None,
    publication_structured: dict | None,
) -> dict:
    """Extract Stage 5 fallback fields from preprocessed sources."""
    return {
        "contract_number_contract": _safe_get(contract_preprocessed, "header", "contract_number"),
        "contract_number_publication": _safe_get(publication_structured, "contract_number"),
        "contract_value": _safe_get(contract_preprocessed, "header", "value")
        or _safe_get(contract_preprocessed, "value"),
        "publication_value": _safe_get(publication_structured, "value"),
    }


def compute_conformity(
    compliance_json: dict,
    contract_preprocessed: dict | None = None,
    publication_structured: dict | None = None,
) -> dict:
    """
    Compute conformity report from Epic 4 compliance output.

    This function is pure domain logic: no file I/O, no API calls.
    """
    processo_id = compliance_json.get("processo_id")

    r001_verdict = str(
        _safe_get(compliance_json, "r001_timeliness", "verdict", default="INCONCLUSIVE")
    )
    r002_verdict = str(
        _safe_get(compliance_json, "r002_party_match", "verdict", default="INCONCLUSIVE")
    )  
    agreement_level = str(
        _safe_get(compliance_json, "extraction_diagnostic", "agreement_level", default="SKIPPED")
    )
    missing_publication = (
        _safe_get(compliance_json, "overall", "status") == "INCONCLUSIVE"
        and _safe_get(compliance_json, "overall", "review_reason") == "no_publication_found"
    )

    fallback_fields = _extract_fallback_fields(contract_preprocessed, publication_structured)

    if agreement_level.upper() == "DIVERGENT":
        r003 = {
            "verdict": "SKIPPED",
            "score": 50,
            "explanation": "Skipped due to extraction diagnostic divergence.",
        }
        r004 = {
            "verdict": "SKIPPED",
            "score": 50,
            "difference_percentage": None,
            "explanation": "Skipped due to extraction diagnostic divergence.",
        }
    else:
        r003 = evaluate_r003(
            fallback_fields["contract_number_contract"],
            fallback_fields["contract_number_publication"],
        )
        r004 = evaluate_r004(
            fallback_fields["contract_value"],
            fallback_fields["publication_value"],
        )

    weighted_score, numeric_scores = compute_weighted_score(
        r001_verdict,
        r002_verdict,
        r003["verdict"],
        r004["verdict"],
    )

    gating = apply_diagnostic_gating(weighted_score, agreement_level)
    final_score = gating["score"]
    flags = list(gating["flags"])

    if missing_publication:
        final_score = 0.0
        flags.append("MISSING_PUBLICATION")

    overall_status = (
        gating["forced_status"]
        if gating["forced_status"]
        else classify_final_status(final_score, agreement_level, missing_publication)
    )

    recommendations = []
    if "MISSING_PUBLICATION" in flags:
        recommendations.append("Run publication extraction/preprocessing before conformity scoring.")
    if "DIAGNOSTIC_DIVERGENCE" in flags:
        recommendations.append("Manual audit required due to divergent extraction diagnostic.")
    if "DIAGNOSTIC_PARTIAL" in flags:
        recommendations.append("Review partially divergent extracted fields before approval.")

    return {
        "processo_id": processo_id,
        "analysis_date": datetime.now().isoformat(),
        "diagnostic": {
            "agreement_level": agreement_level,
            "impact": map_diagnostic(agreement_level),
        },
        "source_summary": {
            "epic4_overall_status": _safe_get(compliance_json, "overall", "status"),
            "epic4_r001_status": map_rule_status(r001_verdict),
            "epic4_r002_status": map_rule_status(r002_verdict),
            "fallback_fields_used": {
                "contract_number_contract": bool(fallback_fields["contract_number_contract"]),
                "contract_number_publication": bool(fallback_fields["contract_number_publication"]),
                "contract_value": bool(fallback_fields["contract_value"]),
                "publication_value": bool(fallback_fields["publication_value"]),
            },
        },
        "score_breakdown": {
            "R001": {"score": numeric_scores["R001"], "weight": WEIGHTS["R001"], "verdict": r001_verdict},
            "R002": {"score": numeric_scores["R002"], "weight": WEIGHTS["R002"], "verdict": r002_verdict},
            "R003": {"score": numeric_scores["R003"], "weight": WEIGHTS["R003"], "verdict": r003["verdict"]},
            "R004": {"score": numeric_scores["R004"], "weight": WEIGHTS["R004"], "verdict": r004["verdict"]},
        },
        "rule_details": {
            "R003": r003,
            "R004": r004,
        },
        "conformity_score": round(final_score, 2),
        "overall_status": overall_status,
        "flags": flags,
        "requires_review": gating["requires_review"] or missing_publication,
        "recommendations": recommendations,
    }
