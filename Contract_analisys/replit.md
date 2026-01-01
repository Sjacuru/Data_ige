# Contract Analyzer - Processo.rio

## Overview
A Streamlit-based contract analysis system that extracts structured data from processo.rio PDF contracts using AI-enhanced text parsing.

## Project Structure
```
├── app.py                    # Main Streamlit dashboard
├── contract_extractor.py     # Contract extraction module with AI parsing
├── data/
│   ├── analysis_summary.csv  # List of processes and companies
│   ├── downloads/
│   │   └── processos/        # Downloaded PDFs (contracts)
│   └── extractions/          # Output Excel and JSON files
```

## Features
- PDF text extraction using PyMuPDF
- AI-powered contract data extraction (via Replit AI Integrations for OpenAI)
- Extracts: contract value, validity dates, parties, object/purpose, clauses
- Full paragraph extraction for later analysis
- Cross-references with analysis_summary.csv using Processo ID
- Dual-format export: Excel (.xlsx) + JSON
- Batch processing with progress tracking

## How to Use
1. Place PDF contracts in `data/downloads/processos/`
2. Ensure `data/analysis_summary.csv` has your process data
3. Run the app and go to "Extract Data" tab
4. Click "Start Extraction" to process all PDFs
5. View results in "Results" tab
6. Export to Excel/JSON in "Export" tab

## Running the App
```bash
streamlit run app.py --server.port 5000
```

## Dependencies
- streamlit
- pymupdf (fitz)
- pandas
- openpyxl
- openai (via AI Integrations)
- tenacity

## AI Integration
Uses Replit AI Integrations for OpenAI access (gpt-5 model). No API key required - charges are billed to your Replit credits.
