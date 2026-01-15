"""
TCMRio Contract Analysis Dashboard v2.1
=======================================
Streamlit interface for contract extraction and analysis.

Features:
- Folder statistics and overview
- Single file or batch extraction
- Real-time progress tracking
- Results viewer with filtering
- Export to Excel/JSON
- Contract type identification
- 🆕 Data collection from ContasRio (scraping)
"""

import os
import pytesseract
import streamlit as st
import pandas as pd
import json
from pathlib import Path
from datetime import datetime
import subprocess
import time
import re

try:
    from Contract_analisys.contract_extractor import (
        process_single_contract,
        process_all_contracts,
        export_to_excel,
        export_to_json,
        get_folder_stats,
        load_analysis_summary,
        identify_contract_types,
        TYPES_KEYWORDS,
    )
    EXTRACTOR_LOADED = True
except ImportError as e:
    EXTRACTOR_LOADED = False
    IMPORT_ERROR = str(e)

# Conformity module
try:
    from conformity.models.conformity_result import ConformityStatus
    CONFORMITY_LOADED = True
except ImportError:
    CONFORMITY_LOADED = False
    ConformityStatus = None

# ════════════════════════════════════════════════════════════════
# 🆕 NEW IMPORTS: Scraping module
# ════════════════════════════════════════════════════════════════
try:
    from src.scraper import (
        initialize_driver,
        navigate_to_home,
        navigate_to_contracts,
        scroll_and_collect_rows,
        parse_row_data,
        close_driver
    )
    SCRAPER_LOADED = True
except ImportError as e:
    SCRAPER_LOADED = False
    SCRAPER_IMPORT_ERROR = str(e)

try:
    from scripts.download_csv import download_contracts_csv, DOWNLOAD_FOLDER
    DOWNLOAD_CSV_LOADED = True
except ImportError as e:
    DOWNLOAD_CSV_LOADED = False
    DOWNLOAD_CSV_IMPORT_ERROR = str(e)
    DOWNLOAD_FOLDER = None

# ════════════════════════════════════════════════════════════════
# 🆕 NEW IMPORTS: Download Contracts
# ════════════════════════════════════════════════════════════════
try:
    from src.document_extractor import download_processo_pdf
    DOWNLOAD_CONTRACTS_LOADED = True
except ImportError as e:
    DOWNLOAD_CONTRACTS_LOADED = False
    DOWNLOAD_CONTRACTS_ERROR = str(e)


# Check if driver is available
try:
    from core.driver import is_driver_available
    DRIVER_AVAILABLE = is_driver_available()
except ImportError:
    DRIVER_AVAILABLE = False

# ============================================================
# CONFIGURATION
# ============================================================

from config import (
    PROCESSOS_DIR,
    ANALYSIS_SUMMARY_CSV,
    EXTRACTIONS_DIR,
    FILTER_YEAR  # 🆕 Added for scraping default year
)

PDF_FOLDER = PROCESSOS_DIR
CSV_PATH = ANALYSIS_SUMMARY_CSV
OUTPUT_FOLDER = EXTRACTIONS_DIR
OUTPUT_DIR = Path("data/extractions")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 🆕 Scraping output directory
SCRAPING_OUTPUT_DIR = Path("data/outputs")
SCRAPING_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

st.set_page_config(
    page_title="Análise de Contratos - Processo.rio",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================================
# SESSION STATE INITIALIZATION
# ============================================================

@st.cache_resource
def check_tesseract():
    """Check Tesseract availability once and cache the result."""
    try:
        result = subprocess.run(
            [pytesseract.pytesseract.tesseract_cmd, "--version"],
            capture_output=True,
            text=True
        )
        return True, result.stdout.splitlines()[0]
    except Exception as e:
        return False, str(e)

# Call the cached function
tesseract_ok, tesseract_info = check_tesseract()
if tesseract_ok:
    st.success(f"Tesseract: {tesseract_info}")
else:
    st.error(f"Tesseract NOT available: {tesseract_info}")

# ════════════════════════════════════════════════════════════════
# 🆕STATE INITIALIZATION
# ════════════════════════════════════════════════════════════════

if "results" not in st.session_state:
    st.session_state.results = []
if "processing" not in st.session_state:
    st.session_state.processing = False
if "last_export" not in st.session_state:
    st.session_state.last_export = None

# ════════════════════════════════════════════════════════════════
# 🆕 NEW SESSION STATE: Scraping
# ════════════════════════════════════════════════════════════════
if "scraping_in_progress" not in st.session_state:
    st.session_state.scraping_in_progress = False
if "scraped_companies" not in st.session_state:
    st.session_state.scraped_companies = []
if "scraping_status" not in st.session_state:
    st.session_state.scraping_status = None
if "scraping_trigger" not in st.session_state:
    st.session_state.scraping_trigger = False
if "csv_download_in_progress" not in st.session_state:
    st.session_state.csv_download_in_progress = False
if "csv_download_status" not in st.session_state:
    st.session_state.csv_download_status = None
if "csv_download_trigger" not in st.session_state:
    st.session_state.csv_download_trigger = False
if "comparison_result" not in st.session_state:
    st.session_state.comparison_result = None
if "contracts_download_in_progress" not in st.session_state:
    st.session_state.contracts_download_in_progress = False
if "contracts_download_status" not in st.session_state:
    st.session_state.contracts_download_status = None
if "contracts_download_trigger" not in st.session_state:
    st.session_state.contracts_download_trigger = False

st.sidebar.markdown("### Debug paths")
st.sidebar.code(f"""
PDF_FOLDER = {PDF_FOLDER}
CSV_PATH = {CSV_PATH }
OUTPUT_FOLDER = {OUTPUT_FOLDER}
""")

# ============================================================
# HELPER FUNCTIONS
# ============================================================

def format_file_size(size_mb: float) -> str:
    """Format file size for display."""
    if size_mb < 1:
        return f"{size_mb * 1024:.0f} KB"
    return f"{size_mb:.2f} MB"


def get_status_emoji(success: bool) -> str:
    """Get status emoji based on success."""
    return "✅" if success else "❌"


def format_currency(value: str) -> str:
    """Format currency value for display."""
    if not value:
        return "N/A"
    return value


def create_results_dataframe(results: list) -> pd.DataFrame:
    """Convert results list to a DataFrame for display."""
    if not results:
        return pd.DataFrame()
    
    rows = []
    for r in results:
        data = r.get("extracted_data", {})
        types_info = r.get("type_analysis", {})
        csv_match = r.get("csv_match", {})
        conformity = r.get("conformity", {})
        
        rows.append({
            "Status": get_status_emoji(r.get("success", False)),
            "Arquivo": r.get("file_name", ""),
            "Processo": r.get("processo_id", "") or data.get("processo_administrativo", "") or "N/A",
            "Valor": format_currency(data.get("valor_contrato")),
            "Contratada": data.get("contratada", "N/A") or "N/A",
            "Tipo": data.get("tipo_contrato", "N/A") or "N/A",
            "Tipos Identificados": types_info.get("primary_type", "N/A"),
            "Conformidade": get_conformity_badge(conformity) if conformity else "⏳ Pendente",
            "Páginas": r.get("total_pages", 0),
            "CSV Match": "✅" if csv_match.get("matched") else "❌",
            "Erro": r.get("error", "") or "",
        })
    
    return pd.DataFrame(rows)


def get_conformity_badge(conformity_data: dict) -> str:
    """Get conformity status badge."""
    if not conformity_data:
        return "⏳ Pendente"
    
    if conformity_data.get("error"):
        return "⚠️ Erro"
    
    status = conformity_data.get("overall_status", "")
    
    if status == "CONFORME":
        return "✅ Conforme"
    elif status == "PARCIAL":
        return "⚠️ Parcial"
    elif status == "NÃO CONFORME":
        return "❌ Não Conforme"
    else:
        return "❓ Desconhecido"


def get_conformity_color(status: str) -> str:
    """Get color for conformity status."""
    if "CONFORME" in status and "NÃO" not in status:
        return "green"
    elif "PARCIAL" in status:
        return "orange"
    elif "NÃO CONFORME" in status:
        return "red"
    else:
        return "gray"


def render_conformity_badge(conformity_data: dict):
    """Render a conformity status badge."""
    if not conformity_data:
        st.info("⏳ Verificação de conformidade pendente")
        return
    
    if conformity_data.get("error"):
        st.warning(f"⚠️ Erro na verificação: {conformity_data.get('error')}")
        return
    
    status = conformity_data.get("overall_status", "DESCONHECIDO")
    score = conformity_data.get("conformity_score", 0)
    
    if status == "CONFORME":
        st.success(f"✅ **CONFORME** — Score: {score:.0f}%")
    elif status == "PARCIAL":
        st.warning(f"⚠️ **PARCIAL** — Score: {score:.0f}%")
    else:
        st.error(f"❌ **NÃO CONFORME** — Score: {score:.0f}%")
    
    pub_check = conformity_data.get("publication_check", {})
    if pub_check:
        if pub_check.get("was_published"):
            pub_date = pub_check.get("publication_date", "N/A")
            link = pub_check.get("download_link", "")
            
            col1, col2 = st.columns([3, 1])
            with col1:
                st.caption(f"📰 Publicado em: {pub_date}")
                if pub_check.get("published_on_time"):
                    st.caption(f"✓ Dentro do prazo ({pub_check.get('days_to_publish')} dias)")
                else:
                    st.caption(f"✗ Fora do prazo ({pub_check.get('days_to_publish')} dias)")
            with col2:
                if link:
                    st.link_button("🔗 Ver D.O.", link)
        else:
            st.caption("📰 Publicação não encontrada no D.O. Rio")

def normalize_id(value):
    """
    Normalize ID/CNPJ for comparison.
    Removes dots, dashes, slashes, spaces. Keeps only alphanumeric.
    """
    if not value:
        return ""
    # Convert to string, lowercase, remove common separators
    normalized = str(value).lower().strip()
    normalized = re.sub(r'[.\-/\s]', '', normalized)
    return normalized


def find_id_column(df, candidates=None):
    """
    Find the ID/CNPJ column in a DataFrame.
    
    Args:
        df: DataFrame to search
        candidates: List of possible column names
        
    Returns:
        Column name if found, None otherwise
    """
    if candidates is None:
        candidates = [
            'ID', 'id', 'Id',
            'CNPJ', 'cnpj', 'Cnpj',
            'CPF/CNPJ', 'cpf/cnpj',
            'Favorecido', 'favorecido',
            'Código', 'codigo', 'Codigo',
            'Identificador', 'identificador'
        ]
    
    for col in candidates:
        if col in df.columns:
            return col
    
    # Fallback: first column that looks like an ID
    for col in df.columns:
        col_lower = col.lower()
        if any(term in col_lower for term in ['id', 'cnpj', 'cpf', 'codigo', 'favorecido']):
            return col
    
    return None

def get_processos_files():
    """Get list of processos CSV files available for download."""
    processos_dir = Path("scripts/outputs")
    if not processos_dir.exists():
        return []
    
    files = list(processos_dir.glob("processos_*.csv"))
    # Sort by modification time, newest first
    files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    return files


def read_processos_csv(filepath):
    """Read processos CSV and return list of URLs."""
    try:
        df = pd.read_csv(filepath, dtype=str)
        
        # Find URL column
        url_col = None
        for col in ['URL', 'url', 'Url', 'href', 'Link']:
            if col in df.columns:
                url_col = col
                break
        
        if not url_col:
            return [], "Coluna URL não encontrada"
        
        # Filter valid URLs
        processos = []
        for _, row in df.iterrows():
            url = row.get(url_col, "")
            if url and url.startswith("http"):
                processos.append({
                    "url": url,
                    "id": row.get("ID", ""),
                    "company": row.get("Company", ""),
                    "processo": row.get("Processo", "")
                })
        
        return processos, None
        
    except Exception as e:
        return [], str(e)


def run_contracts_download_process(processos_file: Path, headless: bool, max_downloads: int = None):
    """
    Execute the contracts download process with progress display.
    """
    from core.driver import create_driver, close_driver
    
    st.header("📥 Download de Contratos em Andamento")
    
    st.info(f"""
    📄 **Arquivo:** `{processos_file.name}`
    
    O sistema irá:
    1. Ler as URLs do arquivo CSV
    2. Acessar cada página de processo
    3. Resolver CAPTCHAs quando necessário
    4. Baixar os PDFs dos contratos
    """)
    
    # Read processos
    processos, error = read_processos_csv(processos_file)
    
    if error:
        st.error(f"Erro ao ler arquivo: {error}")
        st.session_state.contracts_download_in_progress = False
        return
    
    if not processos:
        st.warning("Nenhum processo com URL válida encontrado")
        st.session_state.contracts_download_in_progress = False
        return
    
    # Apply limit if set
    if max_downloads and max_downloads > 0:
        processos = processos[:max_downloads]
        st.caption(f"⚠️ Limitado a {max_downloads} downloads")
    
    total = len(processos)
    st.write(f"**Total de processos:** {total}")
    
    # Progress elements
    progress_bar = st.progress(0)
    status_text = st.empty()
    results_container = st.empty()
    
    # Initialize driver
    status_text.text("🚀 Iniciando navegador...")
    driver = create_driver(headless=headless)
    
    if not driver:
        st.error("Falha ao inicializar navegador")
        st.session_state.contracts_download_in_progress = False
        return
    
    # Output directory
    output_dir = Path("data/downloads/processos")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Process each URL
    results = []
    success_count = 0
    error_count = 0
    
    try:
        for i, proc in enumerate(processos):
            progress = (i + 1) / total
            progress_bar.progress(progress)
            status_text.text(f"📥 [{i+1}/{total}] Baixando: {proc['processo'][:30]}...")
            
            try:
                result = download_processo_pdf(
                    driver=driver,
                    processo_url=proc["url"],
                    output_dir=str(output_dir),
                    empresa_info={"id": proc["id"], "name": proc["company"]}
                )
                
                results.append({
                    "processo": proc["processo"],
                    "status": "✅" if result["success"] else "❌",
                    "arquivo": Path(result["pdf_path"]).name if result["pdf_path"] else "-",
                    "erro": result.get("error", "")
                })
                
                if result["success"]:
                    success_count += 1
                else:
                    error_count += 1
                    
            except Exception as e:
                error_count += 1
                results.append({
                    "processo": proc["processo"],
                    "status": "❌",
                    "arquivo": "-",
                    "erro": str(e)[:50]
                })
            
            # Update results table
            with results_container.container():
                df = pd.DataFrame(results[-10:])  # Show last 10
                st.dataframe(df, use_container_width=True, hide_index=True)
        
        progress_bar.progress(1.0)
        status_text.text("✅ Download concluído!")
        
        # Store status
        st.session_state.contracts_download_status = {
            "success": True,
            "total": total,
            "downloaded": success_count,
            "errors": error_count,
            "output_dir": str(output_dir),
            "timestamp": datetime.now().isoformat()
        }
        
        # Summary
        st.success(f"""
        🎉 **Download finalizado!**
        
        - **Total processados:** {total}
        - **Sucesso:** {success_count} ✅
        - **Erros:** {error_count} ❌
        - **Pasta:** `{output_dir}`
        """)
        
        # Full results table
        if results:
            st.subheader("📋 Resultados Completos")
            df_full = pd.DataFrame(results)
            st.dataframe(df_full, use_container_width=True, height=300)
        
    except Exception as e:
        st.error(f"Erro durante download: {e}")
        st.session_state.contracts_download_status = {
            "success": False,
            "error": str(e)
        }
        
    finally:
        status_text.text("🔒 Fechando navegador...")
        close_driver(driver)
        st.session_state.contracts_download_in_progress = False
    
    # Back button
    st.divider()
    if st.button("🔙 Voltar para o Dashboard", type="primary", use_container_width=True):
        st.rerun()


def render_download_contracts_section():
    """Render the download contracts section in sidebar."""
    st.subheader("📥 Download Contratos")
    
    # Check dependencies
    if not DOWNLOAD_CONTRACTS_LOADED:
        st.error("Módulo não disponível")
        with st.expander("Ver erro"):
            st.code(DOWNLOAD_CONTRACTS_ERROR)
        return
    
    if not DRIVER_AVAILABLE:
        st.warning("Chrome não detectado")
        return
    
    # Find processos files
    processos_files = get_processos_files()
    
    if not processos_files:
        st.warning("Nenhum arquivo de processos")
        st.caption("Execute `process_from_csv.py` primeiro")
        return
    
    # File selector
    selected_file = st.selectbox(
        "Arquivo de processos",
        options=processos_files,
        format_func=lambda x: f"{x.name} ({x.stat().st_size // 1024}KB)",
        key="contracts_file_select"
    )
    
    # Options
    max_downloads = st.number_input(
        "Limite (0 = todos)",
        min_value=0,
        max_value=1000,
        value=0,
        key="contracts_max_downloads"
    )
    
    headless = st.checkbox(
        "Modo invisível",
        value=False,
        key="contracts_headless"
    )
    
    # Status from last run
    if st.session_state.contracts_download_status:
        status = st.session_state.contracts_download_status
        if status.get("success"):
            st.success(f"✓ Último: {status.get('downloaded', 0)}/{status.get('total', 0)}")
        else:
            st.error("✗ Último download falhou")
    
    # Download button
    is_running = st.session_state.get("contracts_download_in_progress", False)
    
    if st.button(
        "📥 Baixar PDFs" if not is_running else "⏳ Baixando...",
        type="secondary",
        use_container_width=True,
        disabled=is_running,
        key="start_contracts_download_btn"
    ):
        st.session_state.contracts_download_in_progress = True
        st.session_state.contracts_download_trigger = True
        st.session_state.contracts_selected_file = selected_file
        st.session_state.contracts_max = max_downloads if max_downloads > 0 else None
        st.session_state.contracts_headless = headless
        st.rerun()

def find_company_column(df, candidates=None):
    """
    Find the company name column in a DataFrame.
    """
    if candidates is None:
        candidates = [
            'Company', 'company',
            'Nome', 'nome',
            'Razão Social', 'razao_social', 'Razao Social',
            'Empresa', 'empresa',
            'Favorecido', 'favorecido',
            'Nome Favorecido', 'nome_favorecido'
        ]
    
    for col in candidates:
        if col in df.columns:
            return col
    
    # Fallback
    for col in df.columns:
        col_lower = col.lower()
        if any(term in col_lower for term in ['nome', 'company', 'empresa', 'razao']):
            return col
    
    return None


def compare_data_sources(scraped_path: Path, portal_path: Path) -> dict:
    """
    Compare scraped data with portal CSV.
    
    Returns:
        Dictionary with comparison results
    """
    result = {
        "success": False,
        "error": None,
        "scraped_count": 0,
        "portal_count": 0,
        "matched_count": 0,
        "only_in_scraped": [],
        "only_in_portal": [],
        "matched": [],
        "scraped_columns": [],
        "portal_columns": [],
        "scraped_id_col": None,
        "portal_id_col": None
    }
    
    # ═══════════════════════════════════════════════════════════
    # STEP 1: Load files
    # ═══════════════════════════════════════════════════════════
    try:
        if not scraped_path.exists():
            result["error"] = f"Arquivo scraped não encontrado: {scraped_path.name}"
            return result
        
        if not portal_path.exists():
            result["error"] = f"Arquivo portal não encontrado: {portal_path.name}"
            return result
        
        df_scraped = pd.read_csv(scraped_path, dtype=str)
        df_portal = pd.read_csv(portal_path, dtype=str)
        
        result["scraped_count"] = len(df_scraped)
        result["portal_count"] = len(df_portal)
        result["scraped_columns"] = list(df_scraped.columns)
        result["portal_columns"] = list(df_portal.columns)
        
    except Exception as e:
        result["error"] = f"Erro ao carregar arquivos: {str(e)}"
        return result
    
    # ═══════════════════════════════════════════════════════════
    # STEP 2: Find ID columns
    # ═══════════════════════════════════════════════════════════
    scraped_id_col = find_id_column(df_scraped)
    portal_id_col = find_id_column(df_portal)
    
    result["scraped_id_col"] = scraped_id_col
    result["portal_id_col"] = portal_id_col
    
    if not scraped_id_col:
        result["error"] = f"Coluna ID não encontrada no arquivo scraped. Colunas: {result['scraped_columns']}"
        return result
    
    if not portal_id_col:
        result["error"] = f"Coluna ID não encontrada no arquivo portal. Colunas: {result['portal_columns']}"
        return result
    
    # ═══════════════════════════════════════════════════════════
    # STEP 3: Find company name columns (optional, for display)
    # ═══════════════════════════════════════════════════════════
    scraped_name_col = find_company_column(df_scraped)
    portal_name_col = find_company_column(df_portal)
    
    # ═══════════════════════════════════════════════════════════
    # STEP 4: Normalize IDs and create lookup sets
    # ═══════════════════════════════════════════════════════════
    df_scraped['_normalized_id'] = df_scraped[scraped_id_col].apply(normalize_id)
    df_portal['_normalized_id'] = df_portal[portal_id_col].apply(normalize_id)
    
    scraped_ids = set(df_scraped['_normalized_id'].dropna().unique())
    portal_ids = set(df_portal['_normalized_id'].dropna().unique())
    
    # ═══════════════════════════════════════════════════════════
    # STEP 5: Compare
    # ═══════════════════════════════════════════════════════════
    matched_ids = scraped_ids & portal_ids
    only_scraped_ids = scraped_ids - portal_ids
    only_portal_ids = portal_ids - scraped_ids
    
    result["matched_count"] = len(matched_ids)
    
    # Get details for unmatched records
    for norm_id in only_scraped_ids:
        row = df_scraped[df_scraped['_normalized_id'] == norm_id].iloc[0]
        result["only_in_scraped"].append({
            "id": row.get(scraped_id_col, ""),
            "name": row.get(scraped_name_col, "") if scraped_name_col else ""
        })
    
    for norm_id in only_portal_ids:
        row = df_portal[df_portal['_normalized_id'] == norm_id].iloc[0]
        result["only_in_portal"].append({
            "id": row.get(portal_id_col, ""),
            "name": row.get(portal_name_col, "") if portal_name_col else ""
        })
    
    # Sample of matched records
    for norm_id in list(matched_ids)[:10]:
        scraped_row = df_scraped[df_scraped['_normalized_id'] == norm_id].iloc[0]
        portal_row = df_portal[df_portal['_normalized_id'] == norm_id].iloc[0]
        result["matched"].append({
            "scraped_id": scraped_row.get(scraped_id_col, ""),
            "portal_id": portal_row.get(portal_id_col, ""),
            "scraped_name": scraped_row.get(scraped_name_col, "") if scraped_name_col else "",
            "portal_name": portal_row.get(portal_name_col, "") if portal_name_col else ""
        })
    
    result["success"] = True
    return result


def render_compare_section():
    """Render the comparison section in sidebar."""
    st.subheader("🔄 Comparar Quantidades")
    
    scraped_file = SCRAPING_OUTPUT_DIR / "favorecidos_latest.csv"
    portal_file = SCRAPING_OUTPUT_DIR / "contasrio_latest.csv"
    
    # Check file existence
    scraped_exists = scraped_file.exists()
    portal_exists = portal_file.exists()
    
    col1, col2 = st.columns(2)
    with col1:
        if scraped_exists:
            st.caption("✅ Scraped")
        else:
            st.caption("❌ Scraped")
    with col2:
        if portal_exists:
            st.caption("✅ Portal")
        else:
            st.caption("❌ Portal")
    
    # Both files needed
    if not scraped_exists or not portal_exists:
        st.warning("Ambos os arquivos são necessários")
        if not scraped_exists:
            st.caption("→ Execute o scraping primeiro")
        if not portal_exists:
            st.caption("→ Baixe o CSV do portal primeiro")
        return
    
    # Compare button
    if st.button(
        "🔄 Comparar",
        type="secondary",
        use_container_width=True,
        key="compare_btn"
    ):
        with st.spinner("Comparando..."):
            result = compare_data_sources(scraped_file, portal_file)
            st.session_state.comparison_result = result
        st.rerun()
    
    # Show last comparison result
    if st.session_state.comparison_result:
        result = st.session_state.comparison_result
        
        if result.get("success"):
            # Summary metrics
            scraped = result["scraped_count"]
            portal = result["portal_count"]
            matched = result["matched_count"]
            only_s = len(result["only_in_scraped"])
            only_p = len(result["only_in_portal"])
            
            # Match percentage
            if scraped > 0:
                match_pct = (matched / scraped) * 100
            else:
                match_pct = 0
            
            st.metric("Scraped", scraped)
            st.metric("Portal", portal)
            st.metric("Match", f"{matched} ({match_pct:.0f}%)")
            
            if only_s > 0:
                st.warning(f"⚠️ {only_s} só no scraped")
            if only_p > 0:
                st.warning(f"⚠️ {only_p} só no portal")
            
            # Expand for details
            with st.expander("📋 Ver detalhes"):
                st.caption(f"ID Scraped: `{result['scraped_id_col']}`")
                st.caption(f"ID Portal: `{result['portal_id_col']}`")
                
                if result["only_in_scraped"]:
                    st.markdown("**Só no Scraped:**")
                    for item in result["only_in_scraped"][:5]:
                        st.caption(f"• {item['id']}: {item['name'][:30]}")
                    if len(result["only_in_scraped"]) > 5:
                        st.caption(f"... +{len(result['only_in_scraped']) - 5} mais")
                
                if result["only_in_portal"]:
                    st.markdown("**Só no Portal:**")
                    for item in result["only_in_portal"][:5]:
                        st.caption(f"• {item['id']}: {item['name'][:30]}")
                    if len(result["only_in_portal"]) > 5:
                        st.caption(f"... +{len(result['only_in_portal']) - 5} mais")
        else:
            st.error(f"Erro: {result.get('error', 'Desconhecido')}")


# ════════════════════════════════════════════════════════════════
# 🆕 NEW HELPER FUNCTIONS: Scraping
# ════════════════════════════════════════════════════════════════

def save_scraping_results(companies: list, year: int) -> tuple:
    """
    Save scraping results to files (replaces previous).
    
    Returns:
        Tuple of (json_path, csv_path)
    """
    SCRAPING_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Save JSON (always replace)
    json_path = SCRAPING_OUTPUT_DIR / "favorecidos_latest.json"
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump({
            "year": year,
            "count": len(companies),
            "timestamp": datetime.now().isoformat(),
            "companies": companies
        }, f, ensure_ascii=False, indent=2)
    
    # Save CSV (always replace)
    csv_path = SCRAPING_OUTPUT_DIR / "favorecidos_latest.csv"
    if companies:
        df = pd.DataFrame(companies)
        df.to_csv(csv_path, index=False, encoding='utf-8')
    
    return json_path, csv_path


def run_scraping_process(year: int, headless: bool):
    """
    Execute the scraping process with progress display.
    
    This function takes over the main area during scraping.
    """
    
    # Header
    st.header("🔄 Coleta de Dados em Andamento")
    
    # Warning box
    st.warning("""
    ⚠️ **Atenção:** Este processo pode demorar **várias horas** dependendo da quantidade de dados.
    
    - Não feche esta aba do navegador
    - O navegador do Selenium ficará visível para você acompanhar
    - Você pode continuar usando o computador normalmente
    """)
    
    st.divider()
    
    # Progress elements
    progress_bar = st.progress(0)
    status_text = st.empty()
    details_container = st.empty()
    results_container = st.empty()
    
    driver = None
    
    try:
        # ─────────────────────────────────────────────────────────
        # Step 1: Initialize driver
        # ─────────────────────────────────────────────────────────
        status_text.text("🚀 Iniciando navegador...")
        progress_bar.progress(5)
        
        driver = initialize_driver(headless=headless)
        
        if not driver:
            st.error("❌ Falha ao inicializar o navegador. Verifique se o Chrome está instalado.")
            st.session_state.scraping_in_progress = False
            return
        
        progress_bar.progress(10)
        status_text.text("✓ Navegador iniciado com sucesso")
        time.sleep(0.5)
        
        # ─────────────────────────────────────────────────────────
        # Step 2: Navigate to home
        # ─────────────────────────────────────────────────────────
        status_text.text("🏠 Navegando para página inicial do ContasRio...")
        progress_bar.progress(15)
        
        if not navigate_to_home(driver):
            st.error("❌ Falha ao carregar página inicial. O site pode estar fora do ar.")
            return
        
        progress_bar.progress(20)
        status_text.text("✓ Página inicial carregada")
        time.sleep(0.5)
        
        # ─────────────────────────────────────────────────────────
        # Step 3: Navigate to contracts
        # ─────────────────────────────────────────────────────────
        status_text.text(f"📋 Navegando para página de contratos (ano: {year})...")
        progress_bar.progress(25)
        
        if not navigate_to_contracts(driver, year=year):
            st.error("❌ Falha ao carregar página de contratos. Tente novamente.")
            return
        
        progress_bar.progress(30)
        status_text.text("✓ Página de contratos carregada")
        time.sleep(0.5)
        
        # ─────────────────────────────────────────────────────────
        # Step 4: Scroll and collect (the LONG part)
        # ─────────────────────────────────────────────────────────
        status_text.text("📜 Coletando dados... Isso pode demorar várias horas.")
        progress_bar.progress(35)
        
        with details_container.container():
            st.info("""
            **🔄 Processo de coleta em andamento**
            
            O sistema está:
            1. Fazendo scroll pela tabela de favorecidos
            2. Coletando cada linha visível
            3. Validando os dados coletados
            4. Fazendo uma segunda passagem para garantir completude
            
            **Acompanhe o progresso no navegador que foi aberto.**
            
            ⏳ Tempo estimado: 1-4 horas dependendo do volume de dados.
            """)
        
        # This is the long-running operation
        raw_rows = scroll_and_collect_rows(driver)
        
        progress_bar.progress(70)
        status_text.text(f"✓ Coletadas {len(raw_rows)} linhas brutas")
        details_container.empty()
        time.sleep(0.5)
        
        # ─────────────────────────────────────────────────────────
        # Step 5: Parse data
        # ─────────────────────────────────────────────────────────
        status_text.text("🔄 Processando e validando dados...")
        progress_bar.progress(80)
        
        companies = parse_row_data(raw_rows)
        
        progress_bar.progress(90)
        status_text.text(f"✓ {len(companies)} empresas processadas com sucesso")
        time.sleep(0.5)
        
        # ─────────────────────────────────────────────────────────
        # Step 6: Save results
        # ─────────────────────────────────────────────────────────
        status_text.text("💾 Salvando resultados...")
        
        json_path, csv_path = save_scraping_results(companies, year)
        
        progress_bar.progress(100)
        
        # Store in session state
        st.session_state.scraped_companies = companies
        st.session_state.scraping_status = {
            "success": True,
            "count": len(companies),
            "year": year,
            "timestamp": datetime.now().isoformat(),
            "json_path": str(json_path),
            "csv_path": str(csv_path)
        }
        
        # ─────────────────────────────────────────────────────────
        # Step 7: Show results
        # ─────────────────────────────────────────────────────────
        status_text.text("✅ Coleta concluída com sucesso!")
        
        with results_container.container():
            st.success(f"""
            🎉 **Coleta finalizada!**
            
            - **Total de empresas:** {len(companies)}
            - **Ano:** {year}
            - **Arquivos salvos:**
              - `{json_path}`
              - `{csv_path}`
            """)
            
            st.divider()
            
            # Show data table
            if companies:
                st.subheader("📊 Dados Coletados")
                df = pd.DataFrame(companies)
                st.dataframe(df, use_container_width=True, height=400)
                
                # Download buttons
                st.subheader("📥 Download")
                col1, col2 = st.columns(2)
                
                with col1:
                    csv_data = df.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        "📥 Baixar CSV",
                        data=csv_data,
                        file_name=f"favorecidos_{year}.csv",
                        mime="text/csv",
                        use_container_width=True,
                        type="primary"
                    )
                
                with col2:
                    json_data = json.dumps(companies, ensure_ascii=False, indent=2)
                    st.download_button(
                        "📥 Baixar JSON",
                        data=json_data,
                        file_name=f"favorecidos_{year}.json",
                        mime="application/json",
                        use_container_width=True
                    )
            
            st.divider()
            
            # Button to go back to normal view
            if st.button("🔙 Voltar para o Dashboard", type="primary", use_container_width=True):
                st.rerun()
    
    except Exception as e:
        progress_bar.progress(0)
        st.error(f"❌ Erro durante o scraping: {str(e)}")
        
        st.session_state.scraping_status = {
            "success": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }
        
        # Show error details
        with st.expander("Ver detalhes do erro"):
            st.exception(e)
    
    finally:
        # Always close driver
        if driver:
            status_text.text("🔒 Fechando navegador...")
            close_driver(driver)
            time.sleep(0.5)
        
        st.session_state.scraping_in_progress = False

def run_csv_download_process(year: int, headless: bool):
    """
    Execute the CSV download process with progress display.
    
    This is much faster than scraping (seconds vs hours).
    """
    
    st.header("📥 Download CSV em Andamento")
    
    st.info("""
    ⏳ **Baixando CSV do portal ContasRio...**
    
    Este processo é rápido (menos de 1 minuto).
    O sistema irá:
    1. Abrir o portal ContasRio
    2. Aplicar o filtro de ano
    3. Clicar no botão de exportação
    4. Baixar o arquivo CSV
    """)
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    try:
        status_text.text("🚀 Iniciando download...")
        progress_bar.progress(10)
        
        # Run the download function
        status_text.text(f"📥 Baixando CSV (ano: {year})...")
        progress_bar.progress(30)
        
        downloaded_file = download_contracts_csv(year=year, headless=headless)
        
        progress_bar.progress(90)
        
        if downloaded_file:
            progress_bar.progress(100)
            status_text.text("✅ Download concluído!")
            
            # Store status
            st.session_state.csv_download_status = {
                "success": True,
                "file_path": downloaded_file,
                "year": year,
                "timestamp": datetime.now().isoformat()
            }
            
            # Success message
            st.success(f"""
            🎉 **Download concluído!**
            
            - **Arquivo:** `{Path(downloaded_file).name}`
            - **Local:** `{downloaded_file}`
            - **Ano:** {year}
            """)
            
            # Read and show preview
            try:
                df = pd.read_csv(downloaded_file, nrows=10)
                st.subheader("📊 Preview (primeiras 10 linhas)")
                st.dataframe(df, use_container_width=True)
                st.caption(f"Total de colunas: {len(df.columns)}")
            except Exception as e:
                st.warning(f"Não foi possível ler preview: {e}")
            
            # Download button for user
            if Path(downloaded_file).exists():
                with open(downloaded_file, 'rb') as f:
                    st.download_button(
                        "📥 Baixar arquivo",
                        data=f.read(),
                        file_name=Path(downloaded_file).name,
                        mime="text/csv",
                        type="primary",
                        use_container_width=True
                    )
        else:
            progress_bar.progress(0)
            status_text.text("❌ Download falhou")
            
            st.session_state.csv_download_status = {
                "success": False,
                "error": "Download retornou None",
                "timestamp": datetime.now().isoformat()
            }
            
            st.error("❌ Falha no download. Verifique se o portal está acessível.")
    
    except Exception as e:
        progress_bar.progress(0)
        status_text.text("❌ Erro durante download")
        
        st.session_state.csv_download_status = {
            "success": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }
        
        st.error(f"❌ Erro: {str(e)}")
        
        with st.expander("Ver detalhes do erro"):
            st.exception(e)
    
    finally:
        st.session_state.csv_download_in_progress = False
    
    # Button to go back
    st.divider()
    if st.button("🔙 Voltar para o Dashboard", type="primary", use_container_width=True):
        st.rerun()

# ============================================================
# UI COMPONENTS
# ============================================================

def render_header():
    """Render the page header."""
    st.title("📄 TCMRio - Análise de Contratos")
    st.markdown("Sistema de extração e análise de contratos públicos")
    
    if not EXTRACTOR_LOADED:
        st.error(f"""
        ❌ **Erro ao carregar o módulo contract_extractor**
        
        ```
        {IMPORT_ERROR}
        ```
        
        Verifique se o arquivo `Contract_analisys/contract_extractor.py` existe e está correto.
        """)
        st.stop()


# ════════════════════════════════════════════════════════════════
# 🆕 NEW FUNCTION: Scraping section in sidebar
# ════════════════════════════════════════════════════════════════

def render_scraping_section():
    """Render the data collection section in sidebar."""
    st.subheader("🔄 Coleta de Dados")
    
    # Check if scraper is available
    if not SCRAPER_LOADED:
        st.error("Módulo scraper não disponível")
        with st.expander("Ver erro"):
            st.code(SCRAPER_IMPORT_ERROR)
        return
    
    if not DRIVER_AVAILABLE:
        st.warning("Chrome não detectado")
        st.caption("Instale o Chrome para usar esta funcionalidade")
        return
    
    # Year input
    default_year = FILTER_YEAR if FILTER_YEAR else 2025
    year = st.number_input(
        "Ano para filtrar",
        min_value=2020,
        max_value=2030,
        value=default_year,
        key="scraping_year"
    )
    
    # Headless mode
    headless = st.checkbox(
        "Modo invisível",
        value=False,
        key="scraping_headless",
        help="Se marcado, o navegador não será visível durante o processo"
    )
    
    # Warning
    st.caption("⚠️ Processo pode demorar **horas**")
    
    # Status from last run
    if st.session_state.scraping_status:
        status = st.session_state.scraping_status
        if status.get("success"):
            st.success(f"✓ Última coleta: {status.get('count', 0)} empresas")
        elif status.get("error"):
            st.error("✗ Última coleta falhou")
    
    # Start button
    is_running = st.session_state.get("scraping_in_progress", False)
    
    if st.button(
        "🚀 Iniciar Scraping" if not is_running else "⏳ Em andamento...",
        type="primary",
        use_container_width=True,
        disabled=is_running,
        key="start_scraping_btn"
    ):
        st.session_state.scraping_in_progress = True
        st.session_state.scraping_trigger = True
        st.rerun()
    
    # Show last results if available
    if st.session_state.scraped_companies and not is_running:
        with st.expander(f"📊 Ver últimos resultados ({len(st.session_state.scraped_companies)})"):
            st.caption("Empresas coletadas na última execução")
            if st.button("Limpar resultados", key="clear_scraped"):
                st.session_state.scraped_companies = []
                st.session_state.scraping_status = None
                st.rerun()

def render_download_csv_section():
    """Render the CSV download section in sidebar."""
    st.subheader("📥 Download CSV (Portal)")
    
    # Check if module is available
    if not DOWNLOAD_CSV_LOADED:
        st.error("Módulo download_csv não disponível")
        with st.expander("Ver erro"):
            st.code(DOWNLOAD_CSV_IMPORT_ERROR)
        return
    
    if not DRIVER_AVAILABLE:
        st.warning("Chrome não detectado")
        st.caption("Instale o Chrome para usar esta funcionalidade")
        return
    
    # Year input (separate from scraping year)
    default_year = FILTER_YEAR if FILTER_YEAR else 2025
    year = st.number_input(
        "Ano para download",
        min_value=2020,
        max_value=2030,
        value=default_year,
        key="csv_download_year"
    )
    
    # Headless mode
    headless = st.checkbox(
        "Modo invisível",
        value=False,
        key="csv_download_headless",
        help="Se marcado, o navegador não será visível"
    )
    
    # Info
    st.caption("⚡ Processo rápido (~30 segundos)")
    
    # Status from last run
    if st.session_state.csv_download_status:
        status = st.session_state.csv_download_status
        if status.get("success"):
            file_name = Path(status.get("file_path", "")).name
            st.success(f"✓ Último: {file_name[:25]}...")
        elif status.get("error"):
            st.error("✗ Último download falhou")
    
    # Download button
    is_running = st.session_state.get("csv_download_in_progress", False)
    
    if st.button(
        "📥 Baixar CSV" if not is_running else "⏳ Baixando...",
        type="secondary",
        use_container_width=True,
        disabled=is_running,
        key="start_csv_download_btn"
    ):
        st.session_state.csv_download_in_progress = True
        st.session_state.csv_download_trigger = True
        st.rerun()
    
    # Show download folder location
    if DOWNLOAD_FOLDER:
        with st.expander("📁 Pasta de downloads"):
            st.caption(f"`{DOWNLOAD_FOLDER}`")
            
            # List recent files
            try:
                import glob
                csv_files = sorted(
                    glob.glob(os.path.join(DOWNLOAD_FOLDER, "*.csv")),
                    key=os.path.getctime,
                    reverse=True
                )[:5]
                
                if csv_files:
                    st.caption("Últimos arquivos:")
                    for f in csv_files:
                        st.caption(f"• {Path(f).name}")
                else:
                    st.caption("Nenhum arquivo ainda")
            except Exception:
                pass

def render_sidebar():
    """Render the sidebar with folder stats and settings."""
    with st.sidebar:
        st.header("📂 Configuração")
        
        # Folder stats
        st.subheader("Status das Pastas")
        
        stats = get_folder_stats(str(PDF_FOLDER))
        
        if stats["exists"]:
            col1, col2 = st.columns(2)
            with col1:
                st.metric("PDFs", stats["total_files"])
            with col2:
                st.metric("Tamanho", format_file_size(stats["total_size_mb"]))
            
            if stats["total_files"] == 0:
                st.warning("Nenhum PDF encontrado na pasta")
        else:
            st.error(f"Pasta não encontrada: {PDF_FOLDER}")
        
        st.divider()
        
        # CSV stats
        st.subheader("Dados de Referência")
        summary_df = load_analysis_summary(str(CSV_PATH))
        
        if not summary_df.empty:
            st.success(f"✅ {len(summary_df)} registros carregados")
            
            with st.expander("Ver colunas"):
                st.write(list(summary_df.columns))
        else:
            st.warning("CSV não carregado ou vazio")
        
        st.divider()
        
        # Types keywords info
        st.subheader("Tipos de Contrato")
        with st.expander("Ver palavras-chave"):
            for category, keywords in TYPES_KEYWORDS.items():
                st.markdown(f"**{category.title()}:**")
                st.caption(", ".join(keywords[:5]) + "...")
        
        st.divider()
        
        # ════════════════════════════════════════════════════════
        # 🆕 NEW: Scraping section (BEFORE Session info)
        # ════════════════════════════════════════════════════════
        render_scraping_section()
        
        st.divider()
        
        # 🆕 NEW: Download CSV section
        render_download_csv_section()

        # 🆕 NEW: Compare section
        render_compare_section()

        render_download_contracts_section()

        st.divider()

        # Session info
        if st.session_state.results:
            st.subheader("📊 Sessão Atual")
            total = len(st.session_state.results)
            success = sum(1 for r in st.session_state.results if r.get("success"))
            st.write(f"Processados: {total}")
            st.write(f"Sucesso: {success}")
            st.write(f"Erros: {total - success}")
            
            if st.button("🗑️ Limpar Resultados", use_container_width=True):
                st.session_state.results = []
                st.rerun()
        
        return stats, summary_df


def render_single_file_tab(stats: dict):
    """Render the single file processing tab."""
    st.header("📄 Processar Arquivo Individual")
    
    if not stats["exists"] or stats["total_files"] == 0:
        st.warning("Nenhum arquivo PDF disponível para processamento.")
        return
    
    # File selector
    selected_file = st.selectbox(
        "Selecione um arquivo PDF:",
        options=stats["files"],
        format_func=lambda x: f"📄 {x}"
    )
    
    col1, col2 = st.columns([1, 3])
    
    with col1:
        process_button = st.button(
            "🔍 Processar",
            type="primary",
            use_container_width=True,
            disabled=st.session_state.processing
        )
    
    if process_button and selected_file:
        st.session_state.processing = True
        
        with st.spinner(f"Processando {selected_file}..."):
            pdf_path = PDF_FOLDER / selected_file
            
            # Progress steps
            progress = st.progress(0)
            status = st.empty()
            
            # Step 1: Extract text
            status.text("📖 Extraindo texto do PDF...")
            progress.progress(25)
            time.sleep(0.3)
            
            # Step 2: Process contract
            status.text("🤖 Analisando com IA...")
            progress.progress(50)
            
            result = process_single_contract(str(pdf_path))
            
            progress.progress(100)
            status.text("✅ Concluído!")
            time.sleep(0.5)
            status.empty()
            progress.empty()
        
        st.session_state.processing = False
        
        # Display results
        with st.expander("📄 Texto extraído (debug)"):
            st.text(result.get("full_text", "")[:5000])
        
        if result["success"]:
            st.success(f"✅ Arquivo processado com sucesso!")
            
            # Add to session results
            st.session_state.results.append(result)
            
            # Display extracted data
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("📋 Dados Extraídos")
                data = result.get("extracted_data", {})
                
                st.markdown(f"""
                | Campo | Valor |
                |-------|-------|
                | **Valor** | {data.get('valor_contrato', 'N/A')} |
                | **Contratante** | {data.get('contratante', 'N/A')} |
                | **Contratada** | {data.get('contratada', 'N/A')} |
                | **Objeto** | {(str(data.get('objeto')) if data.get('objeto') is not None else 'N/A')[:100] + ('...' if len(str(data.get('objeto')) if data.get('objeto') is not None else 'N/A') > 100 else '')} |
                | **Tipo** | {data.get('tipo_contrato', 'N/A')} |
                | **Modalidade** | {data.get('modalidade_licitacao', 'N/A')} |
                | **Vigência** | {data.get('vigencia_meses', 'N/A')} meses |
                """)
            
            with col2:
                st.subheader("📊 Metadados")
                st.markdown(f"""
                - **Páginas:** {result.get('total_pages', 0)}
                - **Parágrafos:** {result.get('paragraph_count', 0)}
                - **Processo ID:** {result.get('processo_id', 'N/A') or 'N/A'}
                """)
                
                st.divider()
                st.subheader("🔍 Verificação de Conformidade")
                
                conformity = result.get("conformity")
                if conformity:
                    render_conformity_badge(conformity)
                    
                    with st.expander("Ver detalhes da verificação"):
                        field_checks = conformity.get("field_checks", [])
                        if field_checks:
                            for check in field_checks:
                                status_icon = "✓" if check.get("status") == "APROVADO" else "✗" if check.get("status") == "REPROVADO" else "◐"
                                match_pct = check.get("match_percentage", 0)
                                st.markdown(f"{status_icon} **{check.get('field_label')}**: {check.get('match_level')} ({match_pct:.0f}%)")
                                
                                col1, col2 = st.columns(2)
                                with col1:
                                    st.caption(f"Contrato: {check.get('contract_value', 'N/A')}")
                                with col2:
                                    st.caption(f"Publicação: {check.get('publication_value', 'N/A')}")
                        else:
                            st.caption("Nenhuma verificação de campo disponível")
                else:
                    st.info("Verificação de conformidade não realizada ou não disponível")

                # Types analysis
                types_info = result.get("type_analysis", {})
                if types_info:
                    st.markdown(f"- **Tipo Principal:** {types_info.get('primary_type', 'N/A')}")
                    if types_info.get("types_found"):
                        st.markdown(f"- **Tipos encontrados:** {', '.join(types_info.get('types_found', []))}")
            
            # Full JSON expander
            with st.expander("🔍 Ver JSON completo"):
                display_data = {k: v for k, v in result.items() if k != "full_text"}
                display_data["text_preview"] = result.get("full_text", "")[:500] + "..."
                st.json(display_data)
        
        else:
            st.error(f"❌ Erro ao processar: {result.get('error', 'Erro desconhecido')}")
            
            with st.expander("Ver detalhes do erro"):
                st.json({
                    "error": result.get("error"),
                    "error_stage": result.get("error_stage"),
                    "file_name": result.get("file_name")
                })


def render_batch_tab(stats: dict):
    """Render the batch processing tab."""
    st.header("📦 Processamento em Lote")
    
    if not stats["exists"] or stats["total_files"] == 0:
        st.warning("Nenhum arquivo PDF disponível para processamento.")
        return
    
    st.info(f"📂 **{stats['total_files']}** arquivos PDF disponíveis ({format_file_size(stats['total_size_mb'])})")
    
    # Options
    col1, col2, col3 = st.columns(3)
    
    with col1:
        limit = st.number_input(
            "Limite de arquivos (0 = todos)",
            min_value=0,
            max_value=stats["total_files"],
            value=0
        )
    
    with col2:
        export_excel = st.checkbox("Exportar Excel", value=True)
    
    with col3:
        export_json = st.checkbox("Exportar JSON", value=True)
    
    # Start button
    if st.button(
        "🚀 Iniciar Processamento",
        type="primary",
        disabled=st.session_state.processing,
        use_container_width=True
    ):
        st.session_state.processing = True
        
        # Progress elements
        progress_bar = st.progress(0)
        status_text = st.empty()
        results_container = st.empty()
        
        # Files to process
        files_to_process = stats["files"][:limit] if limit > 0 else stats["files"]
        total = len(files_to_process)
        
        results = []
        
        for i, file_name in enumerate(files_to_process):
            status_text.text(f"🔄 Processando [{i+1}/{total}]: {file_name}")
            
            pdf_path = PDF_FOLDER / file_name
            result = process_single_contract(str(pdf_path))
            results.append(result)
            
            # Update progress
            progress_bar.progress((i + 1) / total)
            
            # Show live results
            with results_container.container():
                df = create_results_dataframe(results)
                st.dataframe(df, use_container_width=True, hide_index=True)
        
        progress_bar.progress(1.0)
        status_text.text("✅ Processamento concluído!")
        
        # Store results
        st.session_state.results = results
        
        # Export
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        exports = []
        
        if export_excel:
            excel_path = OUTPUT_DIR / f"contracts_{timestamp}.xlsx"
            export_to_excel(results, str(excel_path))
            exports.append(f"📊 Excel: `{excel_path}`")
        
        if export_json:
            json_path = OUTPUT_DIR / f"contracts_{timestamp}.json"
            export_to_json(results, str(json_path))
            exports.append(f"📄 JSON: `{json_path}`")
        
        if exports:
            st.success("Arquivos exportados:\n" + "\n".join(exports))
            st.session_state.last_export = timestamp
        
        st.session_state.processing = False
        
        # Summary
        success_count = sum(1 for r in results if r.get("success"))
        st.markdown(f"""
        ### 📊 Resumo
        - **Total processados:** {len(results)}
        - **Sucesso:** {success_count} ✅
        - **Erros:** {len(results) - success_count} ❌
        """)


def render_results_tab():
    """Render the results viewer tab."""
    st.header("📊 Visualizar Resultados")
    
    if not st.session_state.results:
        st.info("Nenhum resultado disponível. Processe alguns contratos primeiro.")
        
        # Option to load from file
        st.subheader("📂 Carregar resultados salvos")
        
        json_files = list(OUTPUT_DIR.glob("contracts_*.json"))
        
        if json_files:
            selected_json = st.selectbox(
                "Selecione um arquivo de resultados:",
                options=sorted(json_files, reverse=True),
                format_func=lambda x: x.name
            )
            
            if st.button("📥 Carregar"):
                with open(selected_json, 'r', encoding='utf-8') as f:
                    st.session_state.results = json.load(f)
                st.success(f"Carregados {len(st.session_state.results)} resultados")
                st.rerun()
        else:
            st.caption("Nenhum arquivo de resultados encontrado.")
        
        return
    
    # Results DataFrame
    df = create_results_dataframe(st.session_state.results)
    
    # Filters
    st.subheader("🔍 Filtros")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        status_filter = st.selectbox(
            "Status",
            options=["Todos", "✅ Sucesso", "❌ Erro"]
        )
    
    with col2:
        type_options = ["Todos"] + df["Tipo"].dropna().unique().tolist()
        type_filter = st.selectbox("Tipo de Contrato", options=type_options)
    
    with col3:
        search_text = st.text_input("🔎 Buscar", placeholder="Nome do arquivo ou empresa...")
    
    # Apply filters
    filtered_df = df.copy()
    
    if status_filter == "✅ Sucesso":
        filtered_df = filtered_df[filtered_df["Status"] == "✅"]
    elif status_filter == "❌ Erro":
        filtered_df = filtered_df[filtered_df["Status"] == "❌"]
    
    if type_filter != "Todos":
        filtered_df = filtered_df[filtered_df["Tipo"] == type_filter]
    
    if search_text:
        mask = (
            filtered_df["Arquivo"].str.contains(search_text, case=False, na=False) |
            filtered_df["Contratada"].str.contains(search_text, case=False, na=False)
        )
        filtered_df = filtered_df[mask]
    
    # Display
    st.subheader(f"📋 Resultados ({len(filtered_df)} de {len(df)})")
    
    st.dataframe(
        filtered_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Status": st.column_config.TextColumn(width="small"),
            "Valor": st.column_config.TextColumn(width="medium"),
            "Objeto": st.column_config.TextColumn(width="large"),
        }
    )
    
    # Export buttons
    st.subheader("📤 Exportar")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("📊 Exportar Excel", use_container_width=True):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            excel_path = OUTPUT_DIR / f"contracts_{timestamp}.xlsx"
            export_to_excel(st.session_state.results, str(excel_path))
            st.success(f"Exportado: {excel_path}")
    
    with col2:
        if st.button("📄 Exportar JSON", use_container_width=True):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            json_path = OUTPUT_DIR / f"contracts_{timestamp}.json"
            export_to_json(st.session_state.results, str(json_path))
            st.success(f"Exportado: {json_path}")
    
    with col3:
        # Download filtered as CSV
        csv_data = filtered_df.to_csv(index=False).encode('utf-8')
        st.download_button(
            "⬇️ Download CSV",
            data=csv_data,
            file_name=f"contracts_filtered_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
            use_container_width=True
        )
    
    # Detailed view
    st.subheader("🔍 Visualização Detalhada")
    
    file_options = [r.get("file_name", "") for r in st.session_state.results]
    selected_detail = st.selectbox("Selecione um contrato para ver detalhes:", file_options)
    
    if selected_detail:
        result = next((r for r in st.session_state.results if r.get("file_name") == selected_detail), None)
        
        if result:
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("**Dados Extraídos**")
                data = result.get("extracted_data", {})
                st.json(data)
            
            with col2:
                st.markdown("**Análise de Tipos**")
                types_info = result.get("type_analysis", {})
                if types_info:
                    st.json(types_info)
                else:
                    st.caption("Não disponível")
                
                st.markdown("**Match CSV**")
                csv_match = result.get("csv_match", {})
                st.json(csv_match)


def render_conformity_tab():
    """Render the conformity analysis tab."""
    st.header("🔍 Análise de Conformidade")
    
    st.markdown("""
    Esta aba mostra o resultado da verificação de conformidade dos contratos.
    
    A verificação é executada **automaticamente** após a extração de cada contrato e inclui:
    - ✅ Verificação de publicação no D.O. Rio
    - ✅ Verificação do prazo de publicação (20 dias)
    - ✅ Comparação dos dados do contrato com a publicação
    """)
    
    st.divider()
    
    # Check if we have results
    if not st.session_state.results:
        st.info("Nenhum resultado disponível. Processe alguns contratos primeiro.")
        return
    
    # Filter results with conformity data
    results_with_conformity = [
        r for r in st.session_state.results 
        if r.get("conformity") and not r.get("conformity", {}).get("error")
    ]
    
    results_without_conformity = [
        r for r in st.session_state.results 
        if not r.get("conformity") or r.get("conformity", {}).get("error")
    ]
    
    # Summary metrics
    st.subheader("📊 Resumo")
    
    col1, col2, col3, col4 = st.columns(4)
    
    total = len(st.session_state.results)
    verified = len(results_with_conformity)
    
    conforme = sum(1 for r in results_with_conformity 
                   if r.get("conformity", {}).get("overall_status") == "CONFORME")
    parcial = sum(1 for r in results_with_conformity 
                  if r.get("conformity", {}).get("overall_status") == "PARCIAL")
    nao_conforme = sum(1 for r in results_with_conformity 
                       if r.get("conformity", {}).get("overall_status") == "NÃO CONFORME")
    
    with col1:
        st.metric("Total Contratos", total)
    with col2:
        st.metric("✅ Conforme", conforme)
    with col3:
        st.metric("⚠️ Parcial", parcial)
    with col4:
        st.metric("❌ Não Conforme", nao_conforme)
    
    # Pending verification info
    if results_without_conformity:
        st.warning(f"⏳ {len(results_without_conformity)} contrato(s) aguardando verificação ou com erro")
    
    st.divider()
    
    # Detailed results
    st.subheader("📋 Resultados Detalhados")
    
    # Status filter
    status_filter = st.selectbox(
        "Filtrar por status",
        ["Todos", "✅ Conforme", "⚠️ Parcial", "❌ Não Conforme", "⏳ Pendente"]
    )
    
    # Build filtered list
    filtered_results = []
    
    for r in st.session_state.results:
        conformity = r.get("conformity", {})
        status = conformity.get("overall_status", "") if conformity else ""
        
        if status_filter == "Todos":
            filtered_results.append(r)
        elif status_filter == "✅ Conforme" and status == "CONFORME":
            filtered_results.append(r)
        elif status_filter == "⚠️ Parcial" and status == "PARCIAL":
            filtered_results.append(r)
        elif status_filter == "❌ Não Conforme" and status == "NÃO CONFORME":
            filtered_results.append(r)
        elif status_filter == "⏳ Pendente" and not status:
            filtered_results.append(r)
    
    st.caption(f"Mostrando {len(filtered_results)} de {total} contratos")
    
    # Display each result
    for r in filtered_results:
        file_name = r.get("file_name", "Arquivo desconhecido")
        processo = r.get("processo_id", "") or r.get("extracted_data", {}).get("processo_administrativo", "N/A")
        conformity = r.get("conformity", {})
        
        # Get status for header
        if conformity and not conformity.get("error"):
            status = conformity.get("overall_status", "DESCONHECIDO")
            score = conformity.get("conformity_score", 0)
            
            if status == "CONFORME":
                icon = "✅"
            elif status == "PARCIAL":
                icon = "⚠️"
            else:
                icon = "❌"
            
            header = f"{icon} {file_name} — {status} ({score:.0f}%)"
        else:
            header = f"⏳ {file_name} — Pendente"
        
        with st.expander(header):
            col1, col2 = st.columns([2, 1])
            
            with col1:
                st.markdown(f"**Processo:** {processo}")
                
                # Contract data
                data = r.get("extracted_data", {})
                st.markdown(f"**Valor:** {data.get('valor_contrato', 'N/A')}")
                st.markdown(f"**Contratada:** {data.get('contratada', 'N/A')}")
            
            with col2:
                if conformity and not conformity.get("error"):
                    pub = conformity.get("publication_check", {})
                    if pub and pub.get("was_published"):
                        st.markdown(f"**Publicado em:** {pub.get('publication_date', 'N/A')}")
                        st.markdown(f"**Edição:** {pub.get('edition_number', 'N/A')}")
                        if pub.get("download_link"):
                            st.link_button("🔗 Ver no D.O.", pub.get("download_link"))
                    else:
                        st.warning("Publicação não encontrada")
            
            # Field checks
            if conformity and conformity.get("field_checks"):
                st.markdown("---")
                st.markdown("**Verificações:**")
                
                checks_df = []
                for check in conformity.get("field_checks", []):
                    checks_df.append({
                        "Campo": check.get("field_label", ""),
                        "Status": "✓" if check.get("status") == "APROVADO" else "✗",
                        "Match": f"{check.get('match_percentage', 0):.0f}%",
                        "Nível": check.get("match_level", ""),
                    })
                
                if checks_df:
                    st.dataframe(
                        pd.DataFrame(checks_df),
                        use_container_width=True,
                        hide_index=True
                    )
    
    st.divider()
    
    # Export conformity report
    st.subheader("📤 Exportar Relatório")
    
    if st.button("📊 Exportar Relatório de Conformidade", use_container_width=True):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Build report data
        report_rows = []
        for r in st.session_state.results:
            conformity = r.get("conformity", {})
            data = r.get("extracted_data", {})
            pub = conformity.get("publication_check", {}) if conformity else {}
            
            report_rows.append({
                "Arquivo": r.get("file_name", ""),
                "Processo": r.get("processo_id", "") or data.get("processo_administrativo", ""),
                "Status_Extração": "OK" if r.get("success") else "ERRO",
                "Status_Conformidade": conformity.get("overall_status", "PENDENTE") if conformity else "PENDENTE",
                "Score": conformity.get("conformity_score", 0) if conformity else 0,
                "Publicado": "SIM" if pub.get("was_published") else "NÃO",
                "Data_Publicação": pub.get("publication_date", ""),
                "Prazo_OK": "SIM" if pub.get("published_on_time") else "NÃO",
                "Dias_Para_Publicar": pub.get("days_to_publish", ""),
                "Link_DO": pub.get("download_link", ""),
                "Valor_Contrato": data.get("valor_contrato", ""),
                "Contratada": data.get("contratada", ""),
            })
        
        report_df = pd.DataFrame(report_rows)
        
        # Save Excel
        excel_path = OUTPUT_DIR / f"conformity_report_{timestamp}.xlsx"
        report_df.to_excel(excel_path, index=False)
        
        st.success(f"✅ Relatório exportado: {excel_path}")
        
        # Download button
        csv_data = report_df.to_csv(index=False).encode('utf-8')
        st.download_button(
            "⬇️ Download CSV",
            data=csv_data,
            file_name=f"conformity_report_{timestamp}.csv",
            mime="text/csv"
        )


def render_help_tab():
    """Render the help/documentation tab."""
    st.header("❓ Ajuda e Documentação")
    
    st.markdown("""
    ## 📖 Como usar o sistema
    
    ### 1. Preparar os dados
    
    1. Coloque os PDFs de contratos na pasta `data/downloads/processos/`
    2. (Opcional) Tenha o arquivo `data/outputs/analysis_summary.csv` com dados de referência
    
    ### 2. Processar contratos
    
    **Arquivo Individual:**
    - Vá para a aba "📄 Arquivo Individual"
    - Selecione um PDF e clique em "Processar"
    
    **Lote:**
    - Vá para a aba "📦 Processamento em Lote"
    - Configure as opções e clique em "Iniciar"
    
    ### 3. Visualizar resultados
    
    - Vá para a aba "📊 Resultados"
    - Use os filtros para encontrar contratos específicos
    - Exporte para Excel, JSON ou CSV
    
    ---
    
    ## 🆕 Coleta de Dados (Scraping)
    
    O sistema agora permite coletar dados de favorecidos diretamente do portal ContasRio:
    
    1. Na barra lateral, encontre a seção **🔄 Coleta de Dados**
    2. Selecione o ano desejado
    3. Clique em **🚀 Iniciar Scraping**
    4. Aguarde o processo (pode demorar horas)
    5. Os resultados serão salvos automaticamente
    
    **⚠️ Importante:**
    - O processo pode demorar várias horas
    - Não feche a aba do navegador durante o processo
    - O navegador do Selenium ficará visível para acompanhamento
    
    ---
    
    ## 🔧 Configuração
    
    ### Variáveis de Ambiente
    
    Crie um arquivo `.env` na raiz do projeto:
    
    ```
    GROQ_API_KEY=sua_chave_api_aqui
    FILTER_YEAR=2025
    ```
    
    ### Estrutura de Pastas
    
    ```
    Data_ige/
    ├── data/
    │   ├── downloads/processos/    ← PDFs aqui
    │   ├── outputs/                ← CSV de referência + resultados scraping
    │   └── extractions/            ← Resultados exportados
    ├── Contract_analisys/
    │   └── contract_extractor.py
    ├── src/
    │   └── scraper.py              ← Módulo de scraping
    └── app.py
    ```
    
    ---
    
    ## 📊 Dados Extraídos
    
    O sistema extrai automaticamente:
    
    | Campo | Descrição |
    |-------|-----------|
    | `valor_contrato` | Valor total do contrato |
    | `contratante` | Órgão contratante |
    | `contratada` | Empresa contratada |
    | `objeto` | Descrição do objeto |
    | `tipo_contrato` | Tipo (Serviços, Fornecimento, etc) |
    | `vigencia_meses` | Período de vigência |
    | `modalidade_licitacao` | Modalidade usada |
    
    ---
    
    ## ⚠️ Solução de Problemas
    
    **Erro de API Key:**
    - Verifique se o arquivo `.env` existe
    - Confirme que a chave GROQ_API_KEY está correta
    
    **Erro de Rate Limit:**
    - O sistema tenta novamente automaticamente
    - Aguarde alguns segundos entre processamentos
    
    **PDF não processado:**
    - Verifique se o PDF não está corrompido
    - Alguns PDFs escaneados podem não ter texto extraível
    
    **Scraping não inicia:**
    - Verifique se o Chrome está instalado
    - Verifique se o módulo scraper está carregado (ver sidebar)
    """)

# ============================================================
# MAIN APP
# ============================================================

def main():
    """Main application entry point."""
    render_header()
    
    # ════════════════════════════════════════════════════════
    # CHECK IF SCRAPING WAS TRIGGERED
    # ════════════════════════════════════════════════════════
    
    if st.session_state.get("scraping_trigger"):
        st.session_state.scraping_trigger = False  # Reset trigger
        
        year = st.session_state.get("scraping_year", 2025)
        headless = st.session_state.get("scraping_headless", False)
        
        render_sidebar()
        run_scraping_process(year, headless)
        return

    # ════════════════════════════════════════════════════════
    # CHECK IF CSV DOWNLOAD WAS TRIGGERED
    # ════════════════════════════════════════════════════════

    if st.session_state.get("csv_download_trigger"):
        st.session_state.csv_download_trigger = False
        
        year = st.session_state.get("csv_download_year", 2025)
        headless = st.session_state.get("csv_download_headless", False)
        
        render_sidebar()
        run_csv_download_process(year, headless)
        return

    # ════════════════════════════════════════════════════════
    # CHECK IF CONTRACTS DOWNLOAD WAS TRIGGERED
    # ════════════════════════════════════════════════════════
    
    if st.session_state.get("contracts_download_trigger"):
        st.session_state.contracts_download_trigger = False
        
        selected_file = st.session_state.get("contracts_selected_file")
        max_downloads = st.session_state.get("contracts_max")
        headless = st.session_state.get("contracts_headless", False)
        
        render_sidebar()
        run_contracts_download_process(selected_file, headless, max_downloads)
        return    

    # ════════════════════════════════════════════════════════
    # NORMAL RENDERING
    # ════════════════════════════════════════════════════════
    stats, summary_df = render_sidebar()
    
    # Main tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📄 Arquivo Individual",
        "📦 Processamento em Lote",
        "📊 Resultados",
        "🔍 Conformidade", 
        "❓ Ajuda"
    ])
    
    with tab1:
        render_single_file_tab(stats)
    
    with tab2:
        render_batch_tab(stats)
    
    with tab3:
        render_results_tab()
    
    with tab4:
        render_conformity_tab()
    
    with tab5:
        render_help_tab()

if __name__ == "__main__":
    main()

