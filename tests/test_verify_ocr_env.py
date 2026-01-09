import sys
import os
import pytesseract
import subprocess
from PIL import Image
from pdf2image import convert_from_path

TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
TEST_IMAGE = r"data\downloads\processos\teste.png"
POPPLER_PATH = r"C:\poppler-25.12.0\Library\bin"
PDF_FILE = r"data\downloads\processos\AGUCAP202501330.pdf"


print("Python executable:")
print(sys.executable)

print("\nChecking Tesseract path exists:")
print(TESSERACT_PATH, "->", os.path.exists(TESSERACT_PATH))

print("\nPOPPLER EXISTS:")
print(POPPLER_PATH, "->", os.path.exists(POPPLER_PATH))

# -----------------------------
# FORCE TESSERACT
# -----------------------------
pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH

print("\nTesseract cmd (forced):")
print(pytesseract.pytesseract.tesseract_cmd)

# -----------------------------
# TEST Teseract EXECUTION
# -----------------------------
print("\nRunning tesseract --version via subprocess:\n")

subprocess.run(
    [pytesseract.pytesseract.tesseract_cmd, "--version"],
    check=True
)

print("\nTesseract version:")
subprocess.run([pytesseract.pytesseract.tesseract_cmd, "--version"])

print("\nPDF EXISTS:")
print(PDF_FILE, "->", os.path.exists(PDF_FILE))
print("=" * 50)

if not os.path.exists(PDF_FILE):
    raise FileNotFoundError("PDF not found")

# -----------------------------

print("=" * 50)
print("SCRIPT LOCATION:")
print(os.path.abspath(__file__))

print("\nTEST IMAGE EXISTS:")
print(TEST_IMAGE, "->", os.path.exists(TEST_IMAGE))
print("=" * 50)

if not os.path.exists(TESSERACT_PATH):
    raise FileNotFoundError("Tesseract executable not found")

if not os.path.exists(TEST_IMAGE):
    raise FileNotFoundError("Test image not found")


# -----------------------------
# PDF → IMAGE
# -----------------------------

print("\nConverting PDF to images...")
pages = convert_from_path(
    PDF_FILE,
    dpi=300,
    poppler_path=POPPLER_PATH
)

print(f"Pages converted: {len(pages)}")

# -----------------------------
# OCR EACH PAGE
# -----------------------------

print("\nRUNNING OCR...\n")

for i, page in enumerate(pages, start=1):
    text = pytesseract.image_to_string(page)
    print(f"--- PAGE {i} ---")
    print(text)

print("\n✅ PDF OCR COMPLETED SUCCESSFULLY")

# -----------------------------
# OCR TEST
# -----------------------------
print("\nRUNNING OCR...\n")

img = Image.open(TEST_IMAGE)
text = pytesseract.image_to_string(img)

print("OCR RESULT:")
print("-" * 30)
print(text)
print("-" * 30)

print("\n✅ OCR TEST COMPLETED SUCCESSFULLY")
