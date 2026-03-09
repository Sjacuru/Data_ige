"""
domain/services/compliance_engine.py

Pure rule evaluation logic for the contract compliance engine.

No file I/O. No API calls. No infrastructure imports.
Every function takes plain Python values and returns a RuleResult.
The entire module is testable without a Groq key or any data files.

Rules implemented
─────────────────
R001 — Publication Timeliness (deterministic)
    signing_date + 20 calendar days ≥ publication_date → PASS
    Gated: if date field is in diagnostic divergent_fields → INCONCLUSIVE

R002 — Party Name Matching (LLM-assisted)
    LLM confirms contratante and contratada are the same legal entities
    in both contract and publication → PASS / FAIL
    Gated: if party field is in diagnostic divergent_fields → INCONCLUSIVE

Verdict values (all rules)
──────────────────────────
    "PASS"         — check passed, no action needed
    "FAIL"         — check failed, auditor must investigate
    "INCONCLUSIVE" — insufficient data to decide; auditor must review

requires_review
───────────────
    True  for every FAIL and every INCONCLUSIVE result.
    False only for PASS with high confidence.
    The system suggests; the human decides.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
PUBLICATION_DEADLINE_DAYS = 20
DATE_FORMAT               = "%d/%m/%Y"


# ══════════════════════════════════════════════════════════════════════════════
# DATA CLASS
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class RuleResult:
    """
    Structured output for a single compliance rule evaluation.

    Fields
    ──────
    verdict          : "PASS" | "FAIL" | "INCONCLUSIVE"
    explanation      : Human-readable explanation for the auditor.
    confidence       : "high" | "medium" | "low" | "n/a"
    requires_review  : True when the auditor must inspect before sign-off.
    days_delta       : Populated by R001 only; None elsewhere.
    inconclusive_reason : Short machine-readable tag explaining why
                          INCONCLUSIVE was returned (None when not INCONCLUSIVE).
    """
    verdict:             str
    explanation:         str
    confidence:          str
    requires_review:     bool
    days_delta:          Optional[int] = None
    inconclusive_reason: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "verdict":             self.verdict,
            "explanation":         self.explanation,
            "confidence":          self.confidence,
            "requires_review":     self.requires_review,
            "days_delta":          self.days_delta,
            "inconclusive_reason": self.inconclusive_reason,
        }


# ══════════════════════════════════════════════════════════════════════════════
# RULE R001 — PUBLICATION TIMELINESS
# ══════════════════════════════════════════════════════════════════════════════

def evaluate_r001(
    signing_date:              Optional[str],
    publication_date:          Optional[str],
    diagnostic_divergent_fields: Optional[list[str]] = None,
) -> RuleResult:
    """
    Evaluate R001: contract published within PUBLICATION_DEADLINE_DAYS.

    Args:
        signing_date:    Date the contract was signed. Format: DD/MM/YYYY.
                         From _preprocessed.json → header.signing_date.
        publication_date: Date published in the official gazette. Format: DD/MM/YYYY.
                         From _publication_structured.json → publication_date.
        diagnostic_divergent_fields: List of field names flagged as divergent
                         by the extraction comparator. If "signing_date" or
                         "publication_date" appear here, the rule is gated.

    Returns:
        RuleResult with verdict PASS | FAIL | INCONCLUSIVE.
    """
    divergent = set(diagnostic_divergent_fields or [])

    # ── Gate: critical field diverged in diagnostic ────────────────────────────
    if "signing_date" in divergent or "publication_date" in divergent:
        diverged = [f for f in ("signing_date", "publication_date") if f in divergent]
        return RuleResult(
            verdict="INCONCLUSIVE",
            explanation=(
                f"Date field(s) {diverged} showed disagreement between "
                "deterministic extraction and LLM diagnostic. "
                "Auditor must verify the correct date before evaluating timeliness."
            ),
            confidence="n/a",
            requires_review=True,
            inconclusive_reason="divergent_date",
        )

    # ── Missing dates ──────────────────────────────────────────────────────────
    if not signing_date or not publication_date:
        missing = []
        if not signing_date:    missing.append("signing_date")
        if not publication_date: missing.append("publication_date")
        return RuleResult(
            verdict="INCONCLUSIVE",
            explanation=(
                f"Cannot evaluate timeliness: {missing} is missing. "
                "Check extraction quality for this contract."
            ),
            confidence="n/a",
            requires_review=True,
            inconclusive_reason="missing_date",
        )

    # ── Parse dates ───────────────────────────────────────────────────────────
    signing_parsed = _parse_date(signing_date)
    pub_parsed     = _parse_date(publication_date)

    if signing_parsed is None:
        return RuleResult(
            verdict="INCONCLUSIVE",
            explanation=f"signing_date '{signing_date}' could not be parsed as DD/MM/YYYY.",
            confidence="n/a",
            requires_review=True,
            inconclusive_reason="unparseable_date",
        )
    if pub_parsed is None:
        return RuleResult(
            verdict="INCONCLUSIVE",
            explanation=f"publication_date '{publication_date}' could not be parsed as DD/MM/YYYY.",
            confidence="n/a",
            requires_review=True,
            inconclusive_reason="unparseable_date",
        )

    # ── Evaluate ───────────────────────────────────────────────────────────────
    delta = (pub_parsed - signing_parsed).days

    if delta < 0:
        # Publication date is before signing date — data anomaly
        return RuleResult(
            verdict="INCONCLUSIVE",
            explanation=(
                f"Publication date ({publication_date}) is before signing date "
                f"({signing_date}) by {abs(delta)} days. "
                "This indicates a data quality issue — verify both dates."
            ),
            confidence="low",
            requires_review=True,
            days_delta=delta,
            inconclusive_reason="negative_delta",
        )

    if delta <= PUBLICATION_DEADLINE_DAYS:
        return RuleResult(
            verdict="PASS",
            explanation=(
                f"Contract published {delta} day(s) after signing "
                f"({signing_date} → {publication_date}). "
                f"Within the {PUBLICATION_DEADLINE_DAYS}-day legal limit."
            ),
            confidence="high",
            requires_review=False,
            days_delta=delta,
        )
    else:
        return RuleResult(
            verdict="FAIL",
            explanation=(
                f"Contract published {delta} day(s) after signing "
                f"({signing_date} → {publication_date}). "
                f"Exceeds the {PUBLICATION_DEADLINE_DAYS}-day legal limit by "
                f"{delta - PUBLICATION_DEADLINE_DAYS} day(s)."
            ),
            confidence="high",
            requires_review=True,
            days_delta=delta,
        )


# ══════════════════════════════════════════════════════════════════════════════
# RULE R002 — PARTY NAME MATCHING
# ══════════════════════════════════════════════════════════════════════════════

def evaluate_r002(
    contract_contratante:        Optional[str],
    pub_contratante:             Optional[str],
    contract_contratada:         Optional[str],
    pub_contratada:              Optional[str],
    llm_response:                Optional[str],
    diagnostic_divergent_fields: Optional[list[str]] = None,
) -> RuleResult:
    """
    Evaluate R002: party names in contract match those in gazette publication.

    Party names are often abbreviated, reformatted, or differ in legal-suffix
    style between the contract body and the gazette extrato. A deterministic
    string match is insufficient — we use LLM semantic comparison.

    Args:
        contract_contratante:    Party name from contract (contratante).
        pub_contratante:         Party name from publication (contratante).
        contract_contratada:     Party name from contract (contratada).
        pub_contratada:          Party name from publication (contratada).
        llm_response:            Raw JSON string from the R002 LLM prompt.
                                 Expected keys: contratante_match (bool),
                                 contratada_match (bool), overall_verdict (str),
                                 confidence (str), contratante_explanation (str),
                                 contratada_explanation (str).
        diagnostic_divergent_fields: Fields flagged by extraction comparator.

    Returns:
        RuleResult with verdict PASS | FAIL | INCONCLUSIVE.
    """
    divergent = set(diagnostic_divergent_fields or [])

    # ── Gate: party field diverged in diagnostic ───────────────────────────────
    party_fields = {"contratante", "contratada", "contratante_in_pub", "contratada_in_pub"}
    diverged_parties = divergent & party_fields
    if diverged_parties:
        return RuleResult(
            verdict="INCONCLUSIVE",
            explanation=(
                f"Party field(s) {sorted(diverged_parties)} showed disagreement "
                "between deterministic extraction and LLM diagnostic. "
                "Auditor must verify the correct party names before evaluating match."
            ),
            confidence="n/a",
            requires_review=True,
            inconclusive_reason="divergent_party",
        )

    # ── Missing party fields ────────────────────────────────────────────────────
    missing = []
    if not contract_contratante: missing.append("contract_contratante")
    if not pub_contratante:      missing.append("pub_contratante")
    if not contract_contratada:  missing.append("contract_contratada")
    if not pub_contratada:       missing.append("pub_contratada")
    if missing:
        return RuleResult(
            verdict="INCONCLUSIVE",
            explanation=(
                f"Cannot evaluate party match: {missing} is missing. "
                "Check extraction quality for this contract and its publication."
            ),
            confidence="n/a",
            requires_review=True,
            inconclusive_reason="missing_party",
        )

    # ── LLM response missing ───────────────────────────────────────────────────
    if llm_response is None:
        return RuleResult(
            verdict="INCONCLUSIVE",
            explanation=(
                "LLM party comparison was not available (API call returned None). "
                "Auditor must manually compare party names."
            ),
            confidence="n/a",
            requires_review=True,
            inconclusive_reason="llm_unavailable",
        )

    # ── Parse LLM JSON ─────────────────────────────────────────────────────────
    try:
        parsed = json.loads(llm_response)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("R002: LLM response is not valid JSON: %s", exc)
        return RuleResult(
            verdict="INCONCLUSIVE",
            explanation=(
                "LLM returned a response that could not be parsed as JSON. "
                f"Raw response (first 200 chars): {llm_response[:200]!r}"
            ),
            confidence="n/a",
            requires_review=True,
            inconclusive_reason="llm_parse_error",
        )

    # ── Low confidence always → INCONCLUSIVE regardless of verdict ────────────
    confidence = str(parsed.get("confidence", "low")).lower()
    if confidence == "low":
        return RuleResult(
            verdict="INCONCLUSIVE",
            explanation=(
                "LLM expressed low confidence in the party name comparison. "
                f"Contratante: {parsed.get('contratante_explanation', '')} | "
                f"Contratada: {parsed.get('contratada_explanation', '')}. "
                "Auditor must verify party names manually."
            ),
            confidence="low",
            requires_review=True,
            inconclusive_reason="llm_low_confidence",
        )

    # ── Read verdict ───────────────────────────────────────────────────────────
    overall = str(parsed.get("overall_verdict", "")).upper()
    contratante_ok = bool(parsed.get("contratante_match", False))
    contratada_ok  = bool(parsed.get("contratada_match",  False))
    expl_ctante    = parsed.get("contratante_explanation", "")
    expl_ctada     = parsed.get("contratada_explanation",  "")

    summary = (
        f"Contratante: {contract_contratante!r} ↔ {pub_contratante!r} "
        f"→ {'match' if contratante_ok else 'MISMATCH'}. "
        f"{expl_ctante} | "
        f"Contratada: {contract_contratada!r} ↔ {pub_contratada!r} "
        f"→ {'match' if contratada_ok else 'MISMATCH'}. "
        f"{expl_ctada}"
    )

    if overall == "PASS" and contratante_ok and contratada_ok:
        return RuleResult(
            verdict="PASS",
            explanation=summary,
            confidence=confidence,
            requires_review=False,
        )
    elif overall == "FAIL" or not contratante_ok or not contratada_ok:
        return RuleResult(
            verdict="FAIL",
            explanation=summary,
            confidence=confidence,
            requires_review=True,
        )
    else:
        # Unexpected verdict value from LLM
        return RuleResult(
            verdict="INCONCLUSIVE",
            explanation=(
                f"LLM returned unexpected verdict '{parsed.get('overall_verdict')}'. "
                f"{summary}"
            ),
            confidence=confidence,
            requires_review=True,
            inconclusive_reason="llm_unexpected_verdict",
        )


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _parse_date(date_str: str) -> Optional[date]:
    """
    Parse a DD/MM/YYYY date string.

    Returns a date object on success, None on any parse failure.
    Does not raise.
    """
    try:
        return datetime.strptime(date_str.strip(), DATE_FORMAT).date()
    except (ValueError, AttributeError):
        return None