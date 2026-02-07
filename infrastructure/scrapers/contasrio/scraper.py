"""
scraper.py:
- scroll_and_collect_rows: 2-pass scroll, validate rows, wait+0.5s
- parse_row_data: negative nums, alphanumeric IDs, last 5 currency numbers
- filter_by_company: wait 3s
- click_company_button: 5 retries, 3 click methods, verify level transition
- get_all_document_links: search 'processo' href, extract from URL, return list
- get_current_level, get_all_buttons_at_level, click_specific_button, has_processo_links
- discover_all_paths, discover_paths_recursive (tree traversal)
- reset_and_navigate_to_company (BASE_URL first, verify transitions)
- follow_path_and_collect
- REMOVED: click_ug_button, click_next_level
main.py:
- process_single_company: reset first, discover paths, collect processos, return list
- main: loop ALL companies, progress counter, periodic save, error handling
reporter.py:
- add "document_text", "document_url", "Processo", "Link Documento"
Key: doc_link["processo"] → "document_text" → Excel "Processo"
Reset: BASE_URL → CONTRACTS_URL → year → filter → click → verify
Known issue: Path discovery may mix buttons from different branches (to fix later)
"""
"""
scraper.py - Web scraping functions for ContasRio portal.
Handles browser automation, navigation, and data extraction.
"""

import numbers
import re
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    StaleElementReferenceException,
    NoSuchElementException
)
from datetime import datetime

# Import configuration
import sys
sys.path.append('..')
from config import (
    TIMEOUT_SECONDS, MAX_RETRIES, SCROLL_DELAY,
    BASE_URL, CONTRACTS_URL, VALUE_COLUMNS, LOCATORS
)

# Import from core modules                              
from infrastructure.web.driver import create_driver, close_driver 

import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

from infrastructure.web.navigation import (
    wait_for_element,
    get_current_level,
    set_year_filter,
    filter_by_company,
    click_company_button,
    get_all_buttons_at_level,
    click_specific_button,
    has_processo_links
)

from New_Data_ige.domain.parsing.company_row_parser import CompanyRowParser
from New_Data_ige.domain.models.company import CompanyData

# =============================================================================
# DRIVER MANAGEMENT (wrapper for backward compatibility)
# =============================================================================

def initialize_driver(headless=False):
    """
    Initialize Chrome WebDriver.
    
    This is a wrapper around core.driver.create_driver() for backward compatibility.
    """
    return create_driver(headless=headless)

# =============================================================================
# DRIVER MANAGEMENT delegated to core/driver.py
# =============================================================================

# =============================================================================
# NAVIGATION
# =============================================================================

def navigate_to_home(driver):
    """
    Navigate to the home page and wait for it to load.
    
    Args:
        driver: WebDriver instance
        
    Returns:
        True if successful, False otherwise
    """
    try:
        driver.get(BASE_URL)
        logging.info("Checando se o Site funciona. Aguardando carregamento da tela Home...")
        
        wait_for_element(driver, (By.XPATH, LOCATORS["home_menu"]))
        logging.info("✓ Home carregada!")
        return True
        
    except TimeoutException:
        logging.info("✗ Timeout ao carregar, site pode estar fora do ar.")
        return False


def navigate_to_contracts(driver, year=None):
    """
    Navigate to the contracts page with retry logic.
    
    Args:
        driver: WebDriver instance
        year: Optional integer/string, e.g. 2022. If provided, selects this year.
        
    Returns:
        True if successful, False otherwise
    """
    driver.get(CONTRACTS_URL)
    
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logging.info(f"Tentativa {attempt}: Aguardando carregamento do painel...")
            wait_for_element(driver, (By.XPATH, LOCATORS["table_rows"]))
            logging.info("✓ Painel carregado com sucesso!")

            # NEW: set the year filter before any scrolling happens
            if year:
                set_year_filter(driver, year)

            return True
            
        except TimeoutException:
            logging.info(f"Timeout na tentativa {attempt}.")
            if attempt == MAX_RETRIES:
                logger.error(f"✗ O painel não carregou após {MAX_RETRIES} tentativas.")
                return False
            logging.info("Atualizando a página...")
            driver.refresh()
            time.sleep(2)
    
    return False


# =============================================================================
# DATA COLLECTION
# =============================================================================

def scroll_and_collect_rows(driver):
    """
    Scroll through the dynamic table and collect all row data.
    Includes validation and verification pass for reliability.
    """
    logging.info("Iniciando scroll para carregar todas as linhas...")
    
    scroller = driver.find_element(By.CSS_SELECTOR, LOCATORS["grid_scroller"])
    
    all_rows = set()
    last_scroll = -1
    stopped_count = 0
    
    # ═══════════════════════════════════════════════════════════
    # VALIDATION PATTERN: A complete row must match this
    # ID - Company Name + numbers at the end
    # ═══════════════════════════════════════════════════════════
    complete_row_pattern = re.compile(
        r'^[\w\d\.\/\-]+\s*-\s*.+\s+-?[\d\.,]+\s+-?[\d\.,]+\s+-?[\d\.,]+.*$'
    )
    
    def is_complete_row(text):
        """Check if row has ID, company name, AND numbers."""
        if not text or "-" not in text:
            return False
        return bool(complete_row_pattern.match(text.strip()))
    
    # ═══════════════════════════════════════════════════════════
    # FIRST PASS: Scroll and collect
    # ═══════════════════════════════════════════════════════════
    logging.info("   Primeira passagem...")
    
    while True:
        time.sleep(SCROLL_DELAY + 0.5)
        
        visible_rows = driver.find_elements(By.CSS_SELECTOR, LOCATORS["grid_row"])
        
        for row in visible_rows:
            try:
                row_text = row.text.strip()
                if is_complete_row(row_text):
                    all_rows.add(row_text)
            except StaleElementReferenceException:
                continue
        
        driver.execute_script(
            "arguments[0].scrollTop += arguments[0].clientHeight;",
            scroller
        )
        time.sleep(SCROLL_DELAY)
        
        current_scroll = scroller.get_property("scrollTop")
        if current_scroll == last_scroll:
            stopped_count += 1
        else:
            stopped_count = 0
            
        if stopped_count >= 5:
            break
            
        last_scroll = current_scroll
    
    first_pass_count = len(all_rows)
    logging.info(f"   Primeira passagem: {first_pass_count} linhas")
    
    # ═══════════════════════════════════════════════════════════
    # VERIFICATION PASS: Scroll back to top and collect again
    # ═══════════════════════════════════════════════════════════
    logging.info("   Passagem de verificação...")
    
    driver.execute_script("arguments[0].scrollTop = 0;", scroller)
    time.sleep(1)
    
    last_scroll = -1
    stopped_count = 0
    
    while True:
        time.sleep(SCROLL_DELAY + 0.3)
        
        visible_rows = driver.find_elements(By.CSS_SELECTOR, LOCATORS["grid_row"])
        
        for row in visible_rows:
            try:
                row_text = row.text.strip()
                if is_complete_row(row_text):
                    all_rows.add(row_text)
            except StaleElementReferenceException:
                continue
        
        driver.execute_script(
            "arguments[0].scrollTop += arguments[0].clientHeight;",
            scroller
        )
        time.sleep(SCROLL_DELAY)
        
        current_scroll = scroller.get_property("scrollTop")
        if current_scroll == last_scroll:
            stopped_count += 1
        else:
            stopped_count = 0
            
        if stopped_count >= 5:
            break
            
        last_scroll = current_scroll
    
    new_rows = len(all_rows) - first_pass_count
    logging.info(f"   Verificação: +{new_rows} novas linhas encontradas")
    logging.info(f"✓ Scroll finalizado! Total de linhas: {len(all_rows)}")
    
    return all_rows

def parse_row_data(raw_rows: set) -> list[CompanyData]:
    """
    Parse raw row text into CompanyData objects.
    
    Args:
        raw_rows: Set of raw text strings from Selenium scraping
        
    Returns:
        List of CompanyData objects (valid rows only)
    
    This is the FINAL version - returns domain objects, not dicts.
    """
    logging.info("Processando dados das linhas...")
    logging.info(f"\nDEBUG: Total de linhas brutas recebidas: {len(raw_rows)}")
    
    parser = CompanyRowParser()
    companies = []
    
    # Track skips for logging
    skip_empty = 0
    skip_total = 0
    skip_numbers_only = 0
    skip_no_match = 0
    
    for row_text in raw_rows:
        company = parser.parse(row_text)
        
        if company:
            companies.append(company)
        else:
            # Track why it was skipped (for debugging logs)
            if not row_text.strip():
                skip_empty += 1
            elif "total" in row_text.lower():
                skip_total += 1
            elif re.match(r'^[\d\.,\s\-]+$', row_text.strip()):
                skip_numbers_only += 1
            else:
                skip_no_match += 1
    
    # Summary log
    logging.info(f"\n{'='*60}")
    logging.info(f"RESUMO DO PARSING:")
    logging.info(f"  ✓ Processadas com sucesso: {len(companies)}")
    logging.info(f"  ⊘ Vazias ignoradas: {skip_empty}")
    logging.info(f"  ⊘ Linhas 'total' ignoradas: {skip_total}")
    logging.info(f"  ⚠ Apenas números (incompletas): {skip_numbers_only}")
    logging.info(f"  ⚠ Não reconhecidas: {skip_no_match}")
    logging.info(f"  ─────────────────────────────")
    total_accounted = len(companies) + skip_empty + skip_total + skip_numbers_only + skip_no_match
    logging.info(f"  Σ Total contabilizado: {total_accounted} / {len(raw_rows)}")
    logging.info(f"{'='*60}")
    
    # Show first 5 for debugging
    logging.info("\n✓ Primeiros 5 registros:")
    for i, company in enumerate(companies[:5], start=1):
        logging.info(f"{i}: {company}")
    
    return companies

# =============================================================================
# LEVEL DETECTION AND PATH DISCOVERY
# =============================================================================

def discover_paths_recursive(driver, current_path, all_paths, company_id, original_caption, max_depth=10):
    """
    Recursively discover all paths by exploring each branch.
    """
    if len(current_path) >= max_depth:
        return
    
    # ═══════════════════════════════════════════════════════════
    # WAIT FOR PAGE TO LOAD (from original click_next_level)
    # ═══════════════════════════════════════════════════════════
    logging.info("\n   → Aguardando botões carregarem...")
    
    buttons = []
    level = "unknown"
    
    for attempt in range(6):
        time.sleep(1.5)
        
        # Check if we're at the deepest level (processo links visible)
        if has_processo_links(driver):
            all_paths.append(current_path.copy())
            logging.info(f"   ✓ Caminho completo encontrado: {' → '.join(current_path) if current_path else '(direto)'}")
            return
        
        # Get current level
        level = get_current_level(driver)
        
        # Get all buttons at this level (exclude what's already in path + company)
        exclude = set(current_path) | {original_caption}
        buttons = get_all_buttons_at_level(driver, exclude)
        
        if buttons:
            logging.info(f"   Tentativa {attempt + 1}: Nível '{level}', {len(buttons)} botão(ões) encontrado(s)")
            break
        else:
            logging.info(f"   Tentativa {attempt + 1}: Nível '{level}', aguardando botões...")
    
    if not buttons:
        # No buttons found after retries - check for processo links one more time
        if has_processo_links(driver):
            all_paths.append(current_path.copy())
            logging.info(f"   ✓ Caminho completo (sem botões): {' → '.join(current_path) if current_path else '(direto)'}")
        elif current_path:
            # Record incomplete path
            all_paths.append(current_path.copy())
            logging.info(f"   ⚠ Caminho incompleto: {' → '.join(current_path)}")
        else:
            logging.info("   ✗ Nenhum botão encontrado no primeiro nível")
        return
    
    logging.info(f"   Botões encontrados: {buttons[:5]}{'...' if len(buttons) > 5 else ''}")
    
    # Explore each button
    for i, btn_text in enumerate(buttons):
        logging.info(f"\n   --- Explorando branch {i+1}/{len(buttons)}: {btn_text} ---")
        
        # Click this button
        if click_specific_button(driver, btn_text):
            # Recurse with updated path
            new_path = current_path + [btn_text]
            discover_paths_recursive(driver, new_path, all_paths, company_id, original_caption, max_depth)
            
            # Reset to explore next branch (if there are more)
            if i < len(buttons) - 1:
                logging.info(f"   ↩ Resetando para explorar próximo branch...")
                if not reset_and_navigate_to_company(driver, company_id):
                    logging.info("   ✗ Falha ao resetar")
                    return
                
                # Re-navigate to current path position
                for path_btn in current_path:
                    time.sleep(0.5)
                    if not click_specific_button(driver, path_btn):
                        logger.error(f"    ✗ Falha ao re-navegar para: {path_btn}")
                        return
        else:
            logger.error(f"    ✗ Não foi possível clicar em: {btn_text}")

def reset_and_navigate_to_company(driver, company_id):
    """
    Reset to contracts page and navigate back to company.
    """
    from config import FILTER_YEAR, CONTRACTS_URL, BASE_URL
    
    logging.info(f"\n   ↩ Resetando para página de contratos...")
    
    # ═══════════════════════════════════════════════════════════
    # STEP 1: Go to HOME first to fully reset Vaadin state
    # ═══════════════════════════════════════════════════════════
    logging.info(f"   STEP 1: Navegando para HOME para resetar estado...")
    driver.get(BASE_URL)
    time.sleep(2)
    
    # ═══════════════════════════════════════════════════════════
    # STEP 2: Now navigate to contracts page
    # ═══════════════════════════════════════════════════════════
    logging.info(f"   STEP 2: Navegando para página de contratos...")
    driver.get(CONTRACTS_URL)
    time.sleep(2)
    
    # Wait for page to load
    try:
        wait_for_element(driver, (By.XPATH, LOCATORS["table_rows"]), timeout=10)
        logging.info("   STEP 2: ✓ Tabela carregada")
    except TimeoutException:
        logging.info("   STEP 2: ⚠ Timeout, tentando refresh...")
        driver.refresh()
        time.sleep(3)
        try:
            wait_for_element(driver, (By.XPATH, LOCATORS["table_rows"]), timeout=10)
            logging.info("   STEP 2: ✓ Tabela carregada após refresh")
        except TimeoutException:
            logging.info("   STEP 2: ✗ Falha ao carregar página")
            return False
    
    # ═══════════════════════════════════════════════════════════
    # STEP 3: Set year filter if needed
    # ═══════════════════════════════════════════════════════════
    if FILTER_YEAR:
        logging.info(f"   STEP 3: Aplicando filtro de ano: {FILTER_YEAR}")
        set_year_filter(driver, FILTER_YEAR)
        time.sleep(1)
    else:
        logging.info("   STEP 3: Sem filtro de ano")
    
    # ═══════════════════════════════════════════════════════════
    # STEP 4: Verify we're at 'favorecido' level
    # ═══════════════════════════════════════════════════════════
    level = get_current_level(driver)
    logging.info(f"   STEP 4: Nível atual: '{level}'")
    
    if level != "favorecido":
        logging.info(f"   STEP 4: ⚠ Esperado 'favorecido', forçando refresh completo...")
        # Force complete refresh
        driver.get(BASE_URL)
        time.sleep(2)
        driver.get(CONTRACTS_URL)
        time.sleep(3)
        if FILTER_YEAR:
            set_year_filter(driver, FILTER_YEAR)
        time.sleep(1)
        
        level = get_current_level(driver)
        logging.info(f"   STEP 4: Nível após refresh: '{level}'")
        
        if level != "favorecido":
            logging.info("   STEP 4: ✗ Não conseguiu resetar para 'favorecido'")
            return False
    
    # ═══════════════════════════════════════════════════════════
    # STEP 5: Filter by company
    # ═══════════════════════════════════════════════════════════
    logging.info(f"   STEP 5: Filtrando por empresa: {company_id}")
    if not filter_by_company(driver, company_id):
        logging.info("   STEP 5: ✗ Falha ao filtrar")
        return False
    logging.info("   STEP 5: ✓ Filtro aplicado")
    
    # ═══════════════════════════════════════════════════════════
    # STEP 6: Wait for filter results to load
    # ═══════════════════════════════════════════════════════════
    logging.info("   STEP 6: Aguardando resultados do filtro...")
    time.sleep(3)
    
    # ═══════════════════════════════════════════════════════════
    # STEP 7: Click on company
    # ═══════════════════════════════════════════════════════════
    logging.info(f"   STEP 7: Clicando na empresa...")
    caption = click_company_button(driver, company_id)
    if not caption:
        logging.info("   STEP 7: ✗ Falha ao clicar na empresa")
        return False
    
    logging.info(f"   STEP 7: ✓ Empresa clicada: {caption[:50]}...")
    
    # ═══════════════════════════════════════════════════════════
    # STEP 8: Verify we're now at 'orgao' level
    # ═══════════════════════════════════════════════════════════
    time.sleep(2)
    level = get_current_level(driver)
    logging.info(f"   STEP 8: Nível após clicar empresa: '{level}'")
    
    if level != "orgao":
        logging.info(f"   STEP 8: ⚠ Esperado 'orgao', atual: '{level}'")
        # Still return True, the click might have worked but level detection is off
    
    return True

def discover_all_paths(driver, company_id, original_caption):
    """
    Discover all paths from company to deepest level.
    
    Args:
        driver: WebDriver instance
        company_id: Company ID
        original_caption: Company button caption
        
    Returns:
        List of paths, where each path is a list of button texts
    """
    logging.info("\n" + "="*60)
    logging.info("DESCOBRINDO TODOS OS CAMINHOS")
    logging.info("="*60)
    
    all_paths = []
    discover_paths_recursive(driver, [], all_paths, company_id, original_caption)
    
    logging.info(f"\n✓ Total de caminhos descobertos: {len(all_paths)}")
    for i, path in enumerate(all_paths, 1):
        logging.info(f"   {i}: {' → '.join(path)}")
    
    return all_paths


def follow_path_and_collect(driver, company_id, path):
    """
    Follow a specific path and collect all processos.
    """
    logging.info(f"\n   → Seguindo caminho: {' → '.join(path) if path else '(nível atual)'}")
    
    # ═══════════════════════════════════════════════════════════
    # STEP 1: Reset and navigate to company
    # ═══════════════════════════════════════════════════════════
    if not reset_and_navigate_to_company(driver, company_id):
        logging.info("   ✗ Falha ao resetar para seguir caminho")
        return []
    
    # ═══════════════════════════════════════════════════════════
    # STEP 2: Wait for page to transition after company click
    # ═══════════════════════════════════════════════════════════
    logging.info("   → Aguardando transição de página...")
    time.sleep(2)
    
    # Wait for buttons to appear (like original click_next_level did)
    for attempt in range(6):
        buttons = get_all_buttons_at_level(driver, exclude_texts=set())
        if buttons:
            logging.info(f"   ✓ {len(buttons)} botões disponíveis após {attempt + 1} tentativa(s)")
            break
        time.sleep(0.8)
    
    # ═══════════════════════════════════════════════════════════
    # STEP 3: Follow the path
    # ═══════════════════════════════════════════════════════════
    for i, btn_text in enumerate(path):
        logging.info(f"   → Clicando em [{i+1}/{len(path)}]: {btn_text}")
        
        # Wait for this specific button to be clickable
        if not click_specific_button(driver, btn_text):
            logger.error(f"    ✗ Falha ao clicar em: {btn_text}")
            return []
        
        # Wait for page to update after each click
        logging.info(f"   → Aguardando próximo nível...")
        time.sleep(1.5)
    
    # ═══════════════════════════════════════════════════════════
    # STEP 4: Wait for deepest level
    # ═══════════════════════════════════════════════════════════
    time.sleep(1.5)
    
    # Check if we're at deepest level
    for attempt in range(5):
        if has_processo_links(driver):
            logging.info("   ✓ Links de processo encontrados")
            break
        time.sleep(1)
    
    # ═══════════════════════════════════════════════════════════
    # STEP 5: Collect processos
    # ═══════════════════════════════════════════════════════════
    doc_links = get_all_document_links(driver)
    
    logging.info(f"   ✓ Coletados {len(doc_links)} processo(s):")
    for dl in doc_links:
        logging.info(f"      - {dl.get('processo', 'N/A')}: {dl.get('href', 'N/A')[:50]}...")
    
    return doc_links

def get_all_document_links(driver):
    """
    Find and return ALL document links (processos) from the page.
    Searches for all links containing 'processo' in the href.
    
    Args:
        driver: WebDriver instance
        
    Returns:
        List of dictionaries with 'href' and 'processo', or empty list if none found
    """
    logging.info("\n→ Procurando links de processos...")
    
    results = []
    
    try:
        time.sleep(1)
        
        # Find ALL links containing 'processo' in href
        try:
            links = WebDriverWait(driver, TIMEOUT_SECONDS).until(
                EC.presence_of_all_elements_located((
                    By.XPATH,
                    "//a[contains(@href, 'processo')]"
                ))
            )
            
            logging.info(f"   Encontrados {len(links)} link(s) de processo")
            
            for link in links:
                try:
                    href = link.get_attribute("href")
                    processo = link.text.strip()
                    
                    # If text is empty, extract from URL
                    if not processo and href:
                        if "?n=" in href:
                            processo = href.split("?n=")[-1]
                        elif "processo/" in href:
                            processo = href.split("processo/")[-1]
                    
                    # Still empty? Try JavaScript
                    if not processo:
                        processo = driver.execute_script(
                            "return arguments[0].innerText || arguments[0].textContent || '';", 
                            link
                        ).strip()
                    
                    if href:  # Only add if we have a valid href
                        results.append({
                            "href": href,
                            "processo": processo
                        })
                        logging.info(f"   ✓ Processo: {processo}")
                        logging.info(f"     URL: {href}")
                        
                except StaleElementReferenceException:
                    continue
                except Exception as e:
                    logger.error(f"   ⚠ Erro ao processar link: {e}")
                    continue
                    
        except TimeoutException:
            logging.info("   Nenhum link de processo encontrado (timeout)")
        
        # Fallback: Search for any external link with processo pattern
        if not results:
            logging.info("   Tentando método alternativo...")
            try:
                links = driver.find_elements(
                    By.XPATH,
                    "//a[starts-with(@href, 'http')]"
                )
                
                for link in links:
                    href = link.get_attribute("href") or ""
                    text = link.text.strip()
                    
                    if "processo" in href.lower() or "PRO-" in text:
                        processo = text
                        if not processo and "?n=" in href:
                            processo = href.split("?n=")[-1]
                        
                        results.append({
                            "href": href,
                            "processo": processo
                        })
                        logging.info(f"   ✓ Processo (alternativo): {processo}")
                        
            except Exception as e:
                logger.error(f"   Método alternativo falhou: {e}")
        
        if results:
            logging.info(f"\n✓ Total de processos encontrados: {len(results)}")
        else:
            logging.info("✗ Nenhum link de processo encontrado")
        
        return results
        
    except Exception as e:
        logger.error(f"✗ Erro ao buscar links: {e}")
        return []
