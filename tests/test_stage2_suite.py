"""
tests/test_stage2_suite.py

Stage 2 — Contract Text Extraction (NO LLM) — Test Suite
═════════════════════════════════════════════════════════
Mirrors the structure and conventions of tests/test_stage1_suite.py.

Three tracks — run in order:

  TRACK A — Environment & Imports
      Verifies Python environment, required packages (pymupdf, pdfplumber,
      pytesseract), and all Stage 2 module imports resolve without error.
      No files, no browser, no network.

  TRACK B — Unit Tests
      B.1  pdf_text_extractor  — cascade logic, quality check, schema keys
      B.2  downloader helpers  — sanitize, extraction_path, save_extraction schema
      B.3  progress tracking   — load/save/mark cycle (uses tmp dir)
      B.4  Validate existing extraction outputs (if data/ files are present)

  TRACK C — Instructions for live integration test
      Printed guidance — no automated browser run here.

Usage
─────
    python tests/test_stage2_suite.py          # run all tracks
    python tests/test_stage2_suite.py --quick  # Track A + B only (no data checks)

Run after Stage 1 has produced data/discovery/processo_links.json
and after Stage 2 has been run at least once to produce extractions.
"""
import argparse
import json
import os
import platform
import shutil
import sys
import tempfile
import time
from pathlib import Path

# ── Ensure project root is on sys.path ────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# ══════════════════════════════════════════════════════════════════════════════
# Console helpers  (identical palette to test_stage1_suite.py)
# ══════════════════════════════════════════════════════════════════════════════
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
    print(f"\n{BOLD}{CYAN}{'─' * 70}{RESET}")
    print(f"{BOLD}{CYAN}  {title}{RESET}")
    print(f"{BOLD}{CYAN}{'─' * 70}{RESET}")


def check(label: str, condition: bool, hint: str = "") -> None:
    global PASSED, FAILED
    if condition:
        PASSED += 1
        print(f"  {GREEN}✓{RESET}  {label}")
    else:
        FAILED += 1
        msg = f"  {RED}✗{RESET}  {label}"
        if hint:
            msg += f"\n       {YELLOW}hint: {hint}{RESET}"
        print(msg)


def warn(msg: str) -> None:
    global WARNINGS
    WARNINGS += 1
    print(f"  {YELLOW}⚠{RESET}  {msg}")


def info(msg: str) -> None:
    print(f"  {CYAN}ℹ{RESET}  {msg}")


def fail(msg: str) -> None:
    global FAILED
    FAILED += 1
    print(f"  {RED}✗  FATAL: {msg}{RESET}")


# ══════════════════════════════════════════════════════════════════════════════
# TRACK A — Environment & Imports
# ══════════════════════════════════════════════════════════════════════════════

def track_a_environment() -> bool:
    section("TRACK A — ENVIRONMENT & IMPORTS")

    # ── A1: Python version ────────────────────────────────────────────────────
    major, minor = sys.version_info[:2]
    check(
        f"Python {major}.{minor} (need ≥3.9)",
        major == 3 and minor >= 9,
        hint="Upgrade to Python 3.9+"
    )

    # ── A2: Core PDF libraries ─PyMuPDF and pdfplumber deleted. Only OCR solve the problem 

    # ── A3: OCR dependencies (optional — warn, don't fail) ────────────────────
    try:
        import pytesseract
        check("pytesseract importable", True)
    except ImportError:
        warn("pytesseract not installed — OCR fallback unavailable")
        warn("Install: pip install pytesseract  +  system tesseract-ocr")

    try:
        from pdf2image import convert_from_path
        check("pdf2image importable", True)
    except ImportError:
        warn("pdf2image not installed — OCR fallback unavailable")
        warn("Install: pip install pdf2image  +  system poppler-utils")

    # ── A4: requests (used by _download_pdf) ──────────────────────────────────
    try:
        import requests
        check("requests importable", True)
    except ImportError:
        check("requests importable", False, hint="pip install requests")

    # ── A5: Project module imports ────────────────────────────────────────────
    modules = [
        ("infrastructure.extractors.pdf_text_extractor", ["extract_text", "_quality_check"]),
        ("infrastructure.scrapers.transparencia.downloader",
         ["ProcessoDownloader", "load_links_from_discovery",
          "_sanitize", "_extraction_path", "_save_extraction",
          "_load_progress", "_save_progress", "_mark_completed", "_mark_failed"]),
        ("application.workflows.stage2_extraction", ["run_stage2_extraction"]),
        ("domain.models.processo_link", ["ProcessoLink"]),
    ]

    all_imports_ok = True
    for module_path, symbols in modules:
        try:
            mod = __import__(module_path, fromlist=symbols)
            for sym in symbols:
                if not hasattr(mod, sym):
                    check(f"{module_path}.{sym}", False,
                          hint=f"Module loaded but '{sym}' not found")
                    all_imports_ok = False
                else:
                    check(f"{module_path}.{sym}", True)
        except ImportError as e:
            check(f"{module_path}", False, hint=str(e))
            all_imports_ok = False

    # ── A6: Data directories ──────────────────────────────────────────────────
    required_dirs = [
        "data/discovery",
        "data/extractions",
        "data/temp",
        "logs",
    ]
    for d in required_dirs:
        p = ROOT / d
        if p.exists():
            check(f"Directory exists: {d}", True)
        else:
            warn(f"Directory missing: {d} — will be created at runtime")

    # ── A7: Stage 1 prerequisite — discovery file ────────────────────────────
    discovery_file = ROOT / "data/discovery/processo_links.json"
    has_discovery  = discovery_file.exists()
    check(
        "Stage 1 output exists: data/discovery/processo_links.json",
        has_discovery,
        hint="Run Stage 1 (application/main.py) before Stage 2"
    )

    # ── A8: Extraction outputs from a previous Stage 2 run ───────────────────
    extractions_dir  = ROOT / "data/extractions"
    extraction_files = list(extractions_dir.glob("*_raw.json")) if extractions_dir.exists() else []
    has_extractions  = len(extraction_files) > 0

    if has_extractions:
        check(f"Extraction outputs present ({len(extraction_files)} files)", True)
    else:
        warn("No *_raw.json files found — Track B.4 will be skipped")
        warn("Run Stage 2 at least once to generate extraction outputs")

    has_progress = (ROOT / "data/extraction_progress.json").exists()
    if has_progress:
        check("data/extraction_progress.json exists", True)
    else:
        warn("extraction_progress.json not found — normal on first run")

    return has_extractions


# ══════════════════════════════════════════════════════════════════════════════
# TRACK B.1 — UNIT: pdf_text_extractor
# ══════════════════════════════════════════════════════════════════════════════

def track_b1_extractor():
    section("TRACK B.1 — UNIT: pdf_text_extractor")

    try:
        from infrastructure.extractors.pdf_text_extractor import (
            extract_text,
            _quality_check,
            OCR_THRESHOLD,
            MIN_TOTAL_CHARS,
            MIN_PRINTABLE_RATIO,
        )
    except ImportError as e:
        fail(f"Cannot import pdf_text_extractor: {e}")
        return

    # ── B1.1: Quality check — high quality text ───────────────────────────────
    good_text = "Contrato de prestação de serviços. " * 50   # ~1750 chars
    qc = _quality_check(good_text)
    check("_quality_check: passes on sufficient readable text",
          qc["passes"] is True)
    check("_quality_check: returns correct total_chars",
          qc["total_chars"] == len(good_text.strip()))
    check("_quality_check: printable_ratio is float 0–1",
          isinstance(qc["printable_ratio"], float) and 0.0 <= qc["printable_ratio"] <= 1.0)

    # ── B1.2: Quality check — too short ──────────────────────────────────────
    short_text = "abc"
    qc_short = _quality_check(short_text)
    check("_quality_check: fails on text shorter than MIN_TOTAL_CHARS",
          qc_short["passes"] is False)
    check("_quality_check: flag contains 'low_char_count'",
          any("low_char_count" in f for f in qc_short["flags"]))

    # ── B1.3: Quality check — garbled text ───────────────────────────────────
    garbled = "\x00\x01\x02\x03\x04" * 200   # mostly non-printable
    qc_garbled = _quality_check(garbled)
    check("_quality_check: fails on garbled/non-printable text",
          qc_garbled["passes"] is False)
    check("_quality_check: flag contains 'low_printable_ratio'",
          any("low_printable_ratio" in f for f in qc_garbled["flags"]))

    # ── B1.4: Quality check — empty string ───────────────────────────────────
    qc_empty = _quality_check("")
    check("_quality_check: fails on empty string",
          qc_empty["passes"] is False)
    check("_quality_check: printable_ratio is 0.0 for empty string",
          qc_empty["printable_ratio"] == 0.0)

    # ── B1.5: extract_text on missing file ───────────────────────────────────
    result = extract_text("/nonexistent/path/file.pdf")
    check("extract_text: returns success=False for missing file",
          result["success"] is False)
    check("extract_text: error field populated on missing file",
          result["error"] is not None and len(result["error"]) > 0)

    # ── B1.6: extract_text output schema completeness ─────────────────────────
    required_keys = [
        "success", "text", "pages", "source", "pdf_path",
        "total_chars", "quality_passes", "quality_flags", "error"
    ]
    check(
        "extract_text output contains all required schema keys",
        all(k in result for k in required_keys),
        hint=f"Missing: {[k for k in required_keys if k not in result]}"
    )

    # ── B1.7: Threshold constants are sane ───────────────────────────────────
    check(f"OCR_THRESHOLD is positive int ({OCR_THRESHOLD})",
          isinstance(OCR_THRESHOLD, int) and OCR_THRESHOLD > 0)
    check(f"MIN_TOTAL_CHARS == 500 (Epic 2 requirement)",
          MIN_TOTAL_CHARS == 500,
          hint="Epic 2 specifies >500 chars as minimum quality gate")
    check(f"MIN_PRINTABLE_RATIO == 0.70",
          MIN_PRINTABLE_RATIO == 0.70)

    # ── B1.8: Real PDF test (uses existing extraction fixture if available) ───
    sample_pdf = ROOT / "data/downloads" / "TURCAP202500477.pdf"
    if sample_pdf.exists():
        r = extract_text(str(sample_pdf))
        check("extract_text: success=True on sample PDF",
              r["success"] is True)
        check("extract_text: text non-empty on sample PDF",
              len(r.get("text", "")) > 0)
        check("extract_text: source is one of the known methods",
              r.get("source") in ("pymupdf", "pdfplumber", "ocr", "native_insufficient"))
        info(f"Sample PDF: {r.get('total_chars',0):,} chars via [{r.get('source')}]")
    else:
        warn("Sample PDF not found at data/downloads/TURCAP202500477.pdf")
        warn("Skipping live PDF extraction test — place any contract PDF there to enable")


# ══════════════════════════════════════════════════════════════════════════════
# TRACK B.2 — UNIT: downloader helpers
# ══════════════════════════════════════════════════════════════════════════════

def track_b2_downloader_helpers():
    section("TRACK B.2 — UNIT: downloader helpers")

    try:
        from infrastructure.scrapers.transparencia.downloader import (
            _sanitize,
            _extraction_path,
            _is_already_extracted,
            _save_extraction,
            TEMP_PDF_DIR,
            EXTRACTIONS_DIR,
            PROGRESS_FILE,
        )
        from domain.models.processo_link import ProcessoLink
    except ImportError as e:
        fail(f"Cannot import downloader helpers: {e}")
        return

    # ── B2.1: _sanitize ───────────────────────────────────────────────────────
    check("_sanitize: replaces forward slash",
          _sanitize("TUR-PRO-2025/01221") == "TUR-PRO-2025_01221")
    check("_sanitize: replaces backslash",
          _sanitize("TUR-PRO-2025\\01221") == "TUR-PRO-2025_01221")
    check("_sanitize: no-op on clean ID",
          _sanitize("TURCAP202500477") == "TURCAP202500477")

    # ── B2.2: _extraction_path ────────────────────────────────────────────────
    p = _extraction_path("TUR-PRO-2025/01221")
    check("_extraction_path: returns Path object",
          isinstance(p, Path))
    check("_extraction_path: filename ends with _raw.json",
          p.name.endswith("_raw.json"),
          hint=f"Got: {p.name}")
    check("_extraction_path: filename contains sanitised ID",
          "TUR-PRO-2025_01221" in p.name)

    # ── B2.3: _is_already_extracted — false when file absent ─────────────────
    check("_is_already_extracted: False for non-existent processo",
          _is_already_extracted("THIS_ID_DOES_NOT_EXIST_XYZ_999") is False)

    # ── B2.4: TEMP_PDF_DIR is data/temp ──────────────────────────────────────
    # Normalise to forward slashes so the check passes on both Windows and Linux.
    # Windows: Path("data/temp") → str → "data\temp"; normalise → "data/temp"
    temp_dir_normalised = str(TEMP_PDF_DIR).replace("\\", "/")
    check(
        "TEMP_PDF_DIR == data/temp (was data/temp_downloads)",
        temp_dir_normalised in ("data/temp", str(ROOT / "data/temp").replace("\\", "/")),
        hint=f"Got: {TEMP_PDF_DIR} — update constant in downloader.py"
    )

    # ── B2.5: _save_extraction produces correct schema ────────────────────────
    tmp_dir = Path(tempfile.mkdtemp())
    try:
        # Patch EXTRACTIONS_DIR to temp location so we don't pollute real data
        import infrastructure.scrapers.transparencia.downloader as dl_module
        original_extractions_dir = dl_module.EXTRACTIONS_DIR
        dl_module.EXTRACTIONS_DIR = tmp_dir

        link = ProcessoLink(
            processo_id="TURCAP202500477",
            url="https://acesso.processo.rio/test",
            company_name="RIOTUR TEST",
            company_cnpj="33652179000159",
            contract_value="2.150.000,00",
            discovery_path=["RIOTUR TEST", "Secretaria", "UG-001"],
        )
        extraction = {
            "text":          "Contrato de prestação de serviços. " * 100,
            "pages":         5,
            "source":        "pymupdf",
            "total_chars":   3600,
            "quality_passes": True,
            "quality_flags": [],
            "error":         None,
            "pdf_size_bytes":          204857,
            "processing_time_seconds": 1.4,
        }

        ok = _save_extraction(link, extraction)
        check("_save_extraction: returns True on success", ok is True)

        # Find saved file
        saved = list(tmp_dir.glob("*_raw.json"))
        check("_save_extraction: creates exactly one *_raw.json file",
              len(saved) == 1,
              hint=f"Found: {[f.name for f in saved]}")

        if saved:
            with open(saved[0], encoding="utf-8") as f:
                record = json.load(f)

            # Mandatory top-level fields (Epic 2 confirmed schema)
            required_fields = [
                "processo_id", "url", "company_name", "company_cnpj",
                "contract_value", "discovery_path",
                "page_count", "extraction_method", "fallback_used",
                "total_chars", "total_words",
                "quality_passes", "quality_flags",
                "raw_text", "extraction_error", "extracted_at",
                "metadata",
            ]
            check(
                "_save_extraction: all required fields present in JSON",
                all(k in record for k in required_fields),
                hint=f"Missing: {[k for k in required_fields if k not in record]}"
            )

            # Metadata sub-block
            meta = record.get("metadata", {})
            check("_save_extraction: metadata.pdf_size_bytes present",
                  "pdf_size_bytes" in meta)
            check("_save_extraction: metadata.processing_time_seconds present",
                  "processing_time_seconds" in meta)

            # Value correctness
            check("_save_extraction: page_count == 5",
                  record.get("page_count") == 5)
            check("_save_extraction: extraction_method == 'pymupdf'",
                  record.get("extraction_method") == "pymupdf")
            check("_save_extraction: fallback_used == False for pymupdf",
                  record.get("fallback_used") is False)
            check("_save_extraction: total_words > 0",
                  record.get("total_words", 0) > 0)
            check("_save_extraction: raw_text is non-empty string",
                  isinstance(record.get("raw_text"), str)
                  and len(record["raw_text"]) > 0)
            check("_save_extraction: processo_id matches link",
                  record.get("processo_id") == "TURCAP202500477")

            # Confirm old schema keys are NOT present
            check("_save_extraction: old key 'pages' not present (renamed to page_count)",
                  "pages" not in record,
                  hint="Schema migration incomplete — 'pages' should be 'page_count'")
            check("_save_extraction: old key 'extraction_source' not present",
                  "extraction_source" not in record,
                  hint="Schema migration incomplete — use 'extraction_method'")
            check("_save_extraction: old key 'raw_text' (not 'full_text')",
                  "raw_text" in record and "full_text" not in record,
                  hint="Stage 2 stores raw_text; full_text is Stage 3 scope")

        # Restore original
        dl_module.EXTRACTIONS_DIR = original_extractions_dir

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ══════════════════════════════════════════════════════════════════════════════
# TRACK B.3 — UNIT: progress tracking
# ══════════════════════════════════════════════════════════════════════════════

def track_b3_progress():
    section("TRACK B.3 — UNIT: progress tracking")

    try:
        from infrastructure.scrapers.transparencia.downloader import (
            _load_progress,
            _save_progress,
            _mark_completed,
            _mark_failed,
            PROGRESS_FILE,
        )
        import infrastructure.scrapers.transparencia.downloader as dl_module
    except ImportError as e:
        fail(f"Cannot import progress helpers: {e}")
        return

    tmp_dir = Path(tempfile.mkdtemp())
    fake_progress_file = tmp_dir / "extraction_progress.json"

    original_progress_file = dl_module.PROGRESS_FILE
    dl_module.PROGRESS_FILE = fake_progress_file

    try:
        # ── B3.1: fresh load returns skeleton ────────────────────────────────
        progress = _load_progress()
        check("_load_progress: returns dict on missing file",
              isinstance(progress, dict))
        check("_load_progress: fresh skeleton has 'completed' list",
              isinstance(progress.get("completed"), list))
        check("_load_progress: fresh skeleton has 'failed' list",
              isinstance(progress.get("failed"), list))
        check("_load_progress: fresh skeleton has 'pending' list",
              isinstance(progress.get("pending"), list))
        check("_load_progress: fresh skeleton has 'stats' dict",
              isinstance(progress.get("stats"), dict))

        # ── B3.2: save round-trip ─────────────────────────────────────────────
        _save_progress(progress)
        check("_save_progress: creates file on disk",
              fake_progress_file.exists())

        with open(fake_progress_file, encoding="utf-8") as f:
            saved = json.load(f)
        check("_save_progress: 'updated_at' field written",
              "updated_at" in saved)

        # ── B3.3: mark_completed ──────────────────────────────────────────────
        _mark_completed(progress, "TURCAP202500477")
        check("_mark_completed: ID added to completed list",
              "TURCAP202500477" in progress["completed"])
        check("_mark_completed: stats.success incremented",
              progress["stats"]["success"] == 1)

        # ── B3.4: idempotent — mark same ID twice ────────────────────────────
        _mark_completed(progress, "TURCAP202500477")
        check("_mark_completed: idempotent — no duplicate in completed list",
              progress["completed"].count("TURCAP202500477") == 1)

        # ── B3.5: mark_failed ─────────────────────────────────────────────────
        _mark_failed(progress, "TURCAP202500099", "Selenium timeout")
        check("_mark_failed: adds entry to failed list",
              len(progress["failed"]) == 1)
        check("_mark_failed: entry has processo_id key",
              progress["failed"][0].get("processo_id") == "TURCAP202500099")
        check("_mark_failed: entry has error key",
              progress["failed"][0].get("error") == "Selenium timeout")
        check("_mark_failed: entry has timestamp 'at'",
              "at" in progress["failed"][0])
        check("_mark_failed: stats.failed incremented",
              progress["stats"]["failed"] == 1)

        # ── B3.6: save and reload persists all state ──────────────────────────
        _save_progress(progress)
        reloaded = _load_progress()
        check("_load_progress: reloads previously saved completed list",
              "TURCAP202500477" in reloaded.get("completed", []))
        check("_load_progress: reloads previously saved failed list",
              len(reloaded.get("failed", [])) == 1)

    finally:
        dl_module.PROGRESS_FILE = original_progress_file
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ══════════════════════════════════════════════════════════════════════════════
# TRACK B.4 — Validate existing extraction output files
# ══════════════════════════════════════════════════════════════════════════════

def track_b4_extraction_outputs(has_extractions: bool):
    section("TRACK B.4 — Validate existing extraction output files")

    if not has_extractions:
        warn("Skipped — no extraction output files found yet")
        warn("Run Stage 2 once, then re-run this suite to validate outputs")
        return

    extractions_dir = ROOT / "data/extractions"
    files = sorted(extractions_dir.glob("*_raw.json"))

    check(f"data/extractions/ contains *_raw.json files ({len(files)} found)",
          len(files) > 0)

    # ── B4.1: Spot-check first file for schema completeness ──────────────────
    if files:
        sample_path = files[0]
        try:
            with open(sample_path, encoding="utf-8") as f:
                record = json.load(f)

            required_fields = [
                "processo_id", "url", "company_name",
                "page_count", "extraction_method", "fallback_used",
                "total_chars", "total_words",
                "quality_passes", "quality_flags",
                "raw_text", "extracted_at", "metadata",
            ]
            check(
                f"Schema complete in {sample_path.name}",
                all(k in record for k in required_fields),
                hint=f"Missing: {[k for k in required_fields if k not in record]}"
            )
            check("raw_text is non-empty string",
                  isinstance(record.get("raw_text"), str)
                  and len(record["raw_text"]) > 0,
                  hint="Extraction may have failed — check quality_flags")
            check("total_chars > 0",
                  record.get("total_chars", 0) > 0)
            check("total_words > 0",
                  record.get("total_words", 0) > 0)
            check("page_count >= 1",
                  record.get("page_count", 0) >= 1)
            check("extraction_method is a known value",
                  record.get("extraction_method") in (
                      "pymupdf", "pdfplumber", "ocr", "native_insufficient", "partial"
                  ),
                  hint=f"Got: {record.get('extraction_method')}")
            check("metadata block is a dict",
                  isinstance(record.get("metadata"), dict))
            check("metadata.pdf_size_bytes is present",
                  "pdf_size_bytes" in record.get("metadata", {}))
            check("metadata.processing_time_seconds is present",
                  "processing_time_seconds" in record.get("metadata", {}))

            info(f"Sample file : {sample_path.name}")
            info(f"Method      : {record.get('extraction_method')}")
            info(f"Chars       : {record.get('total_chars', 0):,}")
            info(f"Words       : {record.get('total_words', 0):,}")
            info(f"Pages       : {record.get('page_count', 0)}")
            info(f"Quality     : {'✅ passes' if record.get('quality_passes') else '⚠ LOW'}")
            if record.get("quality_flags"):
                info(f"Flags       : {record['quality_flags']}")

        except json.JSONDecodeError as e:
            fail(f"{sample_path.name} is not valid JSON: {e}")

    # ── B4.2: Bulk quality scan ───────────────────────────────────────────────
    if len(files) > 1:
        low_quality = []
        failed_extraction = []
        old_schema = []

        for fp in files:
            try:
                with open(fp, encoding="utf-8") as f:
                    r = json.load(f)
                if not r.get("quality_passes"):
                    low_quality.append(fp.name)
                if r.get("extraction_method") in (None, "failed"):
                    failed_extraction.append(fp.name)
                if "pages" in r or "extraction_source" in r:
                    old_schema.append(fp.name)
            except Exception:
                failed_extraction.append(fp.name)

        total = len(files)
        good  = total - len(failed_extraction)
        rate  = round(good / total * 100, 1) if total else 0

        check(
            f"Extraction success rate ≥90%  ({rate}% — {good}/{total})",
            rate >= 90.0,
            hint=f"Failed IDs: {failed_extraction[:5]}{'...' if len(failed_extraction)>5 else ''}"
        )
        if low_quality:
            warn(f"{len(low_quality)} low-quality extractions (flagged, not failed):")
            for fn in low_quality[:5]:
                warn(f"   {fn}")
        if old_schema:
            check(
                "No files with old schema keys (pages/extraction_source)",
                False,
                hint=f"Old schema found in: {old_schema[:3]}"
            )
        else:
            check("No files with old schema keys (pages/extraction_source)", True)

        info(f"Total extractions: {total}")
        info(f"Success rate     : {rate}%")
        info(f"Low quality      : {len(low_quality)}")

    # ── B4.3: Progress file consistency ──────────────────────────────────────
    progress_path = ROOT / "data/extraction_progress.json"
    if progress_path.exists():
        try:
            with open(progress_path, encoding="utf-8") as f:
                prog = json.load(f)

            required_prog_keys = ["started_at", "updated_at", "completed", "failed", "pending", "stats"]
            check(
                "extraction_progress.json has all required keys",
                all(k in prog for k in required_prog_keys),
                hint=f"Missing: {[k for k in required_prog_keys if k not in prog]}"
            )
            check("completed is a list",
                  isinstance(prog.get("completed"), list))
            check("failed is a list of dicts",
                  isinstance(prog.get("failed"), list))
            check("stats has total/success/failed/skipped",
                  all(k in prog.get("stats", {}) for k in
                      ["total", "success", "failed", "skipped"]))

            # Cross-check: completed count vs actual files on disk
            completed_count = len(prog.get("completed", []))
            file_count      = len(files)
            check(
                f"completed count ({completed_count}) ≈ files on disk ({file_count})",
                abs(completed_count - file_count) <= 2,
                hint="Progress file may be out of sync — re-run Stage 2 to reconcile"
            )

        except json.JSONDecodeError as e:
            fail(f"extraction_progress.json is not valid JSON: {e}")
    else:
        warn("extraction_progress.json not found — skipping progress consistency check")

    # ── B4.4: temp/ directory should have 0 PDFs ─────────────────────────────
    temp_dir  = ROOT / "data/temp"
    temp_pdfs = list(temp_dir.glob("*.pdf")) if temp_dir.exists() else []
    check(
        f"data/temp/ has 0 leftover PDFs (max 1 at any time per Epic 2)",
        len(temp_pdfs) == 0,
        hint=f"Found {len(temp_pdfs)} leftover PDF(s) — a previous run may have crashed"
    )

    # ── B4.5: Log file exists ─────────────────────────────────────────────────
    logs_dir   = ROOT / "logs"
    stage2_logs = list(logs_dir.glob("extraction_contracts_*.log")) if logs_dir.exists() else []
    check(
        "logs/extraction_contracts_*.log exists",
        len(stage2_logs) > 0,
        hint="No log file found — check setup_logging call in stage2_extraction.py"
    )
    if stage2_logs:
        latest = max(stage2_logs, key=lambda p: p.stat().st_mtime)
        size_kb = latest.stat().st_size / 1024
        check(
            f"Latest log file has content (>1 KB)",
            size_kb > 1.0,
            hint=f"Got {size_kb:.1f} KB — log may be empty"
        )
        info(f"Latest log: {latest.name} ({size_kb:.1f} KB)")


# ══════════════════════════════════════════════════════════════════════════════
# TRACK C — Live integration test instructions
# ══════════════════════════════════════════════════════════════════════════════

def track_c_instructions():
    section("TRACK C — LIVE INTEGRATION TEST (run on your machine)")
    print(f"""
  {BOLD}This track requires a real browser + processo.rio portal access.{RESET}
  Only run after Track A + B pass cleanly.

  {BOLD}{CYAN}Option 1 — Quick single-contract smoke test (recommended first){RESET}
  ────────────────────────────────────────────────────────────────
  Extracts 1 contract only, verifying the full pipeline end-to-end.
  Takes ~2–3 minutes. Good for verifying the portal is reachable and
  CAPTCHA handling works.

    {GREEN}python -c "
from infrastructure.scrapers.transparencia.downloader import load_links_from_discovery, ProcessoDownloader
from infrastructure.web.driver import create_driver, close_driver
links = load_links_from_discovery()[:1]
# NOTE: headless must be False so that the CAPTCHA page renders images/fonts;
# running headless will produce an empty gray box that can't be solved by hand.
driver = create_driver(headless=False, anti_detection=True)
d = ProcessoDownloader(driver)
result = d.download_all(links)
close_driver(driver)
print(result)
"{RESET}

  {BOLD}{CYAN}Option 2 — Full Stage 2 run{RESET}
  ────────────────────────────────────────────────────────────────
  Processes all links from Stage 1 discovery.
  Resumable — safe to interrupt and re-run.

    {GREEN}python application/workflows/stage2_extraction.py{RESET}

  {BOLD}Expected Results:{RESET}
  - [ ] Browser opens, CAPTCHA appears on first URL
  - [ ] Solve CAPTCHA once — session persists for all subsequent contracts
  - [ ] Each contract: PDF downloads to data/temp/, text extracted, JSON saved, PDF deleted
  - [ ] data/temp/ stays empty between contracts (max 1 PDF at any time)
  - [ ] data/extractions/{{ID}}_raw.json created per contract
  - [ ] data/extraction_progress.json updated after each contract
  - [ ] Console shows chars + method + quality per contract
  - [ ] Re-running skips already-completed contracts
  - [ ] Interrupting with Ctrl+C then re-running resumes correctly

  {BOLD}Acceptance gates after full run:{RESET}
  - [ ] ≥90% extraction success rate
  - [ ] 0 PDFs left in data/temp/
  - [ ] Total storage < 2 MB for all *_raw.json files
  - [ ] logs/extraction_contracts_YYYYMMDD_HHMMSS.log created
  - [ ] Re-run this suite: all Track B.4 checks pass
""")


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Stage 2 test suite — Contract Text Extraction"
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Track A + B only; skip Track C instructions",
    )
    args = parser.parse_args()

    print(f"\n{BOLD}{'═' * 70}{RESET}")
    print(f"{BOLD}  CONTRACT ANALYSIS — STAGE 2 TEST SUITE{RESET}")
    print(f"{BOLD}  Contract Text Extraction (NO LLM){RESET}")
    print(f"{BOLD}{'═' * 70}{RESET}")

    has_extractions = track_a_environment()
    track_b1_extractor()
    track_b2_downloader_helpers()
    track_b3_progress()
    track_b4_extraction_outputs(has_extractions)

    if not args.quick:
        track_c_instructions()

    # ── Final scoreboard ──────────────────────────────────────────────────────
    print(f"\n{BOLD}{'═' * 70}{RESET}")
    print(f"{BOLD}  RESULTS{RESET}")
    print(f"{'═' * 70}")
    print(f"  {GREEN}✓  Passed  : {PASSED}{RESET}")
    print(f"  {RED}✗  Failed  : {FAILED}{RESET}")
    print(f"  {YELLOW}⚠  Warnings: {WARNINGS}{RESET}")

    if FAILED == 0:
        print(f"\n  {BOLD}{GREEN}✅ ALL CHECKS PASSED — Stage 2 ready for MDAP sign-off{RESET}")
    else:
        print(f"\n  {BOLD}{RED}❌ {FAILED} check(s) failed — resolve before MDAP sign-off{RESET}")
    print(f"{'═' * 70}\n")

    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())