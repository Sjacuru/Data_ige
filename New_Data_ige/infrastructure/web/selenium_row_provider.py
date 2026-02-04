"""
NEW_ARCHITECTURE/infrastructure/web/selenium_row_provider.py

📚 EDUCATIONAL PURPOSE:
This is the INFRASTRUCTURE layer - technical implementation
separated from business logic (domain).

🎯 KEY CONCEPT:
Domain says WHAT to do ("get company rows")
Infrastructure says HOW ("use Selenium to scroll and extract")
"""

from typing import List
from selenium import webdriver
from selenium.webdriver.common.by import By
import time
import re
from New_Data_ige.infrastructure.dtos.company_dto import CompanyRowDTO

class SeleniumRowProvider:
    """
    Provides table rows by scraping with Selenium.
    
    📖 MIGRATED FROM: scroll_and_collect_rows() in src/scraper.py
    
    💡 WHY SEPARATE:
    - Domain (ContasRioScraper) doesn't know about Selenium
    - Can swap this for HttpRowProvider, ApiRowProvider, etc.
    - Infrastructure can change without touching domain
    
    📚 IMPLEMENTS: IRowProvider protocol (duck typing)
    Python doesn't enforce this, but it follows the contract:
    - Has get_rows() method that returns List[str]

    NEW: Returns structured DTOs instead of raw strings
    OLD: Returned List[str] of raw text
    
    Benefits:
    - Pre-parsed structure reduces coupling
    - Can validate before passing to domain
    - Easier to debug (see what Selenium extracted)
    """
    
    def __init__(self, driver: webdriver.Chrome, scroll_delay: float = 3.0):
        """
        📚 LEARNING: Inject dependencies, don't create them
        
        We DON'T create the driver here. Why?
        - Driver creation has many config options
        - Caller decides headless, download dir, etc.
        - Makes this class FOCUSED on one job: scrolling
        """
        self.driver = driver
        self.scroll_delay = scroll_delay
    
    def get_rows_as_dtos(self) -> List[CompanyRowDTO]:
        """
        NEW: Return DTOs instead of raw strings.
        
        Benefits:
        - Pre-parsed structure
        - Can validate before passing to domain
        - Easier to debug
        """
        raw_rows = self._scroll_and_collect_raw()
        
        # Convert to DTOs
        dtos = []
        for raw_text in raw_rows:
            dto = self._parse_raw_to_dto(raw_text)
            if dto:
                dtos.append(dto)
        
        return dtos
    
    def _scroll_and_collect_raw(self) -> List[str]:
        """
        Scroll table and collect raw text.
        
        (This is the existing logic from your selenium_row_provider.py)
        """
        scroller = self.driver.find_element(By.CSS_SELECTOR, ".v-grid-scroller")
        
        all_rows = set()
        last_scroll = -1
        stopped_count = 0
        
        # Validation pattern
        complete_row_pattern = re.compile(
            r'^[\w\d\.\/\-]+\s*-\s*.+\s+-?[\d\.,]+\s+-?[\d\.,]+\s+-?[\d\.,]+.*$'
        )
        
        def is_complete_row(text: str) -> bool:
            if not text or "-" not in text:
                return False
            return bool(complete_row_pattern.match(text.strip()))
        
        # Scroll loop
        while True:
            time.sleep(self.scroll_delay)
            
            visible_rows = self.driver.find_elements(By.CSS_SELECTOR, ".v-grid-row")
            
            for row in visible_rows:
                try:
                    row_text = row.text.strip()
                    if is_complete_row(row_text):
                        all_rows.add(row_text)
                except:
                    continue
            
            self.driver.execute_script(
                "arguments[0].scrollTop += arguments[0].clientHeight;",
                scroller
            )
            time.sleep(self.scroll_delay)
            
            current_scroll = scroller.get_property("scrollTop")
            if current_scroll == last_scroll:
                stopped_count += 1
            else:
                stopped_count = 0
            
            if stopped_count >= 5:
                break
            
            last_scroll = current_scroll
        
        return list(all_rows)
    
    def _parse_raw_to_dto(self, raw_text: str) -> CompanyRowDTO | None:
        """
        Parse raw Selenium text → DTO.
        
        Example:
            Input: "12.345.678/0001-99 - Empresa ABC 1.000,00 500,00 500,00 300,00 200,00"
            Output: CompanyRowDTO(id_part="12.345.678/0001-99", name_part="Empresa ABC", ...)
        """
        
        # Skip invalid rows
        if not raw_text or not raw_text.strip():
            return None
        
        if "total" in raw_text.lower():
            return None
        
        if re.match(r'^[\d\.,\s\-]+$', raw_text.strip()):
            return None
        
        # Extract ID and rest
        id_match = re.match(r'^([\w\d\.\/\-]+)\s*-\s*(.+)$', raw_text.strip())
        if not id_match:
            return None
        
        id_part = id_match.group(1).strip()
        rest_text = id_match.group(2).strip()
        
        # Find currency numbers
        currency_numbers = re.findall(r'-?[\d\.]+,\d{2}', rest_text)
        if len(currency_numbers) < 5:
            return None
        
        value_parts = currency_numbers[-5:]  # Last 5 numbers
        
        # Extract name
        first_number = value_parts[0]
        name_end = rest_text.find(first_number)
        name_part = rest_text[:name_end].strip()
        
        if not name_part:
            return None
        
        # Create DTO
        return CompanyRowDTO(
            raw_text=raw_text,
            id_part=id_part,
            name_part=name_part,
            value_parts=value_parts
        )

    def get_rows(self) -> List[str]:
        """
        📖 MIGRATED FROM: scroll_and_collect_rows()
        
        Scroll through dynamic table and collect all row text.
        
        💡 IMPROVEMENT: Returns just the data, no parsing
        OLD: Returned mix of scrolling + started parsing
        NEW: Clean separation - just get text rows
        """
        scroller = self.driver.find_element(By.CSS_SELECTOR, ".v-grid-scroller")
        
        all_rows = set()
        last_scroll = -1
        stopped_count = 0
        
        # Validation pattern (from old code)
        complete_row_pattern = re.compile(
            r'^[\w\d\.\/\-]+\s*-\s*.+\s+-?[\d\.,]+\s+-?[\d\.,]+\s+-?[\d\.,]+.*$'
        )
        
        def is_complete_row(text: str) -> bool:
            """Check if row has ID, name, and numbers."""
            if not text or "-" not in text:
                return False
            return bool(complete_row_pattern.match(text.strip()))
        
        # Scroll until no new content
        while True:
            time.sleep(self.scroll_delay)
            
            # Get visible rows
            visible_rows = self.driver.find_elements(By.CSS_SELECTOR, ".v-grid-row")
            
            for row in visible_rows:
                try:
                    row_text = row.text.strip()
                    if is_complete_row(row_text):
                        all_rows.add(row_text)
                except:
                    continue
            
            # Scroll down
            self.driver.execute_script(
                "arguments[0].scrollTop += arguments[0].clientHeight;",
                scroller
            )
            time.sleep(self.scroll_delay)
            
            # Check if stopped
            current_scroll = scroller.get_property("scrollTop")
            if current_scroll == last_scroll:
                stopped_count += 1
            else:
                stopped_count = 0
            
            if stopped_count >= 5:
                break
            
            last_scroll = current_scroll
        
        return list(all_rows)


# ============================================================================
# COMPLETE WORKING EXAMPLE: OLD vs NEW
# ============================================================================

"""
# ============================================================================
# FILE: examples/scraping_comparison.py
# ============================================================================

OLD WAY (monolithic):
──────────────────────────────────────────────────────────────
from src.scraper import (
    initialize_driver,
    navigate_to_contracts, 
    scroll_and_collect_rows,
    parse_row_data
)

# Everything is coupled together
driver = initialize_driver()
navigate_to_contracts(driver, year=2025)
raw_rows = scroll_and_collect_rows(driver)  # Returns set of strings
companies = parse_row_data(raw_rows)  # Returns list of dicts

# Problem: Can't test parse_row_data without Selenium!
# Problem: Can't use different data source
# Problem: Dictionaries are error-prone


NEW WAY (modular):
──────────────────────────────────────────────────────────────
# 1. Infrastructure layer (HOW to get data)
from infrastructure.web.selenium_row_provider import SeleniumRowProvider
from core.driver import create_driver

driver = create_driver()
row_provider = SeleniumRowProvider(driver)

# 2. Domain layer (WHAT to do with data)
from domain.scraping.contasrio_scraper import ContasRioScraper

scraper = ContasRioScraper(row_provider)
result = scraper.scrape()

# 3. Use clean typed objects
for company in result.companies:
    print(f"{company.id} - {company.name}: {company.total_contracted}")

# Benefits:
# ✅ Can test scraper.parse_all() without browser
# ✅ Can swap SeleniumRowProvider for FileRowProvider
# ✅ Type-safe Company objects
# ✅ Clear error handling via result.errors


# ============================================================================
# TESTING EXAMPLE: Domain without Infrastructure
# ============================================================================

# tests/domain/test_company_parser.py
──────────────────────────────────────────────────────────────
from domain.scraping.contasrio_scraper import CompanyRowParser

def test_parse_valid_row():
    parser = CompanyRowParser()
    
    # No Selenium! Just a string
    row_text = "12.345.678/0001-99 - Empresa ABC LTDA 1.000,00 500,00 500,00 300,00 200,00"
    
    company = parser.parse_row(row_text)
    
    assert company is not None
    assert company.id == "12.345.678/0001-99"
    assert company.name == "Empresa ABC LTDA"
    assert company.total_contracted == "1.000,00"

# This test runs in MILLISECONDS (no browser!)
# Old code needed full Selenium setup to test parsing

# ============================================================================
# MIGRATION GUIDE: How to Switch
# ============================================================================

STEP 1: Keep old code working
──────────────────────────────────────────────────────────────
# Don't touch OLD_CODE/ yet
# It still works for production


STEP 2: Use new code for NEW features
──────────────────────────────────────────────────────────────
# New script: scripts/scrape_with_new_architecture.py

from infrastructure.web.selenium_row_provider import SeleniumRowProvider
from domain.scraping.contasrio_scraper import ContasRioScraper
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


STEP 3: Gradually migrate
──────────────────────────────────────────────────────────────
Week 1: Use new parsing (this file)
Week 2: Migrate navigation to infrastructure/web/navigator.py
Week 3: Migrate driver creation to infrastructure/web/driver_factory.py
Week 4: Deprecate old code


# ============================================================================
# YOUR LEARNING TASKS
# ============================================================================

TASK 1: Run the test
──────────────────────────────────────────────────────────────
1. Copy CompanyRowParser to your project
2. Create test_parser.py with the example above
3. Run: pytest tests/domain/test_parser.py
4. Notice: No browser, instant feedback!


TASK 2: Compare behavior
──────────────────────────────────────────────────────────────
1. Run old scraper: python -m src.scraper
2. Run new scraper: python scripts/scrape_with_new_architecture.py
3. Compare output
4. Ask: What's clearer in new version?


TASK 3: Extend it
──────────────────────────────────────────────────────────────
1. Add a new field to Company (e.g., cnpj_clean)
2. Notice: Type checker helps you update everywhere
3. In old code: grep for all dictionary keys (error-prone!)


TASK 4: Create FileRowProvider
──────────────────────────────────────────────────────────────
Challenge: Create a provider that reads from CSV

class FileRowProvider:
    def __init__(self, csv_path: str):
        self.csv_path = csv_path
    
    def get_rows(self) -> List[str]:
        # Read CSV and return rows as strings
        # Format them like: "ID - Name 1.000,00 500,00 ..."
        pass

# Then use it:
provider = FileRowProvider("test_data.csv")
scraper = ContasRioScraper(provider)
result = scraper.scrape()  # Works without Selenium!


# ============================================================================
# UNDERSTANDING CHECK
# ============================================================================

Answer these to verify understanding:

1. WHY is SeleniumRowProvider in infrastructure/ not domain/?
   Answer: _________________________________________________

2. HOW does ContasRioScraper work with ANY row provider?
   Answer: _________________________________________________

3. WHAT can you test without Selenium now?
   Answer: _________________________________________________

4. WHERE would you add a new data source (API)?
   Answer: _________________________________________________

If you can answer these, you understand the architecture! 🎓
"""