"""
ContasRio portal scraper.
Handles navigation and data extraction from ContasRio contracts portal.
"""
import time
import logging
from typing import List, Optional
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException

from typing import cast

from config.settings import CONTASRIO_BASE_URL, CONTASRIO_CONTRACTS_URL, FILTER_YEAR
from config.portals import CONTASRIO_LOCATORS
from infrastructure.web.navigation import (
    wait_for_element,
    wait_for_elements,
    click_element_safe,
    scroll_to_bottom,
    get_current_url
)
from infrastructure.scrapers.contasrio.parsers import CompanyRowParser
from domain.models.processo_link import CompanyData, ProcessoLink

logger = logging.getLogger(__name__)


class ContasRioScraper:
    """
    Scraper for ContasRio portal.
    Discovers companies and processo links.
    """
    
    def __init__(self, driver: webdriver.Chrome):
        """
        Initialize scraper.
        
        Args:
            driver: Selenium WebDriver instance
        """
        self.driver = driver
    
    def discover_all_processos(self) -> List[ProcessoLink]:
        """
        Main discovery workflow.
        
        Workflow:
        1. Navigate to contracts page
        2. Apply filters
        3. Collect all companies
        4. For each company, discover processo links
        
        Returns:
            List of discovered ProcessoLink objects
        """
        logger.info("=" * 70)
        logger.info("🔍 STAGE 1: DISCOVERY - ContasRio Portal")
        logger.info("=" * 70)
        
        all_processos = []
        
        # Step 1: Navigate to contracts page
        logger.info("\n📋 Step 1: Navigating to contracts page...")
        if not self._navigate_to_contracts():
            logger.error("✗ Failed to navigate to contracts page")
            return []
        
        # Step 2: Apply filters
        logger.info("\n📋 Step 2: Applying filters...")
        if not self._apply_filters():
            logger.warning("⚠ Filter application failed, continuing anyway...")
        
        # Step 3: Collect companies
        logger.info("\n📋 Step 3: Collecting companies...")
        companies = self._collect_companies()
        logger.info(f"✓ Found {len(companies)} companies")
        
        if not companies:
            logger.error("✗ No companies found")
            return []
        
        # Step 4: For each company, discover processos
        logger.info("\n📋 Step 4: Discovering processos for each company...")
        for i, company in enumerate(companies, 1):
            logger.info(f"\n   [{i}/{len(companies)}] Processing: {company.company_name}")
            
            processos = self._discover_company_processos(company)
            all_processos.extend(processos)
            
            logger.info(f"   ✓ Found {len(processos)} processos")
            logger.info(f"   Running total: {len(all_processos)} processos")
        
        # Summary
        logger.info("\n" + "=" * 70)
        logger.info(f"✓ DISCOVERY COMPLETE")
        logger.info(f"   Companies processed: {len(companies)}")
        logger.info(f"   Total processos found: {len(all_processos)}")
        logger.info("=" * 70)
        
        return all_processos
    
    def _navigate_to_contracts(self) -> bool:
        """
        Navigate to contracts page.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # It doesn't have to exist. We navigate traight to the page
            # First navigate to base URL
            logger.info(f"   → Navigating to: {CONTASRIO_CONTRACTS_URL}")
            self.driver.get(CONTASRIO_CONTRACTS_URL)
            time.sleep(2)

            # Wait for page to load
            if not wait_for_element(self.driver, By.TAG_NAME, "body", timeout=10):
                logger.error("   ✗ Page body not found")
                return False
            
            # "SOFT 404" CHECK ERROR (in case of sudden link/resource change) 
            error_xpath = "//*[contains(text(), 'O recurso requisitado não foi encontrado')]"
            error_element = wait_for_element(self.driver, By.XPATH, error_xpath, timeout=3)

            if error_element:
                logger.error("   ✗ SOFT 404 DETECTED: 'Resource not found' message appeared.")
                return False

            current_url = get_current_url(self.driver)
            logger.info(f"   ✓ Current URL: {current_url}")
            
            return True
            
        except Exception as e:
            logger.error(f"   ✗ Navigation failed: {e}")
            return False
    
    def _apply_filters(self) -> bool:
        """
        Apply year filter if configured.
        
        Returns:
            True if successful or no filter needed, False otherwise
        """
        try:
            if not FILTER_YEAR:
                logger.info("   ⏭️ No year filter configured")
                return True
            
            logger.info(f"   → Looking for year filter selector...")
            
            # Try to find year filter element
            year_filter = wait_for_element(
                self.driver,
                By.TAG_NAME,
                CONTASRIO_LOCATORS["year_filter"],
                timeout=5
            )
            
            if not year_filter:
                logger.warning("   ⚠ Year filter not found (may not exist on this portal)")
                return True
            
            # Select year
            logger.info(f"   → Setting year to: {FILTER_YEAR}")
            year_filter.send_keys(str(FILTER_YEAR))
            time.sleep(1)
            
            logger.info(f"   ✓ Applied filter: Year {FILTER_YEAR}")
            return True
            
        except Exception as e:
            logger.error(f"   ✗ Filter application failed: {e}")
            return False
    
    def _collect_companies(self) -> List[CompanyData]:
        """
        Collect all company rows from the table.
        
        Returns:
            List of CompanyData objects
        """
        companies = []
        
        try:
            logger.info("   → Scrolling to load all companies...")
            scroll_to_bottom(self.driver, pause=0.5)
            time.sleep(1)
            
            logger.info("   → Looking for company table...")
            
            # Wait for table rows
            rows = wait_for_elements(
                self.driver,
                cast(By, By.TAG_NAME),
                CONTASRIO_LOCATORS["company_rows"],
                timeout=10,
                min_count=1
            )
            
            if not rows:
                logger.warning("   ⚠ No company rows found with CSS selector")
                # Try alternative: find table and get all rows
                rows = self._find_table_rows_alternative()
            
            logger.info(f"   ✓ Found {len(rows)} rows in table")
            
            # Parse each row
            for i, row in enumerate(rows, 1):
                company = CompanyRowParser.parse_row(row, i)
                if company:
                    companies.append(company)
            
            logger.info(f"   ✓ Successfully parsed {len(companies)} companies")
            
            return companies
            
        except Exception as e:
            logger.error(f"   ✗ Company collection failed: {e}")
            return []
    
    def _find_table_rows_alternative(self) -> List:
        """
        Alternative method to find table rows.
        
        Returns:
            List of row elements
        """
        try:
            # Look for any table
            tables = self.driver.find_elements(By.TAG_NAME, "table")
            
            if not tables:
                return []
            
            # Use first table (or largest table)
            table = tables[0]
            
            # Get all rows from tbody
            tbody = table.find_element(By.TAG_NAME, "tbody")
            rows = tbody.find_elements(By.TAG_NAME, "tr")
            
            logger.info(f"   ✓ Found {len(rows)} rows using alternative method")
            return rows
            
        except Exception as e:
            logger.debug(f"   Alternative row finding failed: {e}")
            return []
    
    def _discover_company_processos(self, company: CompanyData) -> List[ProcessoLink]:
        """
        Discover all processos for a specific company.
        
        Args:
            company: CompanyData object
            
        Returns:
            List of ProcessoLink objects for this company
        """
        from infrastructure.scrapers.contasrio.navigation import PathNavigator
        
        processos = []
        
        try:
            navigator = PathNavigator(self.driver)
            processos = navigator.discover_company_paths(company)
            
            # Update company contract count
            company.total_contracts = len(processos)
            
        except Exception as e:
            logger.error(f"   ✗ Discovery failed for {company.company_name}: {e}")
        
        return processos