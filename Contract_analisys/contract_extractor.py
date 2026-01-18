
"""
Contract Extractor v2.0
======================
Extracts and analyzes contracts using AI.

Components:
- PDF text extraction (PyMuPDF)
- AI-powered structured data extraction (Groq/LLaMA)
- Cross-reference with analysis_summary.csv
- Risk flag identification
- Export to Excel/JSON
"""
import fitz  # PyMuPDF
import pytesseract
from PIL import Image
import io

from logging import exception
import os
import json
import re
import sys
from pathlib import Path 
from typing import Optional, Callable
from datetime import datetime

from concurrent.futures import ThreadPoolExecutor, as_completed # remove unused concurrent.futures imports

from pdf2image import convert_from_path
import pandas as pd

from langchain_groq import ChatGroq

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

from dotenv import load_dotenv, find_dotenv

try:
    from .text_preprocessor import preprocess_contract_text
except (ImportError, ValueError):
    try:
        from text_preprocessor import preprocess_contract_text
    except ImportError:
        from Contract_analisys.text_preprocessor import preprocess_contract_text

import platform

import logging

# Streamlit secrets support
try:
    import streamlit as st
    HAS_STREAMLIT = True
except ImportError:
    HAS_STREAMLIT = False

def get_secret(key, default=None):
    if HAS_STREAMLIT:
        try:
            return st.secrets.get(key, os.getenv(key, default))
        except:
            pass
    return os.getenv(key, default)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================
# CONFIGURATION
# ============================================================

CONFORMITY_ENABLED = True  # Set to False to disable conformity checks

TESSERACT_PATH = get_secret("TESSERACT_PATH", r"C:\Users\sjacu\AppData\Local\Programs\Tesseract-OCR\tesseract.exe" if platform.system() == "Windows" else "tesseract")
TESSDATA_DIR = get_secret("TESSDATA_PREFIX", r"C:\Users\sjacu\AppData\Local\Programs\Tesseract-OCR\tessdata" if platform.system() == "Windows" else None)
POPPLER_PATH = get_secret("POPPLER_PATH", r"C:\Users\sjacu\anaconda3\envs\MSE800_Salim\Library\bin" if platform.system() == "Windows" else None)

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env") 

GROQ_API_KEY = get_secret("GROQ_API_KEY") 
if not GROQ_API_KEY:
    logger.warning("⚠️ GROQ_API_KEY not found in environment variables!")


MODEL_NAME = "llama-3.3-70b-versatile"
if GROQ_API_KEY:
    model = ChatGroq(model_name=MODEL_NAME, 
                      temperature=0.3, 
                      max_tokens=2048,
                      api_key=GROQ_API_KEY 
                      )
else:
    model = None

pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH
if TESSDATA_DIR:
    os.environ["TESSDATA_PREFIX"] = TESSDATA_DIR

# Check if Tesseract is available
TESSERACT_FOUND = True
if platform.system() == "Windows":
    if not os.path.exists(TESSERACT_PATH):
        TESSERACT_FOUND = False
        logger.warning(f"Tesseract not found at {TESSERACT_PATH}")
else:
    import shutil
    if not shutil.which("tesseract"):
        TESSERACT_FOUND = False
        logger.warning("Tesseract not found in PATH")

EXTRACTOR_LOADED = (model is not None) and TESSERACT_FOUND

# Risk keywords to flag in contracts
# ============================================================
# CONTRACT TYPE IDENTIFICATION (replaces RISK_KEYWORDS)
# ============================================================

TYPES_KEYWORDS = {
    "prestacao_servicos": [
        "prestação de serviços", "serviços continuados", "mão de obra",
        "terceirização", "outsourcing", "serviços técnicos"
    ],
    "fornecimento": [
        "fornecimento", "aquisição", "compra", "material de consumo",
        "equipamentos", "bens permanentes", "material permanente"
    ],
    "obras": [
        "obra", "construção", "reforma", "edificação", "infraestrutura",
        "engenharia civil", "projeto executivo"
    ],
    "locacao": [
        "locação", "aluguel", "arrendamento", "cessão de uso",
        "comodato", "imóvel"
    ],
    "consultoria": [
        "consultoria", "assessoria", "parecer técnico", "estudo",
        "diagnóstico", "auditoria"
    ],
    "tecnologia": [
        "software", "sistema", "licença", "tecnologia da informação",
        "TI", "suporte técnico", "manutenção de sistemas"
    ],
    "saude": [
        "saúde", "medicamento", "insumo hospitalar", "equipamento médico",
        "serviço de saúde", "atendimento médico"
    ],
    "educacao": [
        "educação", "ensino", "capacitação", "treinamento",
        "material didático", "escola"
    ]
}

def identify_contract_types(text: str) -> dict:
    """
    Identify contract types based on keywords in the text.
    
    Args:
        text: Full contract text
        
    Returns:
        dict with identified types and confidence
    """
    text_lower = text.lower()
    found_types = {}
    
    for type_name, keywords in TYPES_KEYWORDS.items():
        matches = []
        for keyword in keywords:
            count = text_lower.count(keyword)
            if count > 0:
                matches.append({"keyword": keyword, "count": count})
        
        if matches:
            total_matches = sum(m["count"] for m in matches)
            found_types[type_name] = {
                "matches": matches,
                "total_count": total_matches
            }
    
    # Determine primary type (most matches)
    primary_type = None
    max_count = 0
    
    for type_name, data in found_types.items():
        if data["total_count"] > max_count:
            max_count = data["total_count"]
            primary_type = type_name
    
    return {
        "primary_type": primary_type.replace("_", " ").title() if primary_type else "Não identificado",
        "types_found": list(found_types.keys()),
        "confidence": "high" if max_count > 5 else "medium" if max_count > 2 else "low",
        "details": found_types
    }

# ============================================================
# HELPER FUNCTIONS
# ============================================================



def is_rate_limit_error(exception: BaseException) -> bool:
    """Return True if the exception indicates a rate limit error."""
    error_msg = str(exception).lower()

    keywords = (
        "429",
        "rate limit",
        "ratelimit",
        "quota",
        "too many requests",
        "rate_limit_exceeded",
    )

    if any(k in error_msg for k in keywords):
        return True

    status_code = getattr(exception, "status_code", None)
    return status_code == 429


def extract_json_from_response(text: str) -> dict:
    """
    Extract JSON from AI response, handling markdown code blocks.
    
    Handles formats like:
    - Pure JSON: {"key": "value"}
    - Markdown: ```json\n{"key": "value"}\n```
    - Mixed text with JSON embedded
    """
    if not text:
        return {}
    
    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    
    # Try to extract from markdown code block
    patterns = [
        r'```json\s*([\s\S]*?)\s*```',  # ```json ... ```
        r'```\s*([\s\S]*?)\s*```',       # ``` ... ```
        r'\{[\s\S]*\}',                   # Raw JSON object
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            try:
                json_str = match.group(1) if '```' in pattern else match.group(0)
                return json.loads(json_str)
            except (json.JSONDecodeError, IndexError):
                continue
    
    return {"parse_error": "Could not extract valid JSON from response"}


def identify_risk_flags(text: str) -> dict:
    """
    Identify risk flags in contract text.
    
    Returns:
        dict with risk level and found keywords
    """
    text_lower = text.lower()
    found_flags = {"high": [], "medium": [], "low": []}

    for level, keywords in TYPES_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text_lower:
                found_flags[level].append(keyword)
    
    # Determine overall risk level
    if found_flags["high"]:
        overall_risk = "high"
    elif found_flags["medium"]:
        overall_risk = "medium"
    elif found_flags["low"]:
        overall_risk = "low"
    else:
        overall_risk = "none"
    
    total_flags = sum(len(v) for v in found_flags.values())
    
    return {
        "risk_level": overall_risk,
        "total_flags": total_flags,
        "flags_detail": found_flags
    }

# ============================================================
# PDF EXTRACTION
# ============================================================

def extract_paragraphs(text: str, min_length: int = 20) -> list:
    """
    Extract clean paragraphs from text.
    
    Args:
        text: Raw text from PDF
        min_length: Minimum paragraph length to include
        
    Returns:
        List of cleaned paragraph strings
    """
    paragraphs = re.split(r'\n\s*\n', text)
    cleaned = []

    for p in paragraphs:
        # Normalize whitespace
        cleaned_p = ' '.join(p.split())
        if len(cleaned_p) > min_length:
            cleaned.append(cleaned_p)
    return cleaned

def setup_ocr():
    """
    Force and validate Tesseract OCR.
    Must be called before any OCR operation.
    """
    global TESSERACT_FOUND
    
    # Try to find tesseract
    tesseract_cmd = TESSERACT_PATH
    
    if platform.system() == "Windows":
        if not os.path.exists(tesseract_cmd):
            TESSERACT_FOUND = False
            return False
    else:
        import shutil
        if not shutil.which(tesseract_cmd):
            # Try common paths as fallback
            common_paths = ["/usr/bin/tesseract", "/usr/local/bin/tesseract", "/Users/sjacu/AppData/Local/ProgramsTesseract-OCR"]
            found = False
            for p in common_paths:
                if os.path.exists(p):
                    tesseract_cmd = p
                    found = True
                    break
            if not found:
                TESSERACT_FOUND = False
                return False
    
    pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    # Validate execution (fast, no OCR yet)
    try:
        pytesseract.get_tesseract_version()
        TESSERACT_FOUND = True
        return True
    except Exception as e:
        logger.warning(f"Tesseract OCR not usable: {e}")
        TESSERACT_FOUND = False
        return False

def extract_text_from_pdf(pdf_path: str) -> dict:
    try:
        # Don't fail here if OCR is missing, just try native extraction
        setup_ocr()

        doc = fitz.open(pdf_path)
        native_text = ""
        char_count_per_page = []

        for page in doc:
            text = page.get_text("text")
            native_text += text
            char_count_per_page.append(len(text.strip()))

        doc.close()

        avg_chars = sum(char_count_per_page) / max(len(char_count_per_page), 1)

        # Decide extraction method
        if avg_chars < 300:
            if TESSERACT_FOUND:
                logging.info("🧠 Low text density detected → switching to full OCR (pdf2image)")
                raw_text = extract_text_with_pdf2image(pdf_path)
                source = "ocr_pdf2image"
            else:
                logging.warning("⚠️ Low text density but Tesseract not found! Using native text anyway.")
                raw_text = native_text
                source = "native_insufficient"
        else:
            logging.info("📄 Native text layer sufficient")
            raw_text = native_text
            source = "native"

        # ═══════════════════════════════════════════════════════
        # NEW: Preprocess the text (clean, structure)
        # ═══════════════════════════════════════════════════════
        preprocessing = preprocess_contract_text(raw_text)
        logging.info(f"📝 Preprocessing: {preprocessing.original_length:,} → {preprocessing.final_length:,} chars ({preprocessing.reduction_percent:.1f}% reduction)")
        
        # Use preprocessed text
        full_text = preprocessing.structured_text
        paragraphs = extract_paragraphs(full_text)

        return {
            "success": True,
            "file_path": pdf_path,
            "file_name": Path(pdf_path).name,
            "total_pages": len(char_count_per_page),
            "total_chars": len(full_text),  # Now reflects cleaned text
            "full_text": full_text,          # Now preprocessed
            "raw_text": raw_text,            # NEW: Keep original for debugging
            "paragraphs": paragraphs,
            "paragraph_count": len(paragraphs),
            "extraction_source": source,
            # NEW: Preprocessing metadata (optional, for debugging)
            "preprocessing": {
                "original_chars": preprocessing.original_length,
                "final_chars": preprocessing.final_length,
                "reduction_percent": preprocessing.reduction_percent,
                "sections_found": len(preprocessing.sections_found),
                "metadata_removed": len(preprocessing.metadata_removed)
            }
        }

    except Exception as e:
        return {
            "success": False,
            "file_path": pdf_path,
            "file_name": Path(pdf_path).name,
            "error": str(e),
            "error_type": type(e).__name__
        }

def safe_ocr(img):
    try:
        return pytesseract.image_to_string(
            img,
            lang="por",
            config="--psm 6 --oem 3"
        )
    except pytesseract.TesseractError:
        # fallback to English if por is not available
        return pytesseract.image_to_string(
            img,
            lang="eng",
            config="--psm 6 --oem 3"
        )

def extract_text_with_pdf2image(pdf_path: str) -> str:
    """
    OCR the entire PDF using pdf2image + Tesseract.
    Returns full extracted text.
    """
    pages = convert_from_path(
        pdf_path,
        dpi=300,
        poppler_path=POPPLER_PATH
    )

    full_text = []

    for i, img in enumerate(pages, start=1):
        text = safe_ocr(img)
        full_text.append(text)

    return "\n\n".join(full_text)

def get_conformity_checker():
    """Lazy import of conformity module."""
    try:
        from conformity.integration import check_publication_conformity
        return check_publication_conformity
    except ImportError as e:
        logger.warning(f"⚠️ Conformity module not available: {e}")
        return None

# ============================================================
# AI ANALYSIS
# ============================================================

@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=2, min=4, max=120),
    retry=retry_if_exception(is_rate_limit_error),
    reraise=True
)

def analyze_contract_with_ai(text: str, processo_id: str = "") -> dict:
    """
    Use AI to extract structured contract information.
    
    Args:
        text: Full contract text
        processo_id: Optional process identifier
        
    Returns:
        dict with extracted contract fields
    """
    # Truncate to avoid token limits (adjust based on model)
    
    max_chars = 12000
    truncated_text = text[:max_chars] if len(text) > max_chars else text
    was_truncated = len(text) > max_chars

    prompt = f"""Analise o seguinte texto de contrato e extraia as informações estruturadas
    em formato JSON.

IMPORTANTE:
- Retorne APENAS um objeto JSON válido, sem texto adicional
- Use null para campos não encontrados
- Datas no formato DD-MM-YYYY
- Valores monetários como string (ex: "R$ 1.234,56")
    
TEXTO DO CONTRATO:
{truncated_text}
Extraia este JSON:
{{
  "valor_contrato": null,  se não encontrar o valor total do contrato (string com o valor monetário) geralmente no início do contrato 
  "moeda": null, se não encontrar a moeda do contrato (ex: "BRL", "USD")
  "data_inicio": null, se não encontrar a data de início do contrato (formato DD-MM-YYYY)
  "data_fim": null, se não encontrar a Data de término/vigência calcule com base na vigência adicionando o período de vigência à data de início - (formato DD-MM-YYYY se possível), pois a data de fim pode não estar explícita no contrato. 
  "vigencia_meses": null, se não encontrar o período de vigência em meses (número) geralmente expresso como "vigência de XX meses" ou similar
  "contratante": null, se não encontrar o nome da parte contratante (geralmente um órgão público municipal, estadual ou federal)
  "contratante_cnpj": null, se não encontrar o CNPJ da parte contratante
  "contratada": null, se não encontrar o nome da parte contratada
  "contratada_cnpj": null, se não encontrar o CNPJ da parte contratada
  "objeto": null, se não encontrar a descrição do objeto/finalidade do contrato
  "clausulas_principais": [], se não encontrar as principais cláusulas do contrato (array de strings com resumos)
  "tipo_contrato": null, se não encontrar o tipo do contrato (ex: "Prestação de Serviços", "Fornecimento", "Obra", etc.)
  "modalidade_licitacao": null, se não encontrar a modalidade de licitação se aplicável
  "numero_contrato": null, se não encontrar o número/identificador do contrato
  "processo_administrativo": null, se não encontrar o número do processo administrativo relacionado ao contrato (formto: XXX-XXX-0000/00000 or 0000/###/000000 or ###/000000)
  "numero_processo": null se não encontrar o número do processo relacionado ao contrato (string), geralmente encontrado no cabeçalho ou no início do contrato
  "foi_truncado": {"true" if was_truncated else "false"}
}}"""

    try:
        response = model.invoke(prompt)

        content = (
            response.content
            if hasattr(response, "content")
            else str(response)
        )

        extracted = extract_json_from_response(content)
        
        if not extracted or not isinstance(extracted, dict):
            return {
                "error": "AI returned invalid or empty JSON",
                "raw_response": content[:500]
            }
        
    except Exception as e:
        result = {
            "error": str(e),
            "error_type": type(e).__name__
        }
    
    # Add metadata
    extracted["processo_id"] = processo_id
    extracted["text_truncated"] = was_truncated
    extracted["analysis_timestamp"] = datetime.now().isoformat()

    return extracted

# ============================================================
# CONTRACT PROCESSING
# ============================================================

def run_conformity_check(
    extracted_data: dict,
    processo_id: str = "",
    headless: bool = True
) -> Optional[dict]:
    """
    Run publication conformity check for extracted contract.
    """
    if not CONFORMITY_ENABLED:
        logging.info("⏭️ Conformity check disabled")
        return None
    
    check_publication = get_conformity_checker()
    if not check_publication:
        logger.warning("⚠️ Conformity checker not available")
        return None
    
    # Build contract data dict for conformity check
    # PRIORITY: Use processo_id (from CSV/Filename) if available, otherwise fallback to AI
    processo = processo_id or extracted_data.get("processo_administrativo") or extracted_data.get("numero_processo")
    
    contract_data = {
        "processo_id": processo_id,
        "processo_administrativo": extracted_data.get("processo_administrativo"),
        "numero_processo": extracted_data.get("numero_processo"),
        "numero_contrato": extracted_data.get("numero_contrato"),
        "valor_contrato": extracted_data.get("valor_contrato"),
        "data_assinatura": extracted_data.get("data_assinatura"),
        "data_inicio": extracted_data.get("data_inicio"),
        "data_fim": extracted_data.get("data_fim"),
        "contratante": extracted_data.get("contratante"),
        "contratada": extracted_data.get("contratada"),
        "objeto": extracted_data.get("objeto"),
    }
    
    if not processo:
        logger.warning("⚠️ No processo number found - skipping conformity check")
        return None
    
    logging.info(f"\n🔍 Running conformity check for {processo}...")
    
    try:
        result = check_publication(
            contract_data=contract_data,
            processo=processo,
            headless=headless
        )
        
        return result.to_dict()
        
    except Exception as e:
        logger.error(f"❌ Conformity check failed: {e}")
        return {"error": str(e), "processo": processo}

def process_single_contract(pdf_path: str, processo_id: str = "") -> dict:
    """
    Process a single contract PDF through the full pipeline.
    
    Pipeline:
    1. Extract text from PDF
    2. Parse into paragraphs
    3. Identify contract types
    4. AI analysis for structured data
    5. Validate extracted data
    6. NEW: Conformity check (publication verification)
    
    Args:
        pdf_path: Path to the PDF file
        processo_id: Optional process identifier
        
    Returns:
        dict with all extraction and analysis results
    """
    # Step 1: Extract text from PDF
    extraction = extract_text_from_pdf(pdf_path)
    
    if not extraction["success"]:
        return {
            "success": False,
            "file_name": extraction.get("file_name", Path(pdf_path).name),
            "file_path": pdf_path,
            "processo_id": processo_id,
            "error": extraction.get("error", "Unknown extraction error"),
            "error_stage": "pdf_extraction",
            "conformity": None  # NEW
        }
    
    # Step 2: Get paragraphs
    paragraphs = extraction.get("paragraphs", [])
    
    # Step 3: Identify contract types
    type_analysis = identify_contract_types(extraction["full_text"])

    # Step 4: AI analysis
    ai_error = None
    ai_analysis = None

    try:
        ai_analysis = analyze_contract_with_ai(extraction["full_text"], processo_id)
        
        if not ai_analysis or not isinstance(ai_analysis, dict):
            ai_error = "AI returned empty or invalid data"
            ai_analysis = {"error": ai_error}
        elif "error" in ai_analysis:
            ai_error = ai_analysis.get("error")
        else:
            # Step 5: Check for required fields
            required_fields = ["valor_contrato", "contratada", "objeto"]
            missing = [f for f in required_fields if not ai_analysis.get(f)]
            if missing:
                ai_analysis["missing_fields"] = missing
                ai_analysis["extraction_warning"] = f"Missing fields: {missing}"
                
    except Exception as e:
        ai_error = str(e)
        ai_analysis = {
            "error": str(e),
            "error_type": type(e).__name__,
            "processo_id": processo_id
        }
    
    # Build result
    result = {
        "success": ai_error is None,
        "file_name": extraction["file_name"],
        "file_path": extraction["file_path"],
        "processo_id": processo_id,
        "total_pages": extraction.get("total_pages", 0),
        "total_chars": extraction.get("total_chars", 0),
        "full_text": extraction.get("full_text", ""),
        "paragraphs": paragraphs,
        "paragraph_count": len(paragraphs),
        "extraction_source": extraction.get("extraction_source", "unknown"),
        "type_analysis": type_analysis,
        "extracted_data": ai_analysis,
        "error": ai_error,
        "error_stage": "ai_analysis" if ai_error else None
    }
    
    # ================================================================
    # Step 6: NEW - Run conformity check if extraction was successful
    # ================================================================
    if result["success"] and ai_analysis and not ai_analysis.get("error"):
        logging.info("\n" + "=" * 50)
        logging.info("📋 CONFORMITY CHECK")
        logging.info("=" * 50)
        
        conformity_result = run_conformity_check(
            extracted_data=ai_analysis,
            processo_id=processo_id,
            headless=True
        )
        
        result["conformity"] = conformity_result
        
        if conformity_result and not conformity_result.get("error"):
            status = conformity_result.get("overall_status", "UNKNOWN")
            score = conformity_result.get("conformity_score", 0)
            logging.info(f"   Status: {status}")
            logging.info(f"   Score: {score}%")
    else:
        result["conformity"] = None
    
    return result

# ============================================================
# CSV CROSS-REFERENCE
# ============================================================

def load_analysis_summary(csv_path: str) -> pd.DataFrame:
    """Load the analysis summary CSV file."""
    try:
        df = pd.read_csv(csv_path, dtype=str)
        return df
    except FileNotFoundError:
        logger.warning(f"⚠️ CSV not found: {csv_path}")
        return pd.DataFrame()
    except Exception as e:
        logger.error(f"Error loading CSV: {e}")
        return pd.DataFrame()


def find_processo_id_for_file(file_name: str, summary_df: pd.DataFrame) -> str:
    """
    Match a PDF file name with data from the analysis summary.
    
    Returns:
        dict with matched processo_id and additional data
    """
    result = {
        "processo_id": "",
        "empresa": "",
        "valor_csv": "",
        "risco_csv": "",
        "matched": False
    }

    if summary_df.empty:
        return result
    
    file_stem = Path(file_name).stem.upper()
    file_stem_clean = re.sub(r'[.\-/\s]', '', file_stem)
    
    # Try to match by Processo column
    if "Processo" in summary_df.columns:
        for _, row in summary_df.iterrows():
            processo = str(row.get("Processo", "")).upper()
            processo_clean = re.sub(r'[.\-/\s]', '', processo)
            
            if processo and (processo in file_stem or file_stem in processo or 
                            processo_clean in file_stem_clean or file_stem_clean in processo_clean):
                result.update({
                    "processo_id": row.get("Processo", ""),
                    "empresa": row.get("Empresa", ""),
                    "valor_csv": row.get("Total Contratado", ""),
                    "risco_csv": row.get("Nível de Risco", ""),
                    "matched": True
                })
                break



    # Also try matching by ID (CNPJ)
    if not result["matched"] and "ID" in summary_df.columns:
        for _, row in summary_df.iterrows():
            cnpj = str(row.get("ID", "")).replace(".", "").replace("/", "").replace("-", "")
            if cnpj and cnpj in file_stem.replace(".", "").replace("/", "").replace("-", ""):
                result.update({
                    "processo_id": row.get("Processo", ""),
                    "empresa": row.get("Empresa", ""),
                    "valor_csv": row.get("Total Contratado", ""),
                    "risco_csv": row.get("Nível de Risco", ""),
                    "matched": True
                })
                break

    return result

# ============================================================
# BATCH PROCESSING
# ============================================================

def process_all_contracts(
    pdf_folder: str,
    csv_path: str,
    progress_callback: Optional[Callable] = None
) -> list:
    
    """
    Process all contracts in a folder with progress tracking.
    
    Args:
        pdf_folder: Path to folder containing PDFs
        csv_path: Path to analysis_summary.csv
        progress_callback: Optional function(current, total, filename)
        
    Returns:
        List of processing results
    """
    
    pdf_folder = Path(pdf_folder)

    if not pdf_folder.exists():
        logger.error(f"❌ Folder not found: {pdf_folder}")
        return []
    
    pdf_files = sorted(pdf_folder.glob("*.pdf"))

    if not pdf_files:
        logger.warning(f"⚠️ No PDF files found in: {pdf_folder}")
        return []
    
    # Load CSV for cross-reference
    summary_df = load_analysis_summary(csv_path)
    logging.info(f"📊 Loaded {len(summary_df)} records from CSV")
    
    results = []
    total = len(pdf_files)
    
    for i, pdf_path in enumerate(pdf_files):
        # Find matching data from CSV
        match_data = find_processo_id_for_file(pdf_path.name, summary_df)
        processo_id = match_data["processo_id"]

        # Process the contract
        result = process_single_contract(str(pdf_path), processo_id)
        
        # Add cross-reference data
        result["csv_match"] = match_data
        
        results.append(result)
        
        # Progress callback
        if progress_callback:
            progress_callback(i + 1, total, pdf_path.name)
        else:
            status = "✅" if result["success"] else "❌"
            logging.info(f"{status} [{i+1}/{total}] {pdf_path.name}")

    return results

# ============================================================
# EXPORT FUNCTIONS
# ============================================================

def export_to_excel(results: list, output_path: str) -> str:
    """Export extracted data to Excel format."""
    
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    
    rows = []
    for r in results:
        data = r.get("extracted_data", {})
        risk = r.get("type_analysis", {})
        csv_match = r.get("csv_match", {})
        
        row = {
            "Arquivo": r.get("file_name", ""),
            "Processo_ID": r.get("processo_id", ""),
            "Status": "Sucesso" if r.get("success") else "Erro",
            "Erro": r.get("error") if not r.get("success") else None,
            
            # AI Extracted Data
            "Valor_Contrato": data.get("valor_contrato"),
            "Moeda": data.get("moeda"),
            "Data_Inicio": data.get("data_inicio"),
            "Data_Fim": data.get("data_fim"),
            "Vigencia_Meses": data.get("vigencia_meses"),
            "Contratante": data.get("contratante"),
            "Contratante_CNPJ": data.get("contratante_cnpj"),
            "Contratada": data.get("contratada"),
            "Contratada_CNPJ": data.get("contratada_cnpj"),
            "Objeto": data.get("objeto"),
            "Tipo_Contrato": data.get("tipo_contrato"),
            "Modalidade_Licitacao": data.get("modalidade_licitacao"),
            "Numero_Contrato": data.get("numero_contrato"),
            
            # Risk Analysis
            "Nivel_Risco": risk.get("risk_level", ""),
            "Total_Flags": risk.get("total_flags", 0),
            "Flags_Alta": ", ".join(risk.get("flags_detail", {}).get("high", [])),
            "Flags_Media": ", ".join(risk.get("flags_detail", {}).get("medium", [])),
            
            # CSV Cross-reference
            "CSV_Empresa": csv_match.get("empresa", ""),
            "CSV_Valor": csv_match.get("valor_csv", ""),
            "CSV_Risco": csv_match.get("risco_csv", ""),
            "CSV_Match": "Sim" if csv_match.get("matched") else "Não",
            
            # Metadata
            "Total_Paginas": r.get("total_pages"),
            "Total_Paragrafos": r.get("paragraph_count"),

            # Conformity data (NEW)
            "Conformidade_Status": r.get("conformity", {}).get("overall_status") if r.get("conformity") else None,
            "Conformidade_Score": r.get("conformity", {}).get("conformity_score") if r.get("conformity") else None,
            "Publicado": r.get("conformity", {}).get("publication_check", {}).get("was_published") if r.get("conformity") else None,
            "Data_Publicacao": r.get("conformity", {}).get("publication_check", {}).get("publication_date") if r.get("conformity") else None,
            "Link_Publicacao": r.get("conformity", {}).get("publication_check", {}).get("download_link") if r.get("conformity") else None,
        }
        rows.append(row)
    
    df = pd.DataFrame(rows)
    df.to_excel(output_path, index=False, engine='openpyxl')
    
    logging.info(f"📁 Excel exported: {output_path}")
    return output_path


def export_to_json(results: list, output_path: str) -> str:
    """Export full extracted data to JSON format."""
    
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    
    export_data = []
    for r in results:
        # Remove full_text to reduce file size (optional)
        export_item = {k: v for k, v in r.items() if k != "full_text"}
        export_item["text_preview"] = r.get("full_text", "")[:500] + "..."
        export_data.append(export_item)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(export_data, f, ensure_ascii=False, indent=2)
    
    logging.info(f"📁 JSON exported: {output_path}")
    return output_path

# ============================================================
# UTILITY FUNCTIONS
# ============================================================

def get_folder_stats(pdf_folder: str) -> dict: 
    """Get statistics about the PDF folder."""
    pdf_folder = Path(pdf_folder)
    
    if not pdf_folder.exists():
        return {
            "exists": False,
            "total_files": 0,
            "total_size_mb": 0
        }
    
    pdf_files = list(pdf_folder.glob("*.pdf"))
    total_size = sum(f.stat().st_size for f in pdf_files) / (1024 * 1024)
    
    return {
        "exists": True,
        "total_files": len(pdf_files),
        "total_size_mb": round(total_size, 2),
        "files": [f.name for f in pdf_files]
    }


# ============================================================
# MAIN ENTRY POINT (for testing)
# ============================================================

if __name__ == "__main__":
    # Test configuration
    PDF_FOLDER = "data/downloads/processos"
    CSV_PATH = "data/outputs/analysis_summary.csv"
    OUTPUT_DIR = "data/extractions"
    
    logging.info("=" * 60)
    logging.info("🔍 Contract Extractor v2.0")
    logging.info("=" * 60)
    
    # Check folder
    stats = get_folder_stats(PDF_FOLDER)
    logging.info(f"\n📂 Folder: {PDF_FOLDER}")
    logging.info(f"   Files: {stats['total_files']}")
    logging.info(f"   Size: {stats['total_size_mb']} MB")
    
    if stats["total_files"] == 0:
        logger.warning("\n⚠️ No PDF files to process!")
    else:
        # Process all contracts
        logging.info(f"\n🚀 Processing {stats['total_files']} contracts...")
        results = process_all_contracts(PDF_FOLDER, CSV_PATH)
        
        # Summary
        success = sum(1 for r in results if r["success"])
        logging.info(f"\n📊 Results: {success}/{len(results)} successful")
        
        # Export
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        export_to_excel(results, f"{OUTPUT_DIR}/contracts_{timestamp}.xlsx")
        export_to_json(results, f"{OUTPUT_DIR}/contracts_{timestamp}.json")
        
        logging.info("\n✅ Done!")
