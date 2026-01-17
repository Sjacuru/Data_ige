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

        if companies:  
            from config import DATA_OUTPUTS_PATH  
            import os  
            os.makedirs(DATA_OUTPUTS_PATH, exist_ok=True)  
              
            df = pd.DataFrame(companies)  
            csv_path = os.path.join(DATA_OUTPUTS_PATH, f"favorecidos_{year}.csv")  
            df.to_csv(csv_path, index=False)  
            st.success(f"✅ Dados salvos em: {csv_path}")  
          
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

def compare_data_sources(scraped_file: str, portal_file: str) -> dict:  
    """  
    Compares the scraped Vaadin data with the official Portal CSV.  
    Provides transparency on data integrity.  
    """  
    try:  
        from src.ui.utils import normalize_id  
          
        df_scraped = pd.read_csv(scraped_file)  
        df_portal = pd.read_csv(portal_file)  
          
        # We assume both have an 'ID' or 'CNPJ' column.   
        # We normalize them to ensure a fair comparison.  
        scraped_ids = set(df_scraped['ID'].astype(str).apply(normalize_id))  
        portal_ids = set(df_portal['ID'].astype(str).apply(normalize_id))  
          
        matched = scraped_ids.intersection(portal_ids)  
          
        return {  
            "success": True,  
            "scraped_count": len(scraped_ids),  
            "portal_count": len(portal_ids),  
            "matched_count": len(matched),  
            "variance": len(scraped_ids) - len(portal_ids)  
        }  
    except Exception as e:  
        return {"success": False, "error": str(e)}  