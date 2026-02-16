# TCMRio Contract Analysis Dashboard

## Overview
A Streamlit-based dashboard for extracting and analyzing Brazilian municipal contracts. The system uses AI (Groq/LLaMA) for structured data extraction from PDFs.

## Project Structure
- `app.py` - Main Streamlit dashboard
- `Contract_analisys/` - Contract extraction and analysis modules
  - `contract_extractor.py` - PDF text extraction with AI analysis
  - `text_preprocessor.py` - OCR text preprocessing
- `conformity/` - Conformity checking module
- `src/` - Core scraping and parsing utilities
- `data/` - Data directories for PDFs, extractions, and outputs
- `config.py` - Central configuration

## Running the App
The Streamlit dashboard runs on port 5000:
```
streamlit run app.py --server.port=5000 --server.address=0.0.0.0
```

## Dependencies
- Python 3.11
- Streamlit for the web interface
- PyMuPDF (fitz) for PDF processing
- Tesseract OCR for scanned documents
- langchain-groq for AI analysis

## Environment Variables
- `GROQ_API_KEY` - Required for AI-powered contract analysis
- `FILTER_YEAR` - Optional year filter for contracts

## Features
- Single file or batch PDF processing
- OCR support for scanned documents
- AI-powered structured data extraction
- Conformity checking against official publications
- Export to Excel/JSON