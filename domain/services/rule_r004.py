"""
domain/services/rule_r004.py

Rule R004 — Value consistency verification.
"""

from __future__ import annotations


def _parse_brl_value(value: str | float | int | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()
    if not text:
        return None

    text = text.replace("R$", "").replace(" ", "")
    if "," in text:
        text = text.replace(".", "").replace(",", ".")

    try:
        return float(text)
    except ValueError:
        return None


def evaluate_r004(
    contract_value: str | float | int | None,
    publication_value: str | float | int | None,
) -> dict:
    """
    Evaluate value consistency between contract and publication.

    Thresholds:
      diff == 0%  -> PASS (100)
      diff <= 1%  -> PARTIAL (75)
      diff > 1%   -> FAIL (0)
      missing     -> INCOMPLETE (50)
    """
    v_contract = _parse_brl_value(contract_value)
    v_publication = _parse_brl_value(publication_value)

    if v_contract is None or v_publication is None:
        return {
            "verdict": "INCOMPLETE",
            "score": 50,
            "difference_percentage": None,
            "explanation": "Missing or invalid value in contract or publication source.",
        }

    if v_contract == 0.0:
        if v_publication == 0.0:
            return {
                "verdict": "PASS",
                "score": 100,
                "difference_percentage": 0.0,
                "explanation": "Both values are zero.",
            }
        return {
            "verdict": "FAIL",
            "score": 0,
            "difference_percentage": None,
            "explanation": "Contract value is zero and publication value is non-zero.",
        }

    diff_pct = abs(v_contract - v_publication) / abs(v_contract) * 100
    diff_pct = round(diff_pct, 6)

    if diff_pct == 0.0:
        return {
            "verdict": "PASS",
            "score": 100,
            "difference_percentage": diff_pct,
            "explanation": "Values are identical.",
        }

    if diff_pct <= 1.0:
        return {
            "verdict": "PARTIAL",
            "score": 75,
            "difference_percentage": diff_pct,
            "explanation": "Values differ by up to 1%.",
        }

    return {
        "verdict": "FAIL",
        "score": 0,
        "difference_percentage": diff_pct,
        "explanation": "Values differ by more than 1%.",
    }
