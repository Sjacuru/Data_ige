"""
infrastructure/extractors/pdf_text_extractor.py

Raw text extraction from PDF files.

Stage 2 responsibility: given a local PDF file, return its COMPLETE text.
No AI, no LLM, no conformity checks — those belong to later stages.

Extraction strategy (3-method cascade):
  1. PyMuPDF  — fast, accurate for digital PDFs (primary)
  2. pdfplumber — alternative parser, better on complex/tabular layouts
  3. Tesseract OCR — last resort for scanned/image-only PDFs

Quality gate:
  - Minimum 500 characters total (Epic 2 requirement)
  - Readability check: printable ratio must be > 70%
  - Low-quality extractions are flagged but still saved

OCR dependencies (optional — gracefully skipped if absent):
  pip install pymupdf pdfplumber pdf2image pytesseract
  System: tesseract-ocr, poppler-utils
"""
import logging
import os
import platform
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Platform detection ────────────────────────────────────────────────────────
_WINDOWS = platform.system() == "Windows"

# ── OCR configuration ─────────────────────────────────────────────────────────
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

# ── Quality thresholds ────────────────────────────────────────────────────────
# Minimum average chars/page before trying the next extraction method
OCR_THRESHOLD = 300

# Epic 2 requirement: minimum total chars for a valid extraction
MIN_TOTAL_CHARS = 500
QUALITY_MEDIUM_THRESHOLD = 2000

# Minimum fraction of printable characters (garbled text fails this)
MIN_PRINTABLE_RATIO = 0.70


# ═══════════════════════════════════════════════════════════════════════════════
# QUALITY VALIDATION
# ═══════════════════════════════════════════════════════════════════════════════

def _quality_check(text: str) -> dict:
    """
    Evaluate extracted text quality against Epic 2 thresholds.

    Args:
        text: Raw extracted text string.

    Returns:
        {
            "passes":          bool,   # True if both checks pass
            "total_chars":     int,
            "printable_ratio": float,  # 0.0 – 1.0
            "flags":           list[str],  # human-readable failure reasons
        }
    """
    flags = []
    total_chars = len(text.strip())

    # Check 1: minimum character count (Epic 2: >500 chars)
    if total_chars < MIN_TOTAL_CHARS:
        flags.append(
            f"low_char_count:{total_chars}<{MIN_TOTAL_CHARS}"
        )

    # Check 2: printable ratio (garbled OCR / encoding issues)
    if total_chars > 0:
        printable = sum(
            1 for c in text
            if c.isprintable() or c in ("\n", "\r", "\t")
        )
        printable_ratio = printable / len(text)
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


# ═══════════════════════════════════════════════════════════════════════════════
# METHOD 1 — PyMuPDF (primary)
# ═══════════════════════════════════════════════════════════════════════════════

def _extract_pymupdf(pdf_path: str) -> Optional[dict]:
    """
    Attempt text extraction with PyMuPDF (fitz).

    Returns result dict on success, None if the library is unavailable
    or extraction yields insufficient text density.
    """
    try:
        import fitz
    except ImportError:
        logger.debug("   PyMuPDF (fitz) not installed — skipping Method 1")
        return None

    try:
        doc = fitz.open(pdf_path)
        page_texts = []
        char_counts = []

        for page in doc:
            t = str(page.get_text("text") or "")
            page_texts.append(t)
            char_counts.append(len(t.strip()))

        doc.close()

        total_pages = len(char_counts)
        avg_chars = sum(char_counts) / max(total_pages, 1)
        text = "\n\n".join(page_texts)

        if avg_chars >= OCR_THRESHOLD:
            logger.info(
                f"   📄 Method 1 (PyMuPDF): {total_pages} pages, "
                f"avg {avg_chars:.0f} chars/page"
            )
            return {
                "text":   text,
                "pages":  total_pages,
                "source": "pymupdf",
            }

        logger.info(
            f"   ⚠  Method 1 (PyMuPDF): low density "
            f"({avg_chars:.0f} chars/page) — trying Method 2"
        )
        return None

    except Exception as e:
        logger.warning(f"   ⚠  Method 1 (PyMuPDF) failed: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# METHOD 2 — pdfplumber (alternative parser)
# ═══════════════════════════════════════════════════════════════════════════════

def _extract_pdfplumber(pdf_path: str) -> Optional[dict]:
    """
    Attempt text extraction with pdfplumber.

    pdfplumber is better than PyMuPDF on complex layouts, multi-column
    text, and embedded tables — common in Brazilian government contracts.

    Returns result dict on success, None if unavailable or insufficient.
    """
    try:
        import pdfplumber
    except ImportError:
        logger.debug("   pdfplumber not installed — skipping Method 2")
        logger.debug("   Install with: pip install pdfplumber")
        return None

    try:
        page_texts = []

        with pdfplumber.open(pdf_path) as pdf:
            total_pages = len(pdf.pages)
            for page in pdf.pages:
                t = page.extract_text() or ""
                page_texts.append(t)

        text = "\n\n".join(page_texts)
        char_counts = [len(t.strip()) for t in page_texts]
        avg_chars = sum(char_counts) / max(total_pages, 1)

        if avg_chars >= OCR_THRESHOLD:
            logger.info(
                f"   📄 Method 2 (pdfplumber): {total_pages} pages, "
                f"avg {avg_chars:.0f} chars/page"
            )
            return {
                "text":   text,
                "pages":  total_pages,
                "source": "pdfplumber",
            }

        logger.info(
            f"   ⚠  Method 2 (pdfplumber): low density "
            f"({avg_chars:.0f} chars/page) — trying Method 3 (OCR)"
        )
        return None

    except Exception as e:
        logger.warning(f"   ⚠  Method 2 (pdfplumber) failed: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# METHOD 3 — Tesseract OCR (final fallback)
# ═══════════════════════════════════════════════════════════════════════════════

def _tesseract_available() -> bool:
    """Check whether Tesseract is installed and callable."""
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
    Extract text via pdf2image + Tesseract OCR.

    Called only when both native methods yield insufficient content.
    Returns result dict on success, None if dependencies are missing.
    """
    if not _tesseract_available():
        logger.warning("   ⚠  Method 3 (OCR): Tesseract not available")
        logger.warning("       Install: https://github.com/UB-Mannheim/tesseract/wiki")
        return None

    try:
        from pdf2image import convert_from_path
        import pytesseract
    except ImportError:
        logger.warning("   ⚠  Method 3 (OCR): pdf2image not installed")
        logger.warning("       Install with: pip install pdf2image")
        return None

    try:
        kwargs = {}
        if POPPLER_PATH:
            kwargs["poppler_path"] = POPPLER_PATH

        pages = convert_from_path(pdf_path, dpi=300, **kwargs)
        total_pages = len(pages)
        texts = []

        for i, page_img in enumerate(pages, 1):
            logger.debug(f"   🔍 OCR page {i}/{total_pages}...")
            try:
                t = pytesseract.image_to_string(
                    page_img, lang="por", config="--psm 6 --oem 3"
                )
            except Exception:
                # Fallback to English if Portuguese data file is missing
                t = pytesseract.image_to_string(
                    page_img, lang="eng", config="--psm 6 --oem 3"
                )
            texts.append(t)

        text = "\n\n".join(texts)
        logger.info(
            f"   📄 Method 3 (OCR): {total_pages} pages, "
            f"{len(text):,} total chars"
        )
        return {
            "text":   text,
            "pages":  total_pages,
            "source": "ocr",
        }

    except Exception as e:
        logger.error(f"   ✗ Method 3 (OCR) failed: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════════════════════

def extract_text(pdf_path: str) -> dict:
    """
    Extract complete raw text from a PDF using a 3-method cascade.

    Tries each method in order until one succeeds with sufficient text
    density. Quality is validated after extraction and flagged if below
    Epic 2 thresholds (500 chars minimum, 70% printable ratio).

    Args:
        pdf_path: Absolute or relative path to the PDF file.

    Returns:
        {
            "success":          bool,
            "text":             str,    # COMPLETE contract text
            "pages":            int,
            "source":           str,    # "pymupdf" | "pdfplumber" | "ocr"
                                        # | "native_insufficient" | "failed"
            "pdf_path":         str,
            "total_chars":      int,
            "quality_passes":   bool,   # True if >=500 chars & readable
            "quality_flags":    list,   # reasons for quality failure (if any)
            "error":            str | None,
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

    # ── Method 1: PyMuPDF ─────────────────────────────────────────────────────
    result = _extract_pymupdf(pdf_path)

    # ── Method 2: pdfplumber ──────────────────────────────────────────────────
    if result is None:
        result = _extract_pdfplumber(pdf_path)

    # ── Method 3: OCR ─────────────────────────────────────────────────────────
    if result is None:
        logger.info("   🧠 Both native methods insufficient — attempting OCR...")
        result = _extract_ocr(pdf_path)

    # ── All methods exhausted ─────────────────────────────────────────────────
    if result is None:
        # Last resort: use whatever PyMuPDF got, even if sparse
        try:
            import fitz
            doc = fitz.open(pdf_path)
            texts = [str(p.get_text("text") or "") for p in doc]
            pages = len(texts)
            doc.close()
            text = "\n\n".join(texts)
            logger.warning(
                f"   ⚠  All methods failed/unavailable — "
                f"using sparse native text ({len(text)} chars)"
            )
            result = {"text": text, "pages": pages, "source": "native_insufficient"}
        except Exception as e:
            base["error"] = f"All extraction methods failed: {e}"
            logger.error(f"   ✗ {base['error']}")
            return base

    # ── Quality validation ────────────────────────────────────────────────────
    quality = _quality_check(result["text"])

    if not quality["passes"]:
        logger.warning(
            f"   ⚠  Quality check FAILED: {quality['flags']} "
            f"({quality['total_chars']:,} chars, "
            f"printable={quality['printable_ratio']:.0%})"
        )
    else:
        logger.info(
            f"   ✓ Quality OK: {quality['total_chars']:,} chars, "
            f"printable={quality['printable_ratio']:.0%}"
        )

    return {
        "success":        True,
        "text":           result["text"],
        "pages":          result["pages"],
        "source":         result["source"],
        "pdf_path":       pdf_path,
        "total_chars":    quality["total_chars"],
        "quality_passes": quality["passes"],
        "quality_flags":  quality["flags"],
        "error":          None,
    }