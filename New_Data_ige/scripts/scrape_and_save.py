"""
scrape_and_save.py - Scrape and persist to repository

Location: NEW_DATA_IGE/scripts/scrape_and_save.py

Run: python -m New_Data_ige.scripts.scrape_and_save
"""

from pathlib import Path

from New_Data_ige.infrastructure.web.selenium_row_provider import SeleniumRowProvider
from New_Data_ige.domain.scraping.contasrio_scraper import ContasRioScraper
from New_Data_ige.infrastructure.persistence.json_company_repository import JsonCompanyRepository
from core.driver import create_driver, close_driver


def main():
    print("\n" + "="*70)
    print("🚀 SCRAPE & SAVE - Repository Pattern")
    print("="*70)
    
    driver = None
    
    try:
        # Step 1: Initialize repository
        print("\n💾 Initializing repository...")
        repo = JsonCompanyRepository("data/companies.json")
        
        # Check existing data
        existing_count = repo.count()
        if existing_count > 0:
            print(f"   ℹ️  Found {existing_count} existing companies")
            overwrite = input("   Overwrite? (y/n): ").lower() == 'y'
            if not overwrite:
                print("   Cancelled.")
                return
        
        # Step 2: Initialize Selenium
        print("\n📡 Initializing Selenium...")
        driver = create_driver()
        
        # Step 3: Navigate
        print("🌐 Navigating to ContasRio...")
        from src.scraper import navigate_to_contracts
        navigate_to_contracts(driver, year=2025)
        
        # Step 4: Scrape with DTO architecture
        print("\n🔄 Scraping data...")
        row_provider = SeleniumRowProvider(driver)
        scraper = ContasRioScraper(row_provider)
        result = scraper.scrape()
        
        print(f"   Found: {result.total_found} DTOs")
        print(f"   Parsed: {result.total_parsed} Companies")
        
        # Step 5: Save to repository
        print("\n💾 Saving to repository...")
        saved_count = repo.save_all(result.companies)
        print(f"   ✅ Saved: {saved_count} companies")
        
        # Step 6: Verify
        print("\n🔍 Verifying save...")
        loaded = repo.find_all()
        print(f"   ✅ Verified: {len(loaded)} companies loaded from disk")
        
        # Show first 5
        print(f"\n👥 First 5 Companies:")
        for i, company in enumerate(loaded[:5], 1):
            print(f"   {i}. {company.id} - {company.name[:40]}...")
        
        print("\n" + "="*70)
        print(f"✅ Success! Data saved to: data/companies.json")
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