"""
domain/services/score_calculator.py

Deterministic weighted score calculator for Epic 5.
"""

from __future__ import annotations


WEIGHTS = {
    "R001": 0.40,
    "R002": 0.30,
    "R003": 0.20,
    "R004": 0.10,
}

NUMERIC_VERDICT = {
    "PASS": 100,
    "FAIL": 0,
    "INCONCLUSIVE": 50,
    "INCOMPLETE": 50,
    "PARTIAL": 75,
}


def verdict_to_numeric(verdict: str | None) -> int:
    key = (verdict or "INCOMPLETE").strip().upper()
    return NUMERIC_VERDICT.get(key, 50)


def compute_weighted_score(
    r001_verdict: str,
    r002_verdict: str,
    r003_verdict: str,
    r004_verdict: str,
) -> tuple[float, dict]:
    rule_scores = {
        "R001": verdict_to_numeric(r001_verdict),
        "R002": verdict_to_numeric(r002_verdict),
        "R003": verdict_to_numeric(r003_verdict),
        "R004": verdict_to_numeric(r004_verdict),
    }
    weighted = sum(rule_scores[k] * WEIGHTS[k] for k in WEIGHTS)
    return round(weighted, 2), rule_scores


def apply_diagnostic_gating(
    score: float,
    agreement_level: str | None,
) -> dict:
    agreement = (agreement_level or "SKIPPED").strip().upper()

    if agreement == "DIVERGENT":
        return {
            "score": 0.0,
            "forced_status": "INCOMPLETE",
            "flags": ["DIAGNOSTIC_DIVERGENCE"],
            "requires_review": True,
            "skip_r003_r004": True,
        }

    if agreement == "PARTIAL":
        return {
            "score": min(score, 85.0),
            "forced_status": None,
            "flags": ["DIAGNOSTIC_PARTIAL"],
            "requires_review": True,
            "skip_r003_r004": False,
        }

    if agreement == "SKIPPED":
        return {
            "score": score,
            "forced_status": None,
            "flags": ["DIAGNOSTIC_SKIPPED"],
            "requires_review": False,
            "skip_r003_r004": False,
        }

    return {
        "score": score,
        "forced_status": None,
        "flags": [],
        "requires_review": False,
        "skip_r003_r004": False,
    }


def classify_final_status(
    score: float,
    agreement_level: str | None,
    missing_publication: bool,
) -> str:
    agreement = (agreement_level or "SKIPPED").strip().upper()

    if missing_publication:
        return "INCOMPLETE"

    if agreement == "DIVERGENT":
        return "INCOMPLETE"

    if score >= 90:
        return "CONFORME"
    if 60 <= score <= 89:
        return "PARCIAL"
    return "NÃO CONFORME"
