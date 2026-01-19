"""
diagnostics/doweb_diagnostic.py - Debug DOWeb search results

Usage:
    python diagnostics/doweb_diagnostic.py TUR-PRO-2025/00350
"""

import sys
import time
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from selenium.webdriver.common.by import By
from core.driver import create_driver, close_driver

def diagnose_doweb_search(processo: str):
    """
    Diagnose what's actually in the DOWeb search results.
    """
    print("\n" + "=" * 70)
    print(f"🔬 DOWEB SEARCH DIAGNOSTIC: {processo}")
    print("=" * 70)
    
    url = f"https://doweb.rio.rj.gov.br/buscanova/#/p=1&q={processo}"
    print(f"\n📍 URL: {url}")
    
    driver = create_driver(headless=False)  # Visible for inspection
    
    try:
        print("\n🌐 Navigating...")
        driver.get(url)
        
        print("⏳ Waiting for page to load (8 seconds)...")
        time.sleep(8)
        
        # Get full page text
        body = driver.find_element(By.TAG_NAME, "body")
        body_text = body.text
        
        print(f"\n📄 Page loaded ({len(body_text)} characters)")
        
        # Check for results count
        if "resultados encontrados" in body_text.lower() or "resultado encontrado" in body_text.lower():
            import re
            count_match = re.search(r"(\d+)\s+resultados?\s+encontrados?", body_text, re.IGNORECASE)
            if count_match:
                count = count_match.group(1)
                print(f"✅ Found: {count} result(s)")
            else:
                print("✅ Results found (count unclear)")
        else:
            print("❌ No 'resultados encontrados' text")
        
        # Find all "Diário publicado em" sections
        import re
        result_pattern = r"Diário publicado em:\s*(\d{2}/\d{2}/\d{4})\s*-\s*Edição\s*(\d+)\s*-\s*Pág\.\s*(\d+)"
        matches = list(re.finditer(result_pattern, body_text))
        
        print(f"\n📋 Found {len(matches)} result card(s)")
        
        if not matches:
            print("\n⚠️  No result cards detected!")
            print("\n📄 First 2000 chars of page:")
            print("─" * 70)
            print(body_text[:2000])
            print("─" * 70)
        else:
            # Analyze each result
            for i, match in enumerate(matches):
                pub_date = match.group(1)
                edition = match.group(2)
                page = match.group(3)
                
                # Get preview text
                start_pos = match.start()
                if i + 1 < len(matches):
                    end_pos = matches[i + 1].start()
                else:
                    end_pos = min(start_pos + 1000, len(body_text))
                
                preview = body_text[start_pos:end_pos]
                
                print(f"\n{'─' * 70}")
                print(f"Result {i+1}: {pub_date} - Edição {edition} - Página {page}")
                print(f"{'─' * 70}")
                
                # Check for keywords
                keywords_to_check = [
                    "EXTRATO",
                    "extrato",
                    "Extrato",
                    "CONTRATO",
                    "Contrato",
                    "contrato",
                    "TERMO ADITIVO",
                    "Termo Aditivo",
                    "ADITIVO",
                    processo.upper(),
                    processo.lower(),
                ]
                
                found_keywords = []
                for kw in keywords_to_check:
                    if kw in preview:
                        found_keywords.append(kw)
                
                if found_keywords:
                    print(f"✅ Keywords found: {', '.join(found_keywords)}")
                else:
                    print(f"❌ NO keywords found (no EXTRATO, no CONTRATO, no processo)")
                
                # Show preview
                print(f"\n📄 Preview (first 500 chars):")
                print(preview[:500])
                print("...")
        
        # Keep browser open for manual inspection
        print("\n" + "=" * 70)
        print("👀 Browser will stay open for 30 seconds")
        print("   You can manually inspect the results")
        print("=" * 70)
        time.sleep(30)
        
    finally:
        close_driver(driver)
        print("\n✅ Browser closed")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python doweb_diagnostic.py <processo_number>")
        print("Example: python doweb_diagnostic.py TUR-PRO-2025/00350")
        sys.exit(1)
    
    processo = sys.argv[1]
    diagnose_doweb_search(processo)