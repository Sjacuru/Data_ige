"""
core/driver.py - Unified WebDriver initialization for all scrapers.

Merged from:
- src/scraper.py
- scripts/download_csv.py
- scripts/process_from_csv.py
- scripts/extract_processo_documents.py
- conformity/scraper/doweb_scraper.py

Usage:
    from core.driver import create_driver, close_driver
    
    # Basic usage
    driver = create_driver()
    
    # With options
    driver = create_driver(
        headless=True,
        download_dir="./downloads",
        anti_detection=True
    )
    
    # Always close when done
    close_driver(driver)
"""

import os
from pathlib import Path
from typing import Optional

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager


# =========================================================================
# CONFIGURATION
# =========================================================================

DEFAULT_WINDOW_SIZE = "1920,1080"
DEFAULT_TIMEOUT = 10


# =========================================================================
# MAIN DRIVER FUNCTION
# =========================================================================

def create_driver(
    headless: bool = False,
    download_dir: Optional[str] = None,
    anti_detection: bool = False,
    window_size: str = DEFAULT_WINDOW_SIZE,
    implicit_wait: int = DEFAULT_TIMEOUT
) -> Optional[webdriver.Chrome]:
    """
    Create and configure a Chrome WebDriver instance.
    
    This is the single source of truth for driver initialization
    across all scrapers in the project.
    
    Args:
        headless: Run browser without visible window
        download_dir: Directory for file downloads (None = browser default)
        anti_detection: Add options to avoid bot detection
        window_size: Browser window size (default: 1920x1080)
        implicit_wait: Implicit wait timeout in seconds (default: 10)
    
    Returns:
        Configured Chrome WebDriver instance, or None if failed
    
    Examples:
        # Basic scraping (no downloads)
        driver = create_driver()
        
        # Headless mode
        driver = create_driver(headless=True)
        
        # With download directory
        driver = create_driver(download_dir="./data/downloads")
        
        # For sites with bot detection
        driver = create_driver(anti_detection=True)
        
        # Full options
        driver = create_driver(
            headless=False,
            download_dir="./downloads",
            anti_detection=True
        )
    """
    try:
        options = Options()
        
        # ─────────────────────────────────────────────────────────────
        # HEADLESS MODE
        # ─────────────────────────────────────────────────────────────
        if headless:
            options.add_argument("--headless")
        
        # ─────────────────────────────────────────────────────────────
        # STABILITY OPTIONS (used by all scrapers)
        # ─────────────────────────────────────────────────────────────
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument(f"--window-size={window_size}")
        
        # ─────────────────────────────────────────────────────────────
        # ANTI-DETECTION OPTIONS (for processo.rio, etc.)
        # ─────────────────────────────────────────────────────────────
        if anti_detection:
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option('useAutomationExtension', False)
        
        # ─────────────────────────────────────────────────────────────
        # DOWNLOAD PREFERENCES
        # ─────────────────────────────────────────────────────────────
        prefs = {}
        
        if download_dir:
            # Ensure directory exists
            download_path = Path(download_dir).absolute()
            download_path.mkdir(parents=True, exist_ok=True)
            
            prefs.update({
                "download.default_directory": str(download_path),
                "download.prompt_for_download": False,
                "download.directory_upgrade": True,
                "safebrowsing.enabled": True,
                "plugins.always_open_pdf_externally": True,
            })
        
        if prefs:
            options.add_experimental_option("prefs", prefs)
        
        # ─────────────────────────────────────────────────────────────
        # CREATE DRIVER
        # ─────────────────────────────────────────────────────────────
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        
        # ─────────────────────────────────────────────────────────────
        # POST-CREATION SETUP
        # ─────────────────────────────────────────────────────────────
        if anti_detection:
            # Remove webdriver property to avoid detection
            driver.execute_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )
        
        if implicit_wait > 0:
            driver.implicitly_wait(implicit_wait)
        
        # ─────────────────────────────────────────────────────────────
        # SUCCESS
        # ─────────────────────────────────────────────────────────────
        print("✓ Driver initialized successfully!")
        if download_dir:
            print(f"  Download folder: {download_path}")
        if headless:
            print("  Mode: headless")
        if anti_detection:
            print("  Anti-detection: enabled")
        
        return driver
        
    except Exception as e:
        print(f"✗ Error initializing driver: {e}")
        return None


def close_driver(driver: Optional[webdriver.Chrome]) -> None:
    """
    Safely close the WebDriver.
    
    Args:
        driver: WebDriver instance to close (can be None)
    """
    if driver:
        try:
            driver.quit()
            print("✓ Driver closed.")
        except Exception as e:
            print(f"⚠ Error closing driver: {e}")


# =========================================================================
# CONVENIENCE FUNCTIONS
# =========================================================================

def create_scraper_driver(headless: bool = False) -> Optional[webdriver.Chrome]:
    """
    Create driver for basic scraping (ContasRio, etc.).
    
    No download directory, no anti-detection.
    """
    return create_driver(headless=headless)


def create_download_driver(
    download_dir: str,
    headless: bool = False
) -> Optional[webdriver.Chrome]:
    """
    Create driver configured for file downloads.
    
    Args:
        download_dir: Directory to save downloaded files
        headless: Run in headless mode
    """
    return create_driver(
        headless=headless,
        download_dir=download_dir
    )


def create_processo_driver(
    download_dir: str,
    headless: bool = False
) -> Optional[webdriver.Chrome]:
    """
    Create driver for processo.rio (with anti-detection).
    
    Args:
        download_dir: Directory to save downloaded files
        headless: Run in headless mode (not recommended for CAPTCHA)
    """
    if headless:
        print("⚠️ Warning: Headless mode may fail with CAPTCHA")
    
    return create_driver(
        headless=headless,
        download_dir=download_dir,
        anti_detection=True
    )


# =========================================================================
# STANDALONE TEST
# =========================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("🧪 Testing core/driver.py")
    print("=" * 60)
    
    print("\n1. Testing basic driver creation...")
    driver = create_driver()
    if driver:
        print(f"   Current URL: {driver.current_url}")
        close_driver(driver)
    
    print("\n2. Testing driver with download directory...")
    driver = create_driver(download_dir="./test_downloads")
    if driver:
        close_driver(driver)
    
    print("\n3. Testing anti-detection driver...")
    driver = create_driver(anti_detection=True)
    if driver:
        close_driver(driver)
    
    print("\n✅ All tests completed!")
    
    # Cleanup test folder
    import shutil
    try:
        shutil.rmtree("./test_downloads")
        print("   Cleaned up test folder")
    except:
        pass