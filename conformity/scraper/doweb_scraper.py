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
from datetime import datetime, timedelta
import requests
import json

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
        "EXTRATO DE INSTRUMENTO CONTRATUAL",  # Added this!  
        "EXTRATO DE CONVÊNIO",  
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
        
        extrato_keywords = [
            "EXTRATO",
            "extrato",
            "Extrato",
            "CONTRATO",
            "Contrato",
            "contrato",
            "TERMO ADITIVO",
            "Termo Aditivo",
            "termo aditivo",
            "ADITIVO",
            "Aditivo",
        ]
        
        # Priority keywords (these are more specific)
        priority_keywords = [
            "EXTRATO DO CONTRATO",
            "EXTRATO DE CONTRATO",
            "Extrato do Contrato",
            "EXTRATO DE TERMO ADITIVO",
            "EXTRATO DO TERMO ADITIVO",
            "Extrato de Termo Aditivo",
        ]

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
            
            has_extrato = False
            is_priority = False
            matched_keyword = None

            # First check priority keywords
            for keyword in priority_keywords:
                if keyword.lower() in preview_text.lower():
                    has_extrato = True
                    is_priority = True
                    matched_keyword = keyword
                    break

            # If not found, check general keywords
            if not has_extrato:
                for keyword in extrato_keywords:
                    if keyword.lower() in preview_text.lower():
                        has_extrato = True
                        is_priority = False
                        matched_keyword = keyword
                        break

            item = SearchResultItem(
                index=i,
                publication_date=pub_date,
                edition_number=edition,
                page_number=page,
                preview_text=preview_text[:500],
                has_extrato=has_extrato
            )
            
            items.append(item)

            # Better logging
            if has_extrato:
                marker = "🎯 HIGH PRIORITY" if is_priority else "✓ EXTRATO"
                logging.info(f"      [{i}] {pub_date} - Ed.{edition} - Pág.{page} {marker} ('{matched_keyword}')")
            else:
                logging.info(f"      [{i}] {pub_date} - Ed.{edition} - Pág.{page}")
   

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
        
        # ═══════════════════════════════════════════════════════════
        # NEW: If NO extratos found, log preview of first result for debugging
        # ═══════════════════════════════════════════════════════════
        if items and not any(item.has_extrato for item in items):
            logging.warning(f"   ⚠️  No EXTRATO keywords detected in any result!")
            logging.info(f"   📄 First result preview (first 300 chars):")
            logging.info(f"   {items[0].preview_text[:300]}")
            logging.info(f"   ...")
            
            # Check if EXTRATO might be there but with different formatting
            if "extrato" in items[0].preview_text.lower():
                logging.warning(f"   🤔 Wait... 'extrato' IS in the text but wasn't matched!")
                logging.warning(f"   This might be a case sensitivity or encoding issue")
        
    except Exception as e:
        logging.error(f"   ❌ Error getting result items: {e}")
        import traceback
        logging.debug(traceback.format_exc())
    
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
    3. Classify results by priority:
       - High priority: Contains "EXTRATO DO CONTRATO" or "EXTRATO DE TERMO ADITIVO"
       - Medium priority: Contains "EXTRATO" or "CONTRATO"
       - Low priority: Any other result
    4. Check high priority first, then medium, then low
    5. For each result:
       a. Download PDF (temp)
       b. Check if it contains our processo
       c. If YES → extract data, store link, return
       d. If NO → delete temp PDF, continue
    6. If nothing found → return not found result
    
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

            # ═══════════════════════════════════════════════════════════
            # NEW: Classify results by priority
            # ═══════════════════════════════════════════════════════════
            high_priority = [item for item in result_items if item.has_extrato and 
                           any(kw in item.preview_text.upper() for kw in 
                               ["EXTRATO DO CONTRATO", "EXTRATO DE CONTRATO", 
                                "EXTRATO DE TERMO ADITIVO", "EXTRATO DO TERMO ADITIVO"])]
            
            medium_priority = [item for item in result_items if item.has_extrato and item not in high_priority]
            
            low_priority = [item for item in result_items if not item.has_extrato]
            
            logging.info(f"   📋 Page {page_num}: {len(result_items)} total " +
                        f"(Priority: {len(high_priority)} Contract, {len(medium_priority)} Extrato, {len(low_priority)} Others)")
            
            # ═══════════════════════════════════════════════════════════
            # NEW: If no high/medium priority, still check some low priority
            # ═══════════════════════════════════════════════════════════
            items_to_check = high_priority + medium_priority
            
            if not items_to_check and low_priority:
                logging.warning(f"   ⚠️  No EXTRATO found, will check first 3 general results")
                items_to_check = low_priority[:3]
            
            # Check each item
            for item in items_to_check:
                results_checked += 1
                priority_marker = "🎯" if item in high_priority else "✓" if item in medium_priority else "📄"
                logging.info(f"\n   → [{results_checked}] {priority_marker} Checking: {item.publication_date} - Ed.{item.edition_number} - Pág.{item.page_number}")
                
                # Download the PDF (now returns tuple)
                pdf_path, pdf_url = download_result_pdf(driver, item.index, temp_folder)
                
                if not pdf_path:
                    logging.warning(f"      ⚠️  Could not download PDF, skipping...")
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


# =========================================================================
# CONFIGURATION
# =========================================================================

# Maximum PDFs to download and check (to avoid checking hundreds of results)
MAX_CANDIDATES_TO_CHECK = 5

# Score thresholds
MIN_CANDIDATE_SCORE = 0.0  # Minimum score to be considered (0 = check all)

# Keywords that increase candidate score
POSITIVE_KEYWORDS = {
    'contrato': 3,
    'extrato': 5,
    'termo aditivo': 4,
    'aditivo': 2,
    'instrumento': 2,
    'publicação': 1,
}

# Keywords in orgao names (adjust based on your needs)
ORGAO_KEYWORDS = {
    'riotur': 2,
    'secretaria': 1,
    'companhia': 1,
    'fundação': 1,
    'município': 1,
}


# =========================================================================
# CANDIDATE SCORING SYSTEM
# =========================================================================

class CandidateResult:
    """Represents a search result with scoring."""
    
    def __init__(self, item: 'SearchResultItem', score: float = 0.0):
        self.item = item
        self.score = score
        self.score_breakdown = {}
    
    def add_score(self, reason: str, points: float):
        """Add points to score with reason."""
        self.score += points
        self.score_breakdown[reason] = points
    
    def __repr__(self):
        return f"Candidate({self.item.publication_date}, score={self.score:.1f})"


def score_candidate(
    item: 'SearchResultItem',
    processo: str,
    contract_date: Optional[str] = None
) -> CandidateResult:
    """
    Score a search result to determine if it's a good candidate.
    
    Args:
        item: Search result item
        processo: Processo number we're looking for
        contract_date: Contract signature date (DD/MM/YYYY) for date proximity scoring
        
    Returns:
        CandidateResult with score
    """
    candidate = CandidateResult(item)
    preview_lower = item.preview_text.lower()
    
    # 1. Check for positive keywords in preview
    for keyword, points in POSITIVE_KEYWORDS.items():
        if keyword in preview_lower:
            candidate.add_score(f"keyword:{keyword}", points)
    
    # 2. Check for orgao keywords
    for keyword, points in ORGAO_KEYWORDS.items():
        if keyword in preview_lower:
            candidate.add_score(f"orgao:{keyword}", points)
    
    # 3. Check if processo appears in preview
    if processo.lower() in preview_lower or processo.upper() in item.preview_text:
        candidate.add_score("processo_in_preview", 10)
    
    # 4. Date proximity scoring (if contract_date provided)
    if contract_date:
        try:
            pub_date = datetime.strptime(item.publication_date, "%d/%m/%Y")
            contract_dt = datetime.strptime(contract_date, "%d/%m/%Y")
            
            days_diff = abs((pub_date - contract_dt).days)
            
            # Publications usually happen within 30 days of signing
            if days_diff <= 7:
                candidate.add_score("date_within_7_days", 8)
            elif days_diff <= 15:
                candidate.add_score("date_within_15_days", 5)
            elif days_diff <= 30:
                candidate.add_score("date_within_30_days", 3)
            elif days_diff <= 60:
                candidate.add_score("date_within_60_days", 1)
            else:
                candidate.add_score("date_far", -2)  # Negative score for very old/future
        except:
            pass
    
    # 5. Bonus for recent publications (assuming we're checking recent contracts)
    try:
        pub_date = datetime.strptime(item.publication_date, "%d/%m/%Y")
        days_ago = (datetime.now() - pub_date).days
        
        if days_ago <= 30:
            candidate.add_score("recent_publication", 2)
        elif days_ago <= 90:
            candidate.add_score("fairly_recent", 1)
    except:
        pass
    
    return candidate


def rank_candidates(
    items: List['SearchResultItem'],
    processo: str,
    contract_date: Optional[str] = None
) -> List[CandidateResult]:
    """
    Score and rank all search results.
    
    Returns:
        List of CandidateResult sorted by score (highest first)
    """
    candidates = []
    
    for item in items:
        candidate = score_candidate(item, processo, contract_date)
        candidates.append(candidate)
    
    # Sort by score (highest first)
    candidates.sort(key=lambda c: c.score, reverse=True)
    
    return candidates


# =========================================================================
# AI-POWERED PDF VERIFICATION
# =========================================================================

def verify_pdf_contains_processo_with_ai(
    pdf_path: Path,
    processo: str,
    quick_check: bool = True
) -> Tuple[bool, dict, str]:
    """
    Use AI to verify if a PDF contains the specific processo and extract data.
    
    This is more reliable than simple text matching because:
    - AI can understand context
    - AI can handle OCR errors
    - AI can extract structured data in one pass
    
    Args:
        pdf_path: Path to PDF file
        processo: Processo number to look for
        quick_check: If True, only check first few pages for processo
        
    Returns:
        Tuple of (found, extracted_data, error_message)
    """
    try:
        # First, do a quick text extraction to see if processo is there
        from conformity.scraper.doweb_extractor import extract_text_from_pdf
        
        success, text, error = extract_text_from_pdf(str(pdf_path))
        
        if not success:
            return False, {}, f"Could not extract text: {error}"
        
        # Quick check: is the processo even mentioned?
        processo_normalized = processo.replace('-', '').replace('/', '').replace(' ', '').lower()
        text_normalized = text.replace('-', '').replace('/', '').replace(' ', '').lower()
        
        if processo_normalized not in text_normalized:
            return False, {}, "Processo number not found in PDF text"
        
        logging.info(f"      ✓ Processo {processo} appears in PDF text")
        
        # Now use AI to extract the EXTRATO structure
        extracted = extract_extrato_with_ai(text, processo)
        
        if extracted and extracted.get("processo_matched"):
            return True, extracted, ""
        else:
            return False, {}, "AI could not confirm processo match or extract data"
        
    except Exception as e:
        return False, {}, f"Error in AI verification: {str(e)}"


def extract_extrato_with_ai(text: str, processo: str) -> dict:
    """
    Use AI to extract EXTRATO structure from PDF text.
    
    Returns structured data like:
    {
        "processo_matched": True/False,
        "processo_instrutivo": "TUR-PRO-2025/00350",
        "instrumento": "Termo de Contrato n° 085/2025",
        "assinatura": "28/02/2025",
        "valor": "R$ 40.000,00",
        "partes": "RIOTUR e a DANIELLA...",
        "objeto": "...",
        ...
    }
    """
    from langchain_groq import ChatGroq
    import os
    
    # Use the same model as contract extraction
    model = ChatGroq(
        model_name="llama-3.3-70b-versatile",
        temperature=0.1,  # Lower temp for precise extraction
        max_tokens=2048,
        api_key=os.getenv("GROQ_API_KEY")
    )
    
    # Truncate text if too long (focus on first part where EXTRATO usually is)
    max_chars = 8000
    text_to_analyze = text[:max_chars]
    
    prompt = f"""Analise o texto abaixo, que é de um Diário Oficial (D.O. Rio).

TAREFA CRÍTICA:
1. Verifique se existe um EXTRATO que menciona o processo "{processo}"
2. Se SIM, extraia TODOS os campos do EXTRATO
3. Se NÃO, retorne "processo_matched": false

FORMATO ESPERADO DO EXTRATO:
[ÓRGÃO]
EXTRATO DE INSTRUMENTO CONTRATUAL (ou similar)
PROCESSO INSTRUTIVO Nº: XXX-XXX-YYYY/NNNNN
INSTRUMENTO: ...
ASSINATURA: DD/MM/YYYY
VALOR: R$ ...
PARTES: ...
OBJETO: ...
NOTA DE EMPENHO: ...
PROGRAMA DE TRABALHO: ...
NATUREZA DE DESPESAS: ...
FUNDAMENTO: ...

TEXTO DO D.O.:
{text_to_analyze}

Retorne APENAS JSON (sem markdown):
{{
  "processo_matched": true/false,
  "processo_instrutivo": "...",
  "orgao": "...",
  "tipo_extrato": "EXTRATO DE INSTRUMENTO CONTRATUAL",
  "instrumento": "...",
  "numero_contrato": "...",
  "assinatura": "DD/MM/YYYY",
  "valor": "R$ ...",
  "partes": "...",
  "objeto": "...",
  "nota_empenho": "...",
  "valor_empenho": "...",
  "programa_trabalho": "...",
  "natureza_despesa": "...",
  "fundamento": "...",
  "razao": "..."
}}

IMPORTANTE:
- processo_matched = true APENAS se o processo "{processo}" está no EXTRATO
- Se não encontrar o EXTRATO, retorne processo_matched = false
- Use null para campos não encontrados"""

    try:
        response = model.invoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)
        
        # Clean and parse JSON
        content_clean = content.strip()
        
        # Remove markdown code blocks if present
        if content_clean.startswith("```"):
            content_clean = re.sub(r'```json\s*|\s*```', '', content_clean)
        
        extracted = json.loads(content_clean)
        
        logging.info(f"      🤖 AI verification: processo_matched = {extracted.get('processo_matched', False)}")
        
        return extracted
        
    except Exception as e:
        logging.error(f"      ❌ AI extraction failed: {e}")
        return {"processo_matched": False, "error": str(e)}


# =========================================================================
# IMPROVED SEARCH AND EXTRACT FUNCTION
# =========================================================================

def search_and_extract_publication_v2(
    processo: str,
    contract_date: Optional[str] = None,
    headless: bool = False,
    max_candidates: int = MAX_CANDIDATES_TO_CHECK
) -> 'PublicationResult':
    """
    IMPROVED VERSION: Smart candidate selection + AI verification.
    
    Args:
        processo: Processo number to search
        contract_date: Contract signature date (DD/MM/YYYY) for better candidate scoring
        headless: Run browser in headless mode
        max_candidates: Maximum number of PDFs to download and check
        
    Returns:
        PublicationResult with extracted data or error info
    """
    logging.info("\n" + "=" * 60)
    logging.info(f"🔎 DOWEB SEARCH V2 (AI-Powered): {processo}")
    if contract_date:
        logging.info(f"   Contract date: {contract_date}")
    logging.info("=" * 60)
    
    driver = None
    temp_folder = ensure_temp_folder()
    results_checked = 0
    pages_navigated = 0
    total_results = 0
    
    try:
        # Initialize driver
        from core.driver import create_download_driver, close_driver
        driver = create_download_driver(download_dir=str(temp_folder), headless=headless)
        if not driver:
            from conformity.models.publication import create_error_result
            return create_error_result(processo, "Failed to initialize driver", "initialization")
        
        # Search for processo
        success, total_results, error = search_processo(driver, processo)
        
        if not success:
            from conformity.models.publication import create_error_result
            return create_error_result(processo, error, "search")
        
        if total_results == 0:
            from conformity.models.publication import create_not_found_result
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
        
        # Collect ALL results from all pages first
        all_items = []
        
        for page_num in range(1, min(total_pages + 1, 3)):  # Limit to first 3 pages
            pages_navigated = page_num
            
            if page_num > 1:
                if not go_to_page(driver, page_num):
                    continue
            
            items = get_result_items(driver)
            all_items.extend(items)
            logging.info(f"   📋 Page {page_num}: {len(items)} items found")
        
        if not all_items:
            from conformity.models.publication import create_not_found_result
            return create_not_found_result(
                processo,
                results_total=total_results,
                results_checked=0,
                pages_navigated=pages_navigated,
                reason="No result items could be parsed"
            )
        
        # ═══════════════════════════════════════════════════════════
        # NEW: Score and rank all candidates
        # ═══════════════════════════════════════════════════════════
        logging.info(f"\n   🎯 Ranking {len(all_items)} candidates...")
        
        candidates = rank_candidates(all_items, processo, contract_date)
        
        # Show top candidates
        logging.info(f"\n   📊 Top {min(10, len(candidates))} candidates:")
        for i, candidate in enumerate(candidates[:10], 1):
            item = candidate.item
            logging.info(f"      {i}. Score {candidate.score:.1f} - {item.publication_date} - Ed.{item.edition_number} - Pág.{item.page_number}")
            if candidate.score_breakdown:
                breakdown = ", ".join(f"{k}:{v:+.1f}" for k, v in sorted(candidate.score_breakdown.items(), key=lambda x: -x[1])[:3])
                logging.info(f"         ({breakdown})")
        
        # ═══════════════════════════════════════════════════════════
        # NEW: Check top candidates with AI verification
        # ═══════════════════════════════════════════════════════════
        candidates_to_check = candidates[:max_candidates]
        
        logging.info(f"\n   🔍 Checking top {len(candidates_to_check)} candidate(s)...")
        
        for i, candidate in enumerate(candidates_to_check, 1):
            item = candidate.item
            results_checked += 1
            
            logging.info(f"\n   → [{i}/{len(candidates_to_check)}] Checking: {item.publication_date} - Ed.{item.edition_number} - Pág.{item.page_number} (score: {candidate.score:.1f})")
            
            # Download PDF
            pdf_path, pdf_url = download_result_pdf(driver, item.index, temp_folder)
            
            if not pdf_path:
                logging.warning(f"      ⚠️  Could not download PDF")
                continue
            
            # AI-powered verification
            logging.info(f"      🤖 Verifying with AI...")
            found, extracted_data, error = verify_pdf_contains_processo_with_ai(
                pdf_path,
                processo,
                quick_check=True
            )
            
            if found:
                logging.info(f"      ✅ MATCH CONFIRMED BY AI!")
                
                # Use the URL we already have
                download_link = pdf_url or f"https://doweb.rio.rj.gov.br/portal/edicoes/download/{item.edition_number}/{item.page_number}"
                
                # Delete temp PDF
                delete_temp_pdf(pdf_path)
                
                # Build result
                from conformity.models.publication import PublicationResult
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
                    data_assinatura=extracted_data.get("assinatura"),
                    partes=extracted_data.get("partes"),
                    objeto=extracted_data.get("objeto"),
                    prazo=extracted_data.get("prazo"),
                    valor=extracted_data.get("valor"),
                    programa_trabalho=extracted_data.get("programa_trabalho"),
                    natureza_despesa=extracted_data.get("natureza_despesa"),
                    nota_empenho=extracted_data.get("nota_empenho"),
                    fundamento=extracted_data.get("fundamento"),
                    raw_text=str(extracted_data),
                )
                
                return result
            else:
                logging.error(f"      ❌ Not a match: {error}")
                delete_temp_pdf(pdf_path)
                continue
        
        # Checked top candidates, nothing found
        logging.error(f"\n   ❌ No matching publication found after checking {results_checked} candidate(s)")
        
        from conformity.models.publication import create_not_found_result
        return create_not_found_result(
            processo,
            results_total=total_results,
            results_checked=results_checked,
            pages_navigated=pages_navigated,
            reason=f"Checked top {results_checked} candidates, none matched processo {processo}"
        )
        
    except Exception as e:
        logging.error(f"   ❌ Error: {e}")
        import traceback
        logging.error(traceback.format_exc())
        from conformity.models.publication import create_error_result
        return create_error_result(processo, str(e), "extraction")
    
    finally:
        # Cleanup
        clear_temp_folder(temp_folder)
        if driver:
            from core.driver import close_driver
            close_driver(driver)


# =========================================================================
# BACKWARD COMPATIBILITY
# =========================================================================

def search_and_extract_publication(
    processo: str,
    headless: bool = False,
    contract_date: Optional[str] = None
) -> 'PublicationResult':
    """
    Main entry point - now uses V2 strategy by default.
    
    Kept for backward compatibility with existing code.
    """
    return search_and_extract_publication_v2(
        processo=processo,
        contract_date=contract_date,
        headless=headless
    )