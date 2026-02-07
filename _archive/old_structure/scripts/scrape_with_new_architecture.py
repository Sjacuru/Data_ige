from New_Data_ige.infrastructure.web.selenium_row_provider import SeleniumRowProvider
from New_Data_ige.domain.scraping.contasrio_scraper import ContasRioScraper
from core.driver import create_driver

def main():
    driver = create_driver()
    
    # Navigate (still using old navigation for now)
    from src.scraper import navigate_to_contracts
    navigate_to_contracts(driver, year=2025)
    
    # NEW: Use new architecture
    row_provider = SeleniumRowProvider(driver)
    scraper = ContasRioScraper(row_provider)
    result = scraper.scrape()
    
    print(f"Success: {result.success}")
    print(f"Found: {result.total_parsed}/{result.total_found}")
    print(f"Errors: {len(result.errors)}")
    
    # NEW: Type-safe objects
    for company in result.companies[:5]:
        print(f"  {company.id} - {company.name}")

if __name__ == "__main__":
    main()
