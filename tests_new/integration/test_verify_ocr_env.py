import sys
import os
import pytesseract
import subprocess
from PIL import Image
from pdf2image import convert_from_path

import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
TEST_IMAGE = r"data\downloads\processos\teste.png"
POPPLER_PATH = r"C:\poppler-25.12.0\Library\bin"
PDF_FILE = r"data\downloads\processos\AGUCAP202501330.pdf"


logging.info("Python executable:")
logging.info(sys.executable)

logging.info("\nChecking Tesseract path exists:")
logging.info(TESSERACT_PATH, "->", os.path.exists(TESSERACT_PATH))

logging.info("\nPOPPLER EXISTS:")
logging.info(POPPLER_PATH, "->", os.path.exists(POPPLER_PATH))

# -----------------------------
# FORCE TESSERACT
# -----------------------------
pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH

logging.info("\nTesseract cmd (forced):")
logging.info(pytesseract.pytesseract.tesseract_cmd)

# -----------------------------
# TEST Teseract EXECUTION
# -----------------------------
logging.info("\nRunning tesseract --version via subprocess:\n")

subprocess.run(
    [pytesseract.pytesseract.tesseract_cmd, "--version"],
    check=True
)

logging.info("\nTesseract version:")
subprocess.run([pytesseract.pytesseract.tesseract_cmd, "--version"])

logging.info("\nPDF EXISTS:")
logging.info(PDF_FILE, "->", os.path.exists(PDF_FILE))
logging.info("=" * 50)

if not os.path.exists(PDF_FILE):
    raise FileNotFoundError("PDF not found")

# -----------------------------

logging.info("=" * 50)
logging.info("SCRIPT LOCATION:")
logging.info(os.path.abspath(__file__))

logging.info("\nTEST IMAGE EXISTS:")
logging.info(TEST_IMAGE, "->", os.path.exists(TEST_IMAGE))
logging.info("=" * 50)

if not os.path.exists(TESSERACT_PATH):
    raise FileNotFoundError("Tesseract executable not found")

if not os.path.exists(TEST_IMAGE):
    raise FileNotFoundError("Test image not found")


# -----------------------------
# PDF → IMAGE
# -----------------------------

logging.info("\nConverting PDF to images...")
pages = convert_from_path(
    PDF_FILE,
    dpi=300,
    poppler_path=POPPLER_PATH
)

logging.info(f"Pages converted: {len(pages)}")

# -----------------------------
# OCR EACH PAGE
# -----------------------------

logging.info("\nRUNNING OCR...\n")

for i, page in enumerate(pages, start=1):
    text = pytesseract.image_to_string(page)
    logging.info(f"--- PAGE {i} ---")
    logging.info(text)

logging.info("\n✅ PDF OCR COMPLETED SUCCESSFULLY")

# -----------------------------
# OCR TEST
# -----------------------------
logging.info("\nRUNNING OCR...\n")

img = Image.open(TEST_IMAGE)
text = pytesseract.image_to_string(img)

logging.info("OCR RESULT:")
logging.info("-" * 30)
logging.info(text)
logging.info("-" * 30)

logging.info("\n✅ OCR TEST COMPLETED SUCCESSFULLY")
