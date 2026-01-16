import streamlit as st  
import pandas as pd  
from pathlib import Path  
from datetime import datetime  
  
# We import your existing functions here  
from src.scraper import (  
    initialize_driver, navigate_to_home, navigate_to_contracts,  
    scroll_and_collect_rows, parse_row_data, close_driver  
)  
from scripts.download_csv import download_contracts_csv  
  
def run_scraping_process(year: int, headless: bool):  
    """Orchestrates the scraping workflow with a progress bar."""  
    st.header("🔄 Coleta de Dados")  
    progress_bar = st.progress(0)  
    status_text = st.empty()  
      
    driver = None  
    try:  
        status_text.text("🚀 Abrindo navegador...")  
        driver = initialize_driver(headless=headless)  
          
        status_text.text("🔎 Navegando para o portal...")  
        navigate_to_home(driver)  
        navigate_to_contracts(driver, year=year)  
          
        status_text.text("📜 Coletando linhas (isso pode demorar)...")  
        raw_rows = scroll_and_collect_rows(driver)  
          
        status_text.text("📊 Processando dados...")  
        companies = parse_row_data(raw_rows)  
          
        st.session_state.scraped_companies = companies  
        st.success(f"✅ Concluído! {len(companies)} empresas encontradas.")  
          
    except Exception as e:  
        st.error(f"❌ Erro: {str(e)}")  
    finally:  
        if driver:  
            close_driver(driver)  
        st.session_state.scraping_in_progress = False  
  
def run_csv_download_process(year: int, headless: bool):  
    """Handles the official CSV download from the portal."""  
    st.info("📥 Baixando CSV oficial...")  
    try:  
        file_path = download_contracts_csv(year=year, headless=headless)  
        if file_path:  
            st.success(f"✅ Arquivo salvo: {Path(file_path).name}")  
    except Exception as e:  
        st.error(f"❌ Falha no download: {e}")  
    finally:  
        st.session_state.csv_download_in_progress = False  