# Integration test (requires actual portal access)
from infrastructure.web.driver import create_driver, close_driver
from infrastructure.scrapers.contasrio.scraper import ContasRioScraper

# Initialize
driver = create_driver(headless=False)
assert driver is not None
scraper = ContasRioScraper(driver)

# Run discovery (will stop at company collection for now)
processos = scraper.discover_all_processos()

print(f"Discovered {len(processos)} processos")

# Cleanup
close_driver(driver)