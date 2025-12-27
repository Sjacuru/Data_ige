"""
scraper.py - Web scraping functions for ContasRio portal.
Handles browser automation, navigation, and data extraction.
"""

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

# Import configuration
import sys
sys.path.append('..')
from config import (
    TIMEOUT_SECONDS, MAX_RETRIES, SCROLL_DELAY,
    BASE_URL, CONTRACTS_URL, VALUE_COLUMNS, LOCATORS
)


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
        print("Aguardando carregamento da tela Home...")
        
        wait_for_element(driver, (By.XPATH, LOCATORS["home_menu"]))
        print("✓ Home carregada!")
        return True
        
    except TimeoutException:
        print("✗ Timeout ao carregar a Home")
        return False


def navigate_to_contracts(driver):
    """
    Navigate to the contracts page with retry logic.
    
    Args:
        driver: WebDriver instance
        
    Returns:
        True if successful, False otherwise
    """
    driver.get(CONTRACTS_URL)
    
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(f"Tentativa {attempt}: Aguardando carregamento do painel...")
            wait_for_element(driver, (By.XPATH, LOCATORS["table_rows"]))
            print("✓ Painel carregado com sucesso!")
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