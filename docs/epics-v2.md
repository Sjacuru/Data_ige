# Epic 2 - **Contract Text Extraction (NO LLM)**

**Priority: CRITICAL** | **Estimated Time: 18-20 hours**

**Why:** We need to extract and preserve the FULL TEXT of all contracts for later processing. This separates PDF handling from AI processing, enabling flexibility, cost efficiency, and resilience.

**What:** For each processo link from Epic 1, download PDF from Transparência portal, extract COMPLETE TEXT using PDF readers or OCR, save full text to JSON, and immediately delete PDF to minimize storage.

**Technical Breakdown:**

- **Transparência Portal Navigation**
    - Navigate to Transparência portal using processo ID
    - Handle authentication/session management
    - Locate PDF download link
    - Trigger PDF download to `data/temp/`
- **PDF Text Extraction Pipeline**
    - **Method 1 (Primary):** PyMuPDF (fitz)
        - Fast extraction for digital PDFs
        - Extracts all text from all pages
        - Preserves paragraph structure
    - **Method 2 (Fallback):** pdfplumber
        - Alternative parser for complex layouts
        - Better table extraction
    - **Method 3 (Final Fallback):** Tesseract OCR
        - For scanned/image-based PDFs
        - Convert PDF pages to images
        - Run OCR on each page
        - Concatenate results
- **Text Quality Validation**
    - Check minimum character count (>500 chars)
    - Verify text is readable (not garbled)
    - Log extraction method used
    - Flag low-quality extractions for review
- **JSON Storage (FULL TEXT)**
    - Save to `data/extractions/PROCESSO_ID_raw.json`
    - Include: full text, metadata, extraction method
    - **CRITICAL:** Store COMPLETE contract text, not excerpts
    - Preserve all pages, all content
- **PDF Cleanup**
    - Delete PDF from `data/temp/` immediately after extraction
    - Ensures only 1 PDF exists at any time
    - Minimizes storage footprint
- **Progress Tracking**
    - Maintain `data/extraction_progress.json`
    - Track: completed, failed, pending
    - Enable resume from interruption
    - Display real-time progress

**Success Metrics:**

- 90%+ successful text extraction rate
- Maximum 1 PDF in temp/ at any time
- Total storage <2 MB for 400 contract texts
- Process 400 contracts in <2 hours
- Zero data loss on interruption (resumable)
- Full text preserved for all contracts

**Deliverables:**

- 400+ files: `data/extractions/PROCESSO_ID_raw.json`
- `data/extraction_progress.json` (resume capability)
- `logs/extraction_contracts_YYYYMMDD_HHMMSS.log`

**Data Output Example:**

json

`{
  "processo_id": "TURCAP202500477",
  "source_url": "https://transparencia.rio/...",
  "extraction_date": "2025-02-14T10:30:00",
  "extraction_method": "pymupdf",
  "fallback_used": false,
  "page_count": 12,
  "char_count": 37276,
  "word_count": 5890,
  "full_text": "PREFEITURA\nÉRIO e\nTERMO DE CONTRATO O 8,5/2025que\nentre si celebram a RIOTUR — Empresa de\nTurismo do Município do Rio de Janeiro\nS/A., como CONTRATANTE, e a\nDANIELLA FONTENELLE GONÇALVES\nLERMA SILVA 131.227.39763, para\nprestação de serviços na forma abaixo.\n\n[... COMPLETE FULL TEXT OF ALL 12 PAGES ...]",
  "metadata": {
    "pdf_size_bytes": 2048576,
    "processing_time_seconds": 2.3,
    "quality_score": "high"
  }
}`