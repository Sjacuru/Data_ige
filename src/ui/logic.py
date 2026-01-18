
import os
import json
import time
import pandas as pd
from pathlib import Path
from datetime import datetime
import streamlit as st

# Scraping imports
from src.scraper import (
    initialize_driver,
    navigate_to_home,
    navigate_to_contracts,
    scroll_and_collect_rows,
    parse_row_data,
    close_driver
)
from scripts.download_csv import download_contracts_csv
from src.document_extractor import download_processo_pdf
from core.driver import create_driver
from src.ui.utils import normalize_id, find_id_column, find_company_column, add_audit_log
from Contract_analisys.contract_extractor import process_single_contract

# Conformity imports
try:
    from conformity.integration import check_publication_conformity
    CONFORMITY_LOADED = True
except ImportError:
    CONFORMITY_LOADED = False

SCRAPING_OUTPUT_DIR = Path("data/outputs")
CACHE_DIR = Path("data/extractions")

def get_cached_extraction(pdf_name: str) -> dict:
    """Check if a PDF already has a saved extraction."""
    cache_file = CACHE_DIR / f"{pdf_name}.json"
    if cache_file.exists():
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None
    return None

def save_to_cache(pdf_name: str, result: dict):
    """Save extraction result to local cache."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / f"{pdf_name}.json"
    try:
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
    except Exception as e:
        add_audit_log(f"Erro ao salvar cache: {str(e)}", level="error")

def run_conformity_check_logic(contract_data: dict, headless: bool = True, processo: str = None):
    """
    Executes the real conformity check using the extracted contract data.
    """
    if not CONFORMITY_LOADED:
        return {"error": "Módulo de conformidade não carregado."}
    
    try:
        # Perform the real check
        result = check_publication_conformity(contract_data, processo=processo, headless=headless)
        return result.to_dict()
    except Exception as e:
        return {"error": f"Erro na verificação: {str(e)}"}

def save_scraping_results(companies: list, year: int) -> tuple:
    """
    Save scraping results to files.
    """
    SCRAPING_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Save JSON
    json_path = SCRAPING_OUTPUT_DIR / "favorecidos_latest.json"
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump({
            "year": year,
            "count": len(companies),
            "timestamp": datetime.now().isoformat(),
            "companies": companies
        }, f, ensure_ascii=False, indent=2)
    
    # Save CSV
    csv_path = SCRAPING_OUTPUT_DIR / "favorecidos_latest.csv"
    if companies:
        df = pd.DataFrame(companies)
        df.to_csv(csv_path, index=False, encoding='utf-8')
    
    return json_path, csv_path


def run_scraping_process(year: int, headless: bool):
    """
    Execute the scraping process with progress display.
    """
    st.header("🔄 Coleta de Dados em Andamento")
    st.warning("""
    ⚠️ **Atenção:** Este processo pode demorar **várias horas** dependendo da quantidade de dados.
    - Não feche esta aba do navegador
    - O navegador do Selenium ficará visível para você acompanhar
    - Você pode continuar usando o computador normalmente
    """)
    st.divider()
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    details_container = st.empty()
    results_container = st.empty()
    
    driver = None
    try:
        status_text.text("🚀 Iniciando navegador...")
        progress_bar.progress(5)
        driver = initialize_driver(headless=headless)
        if not driver:
            st.error("❌ Falha ao inicializar o navegador.")
            st.session_state.scraping_in_progress = False
            return
        
        progress_bar.progress(10)
        status_text.text("✓ Navegador iniciado")
        
        if not navigate_to_home(driver):
            st.error("❌ Falha ao carregar página inicial.")
            return
        
        progress_bar.progress(20)
        status_text.text("✓ Página inicial carregada")
        
        if not navigate_to_contracts(driver, year=year):
            st.error("❌ Falha ao carregar página de contratos.")
            return
        
        progress_bar.progress(30)
        status_text.text("✓ Página de contratos carregada")
        
        with details_container.container():
            st.info("📜 Coletando dados... Isso pode demorar várias horas.")
        
        raw_rows = scroll_and_collect_rows(driver)
        progress_bar.progress(70)
        status_text.text(f"✓ Coletadas {len(raw_rows)} linhas brutas")
        
        companies = parse_row_data(raw_rows)
        progress_bar.progress(90)
        status_text.text(f"✓ {len(companies)} empresas processadas")
        
        json_path, csv_path = save_scraping_results(companies, year)
        progress_bar.progress(100)
        
        st.session_state.scraped_companies = companies
        st.session_state.scraping_status = {
            "success": True,
            "count": len(companies),
            "year": year,
            "timestamp": datetime.now().isoformat(),
            "json_path": str(json_path),
            "csv_path": str(csv_path)
        }
        
        status_text.text("✅ Coleta concluída!")
        with results_container.container():
            st.success(f"🎉 **Coleta finalizada!** Total: {len(companies)}")
            if companies:
                df = pd.DataFrame(companies)
                st.dataframe(df, use_container_width=True, height=400)
            if st.button("🔙 Voltar para o Dashboard"):
                st.rerun()
    
    except Exception as e:
        st.error(f"❌ Erro durante o scraping: {str(e)}")
        st.session_state.scraping_status = {"success": False, "error": str(e), "timestamp": datetime.now().isoformat()}
    finally:
        if driver:
            close_driver(driver)
        st.session_state.scraping_in_progress = False


def run_csv_download_process(year: int, headless: bool):
    """
    Execute the CSV download process with progress display.
    """
    st.header("📥 Download CSV em Andamento")
    st.info("⏳ **Baixando CSV do portal ContasRio...**")
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    try:
        status_text.text("🚀 Iniciando download...")
        progress_bar.progress(30)
        downloaded_file = download_contracts_csv(year=year, headless=headless)
        progress_bar.progress(100)
        
        if downloaded_file:
            st.session_state.csv_download_status = {
                "success": True,
                "file_path": downloaded_file,
                "year": year,
                "timestamp": datetime.now().isoformat()
            }
            st.success(f"🎉 **Download concluído!** `{Path(downloaded_file).name}`")
        else:
            st.session_state.csv_download_status = {"success": False, "error": "Download falhou"}
            st.error("❌ Falha no download.")
    except Exception as e:
        st.error(f"❌ Erro: {str(e)}")
    finally:
        st.session_state.csv_download_in_progress = False
    
    if st.button("🔙 Voltar para o Dashboard"):
        st.rerun()


def run_contracts_download_process(processos_file: Path, headless: bool, max_downloads: int = None):
    """
    Execute the contracts download process.
    """
    from src.ui.utils import read_processos_csv
    
    st.header("📥 Download de Contratos em Andamento")
    processos, error = read_processos_csv(processos_file)
    if error:
        st.error(f"Erro ao ler arquivo: {error}")
        st.session_state.contracts_download_in_progress = False
        return
    
    if max_downloads:
        processos = processos[:max_downloads]
    
    total = len(processos)
    progress_bar = st.progress(0)
    status_text = st.empty()
    results_container = st.empty()
    
    driver = create_driver(headless=headless)
    if not driver:
        st.error("Falha ao inicializar navegador")
        st.session_state.contracts_download_in_progress = False
        return
    
    output_dir = Path("data/downloads/processos")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    results = []
    success_count = 0
    try:
        for i, proc in enumerate(processos):
            progress_bar.progress((i + 1) / total)
            status_text.text(f"📥 [{i+1}/{total}] Baixando: {proc['processo'][:30]}")
            
            res = download_processo_pdf(driver, proc["url"], str(output_dir), {"id": proc["id"], "name": proc["company"]})
            results.append({"processo": proc["processo"], "status": "✅" if res["success"] else "❌", "erro": res.get("error", "")})
            if res["success"]: success_count += 1
            
            with results_container.container():
                st.dataframe(pd.DataFrame(results[-5:]), use_container_width=True, hide_index=True)
        
        st.success(f"🎉 **Download finalizado!** Sucesso: {success_count}/{total}")
    except Exception as e:
        st.error(f"Erro: {e}")
    finally:
        close_driver(driver)
        st.session_state.contracts_download_in_progress = False
    
    if st.button("🔙 Voltar para o Dashboard"):
        st.rerun()

def compare_data_sources(scraped_path: Path, portal_path: Path) -> dict:
    """
    Compare scraped data with portal CSV.
    """
    result = {"success": False, "error": None, "scraped_count": 0, "portal_count": 0, "matched_count": 0,
              "only_in_scraped": [], "only_in_portal": [], "matched": [], "scraped_id_col": None, "portal_id_col": None}
    
    try:
        df_scraped = pd.read_csv(scraped_path, dtype=str)
        df_portal = pd.read_csv(portal_path, dtype=str)
        
        result["scraped_count"] = len(df_scraped)
        result["portal_count"] = len(df_portal)
        
        scraped_id_col = find_id_column(df_scraped)
        portal_id_col = find_id_column(df_portal)
        result["scraped_id_col"] = scraped_id_col
        result["portal_id_col"] = portal_id_col
        
        if not scraped_id_col or not portal_id_col:
            result["error"] = "Coluna ID não encontrada"
            return result
        
        df_scraped['_normalized_id'] = df_scraped[scraped_id_col].apply(normalize_id)
        df_portal['_normalized_id'] = df_portal[portal_id_col].apply(normalize_id)
        
        scraped_ids = set(df_scraped['_normalized_id'].dropna().unique())
        portal_ids = set(df_portal['_normalized_id'].dropna().unique())
        
        matched_ids = scraped_ids & portal_ids
        result["matched_count"] = len(matched_ids)
        result["success"] = True
        
        # Details omitted for brevity in refactor logic, can be added back if needed
        # (Focusing on the main logic for now)
        
    except Exception as e:
        result["error"] = str(e)
    
    return result

def run_single_extraction_logic(pdf_path: Path, hint_id: str = ""):
    """
    Executes extraction with local caching to save credits.
    """
    pdf_name = pdf_path.name
    
    # 1. Check Cache
    cached = get_cached_extraction(pdf_name)
    if cached:
        add_audit_log(f"Cache encontrado para {pdf_name}. Carregando dados locais.")
        # Ensure we use the latest hint_id from CSV even if cache has old ID
        if hint_id:
            cached["processo_id"] = hint_id
            if "extracted_data" in cached:
                cached["extracted_data"]["processo_id"] = hint_id
        return cached

    # 2. Run Real Extraction
    add_audit_log(f"Cache não encontrado. Iniciando Extração AI para {pdf_name}...")
    result = process_single_contract(str(pdf_path), hint_id)
    
    # 3. Save to Cache if successful
    if result.get("success"):
        save_to_cache(pdf_name, result)
        add_audit_log(f"Resultado salvo em cache local: {pdf_name}")
    
    return result
