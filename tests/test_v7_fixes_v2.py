"""
tests/test_v7_fixes.py  (v2 — corrected fixtures)

Regression tests for three v7 fixes and Gap 4 diagnostic.

Fix 1 — _clean_party strips trailing "e" from contratante
Fix 2 — _extract_edition returns None when no masthead present
Fix 3 — object_summary reads multi-line content, stops at structural boundary
Gap 4 — FIL-PRO-2023/00482 embedded flag vs. DoWeb no_results diagnostic

Usage
─────
    python tests/test_v7_fixes.py
    python tests/test_v7_fixes.py --unit-only   # skip Gap 4 file I/O
    python tests/test_v7_fixes.py --gap4-only   # only Gap 4
"""

import re
import sys
import json
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# ══════════════════════════════════════════════════════════════════════════════
# CONSOLE HELPERS
# ══════════════════════════════════════════════════════════════════════════════

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

PASSED = FAILED = WARNINGS = 0


def check(label: str, condition: bool, hint: str = "") -> None:
    global PASSED, FAILED
    if condition:
        print(f"  {GREEN}✓{RESET}  {label}")
        PASSED += 1
    else:
        print(f"  {RED}✗{RESET}  {label}")
        if hint:
            print(f"       {YELLOW}hint: {hint}{RESET}")
        FAILED += 1


def warn(msg: str) -> None:
    global WARNINGS
    print(f"  {YELLOW}⚠{RESET}  {msg}")
    WARNINGS += 1


def info(msg: str) -> None:
    print(f"  {CYAN}·{RESET}  {msg}")


def section(title: str) -> None:
    print(f"\n{BOLD}{title}{RESET}")
    print("  " + "─" * 60)


# ══════════════════════════════════════════════════════════════════════════════
# FIXTURES
# ══════════════════════════════════════════════════════════════════════════════

# ── Fix 1 fixture: full prose opener that triggers Pattern 0 ──────────────────
# Pattern 0 requires ",\s+inscrit[ao]|,\s+CNPJ" after the contratante name.
# Without it, party extraction returns None (vacuous pass — not useful).
_FIX1_CONTRACT = """\
CONTRATO Nº 2403453/2024

Processo Instrutivo: FIL-PRO-2023/00482.

Aos 16 dias do mês de Setembro de 2024, a DISTRIBUIDORA DE FILMES S/A - RIOFILME,
inscrita no CNPJ 01.219.699/0001-34, neste ato representada por seu Diretor Presidente,
doravante denominada CONTRATANTE, e a empresa ARTE VITAL EXIBIÇÕES CINEMATOGRÁFICAS LTDA,
inscrita no CNPJ 00.000.000/0001-00, denominada CONTRATADA.

CLÁUSULA PRIMEIRA - OBJETO
Constitui objeto do presente a contratação de empresa especializada para
operação do CINECARIOCA JOSÉ WILKER, cinema municipal localizado no bairro
da Tijuca, incluindo a gestão de bilheteria, manutenção e programação cultural.

Valor Total: R$ 1.216.829,52
Vigência: 24 meses.
"""

# ── Fix 1 unit inputs — direct _clean_party calls ────────────────────────────
_CLEAN_PARTY_CASES = [
    # (input,                                         expected_no_trailing_e, name_fragment)
    ("DISTRIBUIDORA DE FILMES S/A - RIOFILME e",      True,  "RIOFILME"),
    ("SECRETARIA MUNICIPAL DE SAÚDE    e  ",           True,  "SAÚDE"),
    ("ARTE E CULTURA PRODUÇÕES LTDA",                  True,  "ARTE E CULTURA"),  # "E" inside name
    ("EMPRESA DE TECNOLOGIA E INOVAÇÃO",               True,  "INOVAÇÃO"),        # "E" before last word
    ("Verde Tecnologia LTDA",                          True,  "Verde"),           # ends with "e" inside word
    ("FUNDAÇÃO MUNICIPAL e",                           True,  "FUNDAÇÃO"),
]

# ── Fix 3 fixtures ────────────────────────────────────────────────────────────
# Multi-line object body — the boilerplate opener alone is uninformative
_FIX3_CONTRACT = """\
CONTRATO Nº 0055/2023

Processo: TUR-PRO-2025/01221

Aos 3 dias do mês de Fevereiro de 2026, a EMPRESA MUNICIPAL DE TURISMO DO RIO DE
JANEIRO S.A. – RIOTUR, inscrita no CNPJ 33.400.560/0001-36, denominada CONTRATANTE,
e a empresa SHOWS & EVENTOS LTDA, inscrita no CNPJ 99.888.777/0001-11, denominada CONTRATADA.

CLÁUSULA PRIMEIRA - OBJETO
Constitui objeto do presente contrato a contratação de empresa especializada para
operação do complexo turístico do Morro da Urca, incluindo transporte por teleférico,
manutenção das instalações, atendimento ao público e programação de eventos culturais
e educacionais ao longo do período contratual.

Valor Total: R$ 287.000,00
Vigência: 12 meses.
"""

# Simple contract where object IS on one line (should still work)
_FIX3_ONELINER = """\
CONTRATO Nº 0001/2025

CLÁUSULA PRIMEIRA - OBJETO
Prestação de serviços de limpeza e conservação predial.

Valor Total: R$ 50.000,00
"""

# ── Fix 2 fixtures ────────────────────────────────────────────────────────────
_GAZETTE_WITH_MASTHEAD = """\
Segunda-feira, 30 de Setembro de 2024
D.O.RIO - Nº 136

DISTRIBUIDORA DE FILMES S/A - RIOFILME
EXTRATO DE INSTRUMENTO CONTRATUAL
Processo Instrutivo: FIL-PRO-2023/00482.- CO 01/2024.
Contrato nº: 2403453/2024.
Data da Assinatura: 16/09/2024.
Partes: Distribuidora de Filmes S.A - RIOFILME e Arte Vital Exibições Cinematográficas LTDA
Objeto: Contratação de empresa especializada para operação do CINECARIOCA JOSÉ WILKER.
Valor Total: R$ 1.216.829,52
Vigência: 24 meses.
"""

_GAZETTE_NO_MASTHEAD = """\
DISTRIBUIDORA DE FILMES S/A - RIOFILME
EXTRATO DE INSTRUMENTO CONTRATUAL
Processo Instrutivo: FIL-PRO-2023/00482.- CO 01/2024.
Contrato nº: 2403453/2024.
Data da Assinatura: 16/09/2024.
Partes: Distribuidora de Filmes S.A - RIOFILME e Arte Vital Exibições Cinematográficas LTDA
Objeto: Contratação de empresa especializada para operação do CINECARIOCA JOSÉ WILKER.
Valor Total: R$ 1.216.829,52
Vigência: 24 meses.
"""


# ══════════════════════════════════════════════════════════════════════════════
# FIX 1 — _clean_party trailing "e"
# ══════════════════════════════════════════════════════════════════════════════

def test_fix1_clean_party():
    section("FIX 1 — _clean_party: trailing conjunction 'e' stripped")

    try:
        from infrastructure.extractors.contract_preprocessor import _clean_party
    except ImportError as e:
        check("_clean_party importable", False, hint=str(e))
        return

    # ── Unit cases ────────────────────────────────────────────────────────────
    for raw, expect_clean, fragment in _CLEAN_PARTY_CASES:
        result = _clean_party(raw)
        has_trailing_e = bool(re.search(r'\s+e\s*$', result, re.IGNORECASE))
        fragment_present = fragment.upper() in result.upper()

        check(
            f"Fix1-unit: no trailing 'e' in '{raw[:45]}...'",
            not has_trailing_e,
            hint=f"got: '{result}'"
        )
        check(
            f"Fix1-unit: name fragment '{fragment}' preserved",
            fragment_present,
            hint=f"got: '{result}'"
        )

    # ── End-to-end pipeline check ─────────────────────────────────────────────
    # This fixture has "inscrita no CNPJ" — required by Pattern 0 to extract parties
    try:
        from infrastructure.extractors.contract_preprocessor import preprocess_text
        result = preprocess_text("FIX1-E2E", _FIX1_CONTRACT)
        contratante = result["header"].get("contratante") or ""
        contratada  = result["header"].get("contratada")  or ""

        check(
            "Fix1-E2E: contratante extracted (not None)",
            len(contratante) > 5,
            hint="Pattern 0 failed to extract — check fixture has 'inscrita no CNPJ'"
        )
        check(
            "Fix1-E2E: contratante has no trailing 'e'",
            not bool(re.search(r'\s+e\s*$', contratante, re.IGNORECASE)),
            hint=f"got: '{contratante}'"
        )
        check(
            "Fix1-E2E: contratante contains RIOFILME",
            "RIOFILME" in contratante.upper(),
            hint=f"got: '{contratante}'"
        )
        check(
            "Fix1-E2E: contratada extracted (not None)",
            len(contratada) > 5,
            hint=f"got: '{contratada}'"
        )
        info(f"  contratante: '{contratante}'")
        info(f"  contratada:  '{contratada}'")

    except Exception as ex:
        warn(f"End-to-end pipeline test error: {ex}")


# ══════════════════════════════════════════════════════════════════════════════
# FIX 2 — _extract_edition: no masthead → None
# ══════════════════════════════════════════════════════════════════════════════

def test_fix2_edition():
    section("FIX 2 — _extract_edition: no masthead → None (not contract number)")

    try:
        from infrastructure.extractors.publication_parser import parse_publication_text
    except ImportError as e:
        check("publication_parser importable", False, hint=str(e))
        return

    # Case A: WITH masthead — edition "136" correctly extracted
    r_with = parse_publication_text(_GAZETTE_WITH_MASTHEAD, "FIL-PRO-2023/00482")
    check(
        "Fix2-A: edition = '136' when masthead present",
        r_with.get("edition") == "136",
        hint=f"got: '{r_with.get('edition')}'"
    )
    check(
        "Fix2-A: contract_number = '2403453/2024' (not contaminated by edition)",
        r_with.get("contract_number") == "2403453/2024",
        hint=f"got: '{r_with.get('contract_number')}'"
    )
    info(f"  with masthead  → edition='{r_with.get('edition')}' | "
         f"contract_number='{r_with.get('contract_number')}'")

    # Case B: WITHOUT masthead — edition must be None, contract_number correct
    r_no = parse_publication_text(_GAZETTE_NO_MASTHEAD, "FIL-PRO-2023/00482")
    check(
        "Fix2-B: edition = None when no masthead",
        r_no.get("edition") is None,
        hint=f"got: '{r_no.get('edition')}' — "
             "if '2403453' appears, Fix 2 is NOT yet applied"
    )
    check(
        "Fix2-B: contract_number still '2403453/2024' without masthead",
        r_no.get("contract_number") == "2403453/2024",
        hint=f"got: '{r_no.get('contract_number')}'"
    )
    info(f"  no masthead    → edition='{r_no.get('edition')}' | "
         f"contract_number='{r_no.get('contract_number')}'")

    # Case C: Other fields not affected
    check(
        "Fix2-C: signing_date_in_pub still extracted without masthead",
        r_no.get("signing_date_in_pub") == "16/09/2024",
        hint=f"got: '{r_no.get('signing_date_in_pub')}'"
    )
    check(
        "Fix2-C: contratante still extracted without masthead",
        r_no.get("contratante") is not None,
        hint="contratante is None — parser broke other fields"
    )

    # Case D: masthead day coverage — all 7 weekdays
    section("FIX 2 (bonus) — masthead regex covers all 7 weekdays")
    from infrastructure.extractors.publication_parser import _MASTHEAD_DATE_RE
    day_tests = [
        ("Segunda-feira, 30 de Setembro de 2024", "30/09/2024"),
        ("Terça-feira, 01 de Outubro de 2024",    "01/10/2024"),
        ("Quarta-feira, 02 de Outubro de 2024",   "02/10/2024"),
        ("Quinta-feira, 03 de Outubro de 2024",   "03/10/2024"),
        ("Sexta-feira, 04 de Outubro de 2024",    "04/10/2024"),
        ("Sábado, 05 de Outubro de 2024",         "05/10/2024"),
        ("Domingo, 06 de Outubro de 2024",        "06/10/2024"),
    ]
    from infrastructure.extractors.publication_parser import _MONTHS_PT
    for masthead_line, expected_date in day_tests:
        m = _MASTHEAD_DATE_RE.search(masthead_line)
        if m:
            day   = m.group(1).zfill(2)
            month = _MONTHS_PT.get(m.group(2).lower(), "??")
            year  = m.group(3)
            got   = f"{day}/{month}/{year}"
        else:
            got = None
        check(
            f"masthead '{masthead_line[:20]}...' → {expected_date}",
            got == expected_date,
            hint=f"got: '{got}'"
        )


# ══════════════════════════════════════════════════════════════════════════════
# FIX 3 — object_summary boundary-aware
# ══════════════════════════════════════════════════════════════════════════════

def test_fix3_object_summary():
    section("FIX 3 — object_summary: multi-line boundary-aware extraction")

    try:
        from infrastructure.extractors.contract_preprocessor import preprocess_text
    except ImportError as e:
        check("contract_preprocessor importable", False, hint=str(e))
        return

    # ── Multi-line case ───────────────────────────────────────────────────────
    r = preprocess_text("FIX3-MULTI", _FIX3_CONTRACT)
    obj = r["header"].get("object_summary") or ""
    info(f"  multi-line summary ({len(obj)} chars): '{obj[:100]}...'")

    check(
        "Fix3-A: object_summary > 80 chars (not just boilerplate opener)",
        len(obj) > 80,
        hint=f"got {len(obj)} chars — Fix 3 not applied or boundary fired too early"
    )
    check(
        "Fix3-B: identifies the venue (Morro da Urca / teleférico)",
        any(kw in obj.upper() for kw in ("URCA", "TELEFÉRICO", "TELEF")),
        hint=f"got: '{obj}'"
    )
    check(
        "Fix3-C: does not bleed into Valor field",
        "287.000" not in obj,
        hint=f"boundary stopped too late, leaked into Valor: '{obj[-60:]}'"
    )
    check(
        "Fix3-D: within 400 char cap",
        len(obj) <= 400,
        hint=f"got {len(obj)} chars"
    )

    # ── One-liner case — should still work ────────────────────────────────────
    r2 = preprocess_text("FIX3-ONELINER", _FIX3_ONELINER)
    obj2 = r2["header"].get("object_summary") or ""
    info(f"  one-liner summary: '{obj2}'")
    check(
        "Fix3-E: one-line object also extracted correctly",
        "limpeza" in obj2.lower() or "conservação" in obj2.lower(),
        hint=f"got: '{obj2}'"
    )

    # ── No crash on minimal input ─────────────────────────────────────────────
    r3 = preprocess_text("FIX3-MINIMAL", "CONTRATO Nº 0001/2025\nSem objeto definido.")
    check(
        "Fix3-F: no exception on contract with no OBJETO clause",
        isinstance(r3, dict),
        hint="preprocess_text raised an exception"
    )


# ══════════════════════════════════════════════════════════════════════════════
# GAP 4 — FIL-PRO-2023/00482 embedded flag diagnostic
# ══════════════════════════════════════════════════════════════════════════════

def test_gap4_embedded_flag():
    section("GAP 4 — FIL-PRO-2023/00482: embedded flag vs. DoWeb no_results")

    PID      = "FIL-PRO-2023/00482"
    PID_SAFE = "FIL-PRO-2023_00482"

    PREPROCESSED = ROOT / "data" / "preprocessed"
    EXTRACTIONS  = ROOT / "data" / "extractions"

    flag_path   = PREPROCESSED / f"{PID_SAFE}_pub_embedded.flag"
    pre_path    = PREPROCESSED / f"{PID_SAFE}_preprocessed.json"
    raw_pub     = EXTRACTIONS  / f"{PID_SAFE}_publications_raw.json"
    progress_p  = ROOT / "data" / "publication_extraction_progress.json"

    # ── 1. Flag file ──────────────────────────────────────────────────────────
    flag_exists = flag_path.exists()
    check("Gap4-1: _pub_embedded.flag exists", flag_exists,
          hint=f"Expected: {flag_path}\nRun contract_preprocessor on this PID to create it")

    # ── 2. Preprocessed JSON confirms embedded=found ──────────────────────────
    if pre_path.exists():
        with open(pre_path, encoding="utf-8") as f:
            pre = json.load(f)
        emb = pre.get("embedded_publication", {})
        check("Gap4-2: embedded_publication.found = True in preprocessed JSON",
              emb.get("found") is True, hint=f"found={emb.get('found')}")
        info(f"  pub_date:    {emb.get('publication_date')}")
        info(f"  contratante: {emb.get('contratante_pub')}")
    else:
        warn(f"Preprocessed file missing: {pre_path}")

    # ── 3. Progress log shows no_results ─────────────────────────────────────
    in_no_results = False
    stage3_time   = None
    if progress_p.exists():
        with open(progress_p, encoding="utf-8") as f:
            prog = json.load(f)
        for entry in prog.get("no_results", []):
            if entry["processo_id"] == PID:
                in_no_results = True
                stage3_time = entry.get("at")
        check("Gap4-3: PID is in publication_extraction_progress.no_results",
              in_no_results, hint="Not there — may have been processed in a later run")
        if stage3_time:
            info(f"  DoWeb no_results at: {stage3_time}")
    else:
        warn(f"Progress file missing: {progress_p}")

    # ── 4. Downloader short-circuit function ──────────────────────────────────
    try:
        from infrastructure.scrapers.doweb.downloader import _has_embedded_publication
        result = _has_embedded_publication(PID)
        check("Gap4-4: _has_embedded_publication(PID) returns True",
              result is True,
              hint=f"returned {result} — flag missing or function not checking it")
        info(f"  _has_embedded_publication → {result}")
    except ImportError as e:
        warn(f"Cannot import _has_embedded_publication: {e}")

    # ── 5. Timeline: did preprocessing run before or after Stage 3? ───────────
    pre_time = None
    if pre_path.exists():
        with open(pre_path, encoding="utf-8") as f:
            pre_data = json.load(f)
        pre_time = pre_data.get("preprocessed_at")

    if pre_time and stage3_time:
        from datetime import datetime
        try:
            t_pre    = datetime.fromisoformat(pre_time)
            t_stage3 = datetime.fromisoformat(stage3_time)
            pre_after = t_pre > t_stage3
            check(
                "Gap4-5: preprocessing ran AFTER Stage 3 DoWeb run",
                pre_after,
                hint=(
                    f"pre={pre_time}\nstage3={stage3_time}\n"
                    "If pre < stage3: flag didn't exist when DoWeb ran — "
                    "re-run Stage 3 for this PID"
                )
            )
            info(f"  preprocessed_at : {pre_time}")
            info(f"  stage3 no_result: {stage3_time}")
        except ValueError as e:
            warn(f"Timestamp parse error: {e}")

    # ── 6. Was the raw publications file created despite the flag? ────────────
    raw_exists = raw_pub.exists()
    if raw_exists:
        warn(f"Gap4-6: {raw_pub.name} EXISTS — Stage 3 was NOT short-circuited")
        with open(raw_pub, encoding="utf-8") as f:
            raw = json.load(f)
        info(f"  publication records: {len(raw.get('publications', []))}")
    else:
        check("Gap4-6: no _publications_raw.json (correctly skipped)", True)

    # ── Diagnosis summary ─────────────────────────────────────────────────────
    print(f"\n  {BOLD}DIAGNOSIS{RESET}")
    if flag_exists and raw_exists:
        print(f"  {RED}⚠  Flag exists but Stage 3 was NOT skipped{RESET}")
        print(f"     Most likely: Stage 3 ran before preprocessing wrote the flag.")
        print(f"     Action: re-run Stage 3 for {PID} alone, or mark it skipped manually.")
    elif flag_exists and not raw_exists:
        print(f"  {GREEN}✓  Short-circuit is working correctly{RESET}")
    elif not flag_exists and raw_exists and in_no_results:
        print(f"  {YELLOW}⚠  No flag, Stage 3 ran, DoWeb returned no_results{RESET}")
        print(f"     Preprocessing may not have run for this PID yet.")
        print(f"     Action: run contract_preprocessor for {PID}, then re-run Stage 3.")
    else:
        print(f"  {YELLOW}⚠  Indeterminate — missing files, check warnings above{RESET}")


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="v7 fix regression tests + Gap 4 diagnostic"
    )
    parser.add_argument("--unit-only", action="store_true",
                        help="Skip Gap 4 file I/O checks")
    parser.add_argument("--gap4-only", action="store_true",
                        help="Only run Gap 4 diagnostic")
    args = parser.parse_args()

    print(f"\n{BOLD}{'═' * 65}{RESET}")
    print(f"{BOLD}  CONTRACT ANALYSIS — v7 FIXES + GAP 4 DIAGNOSTIC{RESET}")
    print(f"{BOLD}{'═' * 65}{RESET}")

    if not args.gap4_only:
        test_fix1_clean_party()
        test_fix2_edition()
        test_fix3_object_summary()

    if not args.unit_only:
        test_gap4_embedded_flag()

    print(f"\n{BOLD}{'═' * 65}{RESET}")
    print(f"{BOLD}  RESULTS{RESET}")
    print(f"{'═' * 65}")
    print(f"  {GREEN}✓  Passed  : {PASSED}{RESET}")
    print(f"  {RED}✗  Failed  : {FAILED}{RESET}")
    print(f"  {YELLOW}⚠  Warnings: {WARNINGS}{RESET}")

    if FAILED == 0:
        print(f"\n  {BOLD}{GREEN}✅ ALL CHECKS PASSED — safe to proceed to Epic 4{RESET}")
    else:
        print(f"\n  {BOLD}{RED}❌ {FAILED} check(s) failed — apply patches before Epic 4{RESET}")
    print(f"{'═' * 65}\n")

    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())