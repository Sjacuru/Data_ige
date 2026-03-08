"""
tests/test_v7_fixes.py

Regression tests for three targeted fixes (v7) and Gap 4 diagnostic.

Fix 1 — _clean_party strips trailing "e" from contratante
Fix 2 — _extract_edition returns None when no masthead anchor present
Fix 3 — object_summary extraction uses boundary-aware multi-line regex
Gap 4 — FIL-PRO-2023/00482 embedded flag diagnostic

Usage
─────
    python tests/test_v7_fixes.py
    python tests/test_v7_fixes.py --gap4-only    # only run Gap 4 section
    python tests/test_v7_fixes.py --unit-only    # skip Gap 4 file I/O
"""

import re
import sys
import json
import argparse
from pathlib import Path

# ── path bootstrap ─────────────────────────────────────────────────────────────
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

# Contract text with the boilerplate opener that triggered Issue 1 + Issue 3
_CONTRACT_BODY = """\
CONTRATO Nº 2403453/2024

Processo Instrutivo: FIL-PRO-2023/00482.

Aos 16 dias do mês de Setembro de 2024, a DISTRIBUIDORA DE FILMES S/A - RIOFILME e
a empresa ARTE VITAL EXIBIÇÕES CINEMATOGRÁFICAS LTDA, inscrita no CNPJ 00.000.000/0001-00.

CLÁUSULA PRIMEIRA - OBJETO
Constitui objeto do presente a contratação de empresa especializada para
operação do CINECARIOCA JOSÉ WILKER, cinema municipal localizado no bairro
da Tijuca, incluindo a gestão de bilheteria, manutenção e programação cultural.

Valor Total: R$ 1.216.829,52
Vigência: 24 meses.
"""

# Gazette text WITH masthead — edition should be extracted correctly
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

# Gazette text WITHOUT masthead — bare extrato only (embedded in contract PDF)
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

    # Core case — trailing " e" from "RIOFILME e" in prose
    result = _clean_party("DISTRIBUIDORA DE FILMES S/A - RIOFILME e")
    check(
        "Fix1-A: trailing ' e' removed",
        not result.endswith(" e") and not result.endswith(" E"),
        hint=f"got: '{result}'"
    )
    check(
        "Fix1-A: name body preserved",
        "RIOFILME" in result,
        hint=f"got: '{result}'"
    )
    info(f"  result: '{result}'")

    # Should NOT strip "e" that is PART of the name
    result2 = _clean_party("ARTE E CULTURA PRODUÇÕES LTDA")
    check(
        "Fix1-B: 'e' inside name body not stripped",
        "ARTE E CULTURA" in result2,
        hint=f"got: '{result2}'"
    )

    # Should NOT strip "e" followed by space (mid-name word)
    result3 = _clean_party("EMPRESA DE TECNOLOGIA")
    check(
        "Fix1-C: 'DE' connector inside name preserved",
        "DE TECNOLOGIA" in result3,
        hint=f"got: '{result3}'"
    )

    # Trailing " e" with extra whitespace
    result4 = _clean_party("SECRETARIA MUNICIPAL DE SAÚDE    e  ")
    check(
        "Fix1-D: trailing 'e' with surrounding whitespace removed",
        not re.search(r'\se\s*$', result4, re.IGNORECASE),
        hint=f"got: '{result4}'"
    )

    # Verify fix is applied end-to-end through preprocess_text
    try:
        from infrastructure.extractors.contract_preprocessor import preprocess_text
        result5 = preprocess_text("FIX1-TEST", _CONTRACT_BODY)
        contratante = result5["header"].get("contratante", "")
        check(
            "Fix1-E: contratante in full pipeline has no trailing 'e'",
            not re.search(r'\se\s*$', contratante or "", re.IGNORECASE),
            hint=f"got: '{contratante}'"
        )
        info(f"  pipeline contratante: '{contratante}'")
    except Exception as ex:
        warn(f"Full pipeline test skipped: {ex}")


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

    # Case A: WITH masthead — edition should be "136"
    result_with = parse_publication_text(_GAZETTE_WITH_MASTHEAD, "FIL-PRO-2023/00482")
    check(
        "Fix2-A: edition extracted from masthead text is '136'",
        result_with.get("edition") == "136",
        hint=f"got: '{result_with.get('edition')}'"
    )
    check(
        "Fix2-A: contract_number is still '2403453/2024' (not contaminated)",
        result_with.get("contract_number") == "2403453/2024",
        hint=f"got: '{result_with.get('contract_number')}'"
    )
    info(f"  with masthead  → edition='{result_with.get('edition')}', "
         f"contract_number='{result_with.get('contract_number')}'")

    # Case B: WITHOUT masthead — edition must be None, contract_number must be correct
    result_without = parse_publication_text(_GAZETTE_NO_MASTHEAD, "FIL-PRO-2023/00482")
    check(
        "Fix2-B: edition is None when no masthead present",
        result_without.get("edition") is None,
        hint=f"got: '{result_without.get('edition')}' — "
             f"if '2403453' then Fix 2 is NOT yet applied"
    )
    check(
        "Fix2-B: contract_number still correctly '2403453/2024'",
        result_without.get("contract_number") == "2403453/2024",
        hint=f"got: '{result_without.get('contract_number')}'"
    )
    info(f"  no masthead    → edition='{result_without.get('edition')}', "
         f"contract_number='{result_without.get('contract_number')}'")

    # Case C: Verify other fields not affected by the fix
    check(
        "Fix2-C: signing_date still extracted without masthead",
        result_without.get("signing_date_in_pub") == "16/09/2024",
        hint=f"got: '{result_without.get('signing_date_in_pub')}'"
    )
    check(
        "Fix2-C: contratante still extracted without masthead",
        result_without.get("contratante") is not None,
        hint=f"got: '{result_without.get('contratante')}'"
    )


# ══════════════════════════════════════════════════════════════════════════════
# FIX 3 — object_summary boundary-aware extraction
# ══════════════════════════════════════════════════════════════════════════════

def test_fix3_object_summary():
    section("FIX 3 — object_summary: boundary-aware multi-line extraction")

    try:
        from infrastructure.extractors.contract_preprocessor import preprocess_text
    except ImportError as e:
        check("contract_preprocessor importable", False, hint=str(e))
        return

    result = preprocess_text("FIX3-TEST", _CONTRACT_BODY)
    obj = result["header"].get("object_summary", "")
    info(f"  extracted summary: '{obj}'")

    # The boilerplate opener alone is < 60 chars — if that's all we get, fix failed
    # The full meaningful text includes "operação do CINECARIOCA JOSÉ WILKER"
    check(
        "Fix3-A: object_summary is not just the boilerplate opener",
        len(obj or "") > 60,
        hint=f"got {len(obj or '')} chars: '{obj}'"
    )
    check(
        "Fix3-B: object_summary contains identifying content (CINECARIOCA)",
        "CINECARIOCA" in (obj or "").upper() or "TIJUCA" in (obj or "").upper(),
        hint=f"got: '{obj}' — expected location/name to appear"
    )
    check(
        "Fix3-C: object_summary does not bleed into Valor field",
        "1.216.829" not in (obj or ""),
        hint=f"boundary not stopping before Valor: '{obj}'"
    )
    check(
        "Fix3-D: object_summary within 400 char cap",
        len(obj or "") <= 400,
        hint=f"got {len(obj or '')} chars"
    )

    # Edge case: contract with no clear boundary — must not crash
    sparse = "CONTRATO Nº 0001/2024\nOBJETO: Prestação de serviços técnicos."
    result2 = preprocess_text("FIX3-EDGE", sparse)
    check(
        "Fix3-E: no crash on contract with no boundary markers",
        isinstance(result2, dict),
        hint="preprocess_text raised an exception"
    )
    obj2 = result2["header"].get("object_summary", "")
    info(f"  edge case summary: '{obj2}'")


# ══════════════════════════════════════════════════════════════════════════════
# GAP 4 — FIL-PRO-2023/00482 embedded flag diagnostic
# ══════════════════════════════════════════════════════════════════════════════

def test_gap4_embedded_flag_diagnostic():
    section("GAP 4 — FIL-PRO-2023/00482: embedded flag vs. DoWeb no_results")

    PID      = "FIL-PRO-2023/00482"
    PID_SAFE = "FIL-PRO-2023_00482"

    PREPROCESSED_DIR = ROOT / "data" / "preprocessed"
    EXTRACTIONS_DIR  = ROOT / "data" / "extractions"

    # ── Check 1: Does the _pub_embedded.flag file exist? ─────────────────────
    flag_path = PREPROCESSED_DIR / f"{PID_SAFE}_pub_embedded.flag"
    flag_exists = flag_path.exists()
    check(
        "Gap4-1: _pub_embedded.flag exists for FIL-PRO-2023/00482",
        flag_exists,
        hint=f"Expected at: {flag_path}\n"
             "  If missing: preprocessor ran before v6, or contract was never preprocessed"
    )
    if flag_exists:
        info(f"  flag path   : {flag_path}")
        info(f"  flag size   : {flag_path.stat().st_size} bytes")

    # ── Check 2: Does the preprocessed JSON confirm embedded=found? ───────────
    pre_path = PREPROCESSED_DIR / f"{PID_SAFE}_preprocessed.json"
    if pre_path.exists():
        with open(pre_path, encoding="utf-8") as f:
            pre = json.load(f)
        emb = pre.get("embedded_publication", {})
        check(
            "Gap4-2: preprocessed JSON has embedded_publication.found=True",
            emb.get("found") is True,
            hint=f"found={emb.get('found')}"
        )
        info(f"  pub_date    : {emb.get('publication_date')}")
        info(f"  contratante : {emb.get('contratante_pub')}")
        info(f"  contratada  : {emb.get('contratada_pub')}")
    else:
        warn(f"Preprocessed file not found: {pre_path}")

    # ── Check 3: Does the publication progress log show it as no_results? ─────
    progress_path = ROOT / "data" / "publication_extraction_progress.json"
    if progress_path.exists():
        with open(progress_path, encoding="utf-8") as f:
            progress = json.load(f)
        no_results_pids = [r["processo_id"] for r in progress.get("no_results", [])]
        in_no_results = PID in no_results_pids
        check(
            "Gap4-3: FIL-PRO-2023/00482 is in publication_extraction_progress.no_results",
            in_no_results,
            hint="Not in no_results — may have been processed in a later run"
        )
        if in_no_results:
            entry = next(r for r in progress["no_results"] if r["processo_id"] == PID)
            info(f"  DoWeb no_results recorded at: {entry.get('at')}")
    else:
        warn(f"Progress file not found: {progress_path}")

    # ── Check 4: Is the flag READ by downloader._has_embedded_publication? ────
    try:
        from infrastructure.scrapers.doweb.downloader import _has_embedded_publication
        has_flag = _has_embedded_publication(PID)
        check(
            "Gap4-4: downloader._has_embedded_publication(PID) returns True",
            has_flag is True,
            hint=f"returned {has_flag} — if False, flag either missing or function not checking it"
        )
        info(f"  _has_embedded_publication('{PID}') → {has_flag}")
    except ImportError as e:
        warn(f"Could not import _has_embedded_publication: {e}")
    except Exception as e:
        warn(f"_has_embedded_publication raised: {e}")

    # ── Check 5: Timeline — was preprocessing done BEFORE or AFTER Stage 3? ──
    pre_time   = None
    stage3_time = None

    if pre_path.exists():
        with open(pre_path, encoding="utf-8") as f:
            pre_data = json.load(f)
        pre_time = pre_data.get("preprocessed_at")

    if progress_path.exists():
        with open(progress_path, encoding="utf-8") as f:
            prog_data = json.load(f)
        for entry in prog_data.get("no_results", []):
            if entry["processo_id"] == PID:
                stage3_time = entry.get("at")

    if pre_time and stage3_time:
        from datetime import datetime
        try:
            t_pre    = datetime.fromisoformat(pre_time)
            t_stage3 = datetime.fromisoformat(stage3_time)
            pre_after_stage3 = t_pre > t_stage3
            check(
                "Gap4-5: preprocessing ran AFTER Stage 3 DoWeb run",
                pre_after_stage3,
                hint=f"pre_time={pre_time}, stage3_time={stage3_time}\n"
                     "  If pre_time < stage3_time: flag didn't exist when DoWeb ran → "
                     "Stage 3 should be re-run with --skip-embedded to honour the flag"
            )
            info(f"  preprocessed_at : {pre_time}")
            info(f"  stage3 no_result: {stage3_time}")
            if pre_after_stage3:
                info(f"  → Preprocessing ran AFTER Stage 3. "
                     f"Flag was available but DoWeb ran before it was written.")
                info(f"  → Recommendation: re-run Stage 3 for {PID} with embedded-skip logic.")
            else:
                info(f"  → Preprocessing ran BEFORE Stage 3. "
                     f"Flag existed — investigate why downloader didn't skip.")
        except ValueError as e:
            warn(f"Could not parse timestamps: {e}")
    else:
        if not pre_time:
            warn("Cannot determine preprocessing time — preprocessed file missing")
        if not stage3_time:
            warn("Cannot determine Stage 3 time — progress entry missing for this PID")

    # ── Check 6: Raw publications file — does it exist despite the flag? ──────
    raw_pub_path = EXTRACTIONS_DIR / f"{PID_SAFE}_publications_raw.json"
    raw_exists = raw_pub_path.exists()
    if raw_exists:
        warn(
            f"Gap4-6: {PID_SAFE}_publications_raw.json EXISTS despite embedded flag "
            f"→ Stage 3 was NOT short-circuited"
        )
        with open(raw_pub_path, encoding="utf-8") as f:
            raw = json.load(f)
        pub_count = len(raw.get("publications", []))
        info(f"  publication records in file: {pub_count}")
    else:
        check(
            "Gap4-6: no _publications_raw.json (correctly skipped by downloader)",
            True
        )

    # ── Summary diagnosis ─────────────────────────────────────────────────────
    print(f"\n  {BOLD}GAP 4 DIAGNOSIS SUMMARY{RESET}")
    print("  " + "─" * 50)
    if flag_exists and raw_exists:
        print(f"  {RED}⚠  Flag exists but Stage 3 was NOT skipped.{RESET}")
        print(f"     Likely cause: Stage 3 ran before preprocessing wrote the flag.")
        print(f"     Action: Re-run Stage 3 for this PID only, or add it to")
        print(f"             'no_results' manually (it has an embedded publication).")
    elif flag_exists and not raw_exists:
        print(f"  {GREEN}✓  Flag correctly prevented Stage 3 download.{RESET}")
    elif not flag_exists and raw_exists:
        print(f"  {YELLOW}⚠  No flag, Stage 3 ran, DoWeb returned no_results.{RESET}")
        print(f"     This could be a DoWeb search miss (CAPTCHA, format mismatch).")
        print(f"     OR: preprocessing was never run for this PID.")
        print(f"     Action: Run contract_preprocessor on this PID then re-run Stage 3.")
    else:
        print(f"  {YELLOW}⚠  Neither flag nor raw file found.{RESET}")
        print(f"     This PID may not have been processed at all in the current run.")


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="v7 fix regression tests + Gap 4 diagnostic"
    )
    parser.add_argument("--gap4-only",  action="store_true")
    parser.add_argument("--unit-only",  action="store_true")
    args = parser.parse_args()

    print(f"\n{BOLD}{'═' * 65}{RESET}")
    print(f"{BOLD}  CONTRACT ANALYSIS — v7 FIX REGRESSION + GAP 4 DIAGNOSTIC{RESET}")
    print(f"{BOLD}{'═' * 65}{RESET}")

    if not args.gap4_only:
        test_fix1_clean_party()
        test_fix2_edition()
        test_fix3_object_summary()

    if not args.unit_only:
        test_gap4_embedded_flag_diagnostic()

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