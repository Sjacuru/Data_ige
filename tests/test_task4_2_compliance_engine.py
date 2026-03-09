"""
tests/test_task4_2_compliance_engine.py

Acceptance tests for Task 4.2 — domain/services/compliance_engine.py

Covers every acceptance criterion from the MDAP plus edge cases.
No Groq key required. No file I/O. Pure unit tests.

Usage
─────
    python tests/test_task4_2_compliance_engine.py
"""

import sys
import json
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# ── Console helpers ───────────────────────────────────────────────────────────
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


# ── LLM response builders ─────────────────────────────────────────────────────

def _llm_pass(confidence="high"):
    return json.dumps({
        "contratante_match": True,
        "contratada_match":  True,
        "contratante_explanation": "Same entity, abbreviated in publication.",
        "contratada_explanation":  "Names are identical.",
        "overall_verdict": "PASS",
        "confidence": confidence,
    })

def _llm_fail(confidence="high"):
    return json.dumps({
        "contratante_match": True,
        "contratada_match":  False,
        "contratante_explanation": "Same entity.",
        "contratada_explanation":  "Names differ — possible mismatch.",
        "overall_verdict": "FAIL",
        "confidence": confidence,
    })

def _llm_low_confidence():
    return _llm_pass(confidence="low")


# ══════════════════════════════════════════════════════════════════════════════
# TRACK A — Import
# ══════════════════════════════════════════════════════════════════════════════

def track_a():
    section("TRACK A — Import")
    try:
        from domain.services.compliance_engine import (
            evaluate_r001, evaluate_r002, RuleResult,
            PUBLICATION_DEADLINE_DAYS, DATE_FORMAT,
        )
        check("A1: domain.services.compliance_engine imports cleanly", True)
        check("A2: PUBLICATION_DEADLINE_DAYS == 20",
              PUBLICATION_DEADLINE_DAYS == 20,
              hint=f"got: {PUBLICATION_DEADLINE_DAYS}")
        check("A3: DATE_FORMAT == '%d/%m/%Y'",
              DATE_FORMAT == "%d/%m/%Y",
              hint=f"got: {DATE_FORMAT}")
        return True
    except ImportError as e:
        check("A1: domain.services.compliance_engine imports cleanly", False, hint=str(e))
        return False


# ══════════════════════════════════════════════════════════════════════════════
# TRACK B — R001 (14 checks)
# ══════════════════════════════════════════════════════════════════════════════

def track_b_r001():
    section("TRACK B — Rule R001: Publication Timeliness")
    from domain.services.compliance_engine import evaluate_r001, RuleResult

    # B1.1: 7 days → PASS
    r = evaluate_r001("03/02/2026", "10/02/2026")
    check("B1.1: delta=7 days → PASS",
          r.verdict == "PASS" and r.days_delta == 7,
          hint=f"verdict={r.verdict} days_delta={r.days_delta}")

    # B1.2: 24 days → FAIL
    r = evaluate_r001("01/01/2026", "25/01/2026")
    check("B1.2: delta=24 days → FAIL",
          r.verdict == "FAIL" and r.days_delta == 24,
          hint=f"verdict={r.verdict} days_delta={r.days_delta}")

    # B1.3: exactly 20 days → PASS (boundary inclusive)
    r = evaluate_r001("01/01/2026", "21/01/2026")
    check("B1.3: delta=20 days → PASS (boundary inclusive)",
          r.verdict == "PASS" and r.days_delta == 20,
          hint=f"verdict={r.verdict} days_delta={r.days_delta}")

    # B1.4: 21 days → FAIL (just over boundary)
    r = evaluate_r001("01/01/2026", "22/01/2026")
    check("B1.4: delta=21 days → FAIL (just over boundary)",
          r.verdict == "FAIL" and r.days_delta == 21,
          hint=f"verdict={r.verdict} days_delta={r.days_delta}")

    # B1.5: signing_date=None → INCONCLUSIVE (missing_date)
    r = evaluate_r001(None, "10/02/2026")
    check("B1.5: signing_date=None → INCONCLUSIVE (missing_date)",
          r.verdict == "INCONCLUSIVE" and r.inconclusive_reason == "missing_date",
          hint=f"verdict={r.verdict} reason={r.inconclusive_reason}")

    # B1.6: publication_date=None → INCONCLUSIVE (missing_date)
    r = evaluate_r001("03/02/2026", None)
    check("B1.6: publication_date=None → INCONCLUSIVE (missing_date)",
          r.verdict == "INCONCLUSIVE" and r.inconclusive_reason == "missing_date",
          hint=f"verdict={r.verdict} reason={r.inconclusive_reason}")

    # B1.7: both None → INCONCLUSIVE
    r = evaluate_r001(None, None)
    check("B1.7: both dates None → INCONCLUSIVE",
          r.verdict == "INCONCLUSIVE",
          hint=f"verdict={r.verdict}")

    # B1.8: signing_date in divergent_fields → INCONCLUSIVE (divergent_date)
    r = evaluate_r001("03/02/2026", "10/02/2026",
                      diagnostic_divergent_fields=["signing_date"])
    check("B1.8: signing_date in divergent_fields → INCONCLUSIVE (divergent_date)",
          r.verdict == "INCONCLUSIVE" and r.inconclusive_reason == "divergent_date",
          hint=f"verdict={r.verdict} reason={r.inconclusive_reason}")

    # B1.9: publication_date in divergent_fields → INCONCLUSIVE (divergent_date)
    r = evaluate_r001("03/02/2026", "10/02/2026",
                      diagnostic_divergent_fields=["publication_date"])
    check("B1.9: publication_date in divergent → INCONCLUSIVE (divergent_date)",
          r.verdict == "INCONCLUSIVE" and r.inconclusive_reason == "divergent_date",
          hint=f"verdict={r.verdict} reason={r.inconclusive_reason}")

    # B1.10: unparseable signing_date → INCONCLUSIVE (unparseable_date)
    r = evaluate_r001("99/99/9999", "10/02/2026")
    check("B1.10: unparseable signing_date → INCONCLUSIVE (unparseable_date)",
          r.verdict == "INCONCLUSIVE" and r.inconclusive_reason == "unparseable_date",
          hint=f"verdict={r.verdict} reason={r.inconclusive_reason}")

    # B1.11: unparseable publication_date → INCONCLUSIVE
    r = evaluate_r001("03/02/2026", "not-a-date")
    check("B1.11: unparseable publication_date → INCONCLUSIVE",
          r.verdict == "INCONCLUSIVE",
          hint=f"verdict={r.verdict}")

    # B1.12: PASS → requires_review = False
    r = evaluate_r001("03/02/2026", "10/02/2026")
    check("B1.12: PASS → requires_review = False",
          r.requires_review is False,
          hint=f"requires_review={r.requires_review}")

    # B1.13: FAIL → requires_review = True
    r = evaluate_r001("01/01/2026", "25/01/2026")
    check("B1.13: FAIL → requires_review = True",
          r.requires_review is True,
          hint=f"requires_review={r.requires_review}")

    # B1.14: publication before signing → INCONCLUSIVE (negative_delta)
    r = evaluate_r001("10/02/2026", "03/02/2026")
    check("B1.14: publication before signing → INCONCLUSIVE (negative_delta)",
          r.verdict == "INCONCLUSIVE" and r.inconclusive_reason == "negative_delta",
          hint=f"verdict={r.verdict} reason={r.inconclusive_reason}")

    # B1.15: real-world FIL-PRO-2023/00482 — signed 16/09/2024, published 30/09/2024
    r = evaluate_r001("16/09/2024", "30/09/2024")
    check("B1.15: FIL-PRO-2023/00482 real data → PASS (14 days)",
          r.verdict == "PASS" and r.days_delta == 14,
          hint=f"verdict={r.verdict} days_delta={r.days_delta}")
    info(f"  FIL-PRO-2023/00482: {r.explanation}")

    # B1.16: to_dict() returns all required keys
    r = evaluate_r001("03/02/2026", "10/02/2026")
    d = r.to_dict()
    required = {"verdict", "explanation", "confidence", "requires_review",
                "days_delta", "inconclusive_reason"}
    check("B1.16: to_dict() has all required keys",
          required.issubset(d.keys()),
          hint=f"missing: {required - set(d.keys())}")


# ══════════════════════════════════════════════════════════════════════════════
# TRACK C — R002 (13 checks)
# ══════════════════════════════════════════════════════════════════════════════

def track_c_r002():
    section("TRACK C — Rule R002: Party Name Matching")
    from domain.services.compliance_engine import evaluate_r002

    ctante_c = "DISTRIBUIDORA DE FILMES S/A - RIOFILME"
    ctante_p = "Distribuidora de Filmes S.A - RIOFILME"
    ctada_c  = "ARTE VITAL EXIBIÇÕES CINEMATOGRÁFICAS LTDA"
    ctada_p  = "Arte Vital Exibições Cinematográficas LTDA ME"

    # C2.1: matching parties + PASS LLM → PASS
    r = evaluate_r002(ctante_c, ctante_p, ctada_c, ctada_p, _llm_pass())
    check("C2.1: matching parties + PASS LLM → PASS",
          r.verdict == "PASS",
          hint=f"verdict={r.verdict}")

    # C2.2: mismatch + FAIL LLM → FAIL
    r = evaluate_r002(ctante_c, ctante_p, ctada_c, "EMPRESA ESTRANHA LTDA", _llm_fail())
    check("C2.2: mismatch + FAIL LLM → FAIL",
          r.verdict == "FAIL",
          hint=f"verdict={r.verdict}")

    # C2.3: contract_contratante=None → INCONCLUSIVE (missing_party)
    r = evaluate_r002(None, ctante_p, ctada_c, ctada_p, _llm_pass())
    check("C2.3: contract_contratante=None → INCONCLUSIVE (missing_party)",
          r.verdict == "INCONCLUSIVE" and r.inconclusive_reason == "missing_party",
          hint=f"verdict={r.verdict} reason={r.inconclusive_reason}")

    # C2.4: pub_contratante=None → INCONCLUSIVE
    r = evaluate_r002(ctante_c, None, ctada_c, ctada_p, _llm_pass())
    check("C2.4: pub_contratante=None → INCONCLUSIVE (missing_party)",
          r.verdict == "INCONCLUSIVE" and r.inconclusive_reason == "missing_party",
          hint=f"verdict={r.verdict} reason={r.inconclusive_reason}")

    # C2.5: contract_contratada=None → INCONCLUSIVE
    r = evaluate_r002(ctante_c, ctante_p, None, ctada_p, _llm_pass())
    check("C2.5: contract_contratada=None → INCONCLUSIVE (missing_party)",
          r.verdict == "INCONCLUSIVE" and r.inconclusive_reason == "missing_party",
          hint=f"verdict={r.verdict} reason={r.inconclusive_reason}")

    # C2.6: pub_contratada=None → INCONCLUSIVE
    r = evaluate_r002(ctante_c, ctante_p, ctada_c, None, _llm_pass())
    check("C2.6: pub_contratada=None → INCONCLUSIVE (missing_party)",
          r.verdict == "INCONCLUSIVE" and r.inconclusive_reason == "missing_party",
          hint=f"verdict={r.verdict} reason={r.inconclusive_reason}")

    # C2.7: contratante in divergent_fields → INCONCLUSIVE (divergent_party)
    r = evaluate_r002(ctante_c, ctante_p, ctada_c, ctada_p, _llm_pass(),
                      diagnostic_divergent_fields=["contratante"])
    check("C2.7: contratante in divergent_fields → INCONCLUSIVE (divergent_party)",
          r.verdict == "INCONCLUSIVE" and r.inconclusive_reason == "divergent_party",
          hint=f"verdict={r.verdict} reason={r.inconclusive_reason}")

    # C2.8: contratada in divergent_fields → INCONCLUSIVE
    r = evaluate_r002(ctante_c, ctante_p, ctada_c, ctada_p, _llm_pass(),
                      diagnostic_divergent_fields=["contratada"])
    check("C2.8: contratada in divergent_fields → INCONCLUSIVE (divergent_party)",
          r.verdict == "INCONCLUSIVE" and r.inconclusive_reason == "divergent_party",
          hint=f"verdict={r.verdict} reason={r.inconclusive_reason}")

    # C2.9: llm_response=None → INCONCLUSIVE (llm_unavailable)
    r = evaluate_r002(ctante_c, ctante_p, ctada_c, ctada_p, None)
    check("C2.9: llm_response=None → INCONCLUSIVE (llm_unavailable)",
          r.verdict == "INCONCLUSIVE" and r.inconclusive_reason == "llm_unavailable",
          hint=f"verdict={r.verdict} reason={r.inconclusive_reason}")

    # C2.10: malformed JSON → INCONCLUSIVE (llm_parse_error)
    r = evaluate_r002(ctante_c, ctante_p, ctada_c, ctada_p, "not json {{{{")
    check("C2.10: malformed LLM JSON → INCONCLUSIVE (llm_parse_error)",
          r.verdict == "INCONCLUSIVE" and r.inconclusive_reason == "llm_parse_error",
          hint=f"verdict={r.verdict} reason={r.inconclusive_reason}")

    # C2.11: LLM confidence=low → INCONCLUSIVE (llm_low_confidence)
    r = evaluate_r002(ctante_c, ctante_p, ctada_c, ctada_p, _llm_low_confidence())
    check("C2.11: LLM confidence=low → INCONCLUSIVE (llm_low_confidence)",
          r.verdict == "INCONCLUSIVE" and r.inconclusive_reason == "llm_low_confidence",
          hint=f"verdict={r.verdict} reason={r.inconclusive_reason}")

    # C2.12: PASS → requires_review = False
    r = evaluate_r002(ctante_c, ctante_p, ctada_c, ctada_p, _llm_pass())
    check("C2.12: PASS → requires_review = False",
          r.requires_review is False,
          hint=f"requires_review={r.requires_review}")

    # C2.13: FAIL → requires_review = True
    r = evaluate_r002(ctante_c, ctante_p, ctada_c, ctada_p, _llm_fail())
    check("C2.13: FAIL → requires_review = True",
          r.requires_review is True,
          hint=f"requires_review={r.requires_review}")

    # C2.14: to_dict() schema
    r = evaluate_r002(ctante_c, ctante_p, ctada_c, ctada_p, _llm_pass())
    d = r.to_dict()
    required = {"verdict", "explanation", "confidence", "requires_review",
                "days_delta", "inconclusive_reason"}
    check("C2.14: to_dict() has all required keys",
          required.issubset(d.keys()),
          hint=f"missing: {required - set(d.keys())}")

    # C2.15: medium confidence PASS still passes
    r = evaluate_r002(ctante_c, ctante_p, ctada_c, ctada_p,
                      _llm_pass(confidence="medium"))
    check("C2.15: medium confidence PASS → PASS (not INCONCLUSIVE)",
          r.verdict == "PASS",
          hint=f"verdict={r.verdict}")


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print(f"\n{BOLD}{'═' * 65}{RESET}")
    print(f"{BOLD}  TASK 4.2 — compliance_engine.py Acceptance Tests{RESET}")
    print(f"{BOLD}{'═' * 65}{RESET}")

    ok = track_a()
    if ok:
        track_b_r001()
        track_c_r002()

    print(f"\n{BOLD}{'═' * 65}{RESET}")
    print(f"{BOLD}  RESULTS{RESET}")
    print(f"{'═' * 65}")
    print(f"  {GREEN}✓  Passed  : {PASSED}{RESET}")
    print(f"  {RED}✗  Failed  : {FAILED}{RESET}")

    if FAILED == 0:
        print(f"\n  {BOLD}{GREEN}✅ Task 4.2 COMPLETE — safe to proceed to Task 4.3{RESET}")
    else:
        print(f"\n  {BOLD}{RED}❌ {FAILED} check(s) failed{RESET}")
    print(f"{'═' * 65}\n")
    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())