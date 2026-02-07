""" 
process_from_csv.py - Process companies from downloaded CSV file.
Take only the CSV from the link.
Reads company IDs from CSV and retrieves processo data.
Separate from main scraper for AI Agent orchestration.
"""

import os
import sys
import csv
import time
import re
from datetime import datetime
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    StaleElementReferenceException,
    NoSuchElementException
)

# Add project root to path
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Import centralized driver
from core.driver import create_scraper_driver, close_driver

# Import configuration
from config import (
    BASE_URL, CONTRACTS_URL, TIMEOUT_SECONDS, 
    FILTER_YEAR, LOCATORS
)

import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

from core.navigation import (
    get_current_level,
    set_year_filter,
    filter_by_company,
    click_company_button,
    get_all_buttons_at_level,
    click_specific_button,
    has_processo_links
)

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

DOWNLOADS_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "downloads")
OUTPUTS_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs")

# Ensure folders exist
os.makedirs(DOWNLOADS_FOLDER, exist_ok=True)
os.makedirs(OUTPUTS_FOLDER, exist_ok=True)


# ═══════════════════════════════════════════════════════════════════════════════
# CSV READING
# ═══════════════════════════════════════════════════════════════════════════════

def get_latest_csv_file():
    """
    Get the most recent CSV file from downloads folder.
    """
    import glob
    csv_files = glob.glob(os.path.join(DOWNLOADS_FOLDER, "*.csv"))
    
    if not csv_files:
        logger.error(f"✗ Nenhum arquivo CSV encontrado em: {DOWNLOADS_FOLDER}")
        return None
    
    latest = max(csv_files, key=os.path.getctime)
    logging.info(f"✓ Arquivo CSV encontrado: {os.path.basename(latest)}")
    return latest


def read_company_ids_from_csv(filepath):
    """
    Read company IDs from CSV file.
    
    Args:
        filepath: Path to CSV file
        
    Returns:
        List of dictionaries with company data
    """
    logging.info(f"\n→ Lendo arquivo: {os.path.basename(filepath)}")
    
    companies = []
    
    try:
        # Try different encodings
        encodings = ['utf-8', 'latin-1', 'cp1252']
        
        for encoding in encodings:
            try:
                with open(filepath, 'r', encoding=encoding) as f:
                    # Detect delimiter
                    sample = f.read(2048)
                    f.seek(0)
                    
                    # Try to detect delimiter
                    if ';' in sample:
                        delimiter = ';'
                    elif '\t' in sample:
                        delimiter = '\t'
                    else:
                        delimiter = ','
                    
                    reader = csv.DictReader(f, delimiter=delimiter)
                    
                    for row in reader:
                        # Find the ID column (may have different names)
                        company_id = None
                        company_name = None
                        
                        for key, value in row.items():
                            if key is None:
                                continue
                            key_lower = key.lower().strip()
                            
                            # Look for ID column
                            if any(x in key_lower for x in ['cnpj', 'cpf', 'id', 'favorecido', 'documento']):
                                # Extract just the numbers
                                potential_id = re.sub(r'[^\d]', '', str(value))
                                if len(potential_id) >= 11:  # CPF or CNPJ
                                    company_id = potential_id
                            
                            # Look for name column
                            if any(x in key_lower for x in ['nome', 'razao', 'favorecido', 'empresa']):
                                if value and not value.isdigit():
                                    company_name = value.strip()
                        
                        if company_id:
                            companies.append({
                                "ID": company_id,
                                "Company": company_name or "N/A"
                            })
                    
                    if companies:
                        logging.info(f"✓ {len(companies)} empresas encontradas (encoding: {encoding})")
                        break
                        
            except UnicodeDecodeError:
                continue
            except Exception as e:
                logger.error(f"   Erro com encoding {encoding}: {e}")
                continue
        
        # Remove duplicates based on ID
        seen = set()
        unique_companies = []
        for c in companies:
            if c["ID"] not in seen:
                seen.add(c["ID"])
                unique_companies.append(c)
        
        logging.info(f"✓ {len(unique_companies)} empresas únicas")
        
        # Show first 5
        logging.info("\n   Primeiras 5 empresas:")
        for i, c in enumerate(unique_companies[:5], 1):
            logging.info(f"   {i}: {c['ID']} - {c['Company'][:40]}...")
        
        return unique_companies
        
    except Exception as e:
        logger.error(f"✗ Erro ao ler CSV: {e}")
        return []


# ═══════════════════════════════════════════════════════════════════════════════
# NAVIGATION FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def reset_to_contracts_page(driver):
    """Reset to contracts page."""
    driver.get(BASE_URL)
    time.sleep(2)
    driver.get(CONTRACTS_URL)
    time.sleep(2)
    
    try:
        WebDriverWait(driver, TIMEOUT_SECONDS).until(
            EC.presence_of_element_located((By.XPATH, LOCATORS["table_rows"]))
        )
        
        if FILTER_YEAR:
            set_year_filter(driver, FILTER_YEAR)
            time.sleep(1)
        
        return True
    except:
        return False

def get_all_document_links(driver):
    """Get all processo links from current page."""
    results = []
    
    try:
        time.sleep(1)
        links = driver.find_elements(By.XPATH, "//a[contains(@href, 'processo')]")
        
        for link in links:
            try:
                href = link.get_attribute("href")
                processo = link.text.strip()
                
                if not processo and href:
                    if "?n=" in href:
                        processo = href.split("?n=")[-1]
                
                if href:
                    results.append({"href": href, "processo": processo})
            except:
                continue
                
    except:
        pass
    
    return results


# ═══════════════════════════════════════════════════════════════════════════════
# PROCESSO COLLECTION
# ═══════════════════════════════════════════════════════════════════════════════

def collect_processos_for_company(driver, company_id):
    """
    Navigate through all levels and collect all processos for a company.
    """
    all_processos = []
    
    def explore_level(current_path, visited):
        time.sleep(0.8)
        
        # Check for processo links
        if has_processo_links(driver):
            docs = get_all_document_links(driver)
            for doc in docs:
                if doc["href"] not in [p["href"] for p in all_processos]:
                    all_processos.append(doc)
            return
        
        # Get buttons at this level
        buttons = []
        for _ in range(3):
            buttons = get_all_buttons_at_level(driver, set(current_path))
            if buttons:
                break
            time.sleep(0.5)
        
        if not buttons:
            if has_processo_links(driver):
                docs = get_all_document_links(driver)
                for doc in docs:
                    if doc["href"] not in [p["href"] for p in all_processos]:
                        all_processos.append(doc)
            return
        
        # Explore each button
        for i, btn_text in enumerate(buttons):
            path_key = " → ".join(current_path + [btn_text])
            if path_key in visited:
                continue
            visited.add(path_key)
            
            if click_specific_button(driver, btn_text):
                explore_level(current_path + [btn_text], visited)
                
                # Reset for next button
                if i < len(buttons) - 1:
                    if not reset_to_contracts_page(driver):
                        return
                    if not filter_by_company(driver, company_id):
                        return
                    if not click_company_button(driver, company_id):
                        return
                    
                    # Re-navigate path
                    for path_btn in current_path:
                        if not click_specific_button(driver, path_btn):
                            return
                        time.sleep(0.5)
    
    visited = set()
    explore_level([], visited)
    
    return all_processos


def process_company(driver, company):
    """
    Process a single company and return its processos.
    """
    company_id = company["ID"]
    company_name = company.get("Company", "N/A")
    
    # Reset to contracts page
    if not reset_to_contracts_page(driver):
        return []
    
    # Filter by company
    if not filter_by_company(driver, company_id):
        return []
    
    # Click on company
    if not click_company_button(driver, company_id):
        return []
    
    # Collect all processos
    processos = collect_processos_for_company(driver, company_id)
    
    # Add company info to each processo
    results = []
    for p in processos:
        results.append({
            "ID": company_id,
            "Company": company_name,
            "Processo": p.get("processo", ""),
            "URL": p.get("href", "")
        })
    
    return results


# ═══════════════════════════════════════════════════════════════════════════════
# OUTPUT
# ═══════════════════════════════════════════════════════════════════════════════

def save_results_to_csv(results, filename=None):
    """Save results to CSV file."""
    if not filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"processos_{timestamp}.csv"
    
    filepath = os.path.join(OUTPUTS_FOLDER, filename)
    
    try:
        with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
            if results:
                writer = csv.DictWriter(f, fieldnames=results[0].keys())
                writer.writeheader()
                writer.writerows(results)
        
        logging.info(f"✓ Resultados salvos: {filepath}")
        return filepath
    except Exception as e:
        logger.error(f"✗ Erro ao salvar: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN FUNCTION
# ═══════════════════════════════════════════════════════════════════════════════

def process_companies_from_csv(csv_filepath=None, headless=False, max_companies=None):
    """
    Main function to process companies from CSV file.
    
    Args:
        csv_filepath: Path to CSV file (uses latest if None)
        headless: Run browser in headless mode
        max_companies: Maximum number of companies to process (None = all)
        
    Returns:
        Path to results file
    """
    logging.info("\n" + "=" * 60)
    logging.info("     PROCESSAR EMPRESAS DO CSV")
    logging.info("=" * 60)
    
    # ═══════════════════════════════════════════════════════════
    # STEP 1: Get CSV file
    # ═══════════════════════════════════════════════════════════
    if csv_filepath is None:
        csv_filepath = get_latest_csv_file()
    
    if not csv_filepath or not os.path.exists(csv_filepath):
        logging.info("✗ Arquivo CSV não encontrado")
        return None
    
    # ═══════════════════════════════════════════════════════════
    # STEP 2: Read companies from CSV
    # ═══════════════════════════════════════════════════════════
    companies = read_company_ids_from_csv(csv_filepath)
    
    if not companies:
        logging.info("✗ Nenhuma empresa encontrada no CSV")
        return None
    
    if max_companies:
        companies = companies[:max_companies]
        logging.info(f"\n⚠ Limitado a {max_companies} empresas")
    
    # ═══════════════════════════════════════════════════════════
    # STEP 3: Initialize driver
    # ═══════════════════════════════════════════════════════════

    driver = create_scraper_driver(headless=headless)
    if not driver:
        return None
    
    # ═══════════════════════════════════════════════════════════
    # STEP 4: Process each company
    # ═══════════════════════════════════════════════════════════
    all_results = []
    total = len(companies)
    
    try:
        for idx, company in enumerate(companies, 1):
            logging.info(f"\n{'#'*60}")
            logging.info(f"# EMPRESA {idx}/{total}: {company['ID']}")
            logging.info(f"# {company['Company'][:50]}")
            logging.info(f"{'#'*60}")
            
            try:
                results = process_company(driver, company)
                
                if results:
                    all_results.extend(results)
                    logging.info(f"✓ {len(results)} processo(s) encontrado(s)")
                else:
                    # Add entry with no processo
                    all_results.append({
                        "ID": company["ID"],
                        "Company": company["Company"],
                        "Processo": "",
                        "URL": ""
                    })
                    logger.warning("⚠ Nenhum processo encontrado")
                    
            except Exception as e:
                logger.error(f"✗ Erro: {e}")
                all_results.append({
                    "ID": company["ID"],
                    "Company": company["Company"],
                    "Processo": "ERRO",
                    "URL": str(e)[:100]
                })
            
            # Save progress every 10 companies
            if idx % 10 == 0:
                save_results_to_csv(all_results, "processos_progress.csv")
                logging.info(f"\n→ Progresso salvo: {len(all_results)} registros")
                
    except KeyboardInterrupt:
        logger.warning("\n\n⚠️ Interrompido pelo usuário")
        
    finally:
        if driver:
            close_driver(driver)
    
    # ═══════════════════════════════════════════════════════════
    # STEP 5: Save final results
    # ═══════════════════════════════════════════════════════════
    result_file = save_results_to_csv(all_results)
    
    # ═══════════════════════════════════════════════════════════
    # SUMMARY
    # ═══════════════════════════════════════════════════════════
    logging.info("\n" + "=" * 60)
    logging.info("RESUMO")
    logging.info("=" * 60)
    logging.info(f"  Empresas processadas: {total}")
    logging.info(f"  Processos encontrados: {len([r for r in all_results if r['Processo'] and r['Processo'] != 'ERRO'])}")
    logging.info(f"  Arquivo: {result_file}")
    logging.info("=" * 60)
    
    return result_file


# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Process companies from CSV")
    parser.add_argument("--csv", help="Path to CSV file (uses latest if not provided)")
    parser.add_argument("--headless", action="store_true", help="Run in headless mode")
    parser.add_argument("--max", type=int, help="Maximum companies to process")
    
    args = parser.parse_args()
    
    result = process_companies_from_csv(
        csv_filepath=args.csv,
        headless=args.headless,
        max_companies=args.max
    )
    
    if result:
        logging.info(f"\n📁 Arquivo salvo: {result}")
    else:
        logging.info("\n❌ Processamento falhou")