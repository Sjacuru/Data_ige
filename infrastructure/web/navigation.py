"""
Navigation utilities for web scraping.
Provides helper functions for common Selenium operations.
"""
import time
import logging
from typing import Optional, List
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    StaleElementReferenceException,
    ElementClickInterceptedException
)
from selenium.webdriver.remote.webelement import WebElement

from config.settings import TIMEOUT_SECONDS

logger = logging.getLogger(__name__)


def wait_for_element(
    driver: webdriver.Chrome,
    by: str,
    value: str,
    timeout: Optional[int] = None,
    visible: bool = False
) -> Optional[WebElement]:
    """
    Wait for element to be present (or visible) on page.
    
    Args:
        driver: WebDriver instance
        by: Selenium By locator type (By.ID, By.CSS_SELECTOR, etc.)
        value: Locator value
        timeout: Wait timeout in seconds (defaults to config)
        visible: Wait for element to be visible (not just present)
        
    Returns:
        WebElement if found, None if timeout
    """
    timeout = timeout or TIMEOUT_SECONDS
    
    try:

        locator = (by, value)

        condition = (
            EC.visibility_of_element_located(locator)
            if visible
            else EC.presence_of_element_located(locator)
        )
    
        return WebDriverWait(driver, 120).until(
            lambda d: d.find_elements(By.CSS_SELECTOR, "span.v-button-caption")[0]
            if len(d.find_elements(By.CSS_SELECTOR, "span.v-button-caption")) > 0
            else False
        )


    


    except TimeoutException:
        logger.debug(f"⚠ Element not found within {timeout}s: {value}")
        return None


def wait_for_elements(
    driver: webdriver.Chrome,
    by: By,
    value: str,
    timeout: Optional[int] = None,
    min_count: int = 1
) -> List[WebElement]:
    """
    Wait for multiple elements to be present on page.
    
    Args:
        driver: WebDriver instance
        by: Selenium By locator type
        value: Locator value
        timeout: Wait timeout in seconds
        min_count: Minimum number of elements to wait for
        
    Returns:
        List of WebElements (empty list if not found)
    """
    timeout = timeout or TIMEOUT_SECONDS
    
    try:
        WebDriverWait(driver, timeout).until(
            lambda d: len(d.find_elements(str(by), value)) >= min_count
        )
        return driver.find_elements(str(by), value)
        
    except TimeoutException:
        logger.debug(f"⚠ Elements not found: {value}")
        return []


def click_element_safe(
    driver: webdriver.Chrome,
    element: WebElement,
    wait_after: float = 1.0
) -> bool:
    """
    Click element with multiple fallback methods and error handling.
    
    Tries multiple clicking strategies:
    1. Direct click
    2. JavaScript click
    3. Actions click
    
    Args:
        driver: WebDriver instance
        element: WebElement to click
        wait_after: Seconds to wait after successful click
        
    Returns:
        True if clicked successfully, False otherwise
    """
    # Method 1: Direct click
    try:
        element.click()
        time.sleep(wait_after)
        logger.debug("   ✓ Clicked (direct)")
        return True
    except (ElementClickInterceptedException, StaleElementReferenceException) as e:
        logger.debug(f"   Direct click failed: {e.__class__.__name__}")
    
    # Method 2: JavaScript click
    try:
        driver.execute_script("arguments[0].click();", element)
        time.sleep(wait_after)
        logger.debug("   ✓ Clicked (JavaScript)")
        return True
    except Exception as e:
        logger.debug(f"   JavaScript click failed: {e.__class__.__name__}")
    
    # Method 3: ActionChains click
    try:
        from selenium.webdriver.common.action_chains import ActionChains
        ActionChains(driver).move_to_element(element).click().perform()
        time.sleep(wait_after)
        logger.debug("   ✓ Clicked (ActionChains)")
        return True
    except Exception as e:
        logger.error(f"   ✗ All click methods failed: {e}")
        return False

def scroll_to_element(driver: webdriver.Chrome, element: WebElement) -> None:
    """
    Scroll element into view.
    
    Args:
        driver: WebDriver instance
        element: Element to scroll to
    """
    try:
        driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", element)
        time.sleep(0.5)
    except Exception as e:
        logger.debug(f"⚠ Scroll failed: {e}")

def scroll_to_bottom(
    driver: webdriver.Chrome,
    grid_css: str = "div.v-grid",
    pause: float = 2.0,
    max_scrolls: int = 200,
    scroll_increment: int = 300
) -> None:
    """
    Scroll inside a Vaadin grid's internal scrollable container.
    
    Args:
        driver: WebDriver instance
        grid_css: CSS selector for the grid container
        pause: Pause between scrolls (seconds)
        max_scrolls: Safety limit
        scroll_increment: Pixels to scroll per step
    """
    # Vaadin grid's scrollable element is the `.v-grid-scroller-vertical`
    # or the `.v-grid-tablewrapper` depending on Vaadin version.
    # Fallback: find the scrollable div inside the grid.
    
    scroller = driver.execute_script("""
        var grid = document.querySelector(arguments[0]);
        if (!grid) return null;
        
        // Vaadin 7/8 uses a vertical scroller div
        var vertScroller = grid.querySelector('.v-grid-scroller-vertical');
        if (vertScroller) return vertScroller;
        
        // Fallback: the table wrapper itself
        var wrapper = grid.querySelector('.v-grid-tablewrapper');
        if (wrapper) return wrapper;
        
        return grid;
    """, grid_css)
    
    if not scroller:
        logger.warning("Could not find grid scroller element")
        return
    
    for i in range(max_scrolls):
        old_top = driver.execute_script("return arguments[0].scrollTop;", scroller)
        driver.execute_script(
            "arguments[0].scrollTop += arguments[1];",
            scroller,
            scroll_increment
        )
        time.sleep(pause)
        new_top = driver.execute_script("return arguments[0].scrollTop;", scroller)
        
        if new_top == old_top:
            logger.debug(f"   Grid scroll complete after {i + 1} steps")
            return
    
    logger.debug(f"   Grid scroll hit max_scrolls ({max_scrolls})")


def get_current_url(driver: webdriver.Chrome) -> str:
    """
    Get current URL safely.
    
    Args:
        driver: WebDriver instance
        
    Returns:
        Current URL or empty string if error
    """
    try:
        return driver.current_url
    except Exception:
        return ""


def get_page_source(driver: webdriver.Chrome) -> str:
    """
    Get page source safely.
    
    Args:
        driver: WebDriver instance
        
    Returns:
        Page HTML source or empty string if error
    """
    try:
        return driver.page_source
    except Exception:
        return ""


def refresh_page(driver: webdriver.Chrome, wait_after: float = 2.0) -> None:
    """
    Refresh current page.
    
    Args:
        driver: WebDriver instance
        wait_after: Seconds to wait after refresh
    """
    try:
        driver.refresh()
        time.sleep(wait_after)
    except Exception as e:
        logger.error(f"⚠ Page refresh failed: {e}")


def go_back(driver: webdriver.Chrome, wait_after: float = 2.0) -> None:
    """
    Navigate back in browser history.
    
    Args:
        driver: WebDriver instance
        wait_after: Seconds to wait after navigation
    """
    try:
        driver.back()
        time.sleep(wait_after)
    except Exception as e:
        logger.error(f"⚠ Go back failed: {e}")