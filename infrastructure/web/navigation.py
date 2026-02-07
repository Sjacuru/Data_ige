"""
core/navigation.py - Shared navigation functions for ContasRio portal.

Consolidated from:
- src/scraper.py
- scripts/download_csv.py
- scripts/process_from_csv.py

Usage:
    from infrastructure.web.navigation import (
        get_current_level,
        set_year_filter,
        filter_by_company,
        click_company_button,
        wait_for_element
    )
"""

import logging
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

# Import configuration
import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import TIMEOUT_SECONDS, LOCATORS

logger = logging.getLogger(__name__)


# =========================================================================
# WAIT HELPERS
# =========================================================================

def wait_for_element(driver, locator, timeout=None):
    """
    Wait for an element to be present on the page.
    
    Args:
        driver: WebDriver instance
        locator: Tuple of (By.TYPE, "selector")
        timeout: Maximum wait time in seconds (default: TIMEOUT_SECONDS)
        
    Returns:
        WebElement if found, raises TimeoutException if not
    """
    if timeout is None:
        timeout = TIMEOUT_SECONDS
    
    wait = WebDriverWait(driver, timeout)
    return wait.until(EC.presence_of_element_located(locator))


# =========================================================================
# LEVEL DETECTION
# =========================================================================

def get_current_level(driver):
    """
    Identify current navigation level by checking column headers.
    
    Returns:
        String: 'favorecido', 'orgao', 'unidade_gestora', 'objeto', or 'unknown'
    """
    try:
        headers = driver.find_elements(
            By.XPATH,
            "//div[contains(@class,'v-grid-column-header-content')]"
        )
        
        for header in headers:
            text = header.text.strip().lower()
            if "objeto" in text:
                return "objeto"
            elif "unidade gestora" in text:
                return "unidade_gestora"
            elif "órgão" in text or "orgao" in text:
                return "orgao"
            elif "favorecido" in text:
                return "favorecido"
        
        return "unknown"
    except Exception:
        return "unknown"


# =========================================================================
# YEAR FILTER
# =========================================================================

def set_year_filter(driver, year):
    """
    Set the year filter on ContasRio contracts page.
    
    Args:
        driver: WebDriver instance
        year: Year to filter (int or str)
        
    Returns:
        bool: True if successful
    """
    if not year:
        return True
    
    year = str(year)
    logger.info(f"→ Ajustando filtro do ano para: {year}")

    # Capture a row to detect grid refresh
    try:
        first_row = driver.find_element(By.XPATH, LOCATORS["table_rows"])
    except Exception:
        first_row = None

    # Find all Vaadin filter inputs
    try:
        inputs = WebDriverWait(driver, TIMEOUT_SECONDS).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".v-filterselect-input"))
        )
    except TimeoutException:
        logger.warning("Não foi possível encontrar campos de filtro")
        return False

    # Pick the input that already shows the current year (fallback to first)
    current_year = str(datetime.now().year)
    target = next(
        (i for i in inputs if (i.get_attribute("value") or "").strip() == current_year),
        inputs[0] if inputs else None
    )

    if not target:
        logger.warning("Nenhum campo de filtro encontrado")
        return False

    # Interact with the input
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", target)
        target.click()
        target.send_keys(Keys.CONTROL, "a", Keys.DELETE, year, Keys.ENTER)
    except Exception as e:
        logger.warning(f"Erro ao interagir com filtro: {e}")
        return False

    # Wait until the input reflects the selected year
    try:
        WebDriverWait(driver, 5).until(
            lambda d: (target.get_attribute("value") or "").strip() == year
        )
    except Exception:
        pass

    # Wait for grid refresh
    if first_row:
        try:
            WebDriverWait(driver, 10).until(EC.staleness_of(first_row))
        except Exception:
            pass

    # Ensure rows are present
    try:
        WebDriverWait(driver, TIMEOUT_SECONDS).until(
            EC.presence_of_element_located((By.XPATH, LOCATORS["table_rows"]))
        )
    except Exception:
        pass

    logger.info("✓ Ano ajustado.")
    return True


# =========================================================================
# COMPANY FILTER
# =========================================================================

def filter_by_company(driver, company_id):
    """
    Apply filter to show only one company.
    
    Args:
        driver: WebDriver instance
        company_id: Company ID to filter
        
    Returns:
        bool: True if successful
    """
    try:
        logger.info(f"→ Filtrando por ID: {company_id}")
        
        filter_box = wait_for_element(
            driver,
            (By.XPATH, LOCATORS["filter_input"])
        )
        
        filter_box.clear()
        filter_box.send_keys(company_id)
        time.sleep(1)
        filter_box.send_keys(Keys.ENTER)
        
        # Wait longer for filter results to load
        time.sleep(3)
        
        logger.info("✓ Filtro aplicado!")
        return True
        
    except Exception as e:
        logger.error(f"✗ Erro ao filtrar: {e}")
        return False


# =========================================================================
# COMPANY BUTTON CLICK
# =========================================================================

def click_company_button(driver, company_id):
    """
    Click on a company button in the table.
    Verifies the page transitions after clicking.
    
    Args:
        driver: WebDriver instance
        company_id: Company ID to click
        
    Returns:
        str: Company caption if successful, None otherwise
    """
    logger.info(f"→ Clicando na empresa {company_id}...")
    
    # Check current level before clicking
    level_before = get_current_level(driver)
    logger.debug(f"   Nível antes do clique: '{level_before}'")
    
    xpath = (
        f"//div[contains(@class,'v-button-link') and @role='button']"
        f"[.//span[contains(@class,'v-button-caption') and contains(text(), '{company_id}')]]"
    )
    
    company_button = None
    original_caption = None
    
    # Find the button (with retries)
    for attempt in range(5):
        try:
            company_button = WebDriverWait(driver, 3).until(
                EC.presence_of_element_located((By.XPATH, xpath))
            )
            logger.debug(f"   ✓ Botão encontrado na tentativa {attempt + 1}")
            break
        except TimeoutException:
            logger.debug(f"   Tentativa {attempt + 1}: Aguardando elemento...")
            time.sleep(1)
    
    # Fallback method
    if company_button is None:
        logger.debug("   Tentando método alternativo...")
        try:
            all_buttons = driver.find_elements(
                By.XPATH,
                "//span[contains(@class,'v-button-caption')]"
            )
            
            for btn in all_buttons:
                try:
                    if company_id in btn.text:
                        company_button = btn.find_element(
                            By.XPATH, 
                            "./ancestor::div[@role='button']"
                        )
                        logger.debug(f"   ✓ Encontrado via método alternativo")
                        break
                except:
                    continue
                    
        except Exception as e:
            logger.debug(f"   Método alternativo falhou: {e}")
    
    if company_button is None:
        logger.error(f"✗ Elemento não encontrado para empresa {company_id}")
        return None
    
    # Get caption
    try:
        caption_element = company_button.find_element(
            By.XPATH, ".//span[contains(@class,'v-button-caption')]"
        )
        original_caption = caption_element.text.strip()
    except:
        original_caption = company_id
    
    # Try to click (with retries and verification)
    for click_attempt in range(3):
        try:
            # Scroll into view
            driver.execute_script(
                "arguments[0].scrollIntoView({block:'center'});",
                company_button
            )
            time.sleep(0.5)
            
            # Try JavaScript click
            driver.execute_script("arguments[0].click();", company_button)
            logger.debug(f"   Clique executado (tentativa {click_attempt + 1})")
            
            # Wait and verify page transitioned
            time.sleep(2)
            
            level_after = get_current_level(driver)
            logger.debug(f"   Nível após clique: '{level_after}'")
            
            # Check if level changed (favorecido → orgao)
            if level_after != level_before:
                logger.info(f"✓ Empresa clicada: {original_caption[:50]}...")
                return original_caption
            
            # Level didn't change - try alternative click methods
            logger.debug(f"   ⚠ Página não transicionou, tentando outro método...")
            
            # Try regular click
            try:
                company_button.click()
                time.sleep(2)
                level_after = get_current_level(driver)
                if level_after != level_before:
                    logger.info(f"✓ Empresa clicada (click direto): {original_caption[:50]}...")
                    return original_caption
            except:
                pass
            
            # Try ActionChains click
            try:
                from selenium.webdriver.common.action_chains import ActionChains
                actions = ActionChains(driver)
                actions.move_to_element(company_button).click().perform()
                time.sleep(2)
                level_after = get_current_level(driver)
                if level_after != level_before:
                    logger.info(f"✓ Empresa clicada (ActionChains): {original_caption[:50]}...")
                    return original_caption
            except:
                pass
            
            # Re-find button for next attempt
            try:
                company_button = driver.find_element(By.XPATH, xpath)
            except:
                pass
                
        except Exception as e:
            logger.debug(f"   ⚠ Erro no clique {click_attempt + 1}: {e}")
            time.sleep(1)
    
    logger.error(f"✗ Clique na empresa não funcionou após múltiplas tentativas")
    return None


# =========================================================================
# BUTTON UTILITIES
# =========================================================================

def get_all_buttons_at_level(driver, exclude_texts=None):
    """
    Get all clickable button texts at current level.
    
    Args:
        driver: WebDriver instance
        exclude_texts: Set of texts to exclude
        
    Returns:
        List of button text strings
    """
    if exclude_texts is None:
        exclude_texts = set()
    
    try:
        all_buttons = driver.find_elements(
            By.XPATH,
            "//span[contains(@class,'v-button-caption')]"
        )
        
        button_texts = []
        for b in all_buttons:
            try:
                txt = b.text.strip()
                if not txt:
                    continue
                if txt in exclude_texts:
                    continue
                    
                # Pattern "digits - name" (Org/UG pattern)
                if " - " in txt:
                    left = txt.split(" - ", 1)[0]
                    if left.replace(".", "").isdigit():
                        button_texts.append(txt)
                        continue
                
                # FALLBACK: Also accept alphanumeric IDs (like ES20250183)
                if " - " in txt:
                    left = txt.split(" - ", 1)[0]
                    if left.replace(".", "").replace("/", "").replace("-", "").isalnum():
                        button_texts.append(txt)
                        
            except StaleElementReferenceException:
                continue
        
        return button_texts
    except Exception as e:
        logger.warning(f"⚠ Erro ao obter botões: {e}")
        return []


def click_specific_button(driver, button_text):
    """
    Click a button by its text.
    
    Args:
        driver: WebDriver instance
        button_text: Text of the button to click
        
    Returns:
        bool: True if clicked successfully
    """
    # Method 1: Wait for button to appear with retries
    for attempt in range(5):
        try:
            time.sleep(0.5)
            
            # Try exact match first
            try:
                button = driver.find_element(
                    By.XPATH,
                    f"//span[contains(@class,'v-button-caption') and normalize-space(text())='{button_text}']"
                )
            except NoSuchElementException:
                # Try contains match as fallback
                button = driver.find_element(
                    By.XPATH,
                    f"//span[contains(@class,'v-button-caption') and contains(text(), '{button_text[:30]}')]"
                )
            
            # Find clickable parent
            clickable = button.find_element(
                By.XPATH, "./ancestor::div[@role='button']"
            )
            
            # Scroll and click
            driver.execute_script(
                "arguments[0].scrollIntoView({block:'center'});",
                clickable
            )
            time.sleep(0.3)
            driver.execute_script("arguments[0].click();", clickable)
            
            logger.debug(f"   ✓ Botão clicado: {button_text[:50]}...")
            time.sleep(1.0)
            return True
            
        except StaleElementReferenceException:
            logger.debug(f"   ⚠ Tentativa {attempt + 1}: Elemento stale, tentando novamente...")
            time.sleep(0.8)
        except NoSuchElementException:
            logger.debug(f"   ⚠ Tentativa {attempt + 1}: Elemento não encontrado, aguardando...")
            time.sleep(1.0)
        except Exception as e:
            error_msg = str(e).split('\n')[0] if str(e) else "Erro desconhecido"
            logger.debug(f"   ⚠ Tentativa {attempt + 1}: {error_msg}")
            time.sleep(0.8)
    
    # Method 2: Fallback - search all buttons
    logger.debug(f"   → Tentando método alternativo para: {button_text[:40]}...")
    try:
        all_buttons = driver.find_elements(
            By.XPATH,
            "//span[contains(@class,'v-button-caption')]"
        )
        
        for btn in all_buttons:
            try:
                txt = btn.text.strip()
                if txt == button_text or button_text in txt:
                    clickable = btn.find_element(
                        By.XPATH, "./ancestor::div[@role='button']"
                    )
                    
                    driver.execute_script(
                        "arguments[0].scrollIntoView({block:'center'});",
                        clickable
                    )
                    time.sleep(0.3)
                    driver.execute_script("arguments[0].click();", clickable)
                    
                    logger.debug(f"   ✓ Botão clicado (alternativo): {txt[:50]}...")
                    time.sleep(1.0)
                    return True
            except:
                continue
                
    except Exception as e:
        logger.debug(f"   ✗ Método alternativo falhou: {e}")
    
    return False


def has_processo_links(driver):
    """
    Check if processo links are visible (means we're at deepest level).
    
    Args:
        driver: WebDriver instance
        
    Returns:
        bool: True if processo links are present
    """
    try:
        links = driver.find_elements(By.XPATH, "//a[contains(@href, 'processo')]")
        return len(links) > 0
    except:
        return False


# =========================================================================
# STANDALONE TEST
# =========================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logger.info("=" * 60)
    logger.info("🧪 Testing core/navigation.py")
    logger.info("=" * 60)
    logger.info("\nThis module provides shared navigation functions.")
    logger.info("Import and use in your scripts:")
    logger.info("")
    logger.info("    from infrastructure.web.navigation import (")
    logger.info("        get_current_level,")
    logger.info("        set_year_filter,")
    logger.info("        filter_by_company,")
    logger.info("        click_company_button")
    logger.info("    )")