"""
doweb_scraper.py - Selenium scraper for D.O. Rio (doweb.rio.rj.gov.br)

Location: conformity/scraper/doweb_scraper.py

Searches for processo publications, downloads PDFs one at a time,
checks if they match, and extracts data.
"""

import os
import re
import time
from pathlib import Path
from typing import Optional, List, Tuple
import requests

from selenium import webdriver

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    StaleElementReferenceException,
)

# Add project root to path
import sys
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Import centralized driver
from core.driver import create_download_driver, close_driver

# Import from config with fallback
try:
    from config import (
        TIMEOUT_SECONDS,
        DOWEB_BASE_URL,
        DOWEB_TEMP_PATH,
        TARGET_EXTRATO_TYPES,
    )
except ImportError:
    TIMEOUT_SECONDS = 20
    DOWEB_BASE_URL = "https://doweb.rio.rj.gov.br"
    DOWEB_TEMP_PATH = os.path.join("data", "temp_doweb")
    TARGET_EXTRATO_TYPES = [
        "EXTRATO DO CONTRATO",
        "EXTRATO DE TERMO ADITIVO",
    ]

# Import from local modules
from conformity.models.publication import (
    PublicationResult,
    SearchResultItem,
    create_not_found_result,
    create_error_result,
)

from conformity.scraper.doweb_extractor import extract_publication_from_pdf

import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# =========================================================================
# DRIVER INITIALIZATION was MOVED to core/driver.py
# =========================================================================

# =========================================================================
# TEMP FILE MANAGEMENT
# =========================================================================

def ensure_temp_folder() -> Path:
    """Ensure temp folder exists and is empty."""
    temp_path = Path(DOWEB_TEMP_PATH)
    temp_path.mkdir(parents=True, exist_ok=True)
    
    # Clean any existing files
    for file in temp_path.glob("*"):
        try:
            file.unlink()
        except Exception:
            pass
    
    return temp_path


def get_latest_pdf(temp_folder: Path, timeout: int = 60) -> Optional[Path]:
    """
    Wait for PDF download to complete and return the path.
    Improved with better detection and debugging.
    """
    logging.info(f"   📂 Watching folder: {temp_folder.absolute()}")
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        # List ALL files in folder
        all_files = list(temp_folder.glob("*"))
        
        if all_files:
            logging.info(f"   📄 Files in folder: {[f.name for f in all_files]}")
        
        # Find PDF files (not partial downloads)
        pdf_files = [
            f for f in all_files 
            if f.suffix.lower() == '.pdf' 
            and not f.name.endswith('.crdownload')
            and not f.name.endswith('.tmp')
            and not f.name.endswith('.part')
        ]
        
        if pdf_files:
            latest = max(pdf_files, key=lambda f: f.stat().st_mtime)
            
            # Check if file is still being written
            size1 = latest.stat().st_size
            time.sleep(0.5)
            size2 = latest.stat().st_size
            
            if size1 == size2 and size1 > 1000:  # At least 1KB
                logging.info(f"   ✓ PDF ready: {latest.name} ({size2} bytes)")
                return latest
            else:
                logging.info(f"   ⏳ PDF still downloading: {latest.name} ({size1} → {size2} bytes)")
        
        time.sleep(3)
    
    logger.error(f"    ✗ Timeout after {timeout}s - no PDF detected")
    return None


def delete_temp_pdf(pdf_path: Path) -> None:
    """Delete a temporary PDF file."""
    try:
        if pdf_path and pdf_path.exists():
            pdf_path.unlink()
            logging.info(f"   🗑️ Deleted temp PDF: {pdf_path.name}")
    except Exception as e:
        logger.warning(f"   ⚠ Could not delete temp file: {e}")


def clear_temp_folder(temp_folder: Path) -> None:
    """Clear all files in temp folder."""
    for file in temp_folder.glob("*"):
        try:
            file.unlink()
        except Exception:
            pass


# =========================================================================
# SEARCH FUNCTIONS
# =========================================================================

def search_processo(driver: webdriver.Chrome, processo: str) -> Tuple[bool, int, str]:
    """
    Search for a processo on DOWEB.
    
    Args:
        driver: WebDriver instance
        processo: Processo number to search
        
    Returns:
        Tuple of (success, results_count, error_message)
    """
    try:
        # Navigate to search page
        search_url = f"{DOWEB_BASE_URL}/buscanova/#/p=1&q={processo}"
        logging.info(f"🔍 Searching: {search_url}")
        driver.get(search_url)
        
        # Wait for JavaScript to render (8 seconds needed based on debug)
        logging.info("   ⏳ Waiting for page to load...")
        time.sleep(8)
        
        # Get page text to parse results
        body_text = driver.find_element(By.TAG_NAME, "body").text
        
        # Look for "X resultados encontrados"
        count_match = re.search(r"(\d+)\s+resultados?\s+encontrados?", body_text, re.IGNORECASE)
        if count_match:
            count = int(count_match.group(1))
            logging.info(f"   ✓ Found {count} result(s) for {processo}")
            return True, count, ""
        
        # Check for no results
        if "nenhum resultado" in body_text.lower():
            logger.error(f"    ✗ No results found for {processo}")
            return True, 0, ""
        
        # Fallback: check if "Diário publicado em" appears (means there are results)
        if "Diário publicado em" in body_text:
            # Count occurrences
            count = body_text.count("Diário publicado em")
            logging.info(f"   ✓ Found {count} result(s) for {processo} (via text count)")
            return True, count, ""
        
        logger.warning(f"   ⚠ Could not determine result count")
        return True, 0, "Could not find results"
        
    except Exception as e:
        logger.error(f"    ✗ Search error: {e}")
        return False, 0, f"Search error: {str(e)}"

# =========================================================================
# RESULT PARSING
# =========================================================================

def get_result_items(driver: webdriver.Chrome) -> List[SearchResultItem]:
    """
    Get all result items from current results page.
    
    Returns:
        List of SearchResultItem
    """
    items = []
    
    try:
        # Get full page text
        body_text = driver.find_element(By.TAG_NAME, "body").text
        
        # Split by "Diário publicado em:" to find each result
        # Pattern: "Diário publicado em: DD/MM/YYYY - Edição XXX - Pág. YY"
        result_pattern = r"Diário publicado em:\s*(\d{2}/\d{2}/\d{4})\s*-\s*Edição\s*(\d+)\s*-\s*Pág\.\s*(\d+)"
        matches = list(re.finditer(result_pattern, body_text))
        
        logging.info(f"   📋 Found {len(matches)} result cards on this page")
        
        for i, match in enumerate(matches):
            pub_date = match.group(1)
            edition = match.group(2)
            page = match.group(3)
            
            # Get the preview text (text between this match and next, or end)
            start_pos = match.start()
            if i + 1 < len(matches):
                end_pos = matches[i + 1].start()
            else:
                end_pos = min(start_pos + 1500, len(body_text))
            
            preview_text = body_text[start_pos:end_pos]
            
            # Check if it contains EXTRATO
            has_extrato = any(
                extrato_type.lower() in preview_text.lower()
                for extrato_type in TARGET_EXTRATO_TYPES
            )
            
            item = SearchResultItem(
                index=i,
                publication_date=pub_date,
                edition_number=edition,
                page_number=page,
                preview_text=preview_text[:500],
                has_extrato=has_extrato
            )
            
            items.append(item)
            
            extrato_marker = "✓ EXTRATO" if has_extrato else ""
            logging.info(f"      [{i}] {pub_date} - Ed.{edition} - Pág.{page} {extrato_marker}")
        
    except Exception as e:
        logger.error(f"    ✗ Error getting result items: {e}")
    
    return items

def get_total_pages(driver: webdriver.Chrome) -> int:
    """
    Get total number of result pages.
    
    Returns:
        Number of pages (minimum 1)
    """
    try:
        # Look for pagination info "página X de Y"
        page_info = driver.find_elements(
            By.XPATH,
            "//*[contains(text(), 'página') and contains(text(), 'de')]"
        )
        
        for elem in page_info:
            match = re.search(r"p[aá]gina\s+\d+\s+de\s+(\d+)", elem.text, re.IGNORECASE)
            if match:
                return int(match.group(1))
        
        # Fallback: count pagination links
        pagination_links = driver.find_elements(
            By.XPATH,
            "//ul[contains(@class, 'pagination')]//a"
        )
        
        if pagination_links:
            page_numbers = []
            for link in pagination_links:
                text = link.text.strip()
                if text.isdigit():
                    page_numbers.append(int(text))
            
            if page_numbers:
                return max(page_numbers)
        
        return 1
        
    except Exception:
        return 1


def go_to_page(driver: webdriver.Chrome, page_num: int) -> bool:
    """
    Navigate to a specific results page.
    """
    try:
        page_link = driver.find_element(
            By.XPATH,
            f"//ul[contains(@class, 'pagination')]//a[normalize-space(text())='{page_num}']"
        )
        
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", page_link)
        time.sleep(0.3)
        page_link.click()
        
        time.sleep(2)
        
        logging.info(f"   📄 Navigated to page {page_num}")
        return True
        
    except Exception as e:
        logger.warning(f"   ⚠ Could not navigate to page {page_num}: {e}")
        return False

import requests

def download_pdf_directly(url: str, temp_folder: Path) -> Optional[Path]:
    """
    Download PDF directly using requests instead of Selenium.
    More reliable than browser downloads.
    """
    try:
        logging.info(f"   📥 Downloading directly: {url}")
        
        # Extract filename from URL or create one
        # URL format: https://doweb.rio.rj.gov.br/portal/edicoes/download/13857/86
        parts = url.rstrip('/').split('/')
        if len(parts) >= 2:
            edition = parts[-2]
            page = parts[-1]
            filename = f"rio_de_janeiro_ed{edition}_pag{page}.pdf"
        else:
            filename = f"download_{int(time.time())}.pdf"
        
        filepath = temp_folder / filename
        
        # Download with requests
        response = requests.get(url, timeout=60, stream=True)
        response.raise_for_status()
        
        # Save to file
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        file_size = filepath.stat().st_size
        logging.info(f"   ✓ Downloaded: {filename} ({file_size} bytes)")
        
        return filepath
        
    except Exception as e:
        logger.error(f"    ✗ Direct download failed: {e}")
        return None

# =========================================================================
# DOWNLOAD FUNCTIONS
# =========================================================================

def download_result_pdf(
    driver: webdriver.Chrome,
    result_index: int,
    temp_folder: Path
) -> Tuple[Optional[Path], Optional[str]]:
    """
    Download the PDF for a specific result.
    Uses direct HTTP download for reliability.
    
    Returns:
        Tuple of (pdf_path, download_url) or (None, None)
    """
    try:
        # Clear temp folder first
        clear_temp_folder(temp_folder)
        
        # Find all Download buttons
        download_buttons = driver.find_elements(
            By.XPATH,
            "//a[contains(text(), 'Download')] | //button[contains(text(), 'Download')] | //span[contains(text(), 'Download')]"
        )
        
        logging.info(f"   🔽 Found {len(download_buttons)} Download buttons")
        
        if result_index >= len(download_buttons):
            logger.error(f"    ✗ Result index {result_index} out of range")
            return None, None
        
        download_btn = download_buttons[result_index]
        
        # Scroll into view and click
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", download_btn)
        time.sleep(0.5)
        driver.execute_script("arguments[0].click();", download_btn)
        logging.info(f"   📥 Clicked Download button [{result_index}]")
        time.sleep(1.5)
        
        # Find "Baixar apenas a página" link and get URL
        try:
            download_page_link = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((
                    By.XPATH,
                    "//a[contains(text(), 'Baixar apenas a página')]"
                ))
            )
            
            pdf_url = download_page_link.get_attribute("href")
            logging.info(f"   🔗 PDF URL: {pdf_url}")
            
            # Close the dropdown
            driver.find_element(By.TAG_NAME, "body").click()
            time.sleep(0.3)
            
            # Download directly via requests
            pdf_path = download_pdf_directly(pdf_url, temp_folder)
            
            if pdf_path:
                return pdf_path, pdf_url
            else:
                return None, pdf_url
            
        except TimeoutException:
            logger.error(f"    ✗ Could not find 'Baixar apenas a página' link")
            driver.find_element(By.TAG_NAME, "body").click()
            return None, None
        
    except Exception as e:
        logger.error(f"    ✗ Download error: {e}")
        return None, None

def get_download_link(driver: webdriver.Chrome, result_index: int) -> Optional[str]:
    """
    Get the download link for a specific result without downloading.
    """
    try:
        # Find all Download buttons
        download_buttons = driver.find_elements(
            By.XPATH,
            "//a[contains(text(), 'Download')] | //button[contains(text(), 'Download')] | //span[contains(text(), 'Download')]"
        )
        
        if result_index >= len(download_buttons):
            return None
        
        download_btn = download_buttons[result_index]
        
        # Scroll into view
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", download_btn)
        time.sleep(0.5)
        
        # Click to show dropdown
        driver.execute_script("arguments[0].click();", download_btn)
        time.sleep(1)
        
        # Get the link
        try:
            download_link = WebDriverWait(driver, 3).until(
                EC.presence_of_element_located((
                    By.XPATH,
                    "//a[contains(text(), 'Baixar apenas a página')]"
                ))
            )
            url = download_link.get_attribute("href")
            
            # Close dropdown
            driver.find_element(By.TAG_NAME, "body").click()
            time.sleep(0.3)
            
            return url
            
        except TimeoutException:
            # Close dropdown
            driver.find_element(By.TAG_NAME, "body").click()
            return None
        
    except Exception as e:
        logger.warning(f"   ⚠ Could not get download link: {e}")
        return None

# =========================================================================
# MAIN SEARCH AND EXTRACT FUNCTION
# =========================================================================

def search_and_extract_publication(
    processo: str,
    headless: bool = False
) -> PublicationResult:
    """
    Main function: Search for processo, find matching EXTRATO, extract data.
    
    Strategy:
    1. Search DOWEB for the processo
    2. Iterate through results (with pagination)
    3. For each result with "EXTRATO":
       a. Download PDF (temp)
       b. Check if it contains our processo
       c. If YES → extract data, store link, return
       d. If NO → delete temp PDF, continue
    4. If nothing found → return not found result
    
    Args:
        processo: Processo number to search
        headless: Run browser in headless mode
        
    Returns:
        PublicationResult with extracted data or error info
    """
    logging.info("\n" + "=" * 60)
    logging.info(f"🔎 DOWEB SEARCH: {processo}")
    logging.info("=" * 60)
    
    driver = None
    temp_folder = ensure_temp_folder()
    results_checked = 0
    pages_navigated = 0
    total_results = 0
    
    try:
        # Initialize driver
        driver = create_download_driver(download_dir=str(temp_folder), headless=headless)
        if not driver:
            return create_error_result(processo, "Failed to initialize driver", "initialization")
        
        # Search for processo
        success, total_results, error = search_processo(driver, processo)
        
        if not success:
            return create_error_result(processo, error, "search")
        
        if total_results == 0:
            return create_not_found_result(
                processo,
                results_total=0,
                results_checked=0,
                pages_navigated=1,
                reason="No search results found"
            )
        
        # Get total pages
        total_pages = get_total_pages(driver)
        logging.info(f"   📚 Total pages: {total_pages}")
        
        # Iterate through all pages
        for page_num in range(1, total_pages + 1):
            pages_navigated = page_num
            
            if page_num > 1:
                if not go_to_page(driver, page_num):
                    continue
            
            # Get results on this page
            result_items = get_result_items(driver)
            
            # Filter for items that might have EXTRATO
            extrato_items = [item for item in result_items if item.has_extrato]
            
            logging.info(f"   📋 Page {page_num}: {len(extrato_items)} item(s) with EXTRATO")
            
            # Check each EXTRATO item
            for item in extrato_items:
                results_checked += 1
                logging.info(f"\n   → Checking result [{item.index}]: {item.publication_date} - Ed.{item.edition_number} - Pág.{item.page_number}")
                
                # Download the PDF (now returns tuple)
                pdf_path, pdf_url = download_result_pdf(driver, item.index, temp_folder)
                
                if not pdf_path:
                    logger.warning(f"      ⚠ Could not download PDF, skipping...")
                    continue
                
                # Extract and check if it matches our processo
                found, extracted_data, error = extract_publication_from_pdf(
                    str(pdf_path),
                    processo
                )
                
                if found:
                    logging.info(f"      ✅ MATCH FOUND!")
                    
                    # Use the URL we already have
                    download_link = pdf_url
                    if not download_link:
                        download_link = f"{DOWEB_BASE_URL}/portal/edicoes/download/{item.edition_number}/{item.page_number}"
                    
                    # Delete temp PDF
                    delete_temp_pdf(pdf_path)
                    
                    # Build result
                    result = PublicationResult(
                        processo_searched=processo,
                        found=True,
                        search_results_total=total_results,
                        results_checked=results_checked,
                        pages_navigated=pages_navigated,
                        publication_date=item.publication_date,
                        edition_number=item.edition_number,
                        page_number=item.page_number,
                        download_link=download_link,
                        orgao=extracted_data.get("orgao"),
                        tipo_extrato=extracted_data.get("tipo_extrato"),
                        processo_instrutivo=extracted_data.get("processo_instrutivo"),
                        numero_contrato=extracted_data.get("numero_contrato"),
                        data_assinatura=extracted_data.get("data_assinatura"),
                        partes=extracted_data.get("partes"),
                        objeto=extracted_data.get("objeto"),
                        prazo=extracted_data.get("prazo"),
                        valor=extracted_data.get("valor"),
                        programa_trabalho=extracted_data.get("programa_trabalho"),
                        natureza_despesa=extracted_data.get("natureza_despesa"),
                        nota_empenho=extracted_data.get("nota_empenho"),
                        fundamento=extracted_data.get("fundamento"),
                        raw_text=extracted_data.get("raw_text"),
                    )
                    
                    return result
                
                else:
                    logger.error(f"      ❌ Not a match: {error}")
                    delete_temp_pdf(pdf_path)
                    continue
        
        # Checked everything, nothing found
        logger.error(f"\n   ❌ No matching publication found after checking {results_checked} result(s)")
        
        return create_not_found_result(
            processo,
            results_total=total_results,
            results_checked=results_checked,
            pages_navigated=pages_navigated,
            reason=f"Checked {results_checked} EXTRATO results, none matched processo {processo}"
        )
        
    except Exception as e:
        logger.error(f"    ✗ Error: {e}")
        return create_error_result(processo, str(e), "extraction")
    
    finally:
        # Cleanup
        clear_temp_folder(temp_folder)
        if driver:
            close_driver(driver)

# =========================================================================
# BATCH PROCESSING
# =========================================================================

def search_multiple_processos(
    processos: List[str],
    headless: bool = True
) -> List[PublicationResult]:
    """
    Search for multiple processos.
    """
    results = []
    total = len(processos)
    
    logging.info(f"\n{'='*60}")
    logging.info(f"📚 BATCH SEARCH: {total} processo(s)")
    logging.info("=" * 60)
    
    for i, processo in enumerate(processos, 1):
        logging.info(f"\n[{i}/{total}] Processing: {processo}")
        
        result = search_and_extract_publication(processo, headless=headless)
        results.append(result)
        
        status = "✅ FOUND" if result.found else "❌ NOT FOUND"
        logging.info(f"   Result: {status}")
        
        if i < total:
            time.sleep(2)
    
    found_count = sum(1 for r in results if r.found)
    logging.info(f"\n{'='*60}")
    logging.info(f"📊 BATCH COMPLETE: {found_count}/{total} found")
    logging.info("=" * 60)
    
    return results


# =========================================================================
# EXPORT FUNCTIONS
# =========================================================================

def export_results_to_json(results: List[PublicationResult], output_path: str) -> str:
    """Export results to JSON file."""
    import json
    
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    
    data = [r.to_dict() for r in results]
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    logging.info(f"📁 Exported to: {output_path}")
    return output_path


# =========================================================================
# STANDALONE TEST
# =========================================================================

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        logging.info("Usage: python doweb_scraper.py <processo_number> [--headless]")
        logging.info("Example: python doweb_scraper.py SME-PRO-2025/19222")
        logging.info("Example: python doweb_scraper.py SME-PRO-2025/19222 --headless")
        sys.exit(1)
    
    processo = sys.argv[1]
    headless = "--headless" in sys.argv
    
    result = search_and_extract_publication(processo, headless=headless)
    
    logging.info("\n" + "=" * 60)
    logging.info("📊 FINAL RESULT")
    logging.info("=" * 60)
    
    import json
    logging.info(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))