"""
domain/services/status_mapper.py

Status mapping utilities for Epic 5 conformity scoring.
"""

from __future__ import annotations


RULE_STATUS_MAP = {
	"PASS": "CONFORME",
	"FAIL": "NÃO CONFORME",
	"INCONCLUSIVE": "INCOMPLETE",
}

DIAGNOSTIC_MAP = {
	"CONFIRMED": "CONFORME",
	"PARTIAL": "PARCIAL",
	"DIVERGENT": "INCOMPLETE",
	"SKIPPED": "PARCIAL",
}


def map_rule_status(epic4_verdict: str | None) -> str:
	"""Map Epic 4 rule verdict into Epic 5 taxonomy."""
	key = (epic4_verdict or "INCONCLUSIVE").strip().upper()
	return RULE_STATUS_MAP.get(key, "INCOMPLETE")


def map_diagnostic(agreement_level: str | None) -> str:
	"""Map extraction diagnostic agreement level into Epic 5 taxonomy."""
	key = (agreement_level or "SKIPPED").strip().upper()
	return DIAGNOSTIC_MAP.get(key, "PARCIAL")

