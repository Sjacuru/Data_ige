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
import streamlit as st
import pandas as pd
from pathlib import Path

# Module Imports
from src.ui.utils import load_analysis_summary
from src.ui.components import (
    render_header, render_sidebar, render_single_file_tab, 
    render_batch_tab, render_results_tab, render_conformity_tab, render_help_tab
)
from src.ui.logic import (
    run_scraping_process, run_csv_download_process, run_contracts_download_process
)

# Load config
from config import ANALYSIS_SUMMARY_CSV

# Load optional modules
try:
    from Contract_analisys.contract_extractor import EXTRACTOR_LOADED
except ImportError:
    EXTRACTOR_LOADED = False

try:
    from src.scraper import initialize_driver
    SCRAPER_LOADED = True
    SCRAPER_ERROR = None
except ImportError as e:
    SCRAPER_LOADED = False
    SCRAPER_ERROR = str(e)

try:
    from scripts.download_csv import download_contracts_csv
    DOWNLOAD_CSV_LOADED = True
except ImportError:
    DOWNLOAD_CSV_LOADED = False

try:
    from core.driver import is_driver_available
    DRIVER_AVAILABLE = is_driver_available()
except ImportError:
    DRIVER_AVAILABLE = False

# ============================================================
# APP CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="Análise de Contratos - Processo.rio",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================================
# SESSION STATE INITIALIZATION
# ============================================================

def init_session_state():
    if "results" not in st.session_state: st.session_state.results = []
    if "processing" not in st.session_state: st.session_state.processing = False
    if "audit_logs" not in st.session_state: st.session_state.audit_logs = []
    
    # Audit State
    if "show_conformity" not in st.session_state: st.session_state.show_conformity = False
    if "current_extraction" not in st.session_state: st.session_state.current_extraction = None
    
    # Sample data for demo
    if "last_conformity_sample" not in st.session_state:
        st.session_state.last_conformity_sample = {
            "overall_status": "CONFORME",
            "conformity_score": 100.0,
            "publication_check": {
                "status": "REPROVADO",
                "observation": "Publicado em 71 dias (FORA do prazo de 20 dias)"
            },
            "field_checks": [
                {"field_label": "Valor do Contrato", "contract_value": "R$ 572.734,00", "publication_value": "R$ 572.734,00", "status": "APROVADO"},
                {"field_label": "Número do Contrato", "contract_value": "215/2025", "publication_value": "215/2025", "status": "APROVADO"},
                {"field_label": "Objeto do Contrato", "contract_value": "Programa FabLearn", "publication_value": "Programa FabLearn", "status": "APROVADO"}
            ]
        }

    # Scraping
    if "scraping_in_progress" not in st.session_state: st.session_state.scraping_in_progress = False
    if "scraped_companies" not in st.session_state: st.session_state.scraped_companies = []
    if "scraping_status" not in st.session_state: st.session_state.scraping_status = None
    if "scraping_trigger" not in st.session_state: st.session_state.scraping_trigger = False
    if "scraping_year" not in st.session_state: st.session_state.scraping_year = 2025
    if "scraping_headless" not in st.session_state: st.session_state.scraping_headless = False
    
    # CSV Download
    if "csv_download_in_progress" not in st.session_state: st.session_state.csv_download_in_progress = False
    if "csv_download_status" not in st.session_state: st.session_state.csv_download_status = None
    if "csv_download_trigger" not in st.session_state: st.session_state.csv_download_trigger = False
    if "csv_download_year" not in st.session_state: st.session_state.csv_download_year = 2025
    if "csv_download_headless" not in st.session_state: st.session_state.csv_download_headless = False
    
    # Comparison
    if "comparison_result" not in st.session_state: st.session_state.comparison_result = None
    
    # Contracts Download
    if "contracts_download_in_progress" not in st.session_state: st.session_state.contracts_download_in_progress = False
    if "contracts_download_status" not in st.session_state: st.session_state.contracts_download_status = None
    if "contracts_download_trigger" not in st.session_state: st.session_state.contracts_download_trigger = False
    if "contracts_selected_file" not in st.session_state: st.session_state.contracts_selected_file = None
    if "contracts_headless" not in st.session_state: st.session_state.contracts_headless = False
    if "contracts_max" not in st.session_state: st.session_state.contracts_max = None

# ============================================================
# MAIN APP
# ============================================================

def main():
    init_session_state()
    render_header()
    
    # Check for long-running process triggers
    if st.session_state.get("scraping_trigger"):
        st.session_state.scraping_trigger = False
        run_scraping_process(st.session_state.get("scraping_year", 2025), st.session_state.get("scraping_headless", False))
        return

    if st.session_state.get("csv_download_trigger"):
        st.session_state.csv_download_trigger = False
        run_csv_download_process(st.session_state.get("csv_download_year", 2025), st.session_state.get("csv_download_headless", False))
        return

    if st.session_state.get("contracts_download_trigger"):
        st.session_state.contracts_download_trigger = False
        run_contracts_download_process(st.session_state.get("contracts_selected_file"), st.session_state.get("contracts_headless", False), st.session_state.get("contracts_max"))
        return    

    # Normal Rendering
    summary_df = load_analysis_summary(str(ANALYSIS_SUMMARY_CSV))
    stats = render_sidebar(
        EXTRACTOR_LOADED, SCRAPER_LOADED, SCRAPER_ERROR, 
        DOWNLOAD_CSV_LOADED, DRIVER_AVAILABLE, summary_df
    )
    
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📄 Arquivo Individual", "📦 Processamento em Lote", "📊 Resultados", "🔍 Conformidade", "❓ Ajuda"
    ])
    
    with tab1: render_single_file_tab(stats, summary_df)
    with tab2: render_batch_tab(stats)
    with tab3: render_results_tab()
    with tab4: render_conformity_tab()
    with tab5: render_help_tab()

if __name__ == "__main__":
    main()
