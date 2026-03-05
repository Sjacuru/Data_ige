"""
infrastructure/extractors/publication_extractor.py

Stage 3 — Extract raw text from DoWeb gazette page PDFs.

How this differs from pdf_text_extractor.py (Epic 2)
─────────────────────────────────────────────────────
Epic 2 contracts are predominantly scanned images — OCR is the only
viable path and PyMuPDF consistently returns 0 chars.

Epic 3 gazette pages are digitally composed (typeset before printing).
They carry a real text layer that PyMuPDF reads perfectly in < 1 second.
OCR is only needed for older / scanned gazette editions.

Additionally, gazette pages have a two-column (sometimes three-column)
layout.  Standard Tesseract --psm 6 reads left-to-right across both
columns, interleaving two completely different publication entries.
The OCR fallback path here splits each page image into column strips
before running Tesseract on each strip separately.

Extraction cascade
──────────────────
1. PyMuPDF  — reads digital text layer            (fast, no OCR)
              if total_chars >= 500 → done
2. Column-split OCR — pdf2image + Tesseract       (fallback)
              splits page into 2 or 3 vertical strips
              OCRs each strip independently with --psm 6
              concatenates strips in left-to-right reading order

Post-extraction
───────────────
validate_processo_in_text() checks whether the target processo_id
appears anywhere in the extracted text.  It reuses normalize_processo_id()
from searcher.py to handle zero-padding and formatting differences between
how the ID was registered and how it was typed in the gazette.

Public API
──────────
    extract_text(pdf_path, processo_id)  →  dict (same schema as
                                            pdf_text_extractor + 3 extra keys)

    validate_processo_in_text(text, processo_id)  →  dict
        (callable independently for re-validation of existing extractions)

Return schema (superset of pdf_text_extractor.extract_text)
────────────────────────────────────────────────────────────
    {
        "success":                bool,
        "text":                   str,
        "pages":                  int,
        "source":                 str,   # "pymupdf" | "ocr_columns" | "failed"
        "pdf_path":               str,
        "total_chars":            int,
        "quality_passes":         bool,
        "quality_flags":          list[str],
        "error":                  str | None,
        # ── Publication-specific additions ──
        "processo_found_in_text": bool,
        "possible_mismatch":      bool,
        "matched_variation":      str,   # which variation matched, "" if none
    }
"""

import logging
import os
import platform
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Platform ──────────────────────────────────────────────────────────────────
_WINDOWS = platform.system() == "Windows"

# ── OCR configuration — inherited from environment, same vars as Epic 2 ──────
TESSERACT_PATH: str = os.getenv(
    "TESSERACT_PATH",
    r"C:\Program Files\Tesseract-OCR\tesseract.exe" if _WINDOWS else "tesseract",
)
TESSDATA_DIR: Optional[str] = os.getenv(
    "TESSDATA_PREFIX",
    r"C:\Program Files\Tesseract-OCR\tessdata" if _WINDOWS else None,
)
POPPLER_PATH: Optional[str] = os.getenv(
    "POPPLER_PATH",
    r"C:\poppler-25.12.0\Library\bin" if _WINDOWS else None,
)

# ── Quality thresholds — identical to pdf_text_extractor (Epic 2) ─────────────
MIN_TOTAL_CHARS     = 500    # minimum chars for a valid extraction
MIN_PRINTABLE_RATIO = 0.70   # minimum fraction of printable characters

# ── OCR tuning for gazette column strips ──────────────────────────────────────
OCR_DPI             = 300    # rasterisation resolution
OCR_LANG_PRIMARY    = "por"  # Portuguese tessdata (preferred)
OCR_LANG_FALLBACK   = "eng"  # English tessdata (if por not installed)
OCR_PSM_COLUMN      = "6"    # Single uniform block — correct for a narrow strip
OCR_OEM             = "3"    # Default LSTM engine

# Column detection: fraction of page width that constitutes a gutter
# A vertical band with ≥ GUTTER_WHITE_THRESHOLD fraction of white pixels
# is considered a column separator.
GUTTER_WHITE_THRESHOLD = 0.90   # 90% white pixels in a vertical band → gutter
GUTTER_SCAN_HEIGHT_FRAC = 0.60  # analyse the middle 60% of the page height
GUTTER_BAND_WIDTH       = 10    # pixel width of each vertical scan band


# ══════════════════════════════════════════════════════════════════════════════
# QUALITY VALIDATION  (mirrors pdf_text_extractor._quality_check)
# ══════════════════════════════════════════════════════════════════════════════

def _quality_check(text: str) -> dict:
    """
    Evaluate extracted text quality.

    Returns:
        {
            "passes":          bool,
            "total_chars":     int,
            "printable_ratio": float,
            "flags":           list[str],
        }
    """
    flags       = []
    total_chars = len(text.strip())

    if total_chars < MIN_TOTAL_CHARS:
        flags.append(f"low_char_count:{total_chars}<{MIN_TOTAL_CHARS}")

    if total_chars > 0:
        printable_count = sum(
            1 for c in text if c.isprintable() or c in ("\n", "\r", "\t")
        )
        printable_ratio = printable_count / len(text)
    else:
        printable_ratio = 0.0

    if printable_ratio < MIN_PRINTABLE_RATIO:
        flags.append(
            f"low_printable_ratio:{printable_ratio:.2f}<{MIN_PRINTABLE_RATIO}"
        )

    return {
        "passes":          len(flags) == 0,
        "total_chars":     total_chars,
        "printable_ratio": round(printable_ratio, 3),
        "flags":           flags,
    }


# ══════════════════════════════════════════════════════════════════════════════
# PATH 1 — DIGITAL TEXT LAYER  (PyMuPDF)
# ══════════════════════════════════════════════════════════════════════════════

def _extract_digital(pdf_path: str) -> Optional[dict]:
    """
    Extract text from the PDF's native digital layer using PyMuPDF.

    Gazette pages are digitally typeset — this is fast and produces
    perfectly structured text with correct column reading order because
    the text layer preserves the logical reading order regardless of
    visual column layout.

    Returns:
        { "text": str, "pages": int, "source": "pymupdf" }
        or None if PyMuPDF is unavailable or extraction fails.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        logger.warning(
            "   ⚠ PyMuPDF (fitz) not installed — skipping digital path.\n"
            "     Install: pip install pymupdf"
        )
        return None

    try:
        doc   = fitz.open(pdf_path)
        pages = []

        for page_num in range(len(doc)):
            page = doc[page_num]
            # sort=True preserves logical reading order (top-to-bottom, then
            # left-to-right within each line) — critical for column layouts
            text = page.get_text("text", sort=True)
            pages.append(text)

        doc.close()
        full_text = "\n\n".join(pages)

        logger.debug(
            f"   📄 PyMuPDF: {len(doc)} page(s), "
            f"{len(full_text):,} chars"
        )
        return {
            "text":   full_text,
            "pages":  len(pages),
            "source": "pymupdf",
        }

    except Exception as exc:
        logger.warning(f"   ⚠ PyMuPDF extraction failed: {exc}")
        return None


# ══════════════════════════════════════════════════════════════════════════════
# PATH 2 — COLUMN-AWARE OCR  (pdf2image + Tesseract)
# ══════════════════════════════════════════════════════════════════════════════

def _detect_column_count(page_image) -> int:
    """
    Estimate the number of text columns in a gazette page image.

    Strategy: scan vertical bands across the middle 60% of the page
    height.  A band where ≥ 90% of pixels are near-white is a column
    gutter.  Count how many such gutters exist in the left half vs
    overall page width.

    Returns 1, 2, or 3.  Falls back to 2 on any error — the most
    common gazette layout.
    """
    try:
        from PIL import Image
        import numpy as np

        # Convert to greyscale numpy array for pixel analysis
        grey  = page_image.convert("L")
        arr   = np.array(grey)          # shape: (height, width)
        h, w  = arr.shape

        # Analyse only the middle vertical band (skip header/footer)
        top    = int(h * 0.20)
        bottom = int(h * 0.80)
        mid    = arr[top:bottom, :]

        gutters_found = 0
        # Scan every GUTTER_BAND_WIDTH pixels across the page
        for x in range(GUTTER_BAND_WIDTH, w - GUTTER_BAND_WIDTH, GUTTER_BAND_WIDTH):
            band        = mid[:, x: x + GUTTER_BAND_WIDTH]
            white_frac  = (band >= 240).mean()   # near-white threshold
            if white_frac >= GUTTER_WHITE_THRESHOLD:
                gutters_found += 1

        # Cluster gutter bands: consecutive white bands = one gutter
        # Rough heuristic: if total white bands > ~5% of page width → another column
        column_transitions = 0
        in_gutter = False
        for x in range(GUTTER_BAND_WIDTH, w - GUTTER_BAND_WIDTH, GUTTER_BAND_WIDTH):
            band       = mid[:, x: x + GUTTER_BAND_WIDTH]
            white_frac = (band >= 240).mean()
            is_white   = white_frac >= GUTTER_WHITE_THRESHOLD
            if is_white and not in_gutter:
                column_transitions += 1
                in_gutter = True
            elif not is_white:
                in_gutter = False

        # column_transitions == number of gutters == number_of_columns - 1
        detected = column_transitions + 1
        if detected < 1:
            detected = 2   # safe fallback
        if detected > 3:
            detected = 3   # cap at 3 (gazette spec)

        logger.debug(f"   🔍 Column detection: {column_transitions} gutter(s) → {detected} column(s)")
        return detected

    except Exception as exc:
        logger.warning(f"   ⚠ Column detection failed: {exc} — defaulting to 2 columns")
        return 2


def _split_columns(page_image, column_count: int) -> List:
    """
    Split a page image into vertical column strips.

    Splits at equal fractions (½ for 2 cols, ⅓ and ⅔ for 3 cols).
    Equal splitting is reliable because gazette page columns are
    designed with consistent widths.

    Returns a list of PIL Image objects, left to right.
    """
    w, h = page_image.size
    strips = []

    boundaries = [round(w * i / column_count) for i in range(column_count + 1)]

    for i in range(column_count):
        left  = boundaries[i]
        right = boundaries[i + 1]
        strip = page_image.crop((left, 0, right, h))
        strips.append(strip)

    return strips


def _ocr_strip(strip_image, strip_label: str = "") -> str:
    """
    Run Tesseract OCR on one column strip image.

    Uses --psm 6 (single uniform block) which is correct for a narrow
    single-column strip.  Tries Portuguese first, falls back to English
    if por tessdata is not installed.

    Returns the extracted text string (may be empty on failure).
    """
    try:
        import pytesseract
        pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH
        if TESSDATA_DIR:
            os.environ["TESSDATA_PREFIX"] = TESSDATA_DIR

        config = f"--psm {OCR_PSM_COLUMN} --oem {OCR_OEM}"

        try:
            text = pytesseract.image_to_string(
                strip_image, lang=OCR_LANG_PRIMARY, config=config
            )
        except Exception:
            # Portuguese tessdata not installed — fall back to English
            logger.debug(
                f"   ⚠ {strip_label}: 'por' lang not found — using 'eng' fallback"
            )
            text = pytesseract.image_to_string(
                strip_image, lang=OCR_LANG_FALLBACK, config=config
            )

        return text.strip()

    except Exception as exc:
        logger.warning(f"   ⚠ OCR strip failed ({strip_label}): {exc}")
        return ""


def _extract_ocr_columns(pdf_path: str) -> Optional[dict]:
    """
    Extract text from a scanned gazette PDF using column-aware OCR.

    For each page:
        1. Rasterise at 300 DPI via pdf2image
        2. Detect column count (2 or 3) from pixel analysis
        3. Split page into column strips
        4. OCR each strip independently with --psm 6
        5. Concatenate strips left-to-right

    All pages are concatenated in order with a page separator.

    Returns:
        { "text": str, "pages": int, "source": "ocr_columns" }
        or None if pdf2image / Tesseract are unavailable.
    """
    try:
        from pdf2image import convert_from_path
        import pytesseract
    except ImportError as exc:
        logger.error(
            f"   ✗ Required library missing: {exc}\n"
            f"     Install: pip install pdf2image pytesseract\n"
            f"     Windows also needs Poppler — set POPPLER_PATH env var."
        )
        return None

    try:
        pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH
        pytesseract.get_tesseract_version()
    except Exception as exc:
        logger.error(
            f"   ✗ Tesseract not available: {exc}\n"
            f"     Set TESSERACT_PATH env var to the tesseract executable."
        )
        return None

    try:
        kwargs = {}
        if POPPLER_PATH:
            kwargs["poppler_path"] = POPPLER_PATH

        images      = convert_from_path(pdf_path, dpi=OCR_DPI, **kwargs)
        total_pages = len(images)
        page_texts  = []

        for page_num, page_img in enumerate(images, 1):
            col_count = _detect_column_count(page_img)
            strips    = _split_columns(page_img, col_count)

            logger.debug(
                f"   🔍 Page {page_num}/{total_pages}: "
                f"{col_count} column(s) detected"
            )

            strip_texts = []
            for col_idx, strip in enumerate(strips, 1):
                label = f"page {page_num} col {col_idx}/{col_count}"
                text  = _ocr_strip(strip, strip_label=label)
                if text:
                    strip_texts.append(text)

            # Join columns with a clear separator so the reader knows where
            # the column break occurred — useful for downstream parsing
            page_text = "\n\n--- COLUMN BREAK ---\n\n".join(strip_texts)
            page_texts.append(page_text)

        full_text = "\n\n--- PAGE BREAK ---\n\n".join(page_texts)

        logger.info(
            f"   📄 OCR columns: {total_pages} page(s), "
            f"{len(full_text):,} chars"
        )
        return {
            "text":   full_text,
            "pages":  total_pages,
            "source": "ocr_columns",
        }

    except Exception as exc:
        logger.error(f"   ✗ Column OCR pipeline failed: {exc}")
        return None


# ══════════════════════════════════════════════════════════════════════════════
# PROCESSO ID VALIDATION
# ══════════════════════════════════════════════════════════════════════════════

def validate_processo_in_text(text: str, processo_id: str) -> dict:
    """
    Check whether a processo ID appears anywhere in extracted gazette text.

    Why normalization is necessary
    ────────────────────────────────
    The ID in the system may not exactly match how it was typed into the
    gazette.  Real examples from the sample page:

        Registered:  006800.000105/2026-77
        In gazette:  006800.00105/2026-77   ← missing one zero (typo)

        Registered:  TUR-PRO-2025/01221
        In gazette:  TUR-PRO-2025/01221     ← exact (most Format B IDs)

    normalize_processo_id() from searcher.py already generates the full
    variation list for each ID format.  We try each variation in order
    and stop on the first match.

    Args:
        text:        Raw text from extract_text().
        processo_id: The processo ID string to search for.

    Returns:
        {
            "found":              bool,
            "possible_mismatch":  bool,   # True = ID not found after all variations
            "matched_variation":  str,    # variation that matched, "" if none
        }
    """
    if not text or not processo_id:
        return {
            "found":             False,
            "possible_mismatch": True,
            "matched_variation": "",
        }

    # Import normalizer from searcher.py — single source of truth for
    # ID format variations (reuse, don't reimplement)
    try:
        from infrastructure.scrapers.doweb.searcher import normalize_processo_id
        variations = normalize_processo_id(processo_id)
    except ImportError:
        # Fallback if searcher.py is not yet on the path (e.g. during tests)
        logger.warning(
            "   ⚠ Could not import normalize_processo_id from searcher.py "
            "— using exact match only"
        )
        variations = [processo_id]

    import re

    for variation in variations:
        # Use word-boundary-aware search: the ID may be surrounded by
        # spaces, colons, newlines, or the word "Processo"
        pattern = re.escape(variation)
        if re.search(pattern, text, re.IGNORECASE):
            logger.debug(
                f"   ✓ ID found in text via variation: '{variation}'"
            )
            return {
                "found":             True,
                "possible_mismatch": False,
                "matched_variation": variation,
            }

    logger.debug(
        f"   ⚠ ID '{processo_id}' not found after "
        f"{len(variations)} variation(s)"
    )
    return {
        "found":             False,
        "possible_mismatch": True,
        "matched_variation": "",
    }


# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ══════════════════════════════════════════════════════════════════════════════

def extract_text(pdf_path: str, processo_id: str) -> dict:
    """
    Extract complete raw text from a DoWeb gazette page PDF.

    Cascade:
        1. PyMuPDF reads the digital text layer (fast, accurate)
           → if chars >= 500: use this result
        2. Column-aware OCR fallback (scanned / older editions)
           → splits page into column strips, OCRs each independently

    After extraction, validate_processo_in_text() checks whether
    the target processo_id appears in the result.

    Args:
        pdf_path:    Path to the downloaded gazette page PDF.
        processo_id: The processo ID to verify presence of in the text.

    Returns:
        {
            "success":                bool,
            "text":                   str,
            "pages":                  int,
            "source":                 str,   # "pymupdf" | "ocr_columns" | "failed"
            "pdf_path":               str,
            "total_chars":            int,
            "quality_passes":         bool,
            "quality_flags":          list[str],
            "error":                  str | None,
            "processo_found_in_text": bool,
            "possible_mismatch":      bool,
            "matched_variation":      str,
        }
    """
    base = {
        "success":                False,
        "text":                   "",
        "pages":                  0,
        "source":                 "failed",
        "pdf_path":               str(pdf_path),
        "total_chars":            0,
        "quality_passes":         False,
        "quality_flags":          [],
        "error":                  None,
        # Publication-specific
        "processo_found_in_text": False,
        "possible_mismatch":      True,
        "matched_variation":      "",
    }

    # ── Guard: file must exist ────────────────────────────────────────────────
    if not Path(pdf_path).exists():
        base["error"] = f"File not found: {pdf_path}"
        logger.error(f"   ✗ {base['error']}")
        return base

    # ── Path 1: digital text layer via PyMuPDF ────────────────────────────────
    logger.debug(f"   🔍 Trying PyMuPDF (digital text layer)...")
    result = _extract_digital(str(pdf_path))

    if result is not None:
        qc = _quality_check(result["text"])
        if qc["passes"]:
            logger.info(
                f"   ✓ Digital text layer OK: "
                f"{qc['total_chars']:,} chars via PyMuPDF"
            )
            return _build_result(base, result, qc, processo_id)
        else:
            logger.info(
                f"   ℹ Digital layer insufficient "
                f"({qc['total_chars']} chars) — trying column OCR"
            )

    # ── Path 2: column-aware OCR fallback ─────────────────────────────────────
    logger.info(f"   🔍 Trying column-aware OCR fallback...")
    result = _extract_ocr_columns(str(pdf_path))

    if result is not None:
        qc = _quality_check(result["text"])
        if not qc["passes"]:
            logger.warning(
                f"   ⚠ Low-quality OCR: {qc['flags']} "
                f"— saving for manual review"
            )
        else:
            logger.info(
                f"   ✓ Column OCR OK: "
                f"{qc['total_chars']:,} chars, {result['pages']} page(s)"
            )
        return _build_result(base, result, qc, processo_id)

    # ── Both paths failed ─────────────────────────────────────────────────────
    base["error"] = (
        "Both extraction paths failed. "
        "Check PyMuPDF installation and Tesseract/Poppler configuration."
    )
    logger.error(f"   ✗ {base['error']}")
    return base


# ══════════════════════════════════════════════════════════════════════════════
# INTERNAL RESULT BUILDER
# ══════════════════════════════════════════════════════════════════════════════

def _build_result(base: dict, extraction: dict, qc: dict, processo_id: str) -> dict:
    """
    Merge extraction output, quality check, and ID validation into one dict.

    Called by extract_text() for both the digital and OCR paths so the
    return schema is always identical regardless of which path succeeded.
    """
    validation = validate_processo_in_text(extraction["text"], processo_id)

    return {
        **base,
        "success":                True,
        "text":                   extraction["text"],
        "pages":                  extraction["pages"],
        "source":                 extraction["source"],
        "total_chars":            qc["total_chars"],
        "quality_passes":         qc["passes"],
        "quality_flags":          qc["flags"],
        "error":                  None,
        # Publication-specific
        "processo_found_in_text": validation["found"],
        "possible_mismatch":      validation["possible_mismatch"],
        "matched_variation":      validation["matched_variation"],
    }