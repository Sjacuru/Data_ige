"""
infrastructure/extractors/pdf_text_extractor.py

Raw text extraction from PDF files — OCR only.

Stage 2 responsibility: given a local PDF file, return its COMPLETE text.
No AI, no LLM, no conformity checks — those belong to later stages.

Why OCR only?
─────────────
Government contract PDFs from this portal are predominantly scanned images.
PyMuPDF and pdfplumber only read the editable text layer — typically just
headers and footers, missing the entire contract body. Testing confirmed:

    PyMuPDF   → 0 chars (below threshold) — missed the contract body
    OCR       → 40,516 chars              — full contract including typed text

Tesseract OCR reads the full rasterised page image, capturing both printed
text and typed text regardless of whether the PDF was digitally created or
scanned from paper.

Quality gate (Epic 2):
    - Minimum 500 total characters
    - Printable ratio ≥ 70% (catches garbled OCR output)
    - Low-quality extractions are flagged but still saved for manual review

Dependencies:
    pip install pdf2image pytesseract
    Windows: install Tesseract from https://github.com/UB-Mannheim/tesseract/wiki
    Windows: install Poppler  from https://github.com/oschwartz10612/poppler-windows
"""
import logging
import os
import platform
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Platform ──────────────────────────────────────────────────────────────────
_WINDOWS = platform.system() == "Windows"

# ── OCR configuration (override via environment variables) ───────────────────
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

# ── Quality thresholds (Epic 2) ───────────────────────────────────────────────
MIN_TOTAL_CHARS    = 500    # minimum total characters for a valid extraction
MIN_PRINTABLE_RATIO = 0.70  # minimum fraction of printable characters
OCR_THRESHOLD      = 300    # kept for test-suite compatibility — not used in logic


# ══════════════════════════════════════════════════════════════════════════════
# QUALITY VALIDATION
# ══════════════════════════════════════════════════════════════════════════════

def _quality_check(text: str) -> dict:
    """
    Evaluate extracted text quality against Epic 2 thresholds.

    Args:
        text: Raw extracted text string.

    Returns:
        {
            "passes":          bool,
            "total_chars":     int,
            "printable_ratio": float,   # 0.0 – 1.0
            "flags":           list[str],
        }
    """
    flags       = []
    total_chars = len(text.strip())

    # Check 1: minimum character count
    if total_chars < MIN_TOTAL_CHARS:
        flags.append(f"low_char_count:{total_chars}<{MIN_TOTAL_CHARS}")

    # Check 2: printable ratio (catches garbled OCR / encoding noise)
    if total_chars > 0:
        printable_count  = sum(
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
# OCR ENGINE
# ══════════════════════════════════════════════════════════════════════════════

def _tesseract_available() -> bool:
    """Return True if Tesseract is installed and callable."""
    try:
        import pytesseract
        pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH
        if TESSDATA_DIR:
            os.environ["TESSDATA_PREFIX"] = TESSDATA_DIR
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def _extract_ocr(pdf_path: str) -> Optional[dict]:
    """
    Extract text from every page via pdf2image + Tesseract.

    Rasterises each page at 300 DPI and runs OCR with the Portuguese
    language pack (falls back to English if 'por' is not installed).

    Returns:
        {
            "text":   str,   # full concatenated text, all pages
            "pages":  int,
            "source": "ocr",
        }
        or None if Tesseract / pdf2image is unavailable.
    """
    if not _tesseract_available():
        logger.error(
            "   ✗ Tesseract not available — OCR impossible.\n"
            "     Windows install: https://github.com/UB-Mannheim/tesseract/wiki\n"
            "     Set TESSERACT_PATH env var if installed to a non-default location."
        )
        return None

    try:
        from pdf2image import convert_from_path
        import pytesseract
    except ImportError:
        logger.error(
            "   ✗ pdf2image not installed.\n"
            "     Install: pip install pdf2image\n"
            "     Windows also needs Poppler: set POPPLER_PATH env var."
        )
        return None

    try:
        kwargs = {}
        if POPPLER_PATH:
            kwargs["poppler_path"] = POPPLER_PATH

        pages      = convert_from_path(pdf_path, dpi=300, **kwargs)
        total_pages = len(pages)
        texts       = []

        for i, page_img in enumerate(pages, 1):
            logger.debug(f"   🔍 OCR page {i}/{total_pages}...")
            try:
                t = pytesseract.image_to_string(
                    page_img, lang="por", config="--psm 6 --oem 3"
                )
            except Exception:
                # Portuguese tessdata not installed — fall back to English
                t = pytesseract.image_to_string(
                    page_img, lang="eng", config="--psm 6 --oem 3"
                )
            texts.append(t)

        text = "\n\n".join(texts)
        logger.info(
            f"   📄 OCR: {total_pages} page(s), {len(text):,} total chars"
        )
        return {
            "text":   text,
            "pages":  total_pages,
            "source": "ocr",
        }

    except Exception as e:
        logger.error(f"   ✗ OCR failed: {e}")
        return None


# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ══════════════════════════════════════════════════════════════════════════════

def extract_text(pdf_path: str) -> dict:
    """
    Extract complete raw text from a PDF using Tesseract OCR.

    All pages are rasterised and OCR'd regardless of whether the PDF
    contains a native text layer. This ensures the full contract body
    is captured even for scanned-image PDFs from this portal.

    Args:
        pdf_path: Absolute or relative path to the PDF file.

    Returns:
        {
            "success":        bool,
            "text":           str,    # complete OCR'd text, all pages
            "pages":          int,
            "source":         str,    # "ocr" | "failed"
            "pdf_path":       str,
            "total_chars":    int,
            "quality_passes": bool,
            "quality_flags":  list[str],
            "error":          str | None,
        }
    """
    pdf_path = str(pdf_path)
    base = {
        "success":        False,
        "text":           "",
        "pages":          0,
        "source":         "failed",
        "pdf_path":       pdf_path,
        "total_chars":    0,
        "quality_passes": False,
        "quality_flags":  [],
        "error":          None,
    }

    if not Path(pdf_path).exists():
        base["error"] = f"File not found: {pdf_path}"
        logger.error(f"   ✗ {base['error']}")
        return base

    result = _extract_ocr(pdf_path)

    if result is None:
        base["error"] = (
            "OCR failed — check Tesseract installation. "
            "Set TESSERACT_PATH and POPPLER_PATH environment variables."
        )
        logger.error(f"   ✗ {base['error']}")
        return base

    # Quality gate
    qc = _quality_check(result["text"])

    if not qc["passes"]:
        logger.warning(
            f"   ⚠  Low-quality OCR output: {qc['flags']} "
            f"— saving for manual review"
        )
    else:
        logger.info(
            f"   ✓ Quality OK: {qc['total_chars']:,} chars, "
            f"printable ratio {qc['printable_ratio']:.2f}"
        )

    return {
        "success":        True,   # OCR ran; quality issues flagged, not fatal
        "text":           result["text"],
        "pages":          result["pages"],
        "source":         result["source"],
        "pdf_path":       pdf_path,
        "total_chars":    qc["total_chars"],
        "quality_passes": qc["passes"],
        "quality_flags":  qc["flags"],
        "error":          None,
    }