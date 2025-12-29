"""
scraper.py - Web scraping functions for ContasRio portal.
Handles browser automation, navigation, and data extraction.
"""

import numbers
import re
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    StaleElementReferenceException,
    NoSuchElementException
)
from webdriver_manager.chrome import ChromeDriverManager
from datetime import datetime

# Import configuration
import sys
sys.path.append('..')
from config import (
    TIMEOUT_SECONDS, MAX_RETRIES, SCROLL_DELAY,
    BASE_URL, CONTRACTS_URL, VALUE_COLUMNS, LOCATORS
)

# =============================================================================
# DRIVER MANAGEMENT
# =============================================================================

def initialize_driver(headless=False):
    """
    Initialize Chrome WebDriver with proper settings.
    
    Args:
        headless: If True, runs Chrome without visible window
        
    Returns:
        WebDriver instance or None if failed
    """
    try:
        options = Options()
        if headless:
            options.add_argument("--headless") # It makes Chrome run in headless mode 
                                               # (means it doesn't open a visible window).
        
        # Recommended options for stability
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        
        # Use webdriver-manager to handle driver automatically
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        
        print("✓ Driver inicializado com sucesso!")
        return driver
        
    except Exception as e:
        print(f"✗ Erro ao inicializar o driver: {e}")
        return None

# =============================================================================
# WAIT HELPERS
# =============================================================================

def wait_for_element(driver, locator, timeout=TIMEOUT_SECONDS):
    """
    Wait for an element to be present on the page.
    
    Args:
        driver: WebDriver instance
        locator: Tuple of (By.TYPE, "selector")
        timeout: Maximum wait time in seconds
        
    Returns:
        WebElement if found, raises TimeoutException if not
    """
    wait = WebDriverWait(driver, timeout)
    return wait.until(EC.presence_of_element_located(locator))

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
        print("Checando se o Site funciona. Aguardando carregamento da tela Home...")
        
        wait_for_element(driver, (By.XPATH, LOCATORS["home_menu"]))
        print("✓ Home carregada!")
        return True
        
    except TimeoutException:
        print("✗ Timeout ao carregar, site pode estar fora do ar.")
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
            print(f"Tentativa {attempt}: Aguardando carregamento do painel...")
            wait_for_element(driver, (By.XPATH, LOCATORS["table_rows"]))
            print("✓ Painel carregado com sucesso!")

            # NEW: set the year filter before any scrolling happens
            if year:
                set_year_filter(driver, year)

            return True
            
        except TimeoutException:
            print(f"Timeout na tentativa {attempt}.")
            if attempt == MAX_RETRIES:
                print(f"✗ O painel não carregou após {MAX_RETRIES} tentativas.")
                return False
            print("Atualizando a página...")
            driver.refresh()
            time.sleep(2)
    
    return False

def set_year_filter(driver, year):
    """
    Select the desired 'year' in the Vaadin FilterSelect (v-filterselect).
    Attempts to find the combobox whose current value equals the current year,
    then changes it to the requested 'year'.
    """
    if not year:
        return  # Nothing to do

    year = str(year)
    print(f"\n→ Ajustando filtro do ano para: {year}")

    # Try to capture an existing grid row to detect refresh after changing year
    first_row = None
    try:
        first_row = driver.find_element(By.XPATH, LOCATORS["table_rows"])
    except Exception:
        pass

    # 1) Find all filterselect inputs
    inputs = WebDriverWait(driver, TIMEOUT_SECONDS).until(
        EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".v-filterselect-input"))
    )

    # 2) Choose the one likely to be the YEAR filter
    # Heuristic: pick the input whose current value equals the current year
    current_year = str(datetime.now().year)
    target_input = None

    for inp in inputs:
        try:
            val = (inp.get_attribute("value") or "").strip()
            if val == current_year:
                target_input = inp
                break
        except Exception:
            continue

    if target_input is None:
        # Fallback: pick the first input
        target_input = inputs[0]

    # 3) Scroll into view and click the input
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", target_input)
    target_input.click()
    time.sleep(0.2)

    # 4) Clear existing value and type the new year
    target_input.send_keys(Keys.CONTROL, "a")
    target_input.send_keys(Keys.DELETE)
    target_input.send_keys(year)
    time.sleep(0.2)

    # 5) Try to open dropdown and select exact match (if popup appears)
    # Otherwise, just press ENTER to accept the first suggested item
    try:
        # Try clicking the dropdown button next to the input
        try:
            btn = target_input.find_element(
                By.XPATH, "./following-sibling::div[contains(@class,'v-filterselect-button')]"
            )
            btn.click()
            time.sleep(0.2)
        except Exception:
            pass

        # Wait for the popup and click the exact option if visible
        popup = WebDriverWait(driver, 3).until(
            EC.presence_of_element_located((
                By.XPATH,
                "//div[contains(@class,'v-filterselect-suggestpopup') and not(contains(@style,'display: none'))]"
            ))
        )
        option = WebDriverWait(popup, 2).until(
            EC.presence_of_element_located((
                By.XPATH,
                f".//*[normalize-space(text())='{year}']"
            ))
        )
        driver.execute_script("arguments[0].scrollIntoView({block:'nearest'});", option)
        option.click()
    except Exception:
        # Fallback: accept selection by pressing ENTER
        target_input.send_keys(Keys.ENTER)

    # 6) Wait until the input shows the selected year (best-effort)
    try:
        WebDriverWait(driver, 5).until(
            lambda d: ((target_input.get_attribute("value") or "").strip() == year)
        )
    except Exception:
        pass

    # 7) Wait for the grid to refresh (best-effort)
    if first_row is not None:
        try:
            WebDriverWait(driver, 10).until(EC.staleness_of(first_row))
        except Exception:
            pass

    # 8) Ensure rows are present (grid ready)
    try:
        WebDriverWait(driver, TIMEOUT_SECONDS).until(
            EC.presence_of_element_located((By.XPATH, LOCATORS["table_rows"]))
        )
    except Exception:
        pass

    print("✓ Ano ajustado.")

# =============================================================================
# DATA COLLECTION
# =============================================================================

def scroll_and_collect_rows(driver):
    """
    Scroll through the dynamic table and collect all row data.
    Includes validation and verification pass for reliability.
    """
    print("Iniciando scroll para carregar todas as linhas...")
    
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
    print("   Primeira passagem...")
    
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
    print(f"   Primeira passagem: {first_pass_count} linhas")
    
    # ═══════════════════════════════════════════════════════════
    # VERIFICATION PASS: Scroll back to top and collect again
    # ═══════════════════════════════════════════════════════════
    print("   Passagem de verificação...")
    
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
    print(f"   Verificação: +{new_rows} novas linhas encontradas")
    print(f"✓ Scroll finalizado! Total de linhas: {len(all_rows)}")
    
    return all_rows

def parse_row_data(raw_rows):
    """
    Parse raw row text into structured dictionaries.
    """
    print("Processando dados das linhas...")
    print(f"\nDEBUG: Total de linhas brutas recebidas: {len(raw_rows)}")
    
    all_data = []
    
    # Track ALL skip reasons
    skip_empty = 0
    skip_total = 0
    skip_numbers_only = 0
    skip_no_match = 0
    
    for row_text in raw_rows:
        # Skip empty rows
        if not row_text.strip():
            skip_empty += 1
            continue
            
        # Skip summary rows
        if "total" in row_text.lower():
            skip_total += 1
            continue
        
        # Skip rows that are only numbers (incomplete/split rows)
        if re.match(r'^[\d\.,\s\-]+$', row_text.strip()):
            skip_numbers_only += 1
            print(f"  ⚠ Apenas números: {row_text[:50]}...")
            continue
        
        # ═══════════════════════════════════════════════════════════
        # STEP 1: Extract ID
        # ═══════════════════════════════════════════════════════════
        id_match = re.match(r'^([\w\d\.\/\-]+)\s*-\s*(.+)$', row_text.strip())
        
        if not id_match:
            skip_no_match += 1
            print(f"  ⚠ Não reconhecida (sem ID): {row_text[:70]}...")
            continue
        
        identifier = id_match.group(1).strip()
        rest = id_match.group(2).strip()
        
        # ═══════════════════════════════════════════════════════════
        # STEP 2: Find currency numbers (format: 1.234,56 or -1.234,56)
        # This ignores plain numbers like CPF (14707320767)
        # ═══════════════════════════════════════════════════════════
        currency_numbers = re.findall(r'-?[\d\.]+,\d{2}', rest)
        
        if len(currency_numbers) < 5:
            skip_no_match += 1
            print(f"  ⚠ Poucos valores ({len(currency_numbers)}): {row_text[:70]}...")
            continue
        
        # Take only the LAST 5 numbers
        numbers = currency_numbers[-5:]
        
        # ═══════════════════════════════════════════════════════════
        # STEP 3: Company name is everything before the first of last 5
        # ═══════════════════════════════════════════════════════════
        first_currency = numbers[0]
        split_pos = rest.find(first_currency)
        company_name = rest[:split_pos].strip()
        
        # Build data dict
        data_dict = {
            "ID": identifier,
            "Company": company_name
        }
        
        for i, col_name in enumerate(VALUE_COLUMNS):
            if i < len(numbers):
                data_dict[col_name] = numbers[i]
            else:
                data_dict[col_name] = "0"
                
        all_data.append(data_dict)
    
    # Complete summary
    print(f"\n{'='*60}")
    print(f"RESUMO DO PARSING:")
    print(f"  ✓ Processadas com sucesso: {len(all_data)}")
    print(f"  ⊘ Vazias ignoradas: {skip_empty}")
    print(f"  ⊘ Linhas 'total' ignoradas: {skip_total}")
    print(f"  ⚠ Apenas números (incompletas): {skip_numbers_only}")
    print(f"  ⚠ Não reconhecidas: {skip_no_match}")
    print(f"  ─────────────────────────────")
    total_accounted = len(all_data) + skip_empty + skip_total + skip_numbers_only + skip_no_match
    print(f"  Σ Total contabilizado: {total_accounted} / {len(raw_rows)}")
    print(f"{'='*60}")
    
    print("\n✓ Primeiros 5 registros:")
    for i, item in enumerate(all_data[:5], start=1):
        print(f"{i}: {item}")
        
    return all_data

# =============================================================================
# CLICK ACTIONS - NAVIGATION THROUGH THE SITE
# =============================================================================

def filter_by_company(driver, company_id):
    """
    Apply filter to show only one company.
    """
    try:
        print(f"\n→ Filtrando por ID: {company_id}")
        
        filter_box = wait_for_element(
            driver,
            (By.XPATH, LOCATORS["filter_input"])
        )
        
        filter_box.clear()
        filter_box.send_keys(company_id)
        time.sleep(1)
        filter_box.send_keys(Keys.ENTER)
        
        # ═══════════════════════════════════════════════════════════
        # Wait longer for filter results to load
        # ═══════════════════════════════════════════════════════════
        time.sleep(3)  # ← Increased from 2 to 3
        
        print("✓ Filtro aplicado!")
        return True
        
    except Exception as e:
        print(f"✗ Erro ao filtrar: {e}")
        return False


def click_company_button(driver, company_id):
    """
    Click on a company button in the table.
    
    Args:
        driver: WebDriver instance
        company_id: Company ID to click
        
    Returns:
        The original caption text if successful, None otherwise
    """
    print(f"\n→ Clicando na empresa {company_id}...")
    
    # ═══════════════════════════════════════════════════════════
    # Wait for the filtered results to appear
    # ═══════════════════════════════════════════════════════════
    xpath = (
        f"//div[contains(@class,'v-button-link') and @role='button']"
        f"[.//span[contains(@class,'v-button-caption') and contains(text(), '{company_id}')]]"
    )
    
    company_button = None
    
    # Try multiple times with wait
    for attempt in range(5):
        try:
            # Wait for element to be present
            company_button = WebDriverWait(driver, 3).until(
                EC.presence_of_element_located((By.XPATH, xpath))
            )
            break
        except TimeoutException:
            print(f"   Tentativa {attempt + 1}: Aguardando elemento...")
            time.sleep(1)
    
    # If still not found, try alternative approach
    if company_button is None:
        print("   Tentando método alternativo...")
        try:
            # Look for any button containing the ID
            all_buttons = driver.find_elements(
                By.XPATH,
                "//span[contains(@class,'v-button-caption')]"
            )
            
            for btn in all_buttons:
                if company_id in btn.text:
                    company_button = btn.find_element(
                        By.XPATH, 
                        "./ancestor::div[@role='button']"
                    )
                    print(f"   ✓ Encontrado via método alternativo")
                    break
                    
        except Exception as e:
            print(f"   Método alternativo falhou: {e}")
    
    if company_button is None:
        print(f"✗ Erro ao clicar na empresa: Elemento não encontrado")
        return None
    
    try:
        caption_element = company_button.find_element(
            By.XPATH, ".//span[contains(@class,'v-button-caption')]"
        )
        original_caption = caption_element.text.strip()
        
        # Scroll and click
        driver.execute_script(
            "arguments[0].scrollIntoView({block:'center'});",
            company_button
        )
        time.sleep(0.3)
        driver.execute_script("arguments[0].click();", company_button)
        
        print("✓ Empresa clicada!")
        return original_caption
        
    except Exception as e:
        print(f"✗ Erro ao clicar na empresa: {e}")
        return None

def click_next_level(driver, original_caption):
    """
    Click on the next-level button (Org/Secretaria) after clicking a company.
    
    Args:
        driver: WebDriver instance
        original_caption: Caption of the company button (to exclude it)
        
    Returns:
        The clicked button's caption text if successful, None otherwise
    """
    print("\n→ Aguardando botões do próximo nível carregarem...")
    time.sleep(0.7)
    
    found_next = False
    chosen_text = None
    
    for attempt in range(6):
        try:
            captions = driver.find_elements(
                By.XPATH,
                "//div[@role='button' and not(contains(@style,'display: none'))]"
                "//span[contains(@class,'v-button-caption')]"
            )
            
            print(f"   Tentativa {attempt+1}: encontrados {len(captions)} caption(s)")
            
            candidate_captions = []
            for c in captions:
                txt = c.text.strip()
                if not txt:
                    continue
                if txt == original_caption:
                    continue  # Skip the company we already clicked
                
                # Prefer pattern "digits - name"
                if " - " in txt:
                    left, _ = txt.split(" - ", 1)
                    if left.replace(".", "").isdigit():
                        candidate_captions.append((c, txt))
                        continue
                
                # Fallback — any non-empty caption
                candidate_captions.append((c, txt))
            
            if not candidate_captions:
                time.sleep(0.8)
                continue
            
            # Select best match (prefer "digits - name" pattern)
            chosen = None
            for c, txt in candidate_captions:
                if " - " in txt and txt.split(" - ", 1)[0].replace(".", "").isdigit():
                    chosen = (c, txt)
                    break
            
            if not chosen:
                chosen = candidate_captions[0]
            
            chosen_elem, chosen_text = chosen
            print(f"   Selecionado para clicar: '{chosen_text}'")
            
            # Find the clickable parent button
            clickable_next = chosen_elem.find_element(
                By.XPATH, "./ancestor::div[@role='button']"
            )
            
            # Try to click
            for click_attempt in range(3):
                try:
                    driver.execute_script(
                        "arguments[0].scrollIntoView({block:'center'});",
                        clickable_next
                    )
                    time.sleep(0.2)
                    driver.execute_script("arguments[0].click();", clickable_next)
                    found_next = True
                    break
                except Exception as e_click:
                    print(f"   Clique falhou: {e_click}")
                    time.sleep(0.5)
            
            if found_next:
                time.sleep(1.0)
                print(f"✓ Próximo nível clicado: {chosen_text}")
                break
                
        except Exception as e:
            print(f"   Exceção ao localizar botões: {e}")
            time.sleep(0.8)
    
    if not found_next:
        print("⚠️ Não foi possível identificar/clicar o próximo botão")
        return None
    
    return chosen_text


def click_ug_button(driver):
    """
    Keep clicking through hierarchy levels until reaching the deepest level.
    Stops when processo links are found or no new buttons to click.
    """
    print("\n→ Navegando pelos níveis até chegar ao nível mais profundo...")
    
    last_clicked_text = None
    previous_button_texts = set()
    
    max_levels = 10
    level = 0
    
    def has_processo_links():
        """Check if processo links are visible (means we're at deepest level)."""
        try:
            links = driver.find_elements(By.XPATH, "//a[contains(@href, 'processo')]")
            return len(links) > 0
        except:
            return False
    
    while level < max_levels:
        level += 1
        print(f"\n   --- Nível {level} ---")
        
        try:
            # Wait for UI to stabilize
            time.sleep(1.0)  # ← Increased wait time
            
            # ═══════════════════════════════════════════════════════════
            # CHECK: Are we at the deepest level? (processo links visible)
            # ═══════════════════════════════════════════════════════════
            if has_processo_links():
                print("   ✓ Links de processo encontrados - nível mais profundo atingido.")
                break
            
            # Fresh fetch of elements
            try:
                all_buttons = driver.find_elements(
                    By.XPATH,
                    "//span[contains(@class,'v-button-caption')]"
                )
            except StaleElementReferenceException:
                time.sleep(0.5)
                all_buttons = driver.find_elements(
                    By.XPATH,
                    "//span[contains(@class,'v-button-caption')]"
                )
            
            # Extract non-empty captions
            non_empty = []
            current_texts = set()
            
            for b in all_buttons:
                try:
                    txt = b.text.strip()
                    if txt:
                        non_empty.append((b, txt))
                        current_texts.add(txt)
                except StaleElementReferenceException:
                    continue
            
            print(f"   Botões não vazios encontrados: {len(non_empty)}")
            for i, (_, txt) in enumerate(non_empty[:5]):
                print(f"      {i+1}: {txt}")
            
            # If no buttons found, we've reached the end
            if len(non_empty) < 1:
                print("   ✓ Nenhum botão restante - nível mais profundo atingido.")
                break
            
            # If only 1 button and it's the same as last clicked, we're done
            if len(non_empty) == 1 and non_empty[0][1] == last_clicked_text:
                print("   ✓ Apenas o botão já clicado restante - nível mais profundo atingido.")
                break
            
            # Find the last button that is NOT the one we just clicked
            ug_button = None
            ug_text = None
            
            for b, txt in reversed(non_empty):
                if txt != last_clicked_text:
                    ug_button = b
                    ug_text = txt
                    break
            
            # If all buttons are the same as last clicked, we're done
            if ug_button is None:
                print("   ✓ Todos os botões já foram clicados - nível mais profundo atingido.")
                break
            
            # ═══════════════════════════════════════════════════════════
            # REMOVED: "buttons didn't change" check - unreliable
            # Instead, we always try to click if there's a new button
            # ═══════════════════════════════════════════════════════════
            
            print(f"\n   → Clicando em: {ug_text}")
            
            # Click with retry
            clicked = False
            for attempt in range(3):
                try:
                    fresh_button = driver.find_element(
                        By.XPATH,
                        f"//span[contains(@class,'v-button-caption') and normalize-space(text())='{ug_text}']"
                    )
                    
                    clickable = fresh_button.find_element(
                        By.XPATH, "./ancestor::div[@role='button']"
                    )
                    
                    driver.execute_script(
                        "arguments[0].scrollIntoView({block:'center'});",
                        clickable
                    )
                    time.sleep(0.3)
                    driver.execute_script("arguments[0].click();", clickable)
                    
                    print(f"   ✓ Botão clicado: {ug_text}")
                    clicked = True
                    last_clicked_text = ug_text
                    previous_button_texts = current_texts
                    break
                    
                except StaleElementReferenceException:
                    print(f"   ⚠️ Elemento ficou stale, tentativa {attempt + 1}...")
                    time.sleep(0.5)
                except Exception as e:
                    print(f"   Tentativa de clique falhou: {e}")
                    time.sleep(0.4)
            
            if not clicked:
                print("   ✗ Não foi possível clicar - parando navegação.")
                break
            
            # Wait for page to update
            time.sleep(1.5)  # ← Increased wait time
            
        except StaleElementReferenceException:
            print(f"   ⚠️ Stale element no nível {level}, tentando novamente...")
            time.sleep(0.5)
            continue
            
        except Exception as e:
            print(f"   Erro no nível {level}: {e}")
            break
    
    if last_clicked_text:
        print(f"\n✓ Navegação completa! Último nível: {last_clicked_text}")
    else:
        print("\n✗ Nenhum botão foi clicado.")
    
    return last_clicked_text
    
# =============================================================================
# DOCUMENT LINK EXTRACTION
# =============================================================================

def get_all_document_links(driver):
    """
    Find and return ALL document links (processos) from the page.
    Searches for all links containing 'processo' in the href.
    
    Args:
        driver: WebDriver instance
        
    Returns:
        List of dictionaries with 'href' and 'processo', or empty list if none found
    """
    print("\n→ Procurando links de processos...")
    
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
            
            print(f"   Encontrados {len(links)} link(s) de processo")
            
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
                        print(f"   ✓ Processo: {processo}")
                        print(f"     URL: {href}")
                        
                except StaleElementReferenceException:
                    continue
                except Exception as e:
                    print(f"   ⚠ Erro ao processar link: {e}")
                    continue
                    
        except TimeoutException:
            print("   Nenhum link de processo encontrado (timeout)")
        
        # Fallback: Search for any external link with processo pattern
        if not results:
            print("   Tentando método alternativo...")
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
                        print(f"   ✓ Processo (alternativo): {processo}")
                        
            except Exception as e:
                print(f"   Método alternativo falhou: {e}")
        
        if results:
            print(f"\n✓ Total de processos encontrados: {len(results)}")
        else:
            print("✗ Nenhum link de processo encontrado")
        
        return results
        
    except Exception as e:
        print(f"✗ Erro ao buscar links: {e}")
        return []

def close_driver(driver):
    """Safely close the browser."""
    if driver:
        driver.quit()
        print("✓ Driver fechado.")