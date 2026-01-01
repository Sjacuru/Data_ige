import os
import json
import re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

import fitz
import pandas as pd
from openai import OpenAI

AI_INTEGRATIONS_OPENAI_API_KEY = os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY")
AI_INTEGRATIONS_OPENAI_BASE_URL = os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL")

# the newest OpenAI model is "gpt-5" which was released August 7, 2025.
# do not change this unless explicitly requested by the user
openai_client = OpenAI(
    api_key=AI_INTEGRATIONS_OPENAI_API_KEY,
    base_url=AI_INTEGRATIONS_OPENAI_BASE_URL
)


def is_rate_limit_error(exception: BaseException) -> bool:
    error_msg = str(exception)
    return (
        "429" in error_msg
        or "RATELIMIT_EXCEEDED" in error_msg
        or "quota" in error_msg.lower()
        or "rate limit" in error_msg.lower()
        or (hasattr(exception, "status_code") and getattr(exception, "status_code", None) == 429)
    )


def extract_text_from_pdf(pdf_path: str) -> dict:
    """Extract text from a PDF file using PyMuPDF."""
    try:
        doc = fitz.open(pdf_path)
        pages = []
        full_text = ""
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text("text")
            pages.append({
                "page_number": page_num + 1,
                "text": text
            })
            full_text += text + "\n\n"
        
        doc.close()
        
        return {
            "success": True,
            "file_path": pdf_path,
            "file_name": Path(pdf_path).name,
            "total_pages": len(pages),
            "pages": pages,
            "full_text": full_text.strip()
        }
    except Exception as e:
        return {
            "success": False,
            "file_path": pdf_path,
            "file_name": Path(pdf_path).name,
            "error": str(e)
        }


def extract_paragraphs(text: str) -> list:
    """Extract paragraphs from text for later analysis."""
    paragraphs = re.split(r'\n\s*\n', text)
    cleaned = []
    for p in paragraphs:
        cleaned_p = ' '.join(p.split())
        if len(cleaned_p) > 20:
            cleaned.append(cleaned_p)
    return cleaned


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=2, max=64),
    retry=retry_if_exception(is_rate_limit_error),
    reraise=True
)
def analyze_contract_with_ai(text: str, processo_id: str = "") -> dict:
    """Use OpenAI to extract structured contract information."""
    
    truncated_text = text[:15000] if len(text) > 15000 else text
    
    prompt = f"""Analise o seguinte texto de contrato brasileiro e extraia as informações estruturadas em formato JSON.

TEXTO DO CONTRATO:
{truncated_text}

Extraia as seguintes informações (use null se não encontrar):
1. "valor_contrato": Valor total do contrato (string com o valor monetário)
2. "moeda": Moeda do contrato (ex: "BRL", "USD")
3. "data_inicio": Data de início do contrato (formato YYYY-MM-DD se possível)
4. "data_fim": Data de término/vigência (formato YYYY-MM-DD se possível)
5. "vigencia_meses": Período de vigência em meses (número)
6. "contratante": Nome da parte contratante
7. "contratante_cnpj": CNPJ do contratante
8. "contratada": Nome da parte contratada
9. "contratada_cnpj": CNPJ da contratada
10. "objeto": Descrição do objeto/finalidade do contrato (resumo)
11. "clausulas_principais": Lista das principais cláusulas identificadas (array de strings com resumos)
12. "tipo_contrato": Tipo do contrato (ex: "Prestação de Serviços", "Fornecimento", "Obra", etc.)
13. "modalidade_licitacao": Modalidade de licitação se aplicável
14. "numero_contrato": Número/identificador do contrato

Retorne APENAS o JSON válido, sem explicações adicionais."""

    # the newest OpenAI model is "gpt-5" which was released August 7, 2025.
    # do not change this unless explicitly requested by the user
    response = openai_client.chat.completions.create(
        model="gpt-5",
        messages=[
            {"role": "system", "content": "Você é um especialista em análise de contratos públicos brasileiros. Extraia informações estruturadas de contratos com precisão."},
            {"role": "user", "content": prompt}
        ],
        response_format={"type": "json_object"},
        max_completion_tokens=4096
    )
    
    try:
        result = json.loads(response.choices[0].message.content or "{}")
    except json.JSONDecodeError:
        result = {"error": "Failed to parse AI response"}
    
    result["processo_id"] = processo_id
    return result


def process_single_contract(pdf_path: str, processo_id: str = "") -> dict:
    """Process a single contract PDF and extract all information."""
    
    extraction = extract_text_from_pdf(pdf_path)
    
    if not extraction["success"]:
        return {
            "success": False,
            "file_name": extraction["file_name"],
            "processo_id": processo_id,
            "error": extraction.get("error", "Unknown error")
        }
    
    paragraphs = extract_paragraphs(extraction["full_text"])
    
    ai_error = None
    try:
        ai_analysis = analyze_contract_with_ai(extraction["full_text"], processo_id)
        if "error" in ai_analysis and ai_analysis["error"]:
            ai_error = ai_analysis["error"]
    except Exception as e:
        ai_analysis = {"error": str(e), "processo_id": processo_id}
        ai_error = str(e)

    return {
        "success": ai_error is None,
        "file_name": extraction["file_name"],
        "file_path": extraction["file_path"],
        "processo_id": processo_id,
        "total_pages": extraction["total_pages"],
        "full_text": extraction["full_text"],
        "paragraphs": paragraphs,
        "paragraph_count": len(paragraphs),
        "extracted_data": ai_analysis
    }


def load_analysis_summary(csv_path: str = "data/analysis_summary.csv") -> pd.DataFrame:
    """Load the analysis summary CSV file."""
    try:
        df = pd.read_csv(csv_path)
        return df
    except FileNotFoundError:
        return pd.DataFrame()
    except Exception as e:
        print(f"Error loading CSV: {e}")
        return pd.DataFrame()


def find_processo_id_for_file(file_name: str, summary_df: pd.DataFrame) -> str:
    """Try to match a PDF file name with a Processo ID from the summary."""
    if summary_df.empty:
        return ""
    
    file_stem = Path(file_name).stem.upper()
    
    if "Processo" in summary_df.columns:
        for _, row in summary_df.iterrows():
            processo = str(row.get("Processo", "")).upper()
            if processo and (processo in file_stem or file_stem in processo):
                return row.get("Processo", "")
    
    return ""


def process_all_contracts(
    pdf_folder: str = "data/downloads/processos", # Hardcoded path to match app.py change
    csv_path: str = "data/analysis_summary.csv", # Hardcoded path to match app.py change
    max_workers: int = 2,
    progress_callback=None
) -> list:
    """Process all contracts in the folder with progress tracking."""
    
    pdf_folder = Path(pdf_folder)
    if not pdf_folder.exists():
        return []
    
    pdf_files = list(pdf_folder.glob("*.pdf"))
    if not pdf_files:
        return []
    
    summary_df = load_analysis_summary(csv_path)
    
    results = []
    total = len(pdf_files)
    
    for i, pdf_path in enumerate(pdf_files):
        processo_id = find_processo_id_for_file(pdf_path.name, summary_df)
        result = process_single_contract(str(pdf_path), processo_id)
        results.append(result)
        
        if progress_callback:
            progress_callback(i + 1, total, pdf_path.name)
    
    return results


def export_to_excel(results: list, output_path: str = "data/extractions/contract_data.xlsx") -> str:
    """Export extracted data to Excel format."""
    
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    
    rows = []
    for r in results:
        if not r.get("success"):
            error_msg = r.get("error") or r.get("ai_error") or "Unknown error"
            rows.append({
                "Arquivo": r.get("file_name", ""),
                "Processo_ID": r.get("processo_id", ""),
                "Status": "Erro",
                "Erro": error_msg,
            })
            continue
        
        data = r.get("extracted_data", {})
        rows.append({
            "Arquivo": r.get("file_name", ""),
            "Processo_ID": r.get("processo_id", ""),
            "Status": "Sucesso",
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
            "Total_Paginas": r.get("total_pages"),
            "Total_Paragrafos": r.get("paragraph_count"),
        })
    
    df = pd.DataFrame(rows)
    df.to_excel(output_path, index=False, engine='openpyxl')
    
    return output_path


def export_to_json(results: list, output_path: str = "data/extractions/contract_data.json") -> str:
    """Export full extracted data to JSON format."""
    
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    
    export_data = []
    for r in results:
        error_msg = None
        if not r.get("success"):
            error_msg = r.get("error") or r.get("ai_error") or "Unknown error"
        export_data.append({
            "file_name": r.get("file_name"),
            "processo_id": r.get("processo_id"),
            "success": r.get("success"),
            "total_pages": r.get("total_pages"),
            "paragraph_count": r.get("paragraph_count"),
            "paragraphs": r.get("paragraphs", []),
            "extracted_data": r.get("extracted_data", {}),
            "error": error_msg
        })
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(export_data, f, ensure_ascii=False, indent=2)
    
    return output_path


def get_folder_stats(pdf_folder: str = "data/downloads/processos") -> dict: # Hardcoded path to match app.py change
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
