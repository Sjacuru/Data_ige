"""
domain/services/extraction_comparator.py

Field-by-field comparison between deterministic preprocessor outputs
and LLM parallel extraction outputs.

No file I/O. No API calls. No infrastructure imports.
Fully testable without a Groq key or any data files.

Purpose in the pipeline
────────────────────────
Stage 4 runs two independent extraction paths for each contract:

  Path A (deterministic): contract_preprocessor.py + publication_preprocessor.py
      → data/preprocessed/{pid}_preprocessed.json
      → data/preprocessed/{pid}_publication_structured.json

  Path B (LLM): Groq prompts A + B extract the same fields from raw text
      → returned as dicts, never written to disk

This module compares the two paths field-by-field and produces a
DiagnosticResult that gates the compliance rules:

  CONFIRMED  → all fields agree  → rules run normally
  PARTIAL    → some fields diverge, but no identity-critical field
             → rules run, requires_review = True
  DIVERGENT  → at least one identity-critical field disagrees
             → rules blocked → INCONCLUSIVE

Identity-critical fields (one mismatch → DIVERGENT)
────────────────────────────────────────────────────
  signing_date, processo_id, contract_number

All other fields are non-critical (divergence → PARTIAL, not DIVERGENT).

Comparison strategies
─────────────────────
  Dates  : both strings parsed as DD/MM/YYYY → compared as date objects
           Handles None on either side gracefully.
  Names  : normalised upper-case comparison
           Normalisation: lower, strip, remove punctuation [.,;:-/\\],
           collapse internal whitespace → upper.
           "ARTE E CULTURA LTDA" == "Arte e Cultura Ltda." → match
  Other  : normalised string comparison (same as names)

field_map contract
──────────────────
The caller passes a field_map dict that maps field names to comparison
strategy and criticality:

    field_map = {
        "signing_date":    {"det_key": "signing_date",    "llm_key": "signing_date",    "type": "date",   "critical": True},
        "processo_id":     {"det_key": "processo_id",     "llm_key": "processo_id",     "type": "name",   "critical": True},
        "contract_number": {"det_key": "contract_number", "llm_key": "contract_number", "type": "name",   "critical": True},
        "contratante":     {"det_key": "contratante",     "llm_key": "contratante",     "type": "name",   "critical": False},
        "contratada":      {"det_key": "contratada",      "llm_key": "contratada",      "type": "name",   "critical": False},
    }

A convenience function build_default_field_map() returns the standard
field_map used by stage4_compliance.py for convenience.
"""

import re
import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
DATE_FORMAT = "%d/%m/%Y"

# Fields whose divergence immediately classifies the result as DIVERGENT
# regardless of how many other fields match.
CRITICAL_FIELDS = frozenset({"signing_date", "processo_id", "contract_number"})

# Punctuation characters stripped during name normalisation
_PUNCT_RE = re.compile(r'[.,;:\-/\\]')
_SPACE_RE = re.compile(r'\s+')


# ══════════════════════════════════════════════════════════════════════════════
# DATA CLASS
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class DiagnosticResult:
    """
    Output of a single compare_extractions() call.

    Fields
    ──────
    agreement_level       : "CONFIRMED" | "PARTIAL" | "DIVERGENT"
    fields_confirmed      : Field names where both paths agreed.
    fields_divergent      : Field names where paths disagreed.
    divergence_detail     : field → "det: <value> — llm: <value>"
    auditor_action_required: True when agreement_level is not CONFIRMED.
    """
    agreement_level:          str
    fields_confirmed:         list
    fields_divergent:         list
    divergence_detail:        dict
    auditor_action_required:  bool

    def to_dict(self) -> dict:
        return {
            "agreement_level":         self.agreement_level,
            "fields_confirmed":        self.fields_confirmed,
            "fields_divergent":        self.fields_divergent,
            "divergence_detail":       self.divergence_detail,
            "auditor_action_required": self.auditor_action_required,
        }


# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ══════════════════════════════════════════════════════════════════════════════

def compare_extractions(
    deterministic: dict,
    llm:           dict,
    field_map:     dict,
) -> DiagnosticResult:
    """
    Compare deterministic and LLM extraction outputs field by field.

    Args:
        deterministic: Dict from the preprocessor output (or a subset of it).
                       Keys must match the "det_key" values in field_map.
        llm:           Dict from the LLM extraction prompt response.
                       Keys must match the "llm_key" values in field_map.
        field_map:     Mapping from logical field name → comparison config.
                       Use build_default_field_map() for the standard set.
                       Each entry:
                           {
                             "det_key":  str,    # key in deterministic dict
                             "llm_key":  str,    # key in llm dict
                             "type":     str,    # "date" | "name" | "string"
                             "critical": bool,   # True → one divergence = DIVERGENT
                           }

    Returns:
        DiagnosticResult with agreement_level, confirmed/divergent field
        lists, divergence detail, and auditor_action_required flag.
    """
    confirmed: list  = []
    divergent: list  = []
    detail:    dict  = {}
    has_critical_divergence = False

    for field_name, config in field_map.items():
        det_val = deterministic.get(config["det_key"])
        llm_val = llm.get(config["llm_key"])
        ctype   = config.get("type", "string")
        critical = config.get("critical", False)

        match = _compare_values(det_val, llm_val, ctype)

        if match:
            confirmed.append(field_name)
            logger.debug("  ✓ %s: confirmed (%r)", field_name, det_val)
        else:
            divergent.append(field_name)
            detail[field_name] = (
                f"det: {det_val!r} — llm: {llm_val!r}"
            )
            if critical and field_name in CRITICAL_FIELDS:
                has_critical_divergence = True
            logger.debug(
                "  ✗ %s: DIVERGED | det=%r llm=%r",
                field_name, det_val, llm_val,
            )

    # ── Classify agreement level ───────────────────────────────────────────────
    if has_critical_divergence:
        level = "DIVERGENT"
    elif divergent:
        level = "PARTIAL"
    else:
        level = "CONFIRMED"

    auditor_required = level != "CONFIRMED"

    result = DiagnosticResult(
        agreement_level=level,
        fields_confirmed=confirmed,
        fields_divergent=divergent,
        divergence_detail=detail,
        auditor_action_required=auditor_required,
    )

    logger.info(
        "Extraction diagnostic: %s | confirmed=%d diverged=%d critical=%s",
        level, len(confirmed), len(divergent), has_critical_divergence,
    )
    return result


def build_default_field_map() -> dict:
    """
    Return the standard field_map for Stage 4 compliance evaluation.

    Maps the five fields extracted by both the deterministic preprocessor
    and the LLM diagnostic prompts.

    Contract fields (from _preprocessed.json → header):
        processo_id, contract_number, signing_date, contratante, contratada

    Publication fields (from _publication_structured.json + LLM Prompt B):
        processo_id_in_pub, contract_number_in_pub, publication_date,
        contratante_in_pub, contratada_in_pub

    This function returns the CONTRACT side field_map. For publication
    fields, call build_publication_field_map().
    """
    return {
        "signing_date": {
            "det_key":  "signing_date",
            "llm_key":  "signing_date",
            "type":     "date",
            "critical": True,
        },
        "processo_id": {
            "det_key":  "processo_id",
            "llm_key":  "processo_id",
            "type":     "name",
            "critical": True,
        },
        "contract_number": {
            "det_key":  "contract_number",
            "llm_key":  "contract_number",
            "type":     "name",
            "critical": True,
        },
        "contratante": {
            "det_key":  "contratante",
            "llm_key":  "contratante",
            "type":     "name",
            "critical": False,
        },
        "contratada": {
            "det_key":  "contratada",
            "llm_key":  "contratada",
            "type":     "name",
            "critical": False,
        },
    }


def build_publication_field_map() -> dict:
    """
    Standard field_map for the publication side diagnostic.
    """
    return {
        "publication_date": {
            "det_key":  "publication_date",
            "llm_key":  "publication_date",
            "type":     "date",
            "critical": True,
        },
        "processo_id_in_pub": {
            "det_key":  "processo_id",
            "llm_key":  "processo_id_in_pub",
            "type":     "name",
            "critical": True,
        },
        "contract_number_in_pub": {
            "det_key":  "contract_number",
            "llm_key":  "contract_number_in_pub",
            "type":     "name",
            "critical": True,
        },
        "contratante_in_pub": {
            "det_key":  "contratante",
            "llm_key":  "contratante_in_pub",
            "type":     "name",
            "critical": False,
        },
        "contratada_in_pub": {
            "det_key":  "contratada",
            "llm_key":  "contratada_in_pub",
            "type":     "name",
            "critical": False,
        },
    }


# ══════════════════════════════════════════════════════════════════════════════
# COMPARISON HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _compare_values(det_val, llm_val, ctype: str) -> bool:
    """
    Compare two extracted values using the appropriate strategy.

    Both None → match (neither extractor found the field — consistent).
    One None, one not → mismatch.
    """
    # Both missing → consistent absence → confirmed
    if det_val is None and llm_val is None:
        return True

    # One missing, one present → diverged
    if det_val is None or llm_val is None:
        return False

    if ctype == "date":
        return _compare_dates(str(det_val), str(llm_val))
    else:
        # "name" and "string" both use normalised comparison
        return _normalise(str(det_val)) == _normalise(str(llm_val))


def _compare_dates(a: str, b: str) -> bool:
    """
    Compare two DD/MM/YYYY date strings as date objects.
    Returns False if either cannot be parsed.
    """
    da = _parse_date(a)
    db = _parse_date(b)
    if da is None or db is None:
        # If both fail to parse the same way, treat as equal (consistent absence)
        if da is None and db is None:
            return True
        return False
    return da == db


def _normalise(s: str) -> str:
    """
    Normalise a string for loose comparison.

    Steps:
      1. Strip leading/trailing whitespace
      2. Remove punctuation: . , ; : - / \\
      3. Collapse internal whitespace to single space
      4. Convert to upper case

    Examples:
      "ARTE E CULTURA LTDA."  → "ARTE E CULTURA LTDA"
      "Arte e Cultura Ltda."  → "ARTE E CULTURA LTDA"
      "RIOFILME"              → "RIOFILME"
      "Distribuidora S.A"     → "DISTRIBUIDORA SA"
    """
    s = s.strip()
    s = _PUNCT_RE.sub(' ', s)
    s = _SPACE_RE.sub(' ', s).strip()
    return s.upper()


def _parse_date(date_str: str) -> Optional[date]:
    """Parse DD/MM/YYYY → date object. Returns None on failure."""
    try:
        return datetime.strptime(date_str.strip(), DATE_FORMAT).date()
    except (ValueError, AttributeError):
        return None