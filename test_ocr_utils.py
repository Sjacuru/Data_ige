import os
import pytesseract
from PIL import Image
from pdf2image import convert_from_path

# -----------------------------
# CONFIG (single source of truth)
# -----------------------------
TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
POPPLER_PATH = r"C:\poppler-25.12.0\Library\bin"


def setup_ocr():
    """Force and validate Tesseract."""
    if not os.path.exists(TESSERACT_PATH):
        raise FileNotFoundError(f"Tesseract not found: {TESSERACT_PATH}")

    pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH
    return TESSERACT_PATH


def ocr_image(image_path: str) -> str:
    """OCR a single image file."""
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image not found: {image_path}")

    img = Image.open(image_path)
    return pytesseract.image_to_string(img)


def ocr_pdf(pdf_path: str, dpi: int = 300) -> str:
    """OCR a scanned PDF (image-based)."""
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    pages = convert_from_path(
        pdf_path,
        dpi=dpi,
        poppler_path=POPPLER_PATH
    )

    text_pages = []
    for i, page in enumerate(pages, start=1):
        text = pytesseract.image_to_string(page)
        text_pages.append(f"\n--- PAGE {i} ---\n{text}")

    return "\n".join(text_pages)
