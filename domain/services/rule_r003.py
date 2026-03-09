"""
domain/services/rule_r003.py

Rule R003 — Identifier verification.
"""

from __future__ import annotations


def evaluate_r003(
    contract_number_contract: str | None,
    contract_number_publication: str | None,
) -> dict:
    """
    Evaluate contract identifier consistency.

    Returns dict with verdict and score:
      PASS -> 100
      FAIL -> 0
      INCOMPLETE -> 50
    """
    c_num = (contract_number_contract or "").strip()
    p_num = (contract_number_publication or "").strip()

    if not c_num or not p_num:
        return {
            "verdict": "INCOMPLETE",
            "score": 50,
            "explanation": "Missing contract number in contract or publication source.",
        }

    if c_num.casefold() == p_num.casefold():
        return {
            "verdict": "PASS",
            "score": 100,
            "explanation": "Contract numbers match (case-insensitive).",
        }

    return {
        "verdict": "FAIL",
        "score": 0,
        "explanation": f"Contract numbers differ: {c_num!r} vs {p_num!r}.",
    }
