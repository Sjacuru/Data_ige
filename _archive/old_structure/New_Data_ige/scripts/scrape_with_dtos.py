"""
scrape_with_dtos.py - Execute scraping with new DTO architecture

Location: NEW_DATA_IGE/scripts/scrape_with_dtos.py

Run: python -m New_Data_ige.scripts.scrape_with_dtos
"""

from New_Data_ige.infrastructure.web.selenium_row_provider import SeleniumRowProvider
from New_Data_ige.domain.scraping.contasrio_scraper import ContasRioScraper
from core.driver import create_driver, close_driver


def main():
    print("\n" + "="*70)
    print("🚀 CONTASRIO SCRAPER - DTO ARCHITECTURE")
    print("="*70)
    
    driver = None
    
    try:
        # Step 1: Initialize Selenium
        print("\n📡 Initializing Selenium...")
        driver = create_driver()
        
        # Step 2: Navigate (using old navigation for now)
        print("🌐 Navigating to ContasRio...")
        from src.scraper import navigate_to_contracts
        navigate_to_contracts(driver, year=2025)
        
        # Step 3: NEW ARCHITECTURE - DTO Flow
        print("\n🆕 Using NEW DTO Architecture:")
        print("   Selenium → DTOs → Domain")
        
        row_provider = SeleniumRowProvider(driver)
        scraper = ContasRioScraper(row_provider)
        result = scraper.scrape()
        
        # Step 4: Results
        print(f"\n📊 RESULTS:")
        print(f"   Success: {result.success}")
        print(f"   Found: {result.total_found} DTOs")
        print(f"   Parsed: {result.total_parsed} Companies")
        print(f"   Success Rate: {result.success_rate:.1f}%")
        print(f"   Errors: {len(result.errors)}")
        
        # Show first 5 companies
        print(f"\n👥 First 5 Companies:")
        for i, company in enumerate(result.companies[:5], 1):
            print(f"   {i}. {company.id} - {company.name[:40]}...")
        
        print("\n" + "="*70)
        print("✅ Scraping completed!")
        print("="*70)
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        if driver:
            close_driver(driver)


if __name__ == "__main__":
    main()