
from infrastructure.extractors.pdf_text_extractor import _extract_ocr
import pathlib

# Point this at any *_raw.json's source PDF, or place a contract PDF here
pdf = 'data/temp/FIL-PRO-2023_00482.pdf'

# If no PDF on disk, use the extraction we already have
import json, pathlib
files = list(pathlib.Path('data/extractions').glob('*_raw.json'))
with open(files[0], "r", encoding="utf-8") as f:
    r = json.load(f)

print("Chars:", r["total_chars"])
print("Words:", r["total_words"])
print("Text sample:", r["raw_text"][:300])

# If you have the actual PDF, run OCR directly
p = pathlib.Path(pdf)
if p.exists():

    print()
    print('=== OCR ===')
    res_ocr = _extract_ocr(pdf)
    if res_ocr:
        print('Chars:', len(res_ocr['text']), '| Pages:', res_ocr['pages'])
        print('Sample:', res_ocr['text'][:300])
    else:
        print('Result: None (tesseract unavailable or failed)')
else:
    print(f'PDF not on disk at {pdf} — re-run smoke test to get a fresh PDF')
    print('The PDF is deleted after extraction by design.')
    print('Temporarily disable _delete_pdf to keep it for this test.')
