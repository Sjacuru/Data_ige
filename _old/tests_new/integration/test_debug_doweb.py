"""
debug_doweb.py - Debug script to see what DOWEB returns
"""

import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def debug_search(processo: str):
    logging.info(f"🔍 Debugging search for: {processo}")
    
    # Setup driver
    options = Options()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    
    try:
        # Navigate
        url = f"https://doweb.rio.rj.gov.br/buscanova/#/p=1&q={processo}"
        logging.info(f"📄 Navigating to: {url}")
        driver.get(url)
        
        # Wait for page
        logging.info("⏳ Waiting 8 seconds for JavaScript...")
        time.sleep(8)
        
        # Get page info
        logging.info(f"\n📋 Page Title: {driver.title}")
        logging.info(f"🔗 Current URL: {driver.current_url}")
        
        # Get body text
        body = driver.find_element(By.TAG_NAME, "body")
        body_text = body.text
        
        logging.info(f"\n📝 Page Text (first 1500 chars):")
        logging.info("-" * 50)
        logging.info(body_text[:1500])
        logging.info("-" * 50)
        
        # Count elements
        logging.info(f"\n📊 Element counts:")
        for tag in ["div", "span", "a", "button"]:
            elements = driver.find_elements(By.TAG_NAME, tag)
            logging.info(f"   {tag}: {len(elements)}")
        
        # Look for specific text
        logging.info(f"\n🔎 Searching for key text:")
        checks = [
            "resultados encontrados",
            "resultado encontrado",
            "publicado em",
            "Diário publicado",
            "Edição",
            "Download",
            "EXTRATO",
        ]
        
        for check in checks:
            if check.lower() in body_text.lower():
                logging.info(f"   ✓ Found: '{check}'")
            else:
                logger.error(f"    ✗ Not found: '{check}'")
        
        # Keep browser open for manual inspection
        logging.info("\n👀 Browser will stay open for 30 seconds for manual inspection...")
        time.sleep(30)
        
    finally:
        driver.quit()
        logging.info("✓ Browser closed")


if __name__ == "__main__":
    debug_search("SME-PRO-2025/19222")