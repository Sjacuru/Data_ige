
"""
download_csv.py - Download CSV file from ContasRio portal.
Separate from the main scraper for future AI Agent orchestration.
Download folder: see DOWNLOAD_FOLDER variable below.
"""

import os
import time
import glob
from datetime import datetime

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from selenium.common.exceptions import TimeoutException, NoSuchElementException

# Add project root to path
import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Import centralized driver
from core.driver import create_download_driver, close_driver

# Import configuration
from config import BASE_URL, CONTRACTS_URL, TIMEOUT_SECONDS

import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

from core.navigation import set_year_filter

from config import DATA_RAW_PATH

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

# Folder to save downloaded files
DOWNLOAD_FOLDER = os.path.join(str(PROJECT_ROOT), "data", "outputs")

# Ensure download folder exists
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)


# ═══════════════════════════════════════════════════════════════════════════════
# DRIVER SETUP was MOVED to core/driver.py
# ═══════════════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════════════
# NAVIGATION
# ═══════════════════════════════════════════════════════════════════════════════

def navigate_to_contracts_page(driver):
    """
    Navigate to the contracts page and wait for it to load.
    """
    logging.info(f"\n→ Navegando para: {CONTRACTS_URL}")
    
    driver.get(CONTRACTS_URL)
    
    try:
        # Wait for page to load (wait for grid to appear)
        WebDriverWait(driver, TIMEOUT_SECONDS).until(
            EC.presence_of_element_located((
                By.CSS_SELECTOR, 
                ".v-grid"
            ))
        )
        logging.info("✓ Página de contratos carregada!")
        time.sleep(2)  # Extra wait for full render
        return True
        
    except TimeoutException:
        logging.info("✗ Timeout ao carregar página de contratos")
        return False

# ═══════════════════════════════════════════════════════════════════════════════
# DOWNLOAD CSV
# ═══════════════════════════════════════════════════════════════════════════════

def click_download_button(driver):
    """
    Click the download icon to open export options.
    """
    logging.info("\n→ Procurando botão de download...")
    
    try:
        # Method 1: Find by class
        download_btn = WebDriverWait(driver, TIMEOUT_SECONDS).until(
            EC.element_to_be_clickable((
                By.CSS_SELECTOR,
                "span.v-icon.v-icon-download"
            ))
        )
        
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", download_btn)
        time.sleep(0.5)
        driver.execute_script("arguments[0].click();", download_btn)
        
        logging.info("✓ Botão de download clicado!")
        time.sleep(1)
        return True
        
    except TimeoutException:
        logging.info("   Método 1 falhou, tentando alternativo...")
    
    try:
        # Method 2: Find by icon font-family
        icons = driver.find_elements(By.CSS_SELECTOR, "span.v-icon")
        
        for icon in icons:
            style = icon.get_attribute("style") or ""
            if "Vaadin-Icons" in style:
                # Check if it's the download icon
                parent = icon.find_element(By.XPATH, "./..")
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", icon)
                time.sleep(0.3)
                driver.execute_script("arguments[0].click();", icon)
                logging.info("✓ Botão de download clicado (método alternativo)!")
                time.sleep(1)
                return True
                
    except Exception as e:
        logger.error(f"   Método alternativo falhou: {e}")
    
    logger.error("✗ Não foi possível encontrar o botão de download")
    return False


def click_csv_option(driver):
    """
    Click the CSV option in the export menu.
    """
    logging.info("\n→ Selecionando opção CSV...")
    
    try:
        # Wait for menu to appear and find CSV button
        csv_btn = WebDriverWait(driver, TIMEOUT_SECONDS).until(
            EC.element_to_be_clickable((
                By.XPATH,
                "//span[contains(@class,'v-button-caption') and text()='Csv']"
            ))
        )
        
        driver.execute_script("arguments[0].click();", csv_btn)
        logging.info("✓ Opção CSV selecionada!")
        return True
        
    except TimeoutException:
        logging.info("   Método 1 falhou, tentando alternativo...")
    
    try:
        # Method 2: Find all button captions
        buttons = driver.find_elements(
            By.CSS_SELECTOR,
            "span.v-button-caption"
        )
        
        for btn in buttons:
            if btn.text.strip().lower() == "csv":
                driver.execute_script("arguments[0].click();", btn)
                logging.info("✓ Opção CSV selecionada (método alternativo)!")
                return True
                
    except Exception as e:
        logger.error(f"   Método alternativo falhou: {e}")

    logger.error("✗ Não foi possível encontrar a opção CSV")
    return False


def wait_for_download(timeout=60):
    """
    Wait for the CSV file to be downloaded.
    """
    logging.info(f"\n→ Aguardando download (máx {timeout}s)...")
    
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        # Check for CSV files
        csv_files = glob.glob(os.path.join(DOWNLOAD_FOLDER, "*.csv"))
        
        # Check for partial downloads
        crdownload_files = glob.glob(os.path.join(DOWNLOAD_FOLDER, "*.crdownload"))
        
        if csv_files and not crdownload_files:
            # Get the most recent file
            latest_file = max(csv_files, key=os.path.getctime)
            logging.info(f"✓ Download concluído: {os.path.basename(latest_file)}")
            return latest_file
        
        time.sleep(1)
    
    logging.info("✗ Timeout aguardando download")
    return None


def rename_downloaded_file(filepath):
    """
    Rename the downloaded file with timestamp.
    """
    if not filepath or not os.path.exists(filepath):
        return None
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    new_name = f"contasrio_export_{timestamp}.csv"
    new_path = os.path.join(DOWNLOAD_FOLDER, new_name)
    
    try:
        os.rename(filepath, new_path)
        logging.info(f"✓ Arquivo renomeado: {new_name}")
        return new_path
    except Exception as e:
        logger.error(f"⚠ Erro ao renomear: {e}")
        return filepath
    
def copy_to_latest(filepath):
    
    """
    Create a 'latest' copy for easy access and comparison.
    
    Args:
        filepath: Path to the timestamped file
        
    Returns:
        Path to the latest copy
    """

    if not filepath or not os.path.exists(filepath):
        return None
    
    import shutil
    
    latest_path = os.path.join(DOWNLOAD_FOLDER, "contasrio_latest.csv")
    
    try:
        shutil.copy2(filepath, latest_path)
        logging.info(f"✓ Cópia 'latest' criada: contasrio_latest.csv")
        return latest_path
    except Exception as e:
        logger.error(f"⚠ Erro ao criar cópia 'latest': {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN FUNCTION
# ═══════════════════════════════════════════════════════════════════════════════

def download_contracts_csv(year=None, headless=False):
    """
    Main function to download the contracts CSV file.
    
    Args:
        year: Optional year filter (e.g., 2025)
        headless: Run browser in headless mode
        
    Returns:
        Path to downloaded file or None
    """
    os.makedirs(DATA_RAW_PATH, exist_ok=True)  
    
    logging.info("\n" + "=" * 60)
    logging.info("     DOWNLOAD CSV - ContasRio")
    logging.info("=" * 60)
    
    driver = create_download_driver(download_dir=DOWNLOAD_FOLDER, headless=headless)
    if not driver:
        return None
    
    downloaded_file = None
    
    try:
        # ═══════════════════════════════════════════════════════════
        # STEP 1: Navigate to contracts page
        # ═══════════════════════════════════════════════════════════
        if not navigate_to_contracts_page(driver):
            return None
        
        # ═══════════════════════════════════════════════════════════
        # STEP 2: Set year filter (if provided)
        # ═══════════════════════════════════════════════════════════
        if year:
            set_year_filter(driver, year)
            time.sleep(2)
        
        # ═══════════════════════════════════════════════════════════
        # STEP 3: Click download button
        # ═══════════════════════════════════════════════════════════
        if not click_download_button(driver):
            return None
        
        # ═══════════════════════════════════════════════════════════
        # STEP 4: Click CSV option
        # ═══════════════════════════════════════════════════════════
        if not click_csv_option(driver):
            return None
        
        # ═══════════════════════════════════════════════════════════
        # STEP 5: Wait for download to complete
        # ═══════════════════════════════════════════════════════════
        downloaded_file = wait_for_download(timeout=60)
        
        # ═══════════════════════════════════════════════════════════
        # STEP 6: Rename file with timestamp
        # ═══════════════════════════════════════════════════════════
        if downloaded_file:
            downloaded_file = rename_downloaded_file(downloaded_file)
        
        # ═══════════════════════════════════════════════════════════
        # STEP 7: Create 'latest' copy for comparison feature
        # ═══════════════════════════════════════════════════════════
        if downloaded_file:
            copy_to_latest(downloaded_file)
        
    except KeyboardInterrupt:
        logger.warning("\n⚠️ Interrompido pelo usuário")
        
    except Exception as e:
        logger.error(f"\n✗ Erro: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        close_driver(driver)
    
    # ═══════════════════════════════════════════════════════════
    # SUMMARY
    # ═══════════════════════════════════════════════════════════
    
    logging.info("\n" + "=" * 60)
    if downloaded_file:
        logging.info(f"✓ DOWNLOAD CONCLUÍDO")
        logging.info(f"  Arquivo: {downloaded_file}")
        logging.info(f"  Latest:  {os.path.join(DOWNLOAD_FOLDER, 'contasrio_latest.csv')}")
    else:
        logging.info("✗ DOWNLOAD FALHOU")
    logging.info("=" * 60)

    return downloaded_file


# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # Import year from config
    from config import FILTER_YEAR
    
    # Download CSV with same year filter as main scraper
    result = download_contracts_csv(year=FILTER_YEAR, headless=False)
    
    if result:
        logging.info(f"\n📁 Arquivo salvo em: {result}")
    else:
        logging.info("\n❌ Falha no download")