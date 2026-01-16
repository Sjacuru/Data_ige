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
from pathlib import Path  
  
# Module Imports from our new structure  
from src.ui.utils import load_analysis_summary  
from src.ui.components import (  
    render_header, render_sidebar, render_single_file_tab,   
    render_results_tab, render_help_tab  
)  
from src.ui.logic import run_scraping_process, run_csv_download_process  
  
# Configuration imports  
from config import ANALYSIS_SUMMARY_CSV  
  
# ============================================================  
# APP CONFIGURATION  
# ============================================================  
st.set_page_config(  
    page_title="Data_ige - Auditoria de Contratos",  
    page_icon="📄",  
    layout="wide"  
)  
  
def init_session_state():  
    """Initializes all variables needed to keep the app running smoothly."""  
    if "results" not in st.session_state: st.session_state.results = []  
    if "scraping_trigger" not in st.session_state: st.session_state.scraping_trigger = False  
    if "csv_download_trigger" not in st.session_state: st.session_state.csv_download_trigger = False  
    if "scraping_in_progress" not in st.session_state: st.session_state.scraping_in_progress = False  
    if "csv_download_in_progress" not in st.session_state: st.session_state.csv_download_in_progress = False  
  
# ============================================================  
# MAIN APPLICATION LOOP  
# ============================================================  
def main():  
    init_session_state()  
      
    # 1. Triggers  
    if st.session_state.scraping_trigger:  
        st.session_state.scraping_trigger = False  
        run_scraping_process(st.session_state.scraping_year, st.session_state.scraping_headless)  
        return  
  
    # 2. Sidebar  
    summary_df = load_analysis_summary(str(ANALYSIS_SUMMARY_CSV))  
    stats = render_sidebar(True, True, True, summary_df)  
      
    # 3. Content  
    render_header()  # <--- This replaces the manual st.title  
      
    tab1, tab2, tab3 = st.tabs(["🎯 Processamento", "📊 Resultados AI", "❓ Ajuda"]) 
          
    with tab1:  
        render_single_file_tab(stats)  
          
    with tab2:  
        render_results_tab()  
          
    with tab3:  
        render_help_tab()  
  
if __name__ == "__main__":  
    main()  