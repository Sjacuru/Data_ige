"""
debug_doweb.py - Debug script to see what DOWEB returns
"""

import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

def debug_search(processo: str):
    print(f"🔍 Debugging search for: {processo}")
    
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
        print(f"📄 Navigating to: {url}")
        driver.get(url)
        
        # Wait for page
        print("⏳ Waiting 8 seconds for JavaScript...")
        time.sleep(8)
        
        # Get page info
        print(f"\n📋 Page Title: {driver.title}")
        print(f"🔗 Current URL: {driver.current_url}")
        
        # Get body text
        body = driver.find_element(By.TAG_NAME, "body")
        body_text = body.text
        
        print(f"\n📝 Page Text (first 1500 chars):")
        print("-" * 50)
        print(body_text[:1500])
        print("-" * 50)
        
        # Count elements
        print(f"\n📊 Element counts:")
        for tag in ["div", "span", "a", "button"]:
            elements = driver.find_elements(By.TAG_NAME, tag)
            print(f"   {tag}: {len(elements)}")
        
        # Look for specific text
        print(f"\n🔎 Searching for key text:")
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
                print(f"   ✓ Found: '{check}'")
            else:
                print(f"   ✗ Not found: '{check}'")
        
        # Keep browser open for manual inspection
        print("\n👀 Browser will stay open for 30 seconds for manual inspection...")
        time.sleep(30)
        
    finally:
        driver.quit()
        print("✓ Browser closed")


if __name__ == "__main__":
    debug_search("SME-PRO-2025/19222")