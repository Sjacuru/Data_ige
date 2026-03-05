"""
WebDriver management utilities.
Handles Chrome WebDriver initialization, configuration, and cleanup.
"""

import logging
from typing import Optional
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

from typing import Dict, Any

from dotenv import load_dotenv
# Load environment variables
load_dotenv()

from config.settings import HEADLESS_MODE, TIMEOUT_SECONDS

logger = logging.getLogger(__name__)


def _build_prefs(
    use_headless: bool,
    download_dir: Optional[str],
    anti_detection: bool
) -> Dict[str, Any]:
    """Return Chrome preferences based on flags.

    By default images and fonts are blocked when running headless to save
    bandwidth.  Anti-detection mode adds several additional settings, and
    may also configure a download directory when provided.
    """

    prefs: Dict[str, Any] = {}
    if use_headless:
        prefs.update({
            "profile.managed_default_content_settings.images": 2,
            "profile.managed_default_content_settings.fonts": 2,
        })

    if anti_detection:
        prefs.update({
            "profile.default_content_setting_values.notifications": 2,
            "credentials_enable_service": False,
            "profile.password_manager_enabled": False,
        })

        if download_dir:
            prefs.update({
                "download.default_directory": str(download_dir),
                "download.prompt_for_download": False,
                "download.directory_upgrade": True,
                "safebrowsing.enabled": True,
                "plugins.always_open_pdf_externally": True,
            })
    return prefs


def create_driver(
    headless: Optional[bool] = None,
    download_dir: Optional[str] = None,
    anti_detection: bool = False,
    user_data_dir: Optional[str] = None,
) -> Optional[webdriver.Chrome]:
    """
    Create and configure Chrome WebDriver.

    The helper applies a set of sensible defaults for performance and
    anti-detection.  Historically we always blocked images and fonts to
    reduce bandwidth while running headless, but that behaviour prevents a
    human from seeing or solving CAPTCHA widgets (they render as a blank
    grey box).  The implementation now only disables those assets when the
    browser is actually running headless; interactive sessions leave them
    enabled so a human can solve challenges.

    Args:
        headless: Run in headless mode (overrides config if provided)
        download_dir: Directory for file downloads (if needed)
        anti_detection: Enable anti-detection measures for CAPTCHA portals
        user_data_dir: Optional Chrome profile directory; if supplied the
            browser will reuse cookies and state across invocations.  useful
            for keeping a solved CAPTCHA/cookie session alive between runs.

    Returns:
        Configured WebDriver instance or None if initialization failed
    """
    
    try:
        # Determine headless mode
        use_headless = headless if headless is not None else HEADLESS_MODE
        
        logger.info("Initializing WebDriver...")
        logger.info(f"  Headless: {use_headless}")
        if download_dir:
            logger.info(f"  Download dir: {download_dir}")
        
        # Configure Chrome options
        options = Options()

        # reuse an existing profile if requested – this is the easiest way to
        # preserve cookies/solved CAPTCHAs between runs.  the directory may
        # contain an entire Chrome profile; the first time you launch with it
        # Chrome will create the profile, afterwards cookies/plugins/etc will
        # persist.
        if user_data_dir:
            options.add_argument(f"--user-data-dir={user_data_dir}")

        import shutil
        chrome_bin = shutil.which("chrome") or shutil.which("google-chrome")
        if chrome_bin:
            options.binary_location = chrome_bin

        # Load page strategy
        options.page_load_strategy = "normal"
        
        # # Headless mode
        if use_headless:
            options.add_argument("--headless=new")
            options.add_argument("--disable-gpu")
            options.add_argument("--window-size=1400,900")

        # # Standard options
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-background-networking")
        options.add_argument("--disable-sync")
        options.add_argument("--metrics-recording-only")
        options.add_argument("--disable-default-apps")
        options.add_argument("--no-first-run")
        options.add_argument("--disable-features=Translate,BackForwardCache")
        options.add_argument("--enable-logging")
        options.add_argument("--v=1")

        # Build preference dictionary using helper utility.  splitting
        # this out makes the behaviour easier to unit-test.
        prefs = _build_prefs(use_headless, download_dir, anti_detection)
        options.add_experimental_option("prefs", prefs)
        
        # Disable automation flags
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)

        # Initialize driver
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        
        # Anti-detection: Override navigator.webdriver
        if anti_detection:
            driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": """
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                """
            })
        
        logger.info("✓ WebDriver initialized successfully. (file driver.py)")
        return driver
        
    except Exception as e:
        logger.error(f"✗ Failed to initialize WebDriver: {e}")
        return None

def close_driver(driver: Optional[webdriver.Chrome]) -> None:
    """
    Safely close WebDriver and clean up resources.
    
    Args:
        driver: WebDriver instance to close (can be None)
    """
    if driver:
        try:
            driver.quit()
            logger.info("✓ WebDriver closed")
        except Exception as e:
            logger.error(f"⚠ Error closing WebDriver: {e}")


def is_driver_available() -> bool:
    """
    Check if Chrome/ChromeDriver is available on system.
    
    Returns:
        True if available, False otherwise
    """
    try:
        driver = create_driver(headless=True, anti_detection=True)
        if driver:
            close_driver(driver)
            return True
        return False
    except Exception:
        return False