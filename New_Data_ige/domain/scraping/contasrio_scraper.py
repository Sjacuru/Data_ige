"""
NEW_ARCHITECTURE/domain/scraping/contasrio_scraper.py

📚 EDUCATIONAL PURPOSE:
This module demonstrates DOMAIN LAYER design - pure business logic
with NO technical dependencies (Selenium, databases, etc.)

🎯 WHAT vs HOW:
- Domain: WHAT data to collect (contracts, companies)
- Infrastructure: HOW to get it (Selenium, HTTP, etc.)

📖 MIGRATED FROM:
- OLD: src/scraper.py (lines 245-500)
- Improvements: Separated parsing from web automation
"""

from dataclasses import dataclass
from typing import List, Optional, Protocol
from enum import Enum
import re
from New_Data_ige.domain.models.company import CompanyData
from New_Data_ige.domain.parsing.company_row_parser import CompanyRowParser
from New_Data_ige.infrastructure.dtos.company_dto import CompanyRowDTO

# ============================================================================
# 📚 LEARNING CONCEPT 1: Data Classes for Domain Models
# ============================================================================
# Instead of dictionaries, use TYPED data structures
# Benefits:
# - ✅ Auto-complete in IDE
# - ✅ Type checking
# - ✅ Self-documenting
# - ✅ Immutable by default (frozen=True)

@dataclass(frozen=True)
class Company:
    """
    Represents a Favorecido (company/person) from ContasRio.
    
    📖 MIGRATED FROM: Dictionary in parse_row_data()
    OLD: {"ID": "123", "Company": "ABC Corp", "Total Contratado": "1000"}
    NEW: Company(id="123", name="ABC Corp", total_contracted="1000")
    
    💡 WHY BETTER:
    - Type-safe: company.id vs company["ID"] (typo-proof)
    - Immutable: Can't accidentally change data
    - Validated: Can add validation in __post_init__
    """
    id: str                    # CNPJ or CPF
    name: str                  # Company/Person name
    total_contracted: str      # "R$ 1.234.567,89"
    committed: str             # "Empenhado"
    balance: str               # "Saldo a Executar"
    settled: str               # "Liquidado"
    paid: str                  # "Pago"
    
    def __post_init__(self):
        """
        📚 LEARNING: Validation in domain models
        
        Domain objects should validate themselves.
        This ensures INVALID data never enters your system.
        """
        if not self.id or len(self.id) < 5:
            raise ValueError(f"Invalid ID: {self.id}")
        
        if not self.name:
            raise ValueError("Company name cannot be empty")


@dataclass(frozen=True)
class ScrapingResult:
    """Result of scraping operation."""
    companies: List[CompanyData]
    total_found: int
    total_parsed: int
    errors: List[str]
    
    @property
    def success(self) -> bool:
        return len(self.companies) > 0
    
    @property
    def success_rate(self) -> float:
        if self.total_found == 0:
            return 0.0
        return (self.total_parsed / self.total_found) * 100


class IRowProvider(Protocol):
    """Contract for row providers."""
    def get_rows_as_dtos(self) -> List[CompanyRowDTO]:
        """Return DTOs from data source."""
        ...



# ============================================================================
# 📚 LEARNING CONCEPT 2: Protocols (Interfaces)
# ============================================================================
# Protocols define CONTRACTS without inheritance
# "If it has these methods, it's compatible"

class IRowProvider(Protocol):
    """
    Contract: Something that can provide table rows.
    
    📚 LEARNING: Dependency Inversion Principle
    
    The DOMAIN doesn't care HOW rows are obtained:
    - Could be Selenium scraping a website
    - Could be reading from a CSV file
    - Could be fetching from an API
    
    As long as it implements get_rows(), the domain works!
    
    💡 OLD CODE PROBLEM:
    parse_row_data() was tightly coupled to Selenium
    scroll_and_collect_rows() result.
    
    ✅ NEW: Works with ANY row provider
    """
    def get_rows(self) -> List[str]:
        """Get raw text rows from some source."""
        ...


# ============================================================================
# 📚 LEARNING CONCEPT 3: Parser (Single Responsibility)
# ============================================================================
# This class does ONE thing: parse text rows into Company objects

class CompanyRowParser:
    """
    Parses raw table rows into Company domain objects.
    
    📖 MIGRATED FROM: parse_row_data() function (src/scraper.py)
    
    🎯 IMPROVEMENTS:
    1. ✅ Testable WITHOUT Selenium (just pass text)
    2. ✅ Reusable (can parse from file, web, database)
    3. ✅ Configurable (patterns injected)
    4. ✅ Clear error handling
    
    💡 DESIGN PATTERN: Strategy Pattern
    Different parsing strategies for different formats.
    """
    
    # 📚 LEARNING: Class constants vs magic numbers
    # These were hardcoded in old parse_row_data()
    # Now they're named and configurable
    EXPECTED_VALUE_COUNT = 5
    
    def __init__(self, value_columns: Optional[List[str]] = None):
        """
        📚 LEARNING: Dependency Injection via constructor
        
        Instead of hardcoding VALUE_COLUMNS from config,
        we INJECT it. This makes the class:
        - ✅ Testable (can inject test values)
        - ✅ Flexible (different formats)
        - ✅ Explicit (clear what it needs)
        """
        self.value_columns = value_columns or [
            "Total Contratado",
            "Empenhado",
            "Saldo a Executar",
            "Liquidado",
            "Pago"
        ]
    
    def parse_row(self, row_text: str) -> Optional[Company]:
        """
        Parse a single row into a Company object.
        
        📖 MIGRATED FROM: Loop inside parse_row_data()
        
        💡 OLD vs NEW:
        OLD: for row_text in raw_rows: ... (mixed iteration + parsing)
        NEW: parse_row(text) - focused, testable function
        
        Args:
            row_text: Raw text like "12345 - Company ABC 1.000,00 500,00 ..."
            
        Returns:
            Company object or None if parsing fails
        """
        # Skip empty rows
        if not row_text.strip():
            return None
        
        # Skip summary rows (OLD: hardcoded check)
        if "total" in row_text.lower():
            return None
        
        # Skip rows with only numbers (incomplete)
        if re.match(r'^[\d\.,\s\-]+$', row_text.strip()):
            return None
        
        # 📚 STEP 1: Extract ID and rest
        # Pattern: "ID - Company Name values..."
        id_match = re.match(r'^([\w\d\.\/\-]+)\s*-\s*(.+)$', row_text.strip())
        
        if not id_match:
            return None
        
        company_id = id_match.group(1).strip()
        rest = id_match.group(2).strip()
        
        # 📚 STEP 2: Find currency numbers
        # Format: 1.234,56 or -1.234,56
        currency_numbers = re.findall(r'-?[\d\.]+,\d{2}', rest)
        
        if len(currency_numbers) < self.EXPECTED_VALUE_COUNT:
            return None
        
        # Take last 5 numbers
        numbers = currency_numbers[-self.EXPECTED_VALUE_COUNT:]
        
        # 📚 STEP 3: Extract company name
        # Everything before the first currency number
        first_currency = numbers[0]
        split_pos = rest.find(first_currency)
        company_name = rest[:split_pos].strip()
        
        # 📚 STEP 4: Create domain object
        try:
            return Company(
                id=company_id,
                name=company_name,
                total_contracted=numbers[0],
                committed=numbers[1],
                balance=numbers[2],
                settled=numbers[3],
                paid=numbers[4]
            )
        except ValueError as e:
            # Validation failed in Company.__post_init__
            return None
    
    def parse_all(self, rows: List[str]) -> ScrapingResult:
        """
        Parse all rows and return a result object.
        
        📚 LEARNING: Aggregate results instead of side effects
        
        OLD: Printed logs, modified global state
        NEW: Returns a pure Result object
        
        Benefits:
        - ✅ Testable (assert on result)
        - ✅ Composable (can chain operations)
        - ✅ No hidden side effects
        """
        companies = []
        errors = []
        
        for row_text in rows:
            try:
                company = self.parse_row(row_text)
                if company:
                    companies.append(company)
            except Exception as e:
                errors.append(f"Parse error: {row_text[:50]}... - {e}")
        
        return ScrapingResult(
            companies=companies,
            total_found=len(rows),
            total_parsed=len(companies),
            errors=errors
        )


# ============================================================================
# 📚 LEARNING CONCEPT 4: Facade Pattern
# ============================================================================
# Simple interface for complex subsystem

class ContasRioScraper:
    """
    High-level scraper for ContasRio portal.
    
    📚 LEARNING: Facade Pattern
    Hides complexity behind simple interface.
    
    This is what YOUR CODE uses.
    You don't need to know about parsers, providers, etc.
    
    💡 USAGE:
    
    OLD (src/scraper.py):
    ```
    driver = initialize_driver()
    navigate_to_contracts(driver)
    raw_rows = scroll_and_collect_rows(driver)
    companies = parse_row_data(raw_rows)  # Dictionary mess
    ```
    
    NEW:
    ```
    scraper = ContasRioScraper(row_provider)
    result = scraper.scrape()
    for company in result.companies:  # Clean objects
        print(company.name, company.total_contracted)
    ```
        High-level scraper using DTO flow.
    
    NEW Flow:
    1. Row provider → DTOs (infrastructure)
    2. Parser → Domain objects (domain)
    3. Return result
    
    Benefits:
    - Clear layers: infrastructure → domain
    - Domain doesn't know about Selenium
    - Easy to swap providers (Selenium → File → API)
    """
    
    def __init__(self, row_provider: IRowProvider):
        """
        📚 LEARNING: Dependency Injection
        
        We DON'T create the row_provider here.
        It's INJECTED from outside.
        
        WHY?
        - Can inject SeleniumRowProvider for real scraping
        - Can inject FileRowProvider for testing
        - Can inject MockRowProvider for demos
        
        The scraper doesn't care WHERE rows come from!
        """
        self.row_provider = row_provider
        self.parser = CompanyRowParser()
    
    def scrape_with_dtos(self) -> ScrapingResult:
        """
        NEW: Use DTO flow.
        
        Flow:
        1. Selenium → DTOs
        2. DTOs → Domain objects
        """
        # Get DTOs from Selenium
        dtos = self.row_provider.get_rows_as_dtos()
        
        # Parse DTOs → Domain
        companies = []
        for dto in dtos:
            company = self.parser.parse_from_dto(dto)
            if company:
                companies.append(company)
        
        return ScrapingResult(
            companies=companies,
            total_found=len(dtos),
            total_parsed=len(companies),
            errors=[]
        )

    def scrape(self) -> ScrapingResult:
        """
        Execute scraping with DTO flow.
        
        Returns:
            ScrapingResult with companies and metadata
        """
        
        # Step 1: Get DTOs from provider (infrastructure layer)
        dtos = self.row_provider.get_rows_as_dtos()
        
        # Step 2: Parse DTOs → Domain (domain layer)
        companies = []
        errors = []
        
        for dto in dtos:
            try:
                company = self.parser.parse_from_dto(dto)
                if company:
                    companies.append(company)
            except Exception as e:
                errors.append(f"Parse error for {dto.id_part}: {str(e)}")
        
        # Step 3: Return result
        return ScrapingResult(
            companies=companies,
            total_found=len(dtos),
            total_parsed=len(companies),
            errors=errors
        )


# ============================================================================
# 📚 COMPARISON: OLD vs NEW
# ============================================================================

"""
OLD CODE (src/scraper.py):

```python
def process_companies():
    driver = initialize_driver()  # ❌ Creates its own dependencies
    navigate_to_contracts(driver, year=2025)  # ❌ Hardcoded config
    raw_rows = scroll_and_collect_rows(driver)  # ❌ Mixed concerns
    
    all_data = []
    for row_text in raw_rows:  # ❌ No abstraction
        # ... 100 lines of parsing logic mixed with validation ...
        data_dict = {"ID": ..., "Company": ...}  # ❌ Untyped dict
        all_data.append(data_dict)
    
    return all_data  # ❌ No metadata about success/failure
```

PROBLEMS:
1. ❌ Can't test without Selenium
2. ❌ Can't swap data sources
3. ❌ Parsing mixed with iteration
4. ❌ Untyped dictionaries
5. ❌ No error handling
6. ❌ Hard to understand
7. ❌ Hard to modify

NEW CODE (this file):

```python
# In your app:
row_provider = SeleniumRowProvider(driver)  # Infrastructure
scraper = ContasRioScraper(row_provider)    # Domain
result = scraper.scrape()                   # Clean call

# Or for testing:
row_provider = FileRowProvider("test_data.txt")
scraper = ContasRioScraper(row_provider)
result = scraper.scrape()  # Same interface!
```

BENEFITS:
1. ✅ Testable without browser
2. ✅ Swappable data sources
3. ✅ Clear separation
4. ✅ Type-safe objects
5. ✅ Explicit error handling
6. ✅ Self-documenting
7. ✅ Easy to extend
"""

# ============================================================================
# 📚 NEXT STEPS FOR YOU
# ============================================================================

"""
TO COMPLETE THIS MODULE, CREATE:

1. infrastructure/web/selenium_row_provider.py
   - Implements IRowProvider using Selenium
   - Contains scroll_and_collect_rows() logic
   
2. tests/domain/scraping/test_parser.py
   - Test parse_row() with sample strings
   - NO Selenium needed!
   
3. services/scraping_service.py
   - High-level service that:
     - Creates driver
     - Creates SeleniumRowProvider
     - Creates ContasRioScraper
     - Handles errors
     - Saves results

LEARNING EXERCISE:
1. Try to test CompanyRowParser.parse_row() with a string
2. Notice: No Selenium, no browser, instant test!
3. Compare to testing old parse_row_data() - needed full scraping

UNDERSTANDING CHECK:
- Can you explain WHY Company is a dataclass?
- Can you explain WHY we use IRowProvider protocol?
- Can you explain WHAT ContasRioScraper orchestrates?
"""