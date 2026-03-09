"""
tests/test_task4_3_extraction_comparator.py

Acceptance tests for Task 4.3 — domain/services/extraction_comparator.py

No Groq key required. No file I/O. Pure unit tests.

Usage
─────
    python tests/test_task4_3_extraction_comparator.py
"""

import sys
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

GREEN = "\033[92m"; RED = "\033[91m"; YELLOW = "\033[93m"
CYAN  = "\033[96m"; BOLD = "\033[1m"; RESET  = "\033[0m"

PASSED = FAILED = 0

def check(label, condition, hint=""):
    global PASSED, FAILED
    if condition:
        print(f"  {GREEN}✓{RESET}  {label}"); PASSED += 1
    else:
        print(f"  {RED}✗{RESET}  {label}")
        if hint: print(f"       {YELLOW}hint: {hint}{RESET}")
        FAILED += 1

def info(msg): print(f"  {CYAN}·{RESET}  {msg}")

def section(title):
    print(f"\n{BOLD}{title}{RESET}")
    print("  " + "─" * 60)


# ══════════════════════════════════════════════════════════════════════════════
# TRACK A — Import
# ══════════════════════════════════════════════════════════════════════════════

def track_a():
    section("TRACK A — Import")
    try:
        from domain.services.extraction_comparator import (
            compare_extractions, build_default_field_map,
            build_publication_field_map, DiagnosticResult,
            CRITICAL_FIELDS, _normalise, _compare_dates,
        )
        check("A1: domain.services.extraction_comparator imports cleanly", True)
        check("A2: CRITICAL_FIELDS contains signing_date, processo_id, contract_number",
              CRITICAL_FIELDS == frozenset({"signing_date", "processo_id", "contract_number"}),
              hint=f"got: {CRITICAL_FIELDS}")
        check("A3: build_default_field_map() returns dict with 5 entries",
              len(build_default_field_map()) == 5,
              hint=f"got: {len(build_default_field_map())} keys")
        check("A4: build_publication_field_map() returns dict with 5 entries",
              len(build_publication_field_map()) == 5,
              hint=f"got: {len(build_publication_field_map())} keys")
        return True
    except ImportError as e:
        check("A1: import cleanly", False, hint=str(e))
        return False


# ══════════════════════════════════════════════════════════════════════════════
# TRACK B — _normalise helper (7 checks)
# ══════════════════════════════════════════════════════════════════════════════

def track_b_normalise():
    section("TRACK B — _normalise helper")
    from domain.services.extraction_comparator import _normalise

    check("B1: strips trailing period",
          _normalise("ARTE E CULTURA LTDA.") == "ARTE E CULTURA LTDA",
          hint=_normalise("ARTE E CULTURA LTDA."))

    check("B2: case-insensitive — lower input matches upper",
          _normalise("Arte e Cultura Ltda.") == _normalise("ARTE E CULTURA LTDA."),
          hint=f"{_normalise('Arte e Cultura Ltda.')} != {_normalise('ARTE E CULTURA LTDA.')}")

    check("B3: collapses internal whitespace",
          _normalise("RIOFILME   SA") == "RIOFILME SA",
          hint=_normalise("RIOFILME   SA"))

    check("B4: removes comma and semicolons",
          _normalise("Empresa, Ltda; Foo") == "EMPRESA LTDA FOO",
          hint=_normalise("Empresa, Ltda; Foo"))

    # Slash and hyphen are each replaced by a space, then spaces are collapsed.
    # "S/A - RIOFILME" → "S A   RIOFILME" → collapsed → "S A RIOFILME"
    check("B5: removes hyphens and slashes (replaced by space, then collapsed)",
          _normalise("S/A - RIOFILME") == "S A RIOFILME",
          hint=_normalise("S/A - RIOFILME"))

    check("B6: RIOFILME abbreviation round-trip",
          _normalise("RIOFILME") == _normalise("RIOFILME"),
          hint="trivial identity")

    check("B7: strips leading/trailing whitespace",
          _normalise("  EMPRESA  ") == "EMPRESA",
          hint=_normalise("  EMPRESA  "))


# ══════════════════════════════════════════════════════════════════════════════
# TRACK C — _compare_dates helper (5 checks)
# ══════════════════════════════════════════════════════════════════════════════

def track_c_dates():
    section("TRACK C — _compare_dates helper")
    from domain.services.extraction_comparator import _compare_dates

    check("C1: same date string → True",
          _compare_dates("16/09/2024", "16/09/2024") is True)

    check("C2: different dates → False",
          _compare_dates("16/09/2024", "17/09/2024") is False)

    check("C3: both unparseable → True (consistent absence)",
          _compare_dates("not-a-date", "also-bad") is True)

    check("C4: one unparseable → False",
          _compare_dates("16/09/2024", "bad-date") is False)

    check("C5: same date, different formatting spaces → True",
          _compare_dates("01/01/2026", " 01/01/2026 ") is True)


# ══════════════════════════════════════════════════════════════════════════════
# TRACK D — compare_extractions() core logic (MDAP B3 checks + extras)
# ══════════════════════════════════════════════════════════════════════════════

def track_d_compare():
    section("TRACK D — compare_extractions() core logic")
    from domain.services.extraction_comparator import (
        compare_extractions, build_default_field_map, DiagnosticResult,
    )

    fmap = build_default_field_map()

    # ── D/B3.1: identical inputs → CONFIRMED ──────────────────────────────────
    det = {
        "signing_date":   "16/09/2024",
        "processo_id":    "FIL-PRO-2023/00482",
        "contract_number": "002/2024",
        "contratante":    "DISTRIBUIDORA DE FILMES S/A - RIOFILME",
        "contratada":     "ARTE VITAL EXIBIÇÕES CINEMATOGRÁFICAS LTDA",
    }
    llm = dict(det)  # identical
    r = compare_extractions(det, llm, fmap)
    check("D/B3.1: identical inputs → CONFIRMED",
          r.agreement_level == "CONFIRMED",
          hint=f"got: {r.agreement_level}")
    check("D/B3.1: no divergent fields",
          r.fields_divergent == [],
          hint=f"divergent: {r.fields_divergent}")
    check("D/B3.1: all 5 fields confirmed",
          len(r.fields_confirmed) == 5,
          hint=f"confirmed count: {len(r.fields_confirmed)}")

    # ── D/B3.2: case-insensitive normalised names match → CONFIRMED ────────────
    # Use variants that differ only in case and punctuation — same words.
    # "ARTE VITAL EXIBIÇÕES CINEMATOGRÁFICAS LTDA" vs
    # "Arte Vital Exibições Cinematográficas Ltda."  → same after normalise.
    # "DISTRIBUIDORA DE FILMES S/A - RIOFILME" vs
    # "Distribuidora de Filmes S/A - RIOFILME"       → same after normalise.
    llm_norm = dict(det)
    llm_norm["contratante"] = "Distribuidora de Filmes S/A - RIOFILME"
    llm_norm["contratada"]  = "Arte Vital Exibições Cinematográficas Ltda."
    r = compare_extractions(det, llm_norm, fmap)
    check("D/B3.2: normalised name variants → CONFIRMED (no divergence)",
          r.agreement_level == "CONFIRMED",
          hint=f"got: {r.agreement_level}, divergent: {r.fields_divergent}")

    # ── D/B3.3: signing_date mismatch → DIVERGENT (critical) ──────────────────
    llm_date = dict(det)
    llm_date["signing_date"] = "17/09/2024"  # one day off
    r = compare_extractions(det, llm_date, fmap)
    check("D/B3.3: signing_date mismatch → DIVERGENT",
          r.agreement_level == "DIVERGENT",
          hint=f"got: {r.agreement_level}")
    check("D/B3.3: signing_date in fields_divergent",
          "signing_date" in r.fields_divergent,
          hint=f"divergent: {r.fields_divergent}")

    # ── D/B3.4: contract_number mismatch → DIVERGENT (critical) ───────────────
    llm_cnum = dict(det)
    llm_cnum["contract_number"] = "003/2024"
    r = compare_extractions(det, llm_cnum, fmap)
    check("D/B3.4: contract_number mismatch → DIVERGENT",
          r.agreement_level == "DIVERGENT",
          hint=f"got: {r.agreement_level}")

    # ── D/B3.5: party name mismatch only → PARTIAL (non-critical) ─────────────
    llm_party = dict(det)
    llm_party["contratante"] = "EMPRESA COMPLETAMENTE DIFERENTE LTDA"
    r = compare_extractions(det, llm_party, fmap)
    check("D/B3.5: party mismatch only → PARTIAL (not DIVERGENT)",
          r.agreement_level == "PARTIAL",
          hint=f"got: {r.agreement_level}")
    check("D/B3.5: contratante in fields_divergent",
          "contratante" in r.fields_divergent,
          hint=f"divergent: {r.fields_divergent}")

    # ── D/B3.6: DiagnosticResult schema ───────────────────────────────────────
    r = compare_extractions(det, llm, fmap)
    d = r.to_dict()
    required = {"agreement_level", "fields_confirmed", "fields_divergent",
                "divergence_detail", "auditor_action_required"}
    check("D/B3.6: DiagnosticResult.to_dict() has all required keys",
          required.issubset(d.keys()),
          hint=f"missing: {required - set(d.keys())}")

    # ── Extra: CONFIRMED → auditor_action_required = False ────────────────────
    r = compare_extractions(det, dict(det), fmap)
    check("D-extra: CONFIRMED → auditor_action_required = False",
          r.auditor_action_required is False,
          hint=f"got: {r.auditor_action_required}")

    # ── Extra: PARTIAL → auditor_action_required = True ───────────────────────
    llm_partial = dict(det)
    llm_partial["contratada"] = "OUTRA EMPRESA LTDA"
    r = compare_extractions(det, llm_partial, fmap)
    check("D-extra: PARTIAL → auditor_action_required = True",
          r.auditor_action_required is True,
          hint=f"got: {r.auditor_action_required}")

    # ── Extra: DIVERGENT → auditor_action_required = True ─────────────────────
    llm_div = dict(det)
    llm_div["processo_id"] = "TUR-PRO-2025/99999"
    r = compare_extractions(det, llm_div, fmap)
    check("D-extra: DIVERGENT → auditor_action_required = True",
          r.auditor_action_required is True,
          hint=f"got: {r.auditor_action_required}")

    # ── Extra: divergence_detail has readable message ─────────────────────────
    llm_detail = dict(det)
    llm_detail["signing_date"] = "03/01/2026"
    r = compare_extractions(det, llm_detail, fmap)
    detail = r.divergence_detail.get("signing_date", "")
    check("D-extra: divergence_detail contains det and llm values",
          "det:" in detail and "llm:" in detail,
          hint=f"detail: {repr(detail)}")

    # ── Extra: both values None → field confirmed (consistent absence) ─────────
    det_none = dict(det)
    det_none["contract_number"] = None
    llm_none = dict(det)
    llm_none["contract_number"] = None
    r = compare_extractions(det_none, llm_none, fmap)
    check("D-extra: both values None → field confirmed (consistent absence)",
          "contract_number" in r.fields_confirmed,
          hint=f"fields_confirmed: {r.fields_confirmed}")

    # ── Extra: one None, one value → field diverged ────────────────────────────
    det_one = dict(det)
    det_one["contract_number"] = None
    llm_one = dict(det)  # llm has a value
    r = compare_extractions(det_one, llm_one, fmap)
    check("D-extra: one side None, other has value → diverged",
          "contract_number" in r.fields_divergent,
          hint=f"fields_divergent: {r.fields_divergent}")

    # ── Extra: processo_id mismatch → DIVERGENT (third critical field) ─────────
    llm_pid = dict(det)
    llm_pid["processo_id"] = "SMF-PRO-2024/00001"
    r = compare_extractions(det, llm_pid, fmap)
    check("D-extra: processo_id mismatch → DIVERGENT",
          r.agreement_level == "DIVERGENT",
          hint=f"got: {r.agreement_level}")

    # ── Extra: multiple non-critical divergences → PARTIAL (not DIVERGENT) ────
    llm_multi = dict(det)
    llm_multi["contratante"] = "EMPRESA A LTDA"
    llm_multi["contratada"]  = "EMPRESA B LTDA"
    r = compare_extractions(det, llm_multi, fmap)
    check("D-extra: two non-critical divergences → PARTIAL",
          r.agreement_level == "PARTIAL",
          hint=f"got: {r.agreement_level}")
    check("D-extra: both party fields in divergent list",
          "contratante" in r.fields_divergent and "contratada" in r.fields_divergent,
          hint=f"divergent: {r.fields_divergent}")

    # ── Extra: publication field_map works correctly ───────────────────────────
    from domain.services.extraction_comparator import build_publication_field_map
    pub_fmap = build_publication_field_map()
    det_pub = {
        "processo_id":    "FIL-PRO-2023/00482",
        "contract_number": "002/2024",
        "publication_date": "30/09/2024",
        "contratante":    "DISTRIBUIDORA DE FILMES S/A - RIOFILME",
        "contratada":     "ARTE VITAL EXIBIÇÕES CINEMATOGRÁFICAS LTDA",
    }
    llm_pub = {
        "processo_id_in_pub":    "FIL-PRO-2023/00482",
        "contract_number_in_pub": "002/2024",
        "publication_date":      "30/09/2024",
        "contratante_in_pub":    "Distribuidora de Filmes S.A - RIOFILME",
        "contratada_in_pub":     "Arte Vital Exibições Cinematográficas LTDA",
    }
    r = compare_extractions(det_pub, llm_pub, pub_fmap)
    check("D-extra: publication field_map — matching data → CONFIRMED",
          r.agreement_level == "CONFIRMED",
          hint=f"got: {r.agreement_level}, divergent: {r.fields_divergent}")

    # ── Extra: FIL-PRO-2023/00482 full real-world smoke test ──────────────────
    info("FIL-PRO-2023/00482 real-world smoke test:")
    info(f"  agreement_level  : {r.agreement_level}")
    info(f"  fields_confirmed : {r.fields_confirmed}")
    info(f"  fields_divergent : {r.fields_divergent}")


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print(f"\n{BOLD}{'═' * 65}{RESET}")
    print(f"{BOLD}  TASK 4.3 — extraction_comparator.py Acceptance Tests{RESET}")
    print(f"{BOLD}{'═' * 65}{RESET}")

    ok = track_a()
    if ok:
        track_b_normalise()
        track_c_dates()
        track_d_compare()

    print(f"\n{BOLD}{'═' * 65}{RESET}")
    print(f"{BOLD}  RESULTS{RESET}")
    print(f"{'═' * 65}")
    print(f"  {GREEN}✓  Passed  : {PASSED}{RESET}")
    print(f"  {RED}✗  Failed  : {FAILED}{RESET}")

    if FAILED == 0:
        print(f"\n  {BOLD}{GREEN}✅ Task 4.3 COMPLETE — safe to proceed to Task 4.4{RESET}")
    else:
        print(f"\n  {BOLD}{RED}❌ {FAILED} check(s) failed{RESET}")
    print(f"{'═' * 65}\n")
    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())