"""
tests/test_task4_4_diagnostic_prompt.py

Acceptance tests for Task 4.4 — infrastructure/llm/diagnostic_prompt.py

No Groq key required. No file I/O. Pure structural tests on prompt strings.

Usage
─────
    python tests/test_task4_4_diagnostic_prompt.py
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


# ══════════════════════════════════════════════════════════════════════════════
# TRACK A — Import
# ══════════════════════════════════════════════════════════════════════════════

def track_a():
    section("TRACK A — Import")
    try:
        from infrastructure.llm.diagnostic_prompt import (
            build_contract_extraction_prompt,
            build_publication_extraction_prompt,
            MAX_RAW_CHARS,
        )
        check("A1: infrastructure.llm.diagnostic_prompt imports cleanly", True)
        check("A2: MAX_RAW_CHARS == 4000",
              MAX_RAW_CHARS == 4000,
              hint=f"got: {MAX_RAW_CHARS}")
        return True
    except ImportError as e:
        check("A1: import cleanly", False, hint=str(e))
        return False


# ══════════════════════════════════════════════════════════════════════════════
# TRACK B — build_contract_extraction_prompt (MDAP B4.1–B4.3 + extras)
# ══════════════════════════════════════════════════════════════════════════════

def track_b_contract():
    section("TRACK B — build_contract_extraction_prompt")
    from infrastructure.llm.diagnostic_prompt import (
        build_contract_extraction_prompt, MAX_RAW_CHARS,
    )

    sample_text = (
        "EXTRATO DE CONTRATO Nº 002/2024 - PROCESSO Nº FIL-PRO-2023/00482 "
        "CONTRATANTE: DISTRIBUIDORA DE FILMES S/A - RIOFILME "
        "CONTRATADA: ARTE VITAL EXIBIÇÕES CINEMATOGRÁFICAS LTDA "
        "Data de assinatura: 16/09/2024"
    )

    prompt = build_contract_extraction_prompt(sample_text)

    # B4.1: returns non-empty string
    check("B4.1: returns non-empty string",
          isinstance(prompt, str) and len(prompt) > 0,
          hint=f"got type: {type(prompt)}, len: {len(prompt)}")

    # B4.2: JSON schema with all 5 contract fields present
    for field in ["processo_id", "contract_number", "signing_date",
                  "contratante", "contratada"]:
        check(f"B4.2: schema contains field '{field}'",
              field in prompt,
              hint=f"'{field}' not found in prompt")

    # B4.3: raw_text present in prompt body (truncated correctly)
    check("B4.3: raw_text content present in prompt",
          "FIL-PRO-2023/00482" in prompt,
          hint="sample text content not found in prompt body")

    # Extra: JSON-only instruction present
    check("B-extra: 'JSON' instruction in prompt",
          "JSON" in prompt.upper(),
          hint="no JSON instruction found")

    # Extra: null instruction present (not empty string)
    check("B-extra: 'null' mentioned for missing fields",
          "null" in prompt,
          hint="'null' not mentioned for missing fields")

    # Extra: DD/MM/YYYY format instruction present
    check("B-extra: DD/MM/YYYY format instruction present",
          "DD/MM/YYYY" in prompt,
          hint="date format instruction missing")

    # Extra: no-markdown instruction present
    check("B-extra: no markdown / no code fences instruction",
          "markdown" in prompt.lower() or "```" not in prompt,
          hint="no instruction to avoid markdown")

    # Extra: truncation — text longer than MAX_RAW_CHARS is cut
    long_text = "A" * (MAX_RAW_CHARS + 500)
    prompt_long = build_contract_extraction_prompt(long_text)
    check(f"B-extra: text truncated to {MAX_RAW_CHARS} chars in prompt",
          ("A" * MAX_RAW_CHARS) in prompt_long
          and ("A" * (MAX_RAW_CHARS + 1)) not in prompt_long,
          hint=f"truncation at {MAX_RAW_CHARS} not working correctly")

    # Extra: empty string input does not crash
    prompt_empty = build_contract_extraction_prompt("")
    check("B-extra: empty raw_text → prompt still returned (no crash)",
          isinstance(prompt_empty, str) and len(prompt_empty) > 0)

    # Extra: example from FIL-PRO-2023/00482 embedded
    check("B-extra: FIL-PRO-2023/00482 example embedded in prompt",
          "FIL-PRO-2023/00482" in prompt and "16/09/2024" in prompt,
          hint="example data not found in prompt")

    # Extra: CONTRATANTE and CONTRATADA field labels present
    check("B-extra: 'CONTRATANTE' label in prompt",
          "CONTRATANTE" in prompt.upper())
    check("B-extra: 'CONTRATADA' label in prompt",
          "CONTRATADA" in prompt.upper())

    info(f"  Contract prompt length: {len(prompt)} chars")
    info(f"  First 120 chars: {prompt[:120]!r}")


# ══════════════════════════════════════════════════════════════════════════════
# TRACK C — build_publication_extraction_prompt (MDAP B4.4–B4.5 + extras)
# ══════════════════════════════════════════════════════════════════════════════

def track_c_publication():
    section("TRACK C — build_publication_extraction_prompt")
    from infrastructure.llm.diagnostic_prompt import (
        build_publication_extraction_prompt, MAX_RAW_CHARS,
    )

    sample_pub = (
        "D.O.RIO - DIÁRIO OFICIAL DO MUNICÍPIO DO RIO DE JANEIRO "
        "Segunda-feira, 30 de setembro de 2024 "
        "EXTRATO DE CONTRATO Nº 002/2024 - PROCESSO Nº FIL-PRO-2023/00482 "
        "CONTRATANTE: DISTRIBUIDORA DE FILMES S/A - RIOFILME "
        "CONTRATADA: ARTE VITAL EXIBIÇÕES CINEMATOGRÁFICAS LTDA"
    )

    prompt = build_publication_extraction_prompt(sample_pub)

    # B4.4: returns non-empty string
    check("B4.4: returns non-empty string",
          isinstance(prompt, str) and len(prompt) > 0,
          hint=f"got type: {type(prompt)}, len: {len(prompt)}")

    # B4.5: text truncated to MAX_RAW_CHARS
    long_text = "B" * (MAX_RAW_CHARS + 500)
    prompt_long = build_publication_extraction_prompt(long_text)
    check(f"B4.5: text truncated to {MAX_RAW_CHARS} chars in prompt",
          ("B" * MAX_RAW_CHARS) in prompt_long
          and ("B" * (MAX_RAW_CHARS + 1)) not in prompt_long,
          hint=f"truncation at {MAX_RAW_CHARS} not working")

    # Extra: publication-specific schema fields present
    for field in ["processo_id_in_pub", "contract_number_in_pub",
                  "publication_date", "contratante_in_pub", "contratada_in_pub"]:
        check(f"C-extra: schema contains field '{field}'",
              field in prompt,
              hint=f"'{field}' not found in prompt")

    # Extra: raw_text content present
    check("C-extra: raw_text content present in prompt body",
          "FIL-PRO-2023/00482" in prompt,
          hint="sample text content not found in prompt")

    # Extra: null instruction
    check("C-extra: 'null' mentioned for missing fields",
          "null" in prompt)

    # Extra: DD/MM/YYYY instruction
    check("C-extra: DD/MM/YYYY format instruction present",
          "DD/MM/YYYY" in prompt)

    # Extra: gazette masthead hint present
    check("C-extra: masthead / gazette date hint present",
          "masthead" in prompt.lower() or "diário" in prompt.lower()
          or "D.O.RIO" in prompt or "publicado em" in prompt.lower(),
          hint="no gazette-specific date extraction hint found")

    # Extra: publication example date embedded
    check("C-extra: FIL-PRO-2023/00482 publication example embedded",
          "30/09/2024" in prompt,
          hint="publication example date '30/09/2024' not found")

    # Extra: two prompts are different documents (not identical)
    from infrastructure.llm.diagnostic_prompt import build_contract_extraction_prompt
    p_contract = build_contract_extraction_prompt(sample_pub)
    check("C-extra: contract and publication prompts are different",
          prompt != p_contract,
          hint="both prompts returned identical text")

    # Extra: empty string input does not crash
    prompt_empty = build_publication_extraction_prompt("")
    check("C-extra: empty raw_text → prompt still returned (no crash)",
          isinstance(prompt_empty, str) and len(prompt_empty) > 0)

    info(f"  Publication prompt length: {len(prompt)} chars")
    info(f"  First 120 chars: {prompt[:120]!r}")


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print(f"\n{BOLD}{'═' * 65}{RESET}")
    print(f"{BOLD}  TASK 4.4 — diagnostic_prompt.py Acceptance Tests{RESET}")
    print(f"{BOLD}{'═' * 65}{RESET}")

    ok = track_a()
    if ok:
        track_b_contract()
        track_c_publication()

    print(f"\n{BOLD}{'═' * 65}{RESET}")
    print(f"{BOLD}  RESULTS{RESET}")
    print(f"{'═' * 65}")
    print(f"  {GREEN}✓  Passed  : {PASSED}{RESET}")
    print(f"  {RED}✗  Failed  : {FAILED}{RESET}")

    if FAILED == 0:
        print(f"\n  {BOLD}{GREEN}✅ Task 4.4 COMPLETE — safe to proceed to Task 4.5{RESET}")
    else:
        print(f"\n  {BOLD}{RED}❌ {FAILED} check(s) failed{RESET}")
    print(f"{'═' * 65}\n")
    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())