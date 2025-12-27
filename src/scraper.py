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
    
    Args:
        driver: WebDriver instance
        
    Returns:
        Set of row text strings
    """
    print("Iniciando scroll para carregar todas as linhas...")
    
    scroller = driver.find_element(By.CSS_SELECTOR, LOCATORS["grid_scroller"])
    
    all_rows = set()
    last_scroll = -1
    stopped_count = 0
    
    while True:
        # Collect visible rows
        visible_rows = driver.find_elements(By.CSS_SELECTOR, LOCATORS["grid_row"])
        for row in visible_rows:
            all_rows.add(row.text)
        
        # Scroll down
        driver.execute_script(
            "arguments[0].scrollTop += arguments[0].clientHeight;",
            scroller
        )
        time.sleep(SCROLL_DELAY)
        
        # Check if we reached the bottom
        current_scroll = scroller.get_property("scrollTop")
        if current_scroll == last_scroll:
            stopped_count += 1
        else:
            stopped_count = 0
            
        if stopped_count >= 5:
            break
            
        last_scroll = current_scroll
    
    print(f"✓ Scroll finalizado! Total de linhas: {len(all_rows)}")
    print("✓ Primeiras 5 linhas:")
    for i, row in enumerate(all_rows[:5], start=1):
        print(f"{i}: {row}")
    return all_rows


def parse_row_data(raw_rows):
    """
    Parse raw row text into structured dictionaries.
    
    Args:
        raw_rows: Set of row text strings
        
    Returns:
        List of dictionaries with parsed data
    """
    print("Processando dados das linhas...")
    
    all_data = []
    
    for row_text in raw_rows:
        # Skip summary rows
        if "total" in row_text.lower():
            continue
        
        # Regex to capture ID, company name, and 5 numeric values
        match = re.match(r"(.+?)\s*-\s*(.*?)\s((?:[\d\.,]+\s?){5})$", row_text)
        

        if match:
            identifier = match.group(1).strip()
            company_name = match.group(2).strip()
            numbers = match.group(3).split()
            
            data_dict = {
                "ID": identifier,
                "Company": company_name
            }
            data_dict.update({
                name: num for name, num in zip(VALUE_COLUMNS, numbers)
            })
            all_data.append(data_dict)
        else:
            print(f"  ⚠ Linha não reconhecida: {row_text[:50]}...")
    
    print(f"✓ {len(all_data)} registros processados!")
    print("✓ Primeiros 5 registros:")
    for i, item in enumerate(all_data[:5], start=1):
        print(f"{i}: {item}")
    return all_data

# =============================================================================
# CLICK ACTIONS - NAVIGATION THROUGH THE SITE
# =============================================================================

def filter_by_company(driver, company_id):
    """
    Apply filter to show only one company.
    
    Args:
        driver: WebDriver instance
        company_id: Company ID to filter
        
    Returns:
        True if successful, False otherwise
    """
    try:
        print(f"\n→ Filtrando por ID: {company_id}")
        
        filter_box = wait_for_element(
            driver,
            (By.XPATH, LOCATORS["filter_input"])
        )
        
        filter_box.clear()
        filter_box.send_keys(company_id)
        time.sleep(2)
        filter_box.send_keys(Keys.ENTER)
        time.sleep(2)
        
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
    try:
        print(f"\n→ Clicando na empresa {company_id}...")
        
        company_button = driver.find_element(
            By.XPATH,
            f"//div[contains(@class,'v-button-link') and @role='button']"
            f"[.//span[contains(@class,'v-button-caption') and contains(text(), '{company_id}')]]"
        )
        
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
    Click on the UG (Unidade Gestora) button - the 3rd non-empty caption.
    
    Args:
        driver: WebDriver instance
        
    Returns:
        The clicked button's caption text if successful, None otherwise
    """
    print("\n→ Procurando o link da UG dentro do grid (Vaadin)...")
    
    try:
        # Get ALL button captions
        all_buttons = driver.find_elements(
            By.XPATH,
            "//span[contains(@class,'v-button-caption')]"
        )
        
        print(f"   Total de botões encontrados: {len(all_buttons)}")
        
        # Extract non-empty captions
        non_empty = [b for b in all_buttons if b.text.strip() != ""]
        
        print(f"\n   Botões não vazios encontrados: {len(non_empty)}")
        for i, b in enumerate(non_empty[:5]):  # Show first 5
            print(f"      {i+1}: {b.text.strip()}")
        
        # The UG is ALWAYS the 3rd non-empty caption
        if len(non_empty) < 3:
            print("✗ Não há botões suficientes para selecionar UG.")
            return None
        
        ug_button = non_empty[2]  # 3rd non-empty caption (index 2)
        ug_text = ug_button.text.strip()
        
        print(f"\n→ UG encontrada: {ug_text}")
        
        # Go up to the clickable button div
        clickable = ug_button.find_element(
            By.XPATH, "./ancestor::div[@role='button']"
        )
        
        # Try to click
        for attempt in range(3):
            try:
                driver.execute_script(
                    "arguments[0].scrollIntoView({block:'center'});",
                    clickable
                )
                time.sleep(0.2)
                driver.execute_script("arguments[0].click();", clickable)
                print("✓ Link da UG clicado com sucesso.")
                return ug_text
            except Exception as e:
                print(f"   Tentativa de clique falhou: {e}")
                time.sleep(0.3)
        
        print("✗ Não foi possível clicar na UG")
        return None
        
    except Exception as e:
        print(f"✗ Erro ao buscar UG: {e}")
        return None

# =============================================================================
# DOCUMENT LINK EXTRACTION
# =============================================================================

def get_document_link(driver, column_name="Processo"):
    """
    Find and return the document link from the table.
    
    Args:
        driver: WebDriver instance
        column_name: Name of the column containing the link
        
    Returns:
        Dictionary with 'href' and 'text', or None if not found
    """
    try:
        print(f"\n→ Procurando link na coluna '{column_name}'...")
        
        # Wait for grid
        grid = wait_for_element(
            driver,
            (By.XPATH, LOCATORS["grid_wrapper"])
        )
        driver.execute_script(
            "arguments[0].scrollIntoView({block:'center'});",
            grid
        )
        time.sleep(2)
        
        # Find column index
        headers = driver.find_elements(By.XPATH, LOCATORS["column_header"])
        column_index = None
        
        for i, header in enumerate(headers):
            if header.text.strip() == column_name:
                column_index = i + 1  # XPath is 1-indexed
                break
        
        if column_index is None:
            print(f"✗ Coluna '{column_name}' não encontrada")
            return None
        
        # Find link in column
        rows = grid.find_elements(By.XPATH, ".//tbody/tr")
        for row in rows:
            try:
                link = row.find_element(
                    By.XPATH,
                    f"./td[{column_index}]//a[starts-with(@href,'http')]"
                )
                result = {
                    "href": link.get_attribute("href"),
                    "text": link.text
                }
                print(f"✓ Link encontrado: {result['href']}")
                return result
            except NoSuchElementException:
                continue
        
        print("✗ Nenhum link encontrado")
        return None
        
    except Exception as e:
        print(f"✗ Erro ao buscar link: {e}")
        return None

def close_driver(driver):
    """Safely close the browser."""
    if driver:
        driver.quit()
        print("✓ Driver fechado.")