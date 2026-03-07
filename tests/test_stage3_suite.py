"""
tests/test_stage3_suite.py

Stage 3 — DoWeb Publication Extraction — Test Suite
════════════════════════════════════════════════════
Mirrors the structure of test_stage1_suite.py and test_stage2_suite.py.

Four tracks — run in order:

  TRACK A — Environment & Imports
      Verifies all Stage 3 modules import cleanly. No network, no browser.

  TRACK B — Unit Tests (offline)
      B1   detect_format              — ID format detection (A / B / C / UNKNOWN)
      B2   normalize_processo_id      — variation generation per format
      B3   _classify_content          — structured_contract / possible_addendum / unknown
      B4   _parse_publication_metadata — "publicado em:" span parsing
      B5   SearchResultItem           — dataclass schema + to_dict
      B6   _quality_check             — passes / fails / flags
      B7   validate_processo_in_text  — found / not-found / variation match
      B8   extract_text (no PDF)      — missing-file guard
      B9   _build_publication_record  — JSON record schema
      B10  _save_publications_json    — file I/O + schema
      B11  publication_parser Format A — labelled EXTRATO block
      B12  publication_parser Format B — DoWeb numbered block
      B13  publication_parser Format C — D.O.RIO masthead date
      B14  publication_preprocessor   — preprocess_publications_data
      B15  progress helpers           — load / mark / save cycle
      B16  embedded flag short-circuit — _has_embedded_publication

  TRACK C — Validate existing extraction outputs (if data/ present)
      Checks real _publications_raw.json files for schema compliance.

  TRACK D — Live integration test instructions (printed only)

Usage
─────
    python tests/test_stage3_suite.py           # all tracks
    python tests/test_stage3_suite.py --quick   # Track A + B only

Gap Analysis Notes (Epic 3 Plan vs Implementation)
───────────────────────────────────────────────────
IMPLEMENTED ✓ (beyond the plan):
  • publication_parser.py  — shared gazette text parser (not in plan, good addition)
  • publication_preprocessor.py — bridges Stage 3 raw JSON → Epic 4 schema
  • Gap 4 embedded publication flag short-circuit in downloader

MISSING ✗ (in plan, not implemented):
  • Task 3.3 HTML-only path: downloader has no fallback for HTML-only
    publications (no pdf_page_url). Currently a publication with no PDF
    link produces an empty record with download_failed flag.
    Recommendation: add HTML extraction path or document as accepted gap.

NAMING DRIFT ⚠:
  • Plan calls the file publication_text_extractor.py
    Implementation is   publication_extractor.py
    (minor — no functional impact, but worth aligning in docs)
"""

import argparse
import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path

# ── Project root on path ──────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ── Colour helpers ────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

PASSED   = 0
FAILED   = 0
WARNINGS = 0


def section(title: str) -> None:
    print(f"\n{BOLD}{'─' * 60}{RESET}")
    print(f"{BOLD}  {title}{RESET}")
    print(f"{'─' * 60}")


def check(label: str, passed: bool, hint: str = "") -> None:
    global PASSED, FAILED
    if passed:
        PASSED += 1
        print(f"  {GREEN}OK   {RESET} {label}")
    else:
        FAILED += 1
        print(f"  {RED}FAIL {RESET} {label}")
        if hint:
            print(f"         ↳ {YELLOW}{hint}{RESET}")


def warn(msg: str) -> None:
    global WARNINGS
    WARNINGS += 1
    print(f"  {YELLOW}WARN {RESET} {msg}")


def info(msg: str) -> None:
    print(f"  {CYAN}INFO {RESET} {msg}")


def fail(msg: str) -> None:
    global FAILED
    FAILED += 1
    print(f"  {RED}FAIL {RESET} {msg}")


# ══════════════════════════════════════════════════════════════════════════════
# FIXTURES
# ══════════════════════════════════════════════════════════════════════════════

# Format A gazette text — labelled EXTRATO block (most common)
_FORMAT_A_TEXT = """\
DISTRIBUIDORA DE FILMES S/A - RIOFILME
EXTRATO DE INSTRUMENTO CONTRATUAL
Processo Instrutivo: FIL-PRO-2023/00482.- CO 01/2024.
Contrato nº: 2403453/2024.
Data da Assinatura: 16/09/2024.
Partes: Distribuidora de Filmes S.A - RIOFILME e Arte Vital Exibições Cinematográficas LTDA.
Objeto: Contratação de empresa especializada em exibição cinematográfica.
Valor Total: R$ 1.216.829,52
Vigência: 24 meses.
Nota de Empenho: 2024NE00006
Fundamento: Art. 28, CAPUT, Lei Federal nº 13.303/2016.
"""

# Format B gazette text — DoWeb numbered structured block
_FORMAT_B_TEXT = """\
Processo TUR-PRO-2025/01221 1-Objeto: operação do Centro de Convenções 2-Partes: \
RIOTUR e EMPRESA XPTO LTDA 3-Instrumento: Contrato nº 059/2023 \
4-Data: 03/02/2026 5-Valor: R$ 287.000,00
"""

# Format C gazette text — D.O.RIO masthead + EXTRATO
_FORMAT_C_TEXT = """\
Segunda-feira, 30 de Setembro de 2024
Diário Oficial do Município do Rio de Janeiro
D.O.RIO — Edição 136

SECRETARIA MUNICIPAL DE TURISMO
EXTRATO DE INSTRUMENTO CONTRATUAL
Processo Instrutivo: TUR-PRO-2025/01221
Contrato nº: 059/2023.
Data da Assinatura: 15/09/2024.
Partes: RIOTUR e EMPRESA XPTO LTDA.
Objeto: Operação do Centro de Convenções.
Valor Total: R$ 287.000,00
"""

# Minimal raw publications JSON (as produced by downloader._save_publications_json)
def _make_raw_publications(processo_id="FIL-PRO-2023/00482", text=_FORMAT_A_TEXT):
    return {
        "processo_id": processo_id,
        "discovery_metadata": {
            "company_name": "RIOFILME",
            "company_cnpj": "00.000.000/0001-00",
        },
        "search_metadata": {
            "searched_at":   datetime.now().isoformat(),
            "query_used":    processo_id,
            "results_found": 1,
        },
        "publications": [
            {
                "document_index":  1,
                "total_documents": 1,
                "publication_metadata": {
                    "source_url":     "https://doweb.rio.rj.gov.br/portal/edicoes/download/12345/10",
                    "publication_date": "30/09/2024",
                    "edition_number": "136",
                    "page_number":    "10",
                    "content_hint":   "structured_contract",
                    "snippet":        "Processo FIL-PRO-2023/00482 1-Objeto: ...",
                },
                "extraction_metadata": {
                    "method":          "pymupdf",
                    "pages":           1,
                    "text_length":     len(text),
                    "printable_ratio": 0.97,
                    "extracted_at":    datetime.now().isoformat(),
                },
                "validation": {
                    "quality_passes":         True,
                    "quality_flags":          [],
                    "processo_found_in_text": True,
                    "extraction_error":       None,
                },
                "raw_text": text,
            }
        ],
    }


# ══════════════════════════════════════════════════════════════════════════════
# TRACK A — ENVIRONMENT & IMPORTS
# ══════════════════════════════════════════════════════════════════════════════

def track_a_environment() -> bool:
    section("TRACK A — Environment & Imports")

    modules = [
        ("infrastructure.scrapers.doweb.searcher",
         ["detect_format", "normalize_processo_id", "SearchResultItem",
          "DoWebSearcher", "_classify_content", "_parse_publication_metadata"]),

        ("infrastructure.scrapers.doweb.downloader",
         ["DoWebDownloader", "load_processo_ids",
          "_sanitize", "_has_embedded_publication",
          "_build_publication_record", "_save_publications_json",
          "_load_progress", "_save_progress",
          "_mark_completed", "_mark_failed", "_mark_no_results"]),

        ("infrastructure.extractors.publication_extractor",
         ["extract_text", "validate_processo_in_text",
          "_quality_check", "MIN_TOTAL_CHARS", "MIN_PRINTABLE_RATIO"]),

        ("infrastructure.extractors.publication_parser",
         ["parse_publication_text"]),

        ("infrastructure.extractors.publication_preprocessor",
         ["preprocess_publication", "preprocess_publications_data"]),

        ("application.workflows.stage3_publication",
         ["run_stage3_publication"]),
    ]

    all_ok = True
    for module_path, symbols in modules:
        try:
            mod = __import__(module_path, fromlist=symbols)
            for sym in symbols:
                if not hasattr(mod, sym):
                    check(f"{module_path}.{sym}", False,
                          hint=f"Module loaded but '{sym}' not found")
                    all_ok = False
                else:
                    check(f"{module_path}.{sym}", True)
        except ImportError as e:
            check(f"{module_path}", False, hint=str(e))
            all_ok = False

    required_dirs = [
        "data/extractions",
        "data/temp_downloads",
        "data/preprocessed",
        "logs",
    ]
    for d in required_dirs:
        p = ROOT / d
        if p.exists():
            check(f"Directory exists: {d}", True)
        else:
            warn(f"Directory missing: {d} — will be created at runtime")

    discovery_file = ROOT / "data/discovery/processo_links.json"
    has_discovery  = discovery_file.exists()
    check("Stage 1 prerequisite: data/discovery/processo_links.json exists",
          has_discovery,
          hint="Run Stage 1 before Stage 3")

    pub_files = list((ROOT / "data/extractions").glob("*_publications_raw.json")) \
                if (ROOT / "data/extractions").exists() else []
    has_pubs = len(pub_files) > 0
    if has_pubs:
        check(f"Stage 3 outputs present ({len(pub_files)} *_publications_raw.json files)", True)
    else:
        warn("No *_publications_raw.json files found — Track C will be skipped")
        warn("Run Stage 3 at least once to generate publication outputs")

    return has_pubs


# ══════════════════════════════════════════════════════════════════════════════
# TRACK B.1 — detect_format
# ══════════════════════════════════════════════════════════════════════════════

def track_b1_detect_format():
    section("TRACK B.1 — detect_format (Task 3.1)")
    try:
        from infrastructure.scrapers.doweb.searcher import detect_format
    except ImportError as e:
        fail(f"Cannot import detect_format: {e}"); return

    check("Format A detected: 006800.000136/2026-28",
          detect_format("006800.000136/2026-28") == "A")
    check("Format A detected (no check digit): 006800.000136/2026",
          detect_format("006800.000136/2026") == "A")
    check("Format B detected: TUR-PRO-2025/01221",
          detect_format("TUR-PRO-2025/01221") == "B")
    check("Format B detected: FIL-PRO-2023/00482",
          detect_format("FIL-PRO-2023/00482") == "B")
    check("Format C detected: 12/500.078/2021",
          detect_format("12/500.078/2021") == "C")
    check("UNKNOWN for garbage input",
          detect_format("GARBAGE-ID") == "UNKNOWN")


# ══════════════════════════════════════════════════════════════════════════════
# TRACK B.2 — normalize_processo_id
# ══════════════════════════════════════════════════════════════════════════════

def track_b2_normalize():
    section("TRACK B.2 — normalize_processo_id (Task 3.1)")
    try:
        from infrastructure.scrapers.doweb.searcher import normalize_processo_id
    except ImportError as e:
        fail(f"Cannot import normalize_processo_id: {e}"); return

    # Format B: should produce at least 3 variations
    b_vars = normalize_processo_id("TUR-PRO-2025/01221")
    check("Format B: returns a non-empty list",
          isinstance(b_vars, list) and len(b_vars) > 0)
    check("Format B: original ID is first variation",
          b_vars[0] == "TUR-PRO-2025/01221")
    check("Format B: at least 2 variations generated",
          len(b_vars) >= 2)
    check("Format B: no duplicate variations",
          len(b_vars) == len(set(b_vars)))

    # Format A: should produce up to 8 variations
    a_vars = normalize_processo_id("006800.000136/2026-28")
    check("Format A: returns a non-empty list",
          isinstance(a_vars, list) and len(a_vars) > 0)
    check("Format A: original ID is first variation",
          a_vars[0] == "006800.000136/2026-28")
    check("Format A: generates multiple variations (≥3)",
          len(a_vars) >= 3)
    check("Format A: no duplicate variations",
          len(a_vars) == len(set(a_vars)))

    # Format C: should produce at least 3 variations
    c_vars = normalize_processo_id("12/500.078/2021")
    check("Format C: returns a non-empty list",
          isinstance(c_vars, list) and len(c_vars) > 0)
    check("Format C: at least 2 variations generated",
          len(c_vars) >= 2)

    # UNKNOWN format: should fall back gracefully with original only
    unk_vars = normalize_processo_id("GARBAGE-ID")
    check("UNKNOWN format: returns list with at least the original",
          isinstance(unk_vars, list) and "GARBAGE-ID" in unk_vars)


# ══════════════════════════════════════════════════════════════════════════════
# TRACK B.3 — _classify_content
# ══════════════════════════════════════════════════════════════════════════════

def track_b3_classify():
    section("TRACK B.3 — _classify_content (Task 3.2)")
    try:
        from infrastructure.scrapers.doweb.searcher import _classify_content
    except ImportError as e:
        fail(f"Cannot import _classify_content: {e}"); return

    structured_snippet = (
        "Processo TUR-PRO-2025/01221 1-Objeto: operação ... "
        "2-Partes: RIOTUR e EMPRESA X"
    )
    check("structured_contract: snippet with processo + 1-Objeto + 2-Partes",
          _classify_content(structured_snippet, "TUR-PRO-2025/01221") == "structured_contract")

    addendum_snippet = "APROVO o Termo Aditivo nº 2 ao Contrato nº 059/2023"
    check("possible_addendum: snippet with APROVO",
          _classify_content(addendum_snippet, "TUR-PRO-2025/01221") == "possible_addendum")

    authorizo_snippet = "AUTORIZO a prorrogação do contrato"
    check("possible_addendum: snippet with AUTORIZO",
          _classify_content(authorizo_snippet, "TUR-PRO-2025/01221") == "possible_addendum")

    check("unknown: empty snippet",
          _classify_content("", "TUR-PRO-2025/01221") == "unknown")

    check("unknown: snippet without pattern",
          _classify_content("Some unrelated text without keywords", "TUR-PRO-2025/01221") == "unknown")

    # Cross-processo: structured block for a DIFFERENT processo should NOT
    # classify as structured_contract for the searched ID
    wrong_pid_snippet = (
        "Processo FIL-PRO-2023/00482 1-Objeto: exibição ... "
        "2-Partes: RIOFILME e ARTE VITAL"
    )
    result = _classify_content(wrong_pid_snippet, "TUR-PRO-2025/01221")
    check("cross-processo: structured block for other ID is not structured_contract",
          result != "structured_contract",
          hint=f"got: {result} — should be 'unknown' or 'possible_addendum'")


# ══════════════════════════════════════════════════════════════════════════════
# TRACK B.4 — _parse_publication_metadata
# ══════════════════════════════════════════════════════════════════════════════

def track_b4_metadata_parser():
    section("TRACK B.4 — _parse_publication_metadata (Task 3.1)")
    try:
        from infrastructure.scrapers.doweb.searcher import _parse_publication_metadata
    except ImportError as e:
        fail(f"Cannot import _parse_publication_metadata: {e}"); return

    date, edition, page = _parse_publication_metadata(
        "publicado em: 03/02/2026 - Edição 218 - Pág. 38"
    )
    check("date parsed correctly",   date    == "03/02/2026")
    check("edition parsed correctly", edition == "218")
    check("page parsed correctly",   page    == "38")

    # Malformed input should not raise
    d2, e2, p2 = _parse_publication_metadata("bad input")
    check("malformed input returns ('', '', '') without raising",
          (d2, e2, p2) == ("", "", ""))


# ══════════════════════════════════════════════════════════════════════════════
# TRACK B.5 — SearchResultItem
# ══════════════════════════════════════════════════════════════════════════════

def track_b5_search_result_item():
    section("TRACK B.5 — SearchResultItem (Task 3.1 / 3.2)")
    try:
        from infrastructure.scrapers.doweb.searcher import SearchResultItem
    except ImportError as e:
        fail(f"Cannot import SearchResultItem: {e}"); return

    item = SearchResultItem(
        processo_id      = "TUR-PRO-2025/01221",
        query_used       = "TUR-PRO-2025/01221",
        document_index   = 1,
        total_documents  = 2,
        publication_date = "03/02/2026",
        edition_number   = "218",
        page_number      = "38",
        snippet          = "some snippet text",
        pdf_page_url     = "https://doweb.rio.rj.gov.br/portal/edicoes/download/13894/38",
        content_hint     = "structured_contract",
    )

    d = item.to_dict()
    required_keys = {
        "processo_id", "query_used", "document_index", "total_documents",
        "publication_date", "edition_number", "page_number",
        "snippet", "pdf_page_url", "content_hint",
    }
    check("to_dict() contains all required keys",
          required_keys.issubset(d.keys()),
          hint=f"missing: {required_keys - set(d.keys())}")
    check("to_dict(): document_index == 1",   d["document_index"]  == 1)
    check("to_dict(): total_documents == 2",  d["total_documents"] == 2)
    check("to_dict(): content_hint correct",  d["content_hint"]    == "structured_contract")


# ══════════════════════════════════════════════════════════════════════════════
# TRACK B.6 — _quality_check (publication_extractor)
# ══════════════════════════════════════════════════════════════════════════════

def track_b6_quality_check():
    section("TRACK B.6 — _quality_check (Task 3.4 / 3.5)")
    try:
        from infrastructure.extractors.publication_extractor import (
            _quality_check, MIN_TOTAL_CHARS, MIN_PRINTABLE_RATIO
        )
    except ImportError as e:
        fail(f"Cannot import _quality_check: {e}"); return

    good_text = "Contrato de prestação de serviços. " * 50
    qc = _quality_check(good_text)
    check("passes on sufficient readable text",       qc["passes"] is True)
    check("total_chars matches stripped len",
          qc["total_chars"] == len(good_text.strip()))
    check("printable_ratio is float 0–1",
          isinstance(qc["printable_ratio"], float) and 0.0 <= qc["printable_ratio"] <= 1.0)
    check("flags list is empty for good text",        qc["flags"] == [])

    short_text = "abc"
    qc_s = _quality_check(short_text)
    check("fails on text shorter than MIN_TOTAL_CHARS",  qc_s["passes"] is False)
    check("flag 'low_char_count' present for short text",
          any("low_char_count" in f for f in qc_s["flags"]))

    garbled = "\x00\x01\x02\x03" * 200
    qc_g = _quality_check(garbled)
    check("fails on garbled/non-printable text",         qc_g["passes"] is False)
    check("flag 'low_printable_ratio' present for garbled",
          any("low_printable_ratio" in f for f in qc_g["flags"]))

    qc_e = _quality_check("")
    check("fails on empty string",                       qc_e["passes"] is False)
    check("printable_ratio == 0.0 for empty string",     qc_e["printable_ratio"] == 0.0)

    check(f"MIN_TOTAL_CHARS == 500",   MIN_TOTAL_CHARS == 500)
    check(f"MIN_PRINTABLE_RATIO == 0.70", MIN_PRINTABLE_RATIO == 0.70)


# ══════════════════════════════════════════════════════════════════════════════
# TRACK B.7 — validate_processo_in_text
# ══════════════════════════════════════════════════════════════════════════════

def track_b7_validate_processo():
    section("TRACK B.7 — validate_processo_in_text (Task 3.5)")
    try:
        from infrastructure.extractors.publication_extractor import validate_processo_in_text
    except ImportError as e:
        fail(f"Cannot import validate_processo_in_text: {e}"); return

    text_exact = "Processo Instrutivo: FIL-PRO-2023/00482.- CO 01/2024."
    r = validate_processo_in_text(text_exact, "FIL-PRO-2023/00482")
    check("found=True when exact ID present in text",  r["found"] is True)
    check("possible_mismatch=False when found",        r["possible_mismatch"] is False)
    check("matched_variation is non-empty when found", r["matched_variation"] != "")

    r_absent = validate_processo_in_text("Some unrelated text.", "FIL-PRO-2023/00482")
    check("found=False when ID absent",                r_absent["found"] is False)
    check("possible_mismatch=True when not found",     r_absent["possible_mismatch"] is True)

    r_empty = validate_processo_in_text("", "FIL-PRO-2023/00482")
    check("found=False on empty text",                 r_empty["found"] is False)

    r_none_pid = validate_processo_in_text("some text", "")
    check("found=False on empty processo_id",          r_none_pid["found"] is False)


# ══════════════════════════════════════════════════════════════════════════════
# TRACK B.8 — extract_text missing file guard
# ══════════════════════════════════════════════════════════════════════════════

def track_b8_extract_text_guard():
    section("TRACK B.8 — extract_text missing-file guard (Task 3.4)")
    try:
        from infrastructure.extractors.publication_extractor import extract_text
    except ImportError as e:
        fail(f"Cannot import extract_text: {e}"); return

    result = extract_text("/nonexistent/path/gazette.pdf", "TUR-PRO-2025/01221")
    required = {
        "success", "text", "pages", "source", "pdf_path",
        "total_chars", "quality_passes", "quality_flags", "error",
        "processo_found_in_text", "possible_mismatch", "matched_variation",
    }
    check("extract_text: all schema keys present on missing file",
          required.issubset(result.keys()),
          hint=f"missing: {required - set(result.keys())}")
    check("extract_text: success=False for missing file",
          result["success"] is False)
    check("extract_text: error field populated",
          result.get("error") is not None and len(result["error"]) > 0)
    check("extract_text: source='failed' for missing file",
          result.get("source") == "failed")


# ══════════════════════════════════════════════════════════════════════════════
# TRACK B.9 — _build_publication_record schema
# ══════════════════════════════════════════════════════════════════════════════

def track_b9_build_record():
    section("TRACK B.9 — _build_publication_record (Task 3.6)")
    try:
        from infrastructure.scrapers.doweb.searcher import SearchResultItem
        from infrastructure.scrapers.doweb.downloader import _build_publication_record
    except ImportError as e:
        fail(f"Cannot import required symbols: {e}"); return

    item = SearchResultItem(
        processo_id="FIL-PRO-2023/00482", query_used="FIL-PRO-2023/00482",
        document_index=1, total_documents=1,
        publication_date="30/09/2024", edition_number="136", page_number="10",
        snippet="Processo FIL-PRO-2023/00482 ...",
        pdf_page_url="https://doweb.rio.rj.gov.br/test",
        content_hint="structured_contract",
    )
    ocr_result = {
        "text":           _FORMAT_A_TEXT,
        "source":         "pymupdf",
        "pages":          1,
        "quality_passes": True,
        "quality_flags":  [],
        "error":          None,
    }
    record = _build_publication_record(item, ocr_result, "FIL-PRO-2023/00482")

    required_top = {"document_index", "total_documents",
                    "publication_metadata", "extraction_metadata",
                    "validation", "raw_text"}
    check("_build_publication_record: top-level keys present",
          required_top.issubset(record.keys()),
          hint=f"missing: {required_top - set(record.keys())}")

    pub_meta_keys = {"source_url", "publication_date", "edition_number",
                     "page_number", "content_hint", "snippet"}
    check("publication_metadata sub-keys present",
          pub_meta_keys.issubset(record["publication_metadata"].keys()),
          hint=f"missing: {pub_meta_keys - set(record['publication_metadata'].keys())}")

    ext_meta_keys = {"method", "pages", "text_length", "printable_ratio", "extracted_at"}
    check("extraction_metadata sub-keys present",
          ext_meta_keys.issubset(record["extraction_metadata"].keys()),
          hint=f"missing: {ext_meta_keys - set(record['extraction_metadata'].keys())}")

    val_keys = {"quality_passes", "quality_flags",
                "processo_found_in_text", "extraction_error"}
    check("validation sub-keys present",
          val_keys.issubset(record["validation"].keys()),
          hint=f"missing: {val_keys - set(record['validation'].keys())}")

    check("raw_text contains the OCR text",
          record["raw_text"] == _FORMAT_A_TEXT)
    check("document_index == 1",
          record["document_index"] == 1)


# ══════════════════════════════════════════════════════════════════════════════
# TRACK B.10 — _save_publications_json
# ══════════════════════════════════════════════════════════════════════════════

def track_b10_save_publications():
    section("TRACK B.10 — _save_publications_json (Task 3.6)")
    try:
        from infrastructure.scrapers.doweb.downloader import _save_publications_json
        import infrastructure.scrapers.doweb.downloader as dl_mod
    except ImportError as e:
        fail(f"Cannot import _save_publications_json: {e}"); return

    raw = _make_raw_publications()

    with tempfile.TemporaryDirectory() as tmp:
        # Redirect EXTRACTIONS_DIR inside the module
        orig = dl_mod.EXTRACTIONS_DIR
        dl_mod.EXTRACTIONS_DIR = Path(tmp)
        try:
            ok = _save_publications_json(
                processo_id         = "FIL-PRO-2023/00482",
                discovery_meta      = raw["discovery_metadata"],
                search_meta         = raw["search_metadata"],
                publication_records = raw["publications"],
            )
        finally:
            dl_mod.EXTRACTIONS_DIR = orig

        check("_save_publications_json returns True on success",
              ok is True)

        saved = list(Path(tmp).glob("*_publications_raw.json"))
        check("creates exactly one *_publications_raw.json",
              len(saved) == 1,
              hint=f"found: {[f.name for f in saved]}")

        if saved:
            with open(saved[0], encoding="utf-8") as f:
                doc = json.load(f)

            required_top = {"processo_id", "discovery_metadata",
                            "search_metadata", "publications"}
            check("saved JSON has all required top-level keys",
                  required_top.issubset(doc.keys()),
                  hint=f"missing: {required_top - set(doc.keys())}")

            check("publications is a non-empty list",
                  isinstance(doc["publications"], list) and len(doc["publications"]) > 0)

            check("processo_id preserved correctly",
                  doc["processo_id"] == "FIL-PRO-2023/00482")


# ══════════════════════════════════════════════════════════════════════════════
# TRACK B.11 — publication_parser Format A
# ══════════════════════════════════════════════════════════════════════════════

def track_b11_parser_format_a():
    section("TRACK B.11 — publication_parser Format A (Task 3.6 / preprocessor)")
    try:
        from infrastructure.extractors.publication_parser import parse_publication_text
    except ImportError as e:
        fail(f"Cannot import parse_publication_text: {e}"); return

    parsed = parse_publication_text(_FORMAT_A_TEXT, "FIL-PRO-2023/00482")

    required_keys = {
        "processo_id", "publication_date", "signing_date_in_pub",
        "contract_number", "contratante", "contratada",
        "object_summary", "value", "edition", "document_type",
        "warnings", "parsed_at",
    }
    check("Format A: all schema keys present",
          required_keys.issubset(parsed.keys()),
          hint=f"missing: {required_keys - set(parsed.keys())}")

    check("Format A: signing_date_in_pub extracted",
          parsed.get("signing_date_in_pub") == "16/09/2024",
          hint=f"got: {parsed.get('signing_date_in_pub')}")

    check("Format A: contract_number extracted",
          parsed.get("contract_number") == "2403453/2024",
          hint=f"got: {parsed.get('contract_number')}")

    check("Format A: value extracted",
          parsed.get("value") == "1.216.829,52",
          hint=f"got: {parsed.get('value')}")

    check("Format A: contratante extracted (non-empty)",
          parsed.get("contratante") is not None and len(parsed["contratante"]) > 3)

    check("Format A: contratada extracted (non-empty)",
          parsed.get("contratada") is not None and len(parsed["contratada"]) > 3)

    check("Format A: object_summary extracted (non-empty)",
          parsed.get("object_summary") is not None and len(parsed["object_summary"]) > 5)

    check("Format A: document_type is 'contract'",
          parsed.get("document_type") == "contract",
          hint=f"got: {parsed.get('document_type')}")

    check("Format A: warnings is a list",
          isinstance(parsed.get("warnings"), list))


# ══════════════════════════════════════════════════════════════════════════════
# TRACK B.12 — publication_parser Format B
# ══════════════════════════════════════════════════════════════════════════════

def track_b12_parser_format_b():
    section("TRACK B.12 — publication_parser Format B (DoWeb structured block)")
    try:
        from infrastructure.extractors.publication_parser import parse_publication_text
    except ImportError as e:
        fail(f"Cannot import parse_publication_text: {e}"); return

    parsed = parse_publication_text(_FORMAT_B_TEXT, "TUR-PRO-2025/01221")

    check("Format B: value extracted",
          parsed.get("value") is not None,
          hint=f"got: {parsed.get('value')}")

    check("Format B: object_summary extracted (non-empty)",
          parsed.get("object_summary") is not None and len(parsed.get("object_summary", "")) > 5,
          hint=f"got: {parsed.get('object_summary')}")

    check("Format B: at least contratante or contratada extracted",
          parsed.get("contratante") or parsed.get("contratada"),
          hint="both parties are None — Format B parser may not be matching")

    check("Format B: warnings is a list",
          isinstance(parsed.get("warnings"), list))


# ══════════════════════════════════════════════════════════════════════════════
# TRACK B.13 — publication_parser Format C (masthead date)
# ══════════════════════════════════════════════════════════════════════════════

def track_b13_parser_format_c():
    section("TRACK B.13 — publication_parser Format C (D.O.RIO masthead date)")
    try:
        from infrastructure.extractors.publication_parser import parse_publication_text
    except ImportError as e:
        fail(f"Cannot import parse_publication_text: {e}"); return

    parsed = parse_publication_text(_FORMAT_C_TEXT, "TUR-PRO-2025/01221")

    check("Format C: publication_date extracted from masthead",
          parsed.get("publication_date") == "30/09/2024",
          hint=f"got: {parsed.get('publication_date')}")

    check("Format C: edition extracted from masthead",
          parsed.get("edition") == "136",
          hint=f"got: {parsed.get('edition')}")

    check("Format C: signing_date_in_pub extracted",
          parsed.get("signing_date_in_pub") == "15/09/2024",
          hint=f"got: {parsed.get('signing_date_in_pub')}")

    check("Format C: document_type is 'contract'",
          parsed.get("document_type") == "contract",
          hint=f"got: {parsed.get('document_type')}")


# ══════════════════════════════════════════════════════════════════════════════
# TRACK B.14 — publication_preprocessor.preprocess_publications_data
# ══════════════════════════════════════════════════════════════════════════════

def track_b14_preprocessor():
    section("TRACK B.14 — preprocess_publications_data (Epic 3 → Epic 4 bridge)")
    try:
        from infrastructure.extractors.publication_preprocessor import preprocess_publications_data
    except ImportError as e:
        fail(f"Cannot import preprocess_publications_data: {e}"); return

    raw = _make_raw_publications("FIL-PRO-2023/00482", _FORMAT_C_TEXT)
    result = preprocess_publications_data("FIL-PRO-2023/00482", raw)

    check("returns a dict (not None) on valid input",
          result is not None,
          hint="returned None — check quality_passes flag in fixture")

    if result is None:
        return

    required_keys = {
        "processo_id", "source", "publication_date", "signing_date_in_pub",
        "contract_number", "contratante", "contratada",
        "object_summary", "value", "edition", "document_type",
        "documents_found", "documents_parsed", "all_publications", "warnings",
    }
    check("output schema: all required keys present",
          required_keys.issubset(result.keys()),
          hint=f"missing: {required_keys - set(result.keys())}")

    check("source == 'doweb'",
          result.get("source") == "doweb")

    check("documents_found == 1",
          result.get("documents_found") == 1)

    check("documents_parsed == 1",
          result.get("documents_parsed") == 1,
          hint=f"got: {result.get('documents_parsed')}")

    check("all_publications is a list",
          isinstance(result.get("all_publications"), list))

    check("returns None on empty publications list",
          preprocess_publications_data("X", {"publications": []}) is None)


# ══════════════════════════════════════════════════════════════════════════════
# TRACK B.15 — Progress helpers
# ══════════════════════════════════════════════════════════════════════════════

def track_b15_progress():
    section("TRACK B.15 — Progress tracking (Task 3.8)")
    try:
        from infrastructure.scrapers.doweb.downloader import (
            _load_progress, _save_progress,
            _mark_completed, _mark_failed, _mark_no_results,
        )
        import infrastructure.scrapers.doweb.downloader as dl_mod
    except ImportError as e:
        fail(f"Cannot import progress helpers: {e}"); return

    with tempfile.TemporaryDirectory() as tmp:
        orig = dl_mod.PROGRESS_FILE
        dl_mod.PROGRESS_FILE = Path(tmp) / "test_progress.json"
        try:
            prog = _load_progress()
            check("_load_progress: returns dict with 'completed' key",
                  isinstance(prog, dict) and "completed" in prog)
            check("_load_progress: returns dict with 'failed' key",
                  "failed" in prog)
            check("_load_progress: returns dict with 'stats' key",
                  "stats" in prog)

            _mark_completed(prog, "PID-001")
            check("_mark_completed: PID-001 in completed",
                  "PID-001" in prog["completed"])

            _mark_no_results(prog, "PID-002")
            check("_mark_no_results: PID-002 tracked",
                any(
                    (isinstance(e, dict) and e.get("processo_id") == "PID-002")
                    for e in prog.get("no_results", [])
                ))

            _mark_failed(prog, "PID-003", "test error")
            check("_mark_failed: PID-003 in failed",
                  any(
                      (e == "PID-003" or (isinstance(e, dict) and e.get("processo_id") == "PID-003"))
                      for e in prog.get("failed", [])
                  ))

            _save_progress(prog)
            check("_save_progress: file created",
                  dl_mod.PROGRESS_FILE.exists())

            # Reload and verify persistence
            prog2 = _load_progress()
            check("progress persists after save/load",
                  "PID-001" in prog2.get("completed", []))
        finally:
            dl_mod.PROGRESS_FILE = orig


# ══════════════════════════════════════════════════════════════════════════════
# TRACK B.16 — Embedded publication flag short-circuit (Gap 4)
# ══════════════════════════════════════════════════════════════════════════════

def track_b16_embedded_flag():
    section("TRACK B.16 — Embedded publication flag short-circuit (Gap 4)")
    try:
        from infrastructure.scrapers.doweb.downloader import _has_embedded_publication
        import infrastructure.scrapers.doweb.downloader as dl_mod
    except ImportError as e:
        fail(f"Cannot import _has_embedded_publication: {e}"); return

    with tempfile.TemporaryDirectory() as tmp:
        orig = dl_mod.PREPROCESSED_DIR
        dl_mod.PREPROCESSED_DIR = Path(tmp)
        try:
            # No flag file → should return False
            check("_has_embedded_publication: False when no flag file",
                  _has_embedded_publication("FIL-PRO-2023/00482") is False)

            # Create flag file → should return True
            flag_path = Path(tmp) / "FIL-PRO-2023_00482_pub_embedded.flag"
            flag_path.write_text("FIL-PRO-2023/00482", encoding="utf-8")
            check("_has_embedded_publication: True when flag file exists",
                  _has_embedded_publication("FIL-PRO-2023/00482") is True)
        finally:
            dl_mod.PREPROCESSED_DIR = orig


# ══════════════════════════════════════════════════════════════════════════════
# TRACK C — Validate existing extraction outputs
# ══════════════════════════════════════════════════════════════════════════════

def track_c_output_validation():
    section("TRACK C — Validate existing Stage 3 outputs")

    extractions_dir = ROOT / "data/extractions"
    pub_files = list(extractions_dir.glob("*_publications_raw.json")) \
                if extractions_dir.exists() else []

    if not pub_files:
        warn("No *_publications_raw.json files found — skipping Track C")
        warn("Run Stage 3 at least once to generate outputs")
        return

    info(f"Checking {len(pub_files)} publications_raw.json files...")

    schema_errors   = 0
    empty_text      = 0
    quality_failed  = 0
    no_results      = 0

    for f in pub_files:
        try:
            with open(f, encoding="utf-8") as fh:
                doc = json.load(fh)
        except json.JSONDecodeError as e:
            fail(f"{f.name}: invalid JSON — {e}")
            schema_errors += 1
            continue

        top_keys = {"processo_id", "discovery_metadata", "search_metadata", "publications"}
        if not top_keys.issubset(doc.keys()):
            fail(f"{f.name}: missing top-level keys {top_keys - set(doc.keys())}")
            schema_errors += 1
            continue

        pubs = doc["publications"]
        if len(pubs) == 0:
            no_results += 1
            continue

        for pub in pubs:
            if not pub.get("raw_text"):
                empty_text += 1
            if not pub.get("validation", {}).get("quality_passes"):
                quality_failed += 1

    total   = len(pub_files)
    with_pubs = total - no_results

    check(f"All {total} files have valid JSON schema", schema_errors == 0,
          hint=f"{schema_errors} file(s) have schema errors")

    check(f"No publications_raw.json files have empty raw_text",
          empty_text == 0,
          hint=f"{empty_text} publication record(s) have empty raw_text")

    info(f"Files with results:  {with_pubs}/{total}")
    info(f"No-results files:    {no_results}/{total}")
    info(f"Quality-failed pubs: {quality_failed}")

    success_rate = (with_pubs / total * 100) if total > 0 else 0
    check(f"Search success rate ≥ 85% ({success_rate:.1f}%)",
          success_rate >= 85.0,
          hint=f"Target is 85% — currently at {success_rate:.1f}%")

    # Progress file
    progress_file = ROOT / "data/publication_extraction_progress.json"
    if progress_file.exists():
        with open(progress_file, encoding="utf-8") as f:
            prog = json.load(f)
        check("publication_extraction_progress.json: 'completed' key present",
              "completed" in prog)
        check("publication_extraction_progress.json: 'stats' key present",
              "stats" in prog)
        info(f"Progress: {prog.get('stats', {})}")
    else:
        warn("data/publication_extraction_progress.json not found")

    # Temp directory should be empty
    temp_dir  = ROOT / "data/temp_downloads"
    temp_pdfs = list(temp_dir.glob("*.pdf")) if temp_dir.exists() else []
    check("data/temp_downloads/ has 0 leftover PDFs",
          len(temp_pdfs) == 0,
          hint=f"{len(temp_pdfs)} PDF(s) left — previous run may have crashed (Task 3.7)")

    # Log files
    logs_dir = ROOT / "logs"
    pub_logs = list(logs_dir.glob("extraction_publications_*.log")) if logs_dir.exists() else []
    check("logs/extraction_publications_*.log exists (Task 3.9)",
          len(pub_logs) > 0,
          hint="No log file found — check setup_logging in stage3_publication.py")


# ══════════════════════════════════════════════════════════════════════════════
# TRACK D — Live integration instructions
# ══════════════════════════════════════════════════════════════════════════════

def track_d_instructions():
    section("TRACK D — LIVE INTEGRATION TEST (run on your machine)")
    print(f"""
  {BOLD}This track requires a real browser + DoWeb portal access.{RESET}
  Only run after Track A + B + C pass cleanly.

  {BOLD}{CYAN}Option 1 — Quick single-processo smoke test{RESET}
  ────────────────────────────────────────────────────────────
  Searches DoWeb for 1 processo, verifies the full pipeline.

    {GREEN}python -c "
from infrastructure.scrapers.doweb.downloader import DoWebDownloader, load_processo_ids
from infrastructure.web.driver import create_driver, close_driver
pids = load_processo_ids()[:1]
driver = create_driver(headless=False, anti_detection=True)
d = DoWebDownloader(driver)
result = d.download_all(pids)
close_driver(driver)
print(result)
"{RESET}

  {BOLD}{CYAN}Option 2 — Full Stage 3 run{RESET}
  ────────────────────────────────────────────────────────────
    {GREEN}python application/workflows/stage3_publication.py{RESET}

  {BOLD}Expected results:{RESET}
  - [ ] Browser opens, DoWeb CAPTCHA may appear
  - [ ] Solve CAPTCHA once — session persists for all IDs
  - [ ] data/extractions/{{ID}}_publications_raw.json created per ID
  - [ ] data/publication_extraction_progress.json updated after each ID
  - [ ] data/temp_downloads/ stays empty between downloads
  - [ ] Re-running skips already-completed IDs
  - [ ] Embedded-flag IDs are skipped immediately (Gap 4)

  {BOLD}Acceptance gates:{RESET}
  - [ ] ≥ 85% search success rate
  - [ ] 0 PDFs left in data/temp_downloads/
  - [ ] logs/extraction_publications_YYYYMMDD_HHMMSS.log created

  {BOLD}{YELLOW}Known gap (Task 3.3):{RESET}
  The HTML-only publication path is not implemented.
  If a DoWeb result has no PDF link, the record is saved with
  extraction_error='PDF download failed' and quality_passes=False.
  This is tracked as a known limitation — document in docs/epics-v2.md.
""")


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Stage 3 test suite — DoWeb Publication Extraction"
    )
    parser.add_argument("--quick", action="store_true",
                        help="Track A + B only; skip Track C output validation")
    args = parser.parse_args()

    print(f"\n{BOLD}{'═' * 70}{RESET}")
    print(f"{BOLD}  CONTRACT ANALYSIS — STAGE 3 TEST SUITE{RESET}")
    print(f"{BOLD}  DoWeb Publication Extraction{RESET}")
    print(f"{BOLD}{'═' * 70}{RESET}")

    has_outputs = track_a_environment()
    track_b1_detect_format()
    track_b2_normalize()
    track_b3_classify()
    track_b4_metadata_parser()
    track_b5_search_result_item()
    track_b6_quality_check()
    track_b7_validate_processo()
    track_b8_extract_text_guard()
    track_b9_build_record()
    track_b10_save_publications()
    track_b11_parser_format_a()
    track_b12_parser_format_b()
    track_b13_parser_format_c()
    track_b14_preprocessor()
    track_b15_progress()
    track_b16_embedded_flag()

    if not args.quick:
        track_c_output_validation()

    track_d_instructions()

    print(f"\n{BOLD}{'═' * 70}{RESET}")
    print(f"{BOLD}  RESULTS{RESET}")
    print(f"{'═' * 70}")
    print(f"  {GREEN}✓  Passed  : {PASSED}{RESET}")
    print(f"  {RED}✗  Failed  : {FAILED}{RESET}")
    print(f"  {YELLOW}⚠  Warnings: {WARNINGS}{RESET}")

    if FAILED == 0:
        print(f"\n  {BOLD}{GREEN}✅ ALL CHECKS PASSED — Stage 3 ready for MDAP sign-off{RESET}")
    else:
        print(f"\n  {BOLD}{RED}❌ {FAILED} check(s) failed — resolve before MDAP sign-off{RESET}")
    print(f"{'═' * 70}\n")

    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())