"""
infrastructure/extractors/pdf_text_extractor.py

Raw text extraction from PDF files.

Stage 2 responsibility: given a local PDF file, return its text.
No AI, no LLM, no conformity checks — those belong to later stages.

Extraction strategy (mirrors what was proven in contract_extractor.py):
  1. Try PyMuPDF native text layer (fast, accurate for digital PDFs)
  2. If average chars/page < 300, fall back to OCR via Tesseract
  3. Return raw text + basic metadata

OCR dependencies (optional — gracefully skipped if absent):
  pip install pymupdf pdf2image pytesseract
  System: tesseract-ocr, poppler-utils
"""
import logging
import platform
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)

# ── OCR configuration (matches contract_extractor.py settings) ────────────────
import os

_WINDOWS = platform.system() == "Windows"

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

# Minimum average chars/page — below this we switch to OCR
OCR_THRESHOLD = 300


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


def _ocr_pdf(pdf_path: str) -> str:
    """
    OCR all pages of a PDF using pdf2image + Tesseract.
    Called only when native text extraction yields insufficient content.
    """
    from pdf2image import convert_from_path
    import pytesseract

    if POPPLER_PATH:
        pages = convert_from_path(pdf_path, dpi=300, poppler_path=POPPLER_PATH)
    else:
        pages = convert_from_path(pdf_path, dpi=300)

    texts = []
    for page_img in pages:
        try:
            text = pytesseract.image_to_string(
                page_img, lang="por", config="--psm 6 --oem 3"
            )
        except Exception:
            # Fallback to English if Portuguese data file is missing
            text = pytesseract.image_to_string(
                page_img, lang="eng", config="--psm 6 --oem 3"
            )
        texts.append(text)

    return "\n\n".join(texts)


def extract_text(pdf_path: str) -> dict:
    """
    Extract raw text from a PDF file.

    Args:
        pdf_path: Absolute or relative path to the PDF.

    Returns:
        {
            "success":      bool,
            "text":         str,   # full extracted text
            "pages":        int,
            "source":       str,   # "native" | "ocr" | "native_insufficient"
            "pdf_path":     str,
            "error":        str | None,
        }
    """
    pdf_path = str(pdf_path)

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
        native_text = "\n\n".join(page_texts)

        # Decide whether native text is sufficient
        if avg_chars >= OCR_THRESHOLD:
            logger.info(
                f"   📄 Native extraction: {total_pages} pages, "
                f"avg {avg_chars:.0f} chars/page"
            )
            return {
                "success": True,
                "text": native_text,
                "pages": total_pages,
                "source": "native",
                "pdf_path": pdf_path,
                "error": None,
            }

        # Low text density — try OCR
        logger.info(
            f"   🧠 Low text density ({avg_chars:.0f} chars/page) → attempting OCR"
        )

        if not _tesseract_available():
            logger.warning(
                "   ⚠ Tesseract not available — using sparse native text"
            )
            return {
                "success": True,
                "text": native_text,
                "pages": total_pages,
                "source": "native_insufficient",
                "pdf_path": pdf_path,
                "error": None,
            }

        ocr_text = _ocr_pdf(pdf_path)
        logger.info(f"   ✓ OCR complete: {len(ocr_text):,} chars")

        return {
            "success": True,
            "text": ocr_text,
            "pages": total_pages,
            "source": "ocr",
            "pdf_path": pdf_path,
            "error": None,
        }

    except Exception as e:
        logger.error(f"   ✗ Extraction failed: {e}")
        return {
            "success": False,
            "text": "",
            "pages": 0,
            "source": "failed",
            "pdf_path": pdf_path,
            "error": str(e),
        }