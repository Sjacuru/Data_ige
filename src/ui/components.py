import streamlit as st  
import pandas as pd  
from pathlib import Path  
from src.ui.utils import format_file_size, get_status_emoji  
from Contract_analisys.contract_extractor import (  
    process_single_contract, get_folder_stats, export_to_excel, export_to_json  
)  
from config import PROCESSOS_DIR, FILTER_YEAR  
  
def render_header():  
    """Render the page header."""  
    st.title("📄 TCMRio - Análise de Contratos")  
    st.markdown("Sistema de extração e análise de contratos públicos")  

def render_sidebar(extractor_loaded, scraper_loaded, driver_available, summary_df):  
    """Renders the sidebar with statistics and automation triggers."""  
    with st.sidebar:  
        st.header("📂 Dashboard de Controle")  
          
        # Folder Stats  
        stats = get_folder_stats(str(PROCESSOS_DIR))  
        if stats["exists"]:  
            col1, col2 = st.columns(2)  
            col1.metric("PDFs", stats["total_files"])  
            col2.metric("Tamanho", format_file_size(stats["total_size_mb"]))  
          
        st.divider()  
          
        # Scraping Section  
        st.subheader("🔄 Automação")  
        year = st.number_input("Ano Base", 2020, 2030, FILTER_YEAR or 2025)  
        headless = st.checkbox("Modo Invisível (Headless)", value=False)  
          
        if st.button("🚀 Iniciar Scraping", use_container_width=True):  
            st.session_state.scraping_trigger = True  
            st.session_state.scraping_year = year  
            st.session_state.scraping_headless = headless  
            st.rerun()  
  
        if st.button("📥 Baixar CSV Portal", use_container_width=True):  
            st.session_state.csv_download_trigger = True  
            st.session_state.csv_download_year = year  
            st.session_state.csv_download_headless = headless  
            st.rerun()  
              
    return stats  
  
def render_results_tab():  
    """Enhanced Results Viewer with Filters and Export options."""  
    st.header("📊 Resultados da Análise AI")  
      
    if not st.session_state.results:  
        st.info("Aguardando processamento de arquivos para exibir resultados.")  
        return  
  
    # Advanced Filters  
    col1, col2, col3 = st.columns([1, 1, 2])  
    with col1:  
        status_f = st.selectbox("Status", ["Todos", "Sucesso", "Erro"])  
    with col2:  
        search_f = st.text_input("🔎 Buscar Empresa/Arquivo")  
      
    # Logic to filter the dataframe would go here before rendering st.dataframe  
    # (Simplified for the structure update)  
      
    st.dataframe(pd.DataFrame(st.session_state.results), use_container_width=True)  
  
    # Export Section - NEW IMPROVEMENT  
    st.divider()  
    ex1, ex2, _ = st.columns([1, 1, 2])  
    if ex1.button("📊 Exportar Excel"):  
        path = export_to_excel(st.session_state.results, "extractions/result.xlsx")  
        st.success(f"Salvo: {path}")  
    if ex2.button("📝 Exportar JSON"):  
        path = export_to_json(st.session_state.results, "extractions/result.json")  
        st.success(f"Salvo: {path}")  
  
def render_single_file_tab(stats):  
    """Interface for analyzing one specific PDF."""  
    st.subheader("📄 Analisar um Contrato")  
    if not stats["files"]:  
        st.warning("Nenhum arquivo PDF encontrado na pasta de processos.")  
        return  
      
    selected = st.selectbox("Selecione o arquivo:", stats["files"])  
    if st.button("🔍 Iniciar Extração AI"):  
        with st.spinner("A IA está lendo o contrato..."):  
            res = process_single_contract(str(PROCESSOS_DIR / selected))  
            st.session_state.results.append(res)  
            st.success("Análise concluída!")  
            st.json(res)  
  
def render_help_tab():  
    """Basic documentation for the user."""  
    st.markdown("""  
    ### 🛡️ Guia do Auditor  
    1. **Coleta**: Use o Sidebar para buscar dados no portal ContasRio.  
    2. **Processamento**: Escolha entre arquivo único ou lote.  
    3. **Análise**: Verifique os riscos apontados pela IA na aba Resultados.  
    """)  