"""
tests/test_task4_5_r002_prompt.py

Acceptance tests for Task 4.5 — infrastructure/llm/r002_prompt.py

No Groq key required. No file I/O. Pure structural tests on the prompt string.

Usage
─────
    python tests/test_task4_5_r002_prompt.py
"""

import sys
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


# ── Real party names (FIL-PRO-2023/00482) ────────────────────────────────────
CT_C = "DISTRIBUIDORA DE FILMES S/A - RIOFILME"
CT_P = "Distribuidora de Filmes S.A - RIOFILME"
CA_C = "ARTE VITAL EXIBIÇÕES CINEMATOGRÁFICAS LTDA"
CA_P = "Arte Vital Exibições Cinematográficas LTDA"


# ══════════════════════════════════════════════════════════════════════════════
# TRACK A — Import
# ══════════════════════════════════════════════════════════════════════════════

def track_a():
    section("TRACK A — Import")
    try:
        from infrastructure.llm.r002_prompt import build_r002_prompt
        check("A1: infrastructure.llm.r002_prompt imports cleanly", True)
        return True
    except ImportError as e:
        check("A1: import cleanly", False, hint=str(e))
        return False


# ══════════════════════════════════════════════════════════════════════════════
# TRACK B — Structural checks on prompt content (MDAP B5 + extras)
# ══════════════════════════════════════════════════════════════════════════════

def track_b():
    section("TRACK B — build_r002_prompt structural checks")
    from infrastructure.llm.r002_prompt import build_r002_prompt

    prompt = build_r002_prompt(CT_C, CT_P, CA_C, CA_P)

    # B5.1: returns non-empty string
    check("B5.1: returns non-empty string",
          isinstance(prompt, str) and len(prompt) > 0,
          hint=f"type={type(prompt)}, len={len(prompt)}")

    # B5.2: all 4 party fields present in prompt body
    check("B5.2: contract_contratante present in prompt",
          CT_C in prompt,
          hint=f"'{CT_C}' not in prompt")
    check("B5.2: pub_contratante present in prompt",
          CT_P in prompt,
          hint=f"'{CT_P}' not in prompt")
    check("B5.2: contract_contratada present in prompt",
          CA_C in prompt,
          hint=f"'{CA_C}' not in prompt")
    check("B5.2: pub_contratada present in prompt",
          CA_P in prompt,
          hint=f"'{CA_P}' not in prompt")

    # B5.3: JSON schema explicit in prompt
    for key in ["contratante_match", "contratada_match",
                "contratante_explanation", "contratada_explanation",
                "overall_verdict", "confidence"]:
        check(f"B5.3: schema key '{key}' in prompt",
              key in prompt,
              hint=f"'{key}' not found in prompt")

    # Extra: PASS/FAIL verdict options mentioned
    check("B-extra: 'PASS' verdict option in prompt",
          '"PASS"' in prompt or "'PASS'" in prompt or "PASS" in prompt)
    check("B-extra: 'FAIL' verdict option in prompt",
          '"FAIL"' in prompt or "'FAIL'" in prompt or "FAIL" in prompt)

    # Extra: confidence levels mentioned
    for level in ["high", "medium", "low"]:
        check(f"B-extra: confidence level '{level}' in prompt",
              level in prompt,
              hint=f"'{level}' not found in prompt")

    # Extra: JSON-only output instruction
    check("B-extra: JSON-only output instruction present",
          "JSON" in prompt.upper() and
          ("no prose" in prompt.lower() or "no markdown" in prompt.lower()
           or "only" in prompt.lower()),
          hint="no JSON-only instruction found")

    # Extra: null instruction for missing fields
    check("B-extra: 'null' mentioned for missing/empty fields",
          "null" in prompt,
          hint="'null' handling not mentioned in prompt")

    # Extra: LTDA/SA equivalence hints present
    check("B-extra: Brazilian company suffix equivalences mentioned (S/A or LTDA)",
          "S/A" in prompt or "LTDA" in prompt,
          hint="no Brazilian suffix equivalences found")

    # Extra: real example embedded
    check("B-extra: RIOFILME example embedded in prompt",
          "RIOFILME" in prompt,
          hint="FIL-PRO-2023/00482 example not embedded")

    info(f"  Prompt length: {len(prompt)} chars")
    info(f"  First 120 chars: {prompt[:120]!r}")


# ══════════════════════════════════════════════════════════════════════════════
# TRACK C — Edge case inputs
# ══════════════════════════════════════════════════════════════════════════════

def track_c():
    section("TRACK C — Edge case inputs")
    from infrastructure.llm.r002_prompt import build_r002_prompt

    # C1: None inputs render as "null" string in prompt
    prompt_none = build_r002_prompt(None, None, None, None)
    check("C1: None inputs → no crash, returns string",
          isinstance(prompt_none, str) and len(prompt_none) > 0)
    check("C1: None inputs → 'null' appears in prompt body",
          "null" in prompt_none,
          hint="null not rendered for None party values")

    # C2: partial None — one side missing
    prompt_partial = build_r002_prompt(CT_C, None, CA_C, CA_P)
    check("C2: partial None → no crash",
          isinstance(prompt_partial, str) and len(prompt_partial) > 0)
    check("C2: present value still in prompt",
          CT_C in prompt_partial,
          hint=f"'{CT_C}' not found in partial-None prompt")

    # C3: empty string inputs
    prompt_empty = build_r002_prompt("", "", "", "")
    check("C3: empty string inputs → no crash",
          isinstance(prompt_empty, str) and len(prompt_empty) > 0)

    # C4: different prompts for different inputs (not cached/static)
    prompt_a = build_r002_prompt("EMPRESA A LTDA", "Empresa A Ltda",
                                 "EMPRESA B LTDA", "Empresa B Ltda")
    prompt_b = build_r002_prompt("EMPRESA C LTDA", "Empresa C Ltda",
                                 "EMPRESA D LTDA", "Empresa D Ltda")
    check("C4: different inputs produce different prompts",
          prompt_a != prompt_b,
          hint="function returned identical prompt for different inputs")

    # C5: all four party values appear in correct positions in prompt
    p = build_r002_prompt("AAA CONTRATANTE", "BBB CONTRATANTE",
                           "CCC CONTRATADA",  "DDD CONTRATADA")
    check("C5: all four distinct party values present in prompt",
          all(v in p for v in ["AAA CONTRATANTE", "BBB CONTRATANTE",
                                "CCC CONTRATADA",  "DDD CONTRATADA"]),
          hint="one or more party values not found in prompt")


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print(f"\n{BOLD}{'═' * 65}{RESET}")
    print(f"{BOLD}  TASK 4.5 — r002_prompt.py Acceptance Tests{RESET}")
    print(f"{BOLD}{'═' * 65}{RESET}")

    ok = track_a()
    if ok:
        track_b()
        track_c()

    print(f"\n{BOLD}{'═' * 65}{RESET}")
    print(f"{BOLD}  RESULTS{RESET}")
    print(f"{'═' * 65}")
    print(f"  {GREEN}✓  Passed  : {PASSED}{RESET}")
    print(f"  {RED}✗  Failed  : {FAILED}{RESET}")

    if FAILED == 0:
        print(f"\n  {BOLD}{GREEN}✅ Task 4.5 COMPLETE — safe to proceed to Task 4.6{RESET}")
    else:
        print(f"\n  {BOLD}{RED}❌ {FAILED} check(s) failed{RESET}")
    print(f"{'═' * 65}\n")
    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())