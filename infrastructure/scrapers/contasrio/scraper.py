"""
ContasRio portal scraper.
Handles navigation and data extraction from ContasRio contracts portal.
"""
import time
import logging
import re
from datetime import datetime
from typing import List, Optional, Tuple
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options

from infrastructure.scrapers.contasrio.navigation import PathNavigator



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
            # It doesn't have to exist. We navigate traight to the page, but some errors were hapening 
            # and I returned the original structure by following AI suggestion
            logger.info(f"   → Navigating to: {CONTASRIO_BASE_URL}")
            self.driver.get(CONTASRIO_BASE_URL)
            time.sleep(5)
            
            # First navigate to base URL
            logger.info(f"   → Navigating to: {CONTASRIO_CONTRACTS_URL}")
            self.driver.get(CONTASRIO_CONTRACTS_URL)
            time.sleep(5)
            self.driver.refresh()

            # 1️⃣ Confirm correct route
            if "#!Contratos/Contrato" not in self.driver.current_url:
                logger.error("✗ Unexpected redirect")
                return False

            # 2️⃣ Wait for grid container
            wait_for_element(
                self.driver,
                By.CSS_SELECTOR,
                "div.v-grid",
                timeout=60,
                visible=True
            )

            # 3️⃣ Wait for actual data cells
            cells = WebDriverWait(self.driver, 120).until(
                lambda d: d.find_elements(
                    By.CSS_SELECTOR,
                    "td.v-grid-cell[role='gridcell']"
                )
            )

            if not cells:
                logger.error("✗ Grid loaded but no data")
                return False

            logger.info("✓ Contracts grid fully loaded and stable")
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
            
            year_filter = WebDriverWait(self.driver, 30).until(
                EC.element_to_be_clickable((
                    By.XPATH,
                    "//div[contains(@class,'v-label') and contains(text(),'ANO DE CELEBRAÇÃO')]"
                    "/following::input[contains(@class,'v-filterselect-input')][1]"
                ))
            )
            
            # Read current value
            current_value = year_filter.get_attribute("value") or ""
            logger.info(f"   → Current filter value: '{current_value}'")
            
            # Check if already set to desired year
            if current_value.strip() == str(FILTER_YEAR):
                logger.info(f"   ✓ Filter already set to {FILTER_YEAR}")
                return True
            
            # Scroll into view
            self.driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center'});",
                year_filter
            )
            time.sleep(0.5)
            
            # Click to focus (JS click for Vaadin safety)
            self.driver.execute_script(
                "arguments[0].click();", year_filter
            )
            time.sleep(0.3)
            
            # ── Clear using character-by-character backspace ──
            # This is the PROVEN method for Vaadin v-filterselect
            current_value = year_filter.get_attribute("value") or ""
            logger.info(
                f"   → Clearing '{current_value}' "
                f"({len(current_value)} chars)"
            )
            
            year_filter.send_keys(Keys.END)
            time.sleep(0.1)
            
            for i in range(len(current_value)):
                year_filter.send_keys(Keys.BACKSPACE)
                time.sleep(0.05)  # Small delay between keystrokes
            
            # Verify cleared
            after_clear = year_filter.get_attribute("value") or ""
            logger.info(f"   → After clear: '{after_clear}'")
            
            if after_clear.strip() != "":
                logger.warning(
                    f"   ⚠ Field not fully cleared, "
                    f"retrying with more backspaces"
                )
                for _ in range(10):
                    year_filter.send_keys(Keys.BACKSPACE)
                    time.sleep(0.05)
            
            # ── Type the desired year ──
            time.sleep(0.3)
            year_filter.send_keys(str(FILTER_YEAR))
            time.sleep(0.5)
            
            # Verify typed
            after_type = year_filter.get_attribute("value") or ""
            logger.info(f"   → After typing: '{after_type}'")
            
            # ── Confirm selection ──
            # Vaadin filterselect may show a dropdown suggestion
            # We need to either:
            #   a) Press ENTER to confirm
            #   b) Wait for dropdown and click the matching option
            
            # Try ENTER first
            year_filter.send_keys(Keys.ENTER)
            time.sleep(1.0)
            
            # Verify final value
            final_value = year_filter.get_attribute("value") or ""
            logger.info(f"   → Final filter value: '{final_value}'")
            
            if str(FILTER_YEAR) not in final_value:
                logger.warning(
                    f"   ⚠ Filter may not have applied. "
                    f"Expected '{FILTER_YEAR}', got '{final_value}'"
                )
                
                # Fallback: try selecting from dropdown
                logger.info("   → Trying dropdown selection fallback...")
                return self._apply_filter_via_dropdown(
                    year_filter, str(FILTER_YEAR)
                )
            
            # ── Wait for grid to reload with filtered data ──
            logger.info("   → Waiting for grid to reload...")
            time.sleep(2.0)
            
            WebDriverWait(self.driver, 120).until(
                lambda d: d.find_elements(
                    By.CSS_SELECTOR,
                    "td.v-grid-cell[role='gridcell']"
                )
            )
            
            logger.info(f"   ✓ Applied filter: Year {FILTER_YEAR}")
            return True
            
        except Exception as e:
            logger.error(f"   ✗ Filter application failed: {e}")
            return False


    def _apply_filter_via_dropdown(
        self, 
        filter_input, 
        year: str
    ) -> bool:
        """
        Fallback: Select year from Vaadin filterselect dropdown.
        
        When typing + ENTER doesn't work, Vaadin may require
        clicking the dropdown button and selecting the option.
        
        Args:
            filter_input: The filter input WebElement
            year: Year string to select
            
        Returns:
            True if successful
        """
        try:
            # Find the dropdown button next to the input
            # Vaadin filterselect has a button with class v-filterselect-button
            dropdown_btn = self.driver.execute_script("""
                var input = arguments[0];
                var parent = input.closest('.v-filterselect');
                if (!parent) return null;
                return parent.querySelector('.v-filterselect-button');
            """, filter_input)
            
            if not dropdown_btn:
                logger.warning("   ⚠ Could not find dropdown button")
                return False
            
            # Click dropdown to open options
            self.driver.execute_script(
                "arguments[0].click();", dropdown_btn
            )
            time.sleep(1.0)
            
            # Find and click the matching option
            option = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((
                    By.XPATH,
                    f"//div[contains(@class,'v-filterselect-suggestmenu')]"
                    f"//span[text()='{year}']"
                ))
            )
            
            option.click()
            time.sleep(1.0)
            
            # Verify
            final_value = filter_input.get_attribute("value") or ""
            logger.info(f"   → Dropdown selection result: '{final_value}'")
            
            # Wait for grid reload
            WebDriverWait(self.driver, 120).until(
                lambda d: d.find_elements(
                    By.CSS_SELECTOR,
                    "td.v-grid-cell[role='gridcell']"
                )
            )
            
            return year in final_value
            
        except Exception as e:
            logger.warning(f"   ⚠ Dropdown fallback failed: {e}")
            return False
    
    def _collect_companies(self) -> List[CompanyData]:
        """
        Collect all company rows from the Vaadin grid using scroll-and-harvest.
        
        Validates completeness by:
        1. Checking overlap between consecutive harvests (ensures no gaps)
        2. Comparing final count against TOTAL row if available
        3. Cross-referencing with CSV if provided
        
        Returns:
            List of CompanyData objects
        """
        GRID_CSS = "div.v-grid"
        SCROLL_INCREMENT = 200  # Conservative: ~5 rows, ensures overlap
        SCROLL_PAUSE = 2.0
        STALE_ROUNDS = 5
        ABSOLUTE_MAX_SCROLLS = 300  # Pure safety net
        
        seen_ids: set = set()
        companies: List[CompanyData] = []
        previous_harvest_ids: set = set()  # For overlap validation
        total_row_value: Optional[str] = None  # From TOTAL row
        no_overlap_warnings: int = 0
        
        try:
            logger.info("   → Waiting for grid data cells...")
            WebDriverWait(self.driver, 60).until(
                EC.presence_of_element_located((
                    By.CSS_SELECTOR,
                    f"{GRID_CSS} td.v-grid-cell[role='gridcell']"
                ))
            )
            
            # Locate the grid's internal scroller
            scroller = self._find_grid_scroller(GRID_CSS)
            if not scroller:
                logger.error("   ✗ Could not locate grid scroller")
                return []
            
            # Reset to top
            self.driver.execute_script("arguments[0].scrollTop = 0;", scroller, 200)
            time.sleep(SCROLL_PAUSE)
            
            stale_count = 0
            scroll_count = 0
            
            logger.info("   → Scrolling grid and harvesting rows...")
            
            while scroll_count < ABSOLUTE_MAX_SCROLLS:
                # ── Harvest visible rows ──
                visible_rows = self._harvest_visible_rows(GRID_CSS)
                
                current_harvest_ids: set = set()
                new_this_round = 0
                
                for row_cells in visible_rows:
                    # Extract the Favorecido text (first column)
                    if not row_cells or not row_cells[0].strip():
                        continue
                    
                    favorecido_text = row_cells[0].strip()
                    
                    # Capture TOTAL row value for validation, then skip
                    if favorecido_text.upper().startswith("TOTAL"):
                        if len(row_cells) > 1:
                            total_row_value = row_cells[1].strip()
                            logger.info(f"   → TOTAL row detected: {total_row_value}")
                        continue
                    
                    # Parse the Favorecido column
                    parsed = self._parse_favorecido(favorecido_text)
                    if parsed is None:
                        continue
                    
                    company_id, company_name = parsed
                    current_harvest_ids.add(company_id)
                    
                    # Deduplicate
                    if company_id not in seen_ids:
                        seen_ids.add(company_id)
                        
                        company = CompanyData(
                            company_id=company_id,
                            company_name=company_name,
                            company_cnpj=company_id if len(re.sub(r'\D', '', company_id)) == 14 else None,
                            total_contracts=0,
                            total_value= (row_cells[1].strip() if len(row_cells) > 1 else None),
                        # Store raw cells for later use if needed
                        raw_cells=row_cells,  # Clean, explicit, type-safe
                        )

                        companies.append(company)
                        new_this_round += 1
                
                # ── Overlap validation ──
                if previous_harvest_ids and current_harvest_ids:
                    overlap = previous_harvest_ids & current_harvest_ids
                    if not overlap and new_this_round > 0:
                        no_overlap_warnings += 1
                        logger.warning(
                            f"   ⚠ No overlap between harvest {scroll_count} and "
                            f"{scroll_count - 1}. Possible gap! "
                            f"(Warning #{no_overlap_warnings})"
                        )
                        # Reduce scroll increment to try to catch missed rows
                        if no_overlap_warnings >= 2:
                            SCROLL_INCREMENT = max(50, SCROLL_INCREMENT // 2)
                            logger.warning(
                                f"   ⚠ Reducing scroll increment to {SCROLL_INCREMENT}px"
                            )
                
                previous_harvest_ids = current_harvest_ids.copy()
                
                # ── Staleness check ──
                if new_this_round == 0:
                    stale_count += 1
                    if stale_count >= STALE_ROUNDS:
                        logger.info(
                            f"   → No new rows for {STALE_ROUNDS} consecutive scrolls. "
                            f"Collection complete."
                        )
                        break
                else:
                    stale_count = 0
                
                time.sleep(0.5)

                # ── Scroll ──
                old_top = self.driver.execute_script(
                    "return arguments[0].scrollTop;", scroller
                )
                self.driver.execute_script(
                    "arguments[0].scrollTop += arguments[1];",
                    scroller,
                    SCROLL_INCREMENT
                )
                time.sleep(SCROLL_PAUSE)
                new_top = self.driver.execute_script(
                    "return arguments[0].scrollTop;", scroller
                )
                
                # Bottom reached
                if new_top == old_top:
                    # Final harvest
                    visible_rows = self._harvest_visible_rows(GRID_CSS)
                    for row_cells in visible_rows:
                        if not row_cells or not row_cells[0].strip():
                            continue
                        favorecido_text = row_cells[0].strip()
                        if favorecido_text.upper().startswith("TOTAL"):
                            continue
                        parsed = self._parse_favorecido(favorecido_text)
                        if parsed and parsed[0] not in seen_ids:
                            seen_ids.add(parsed[0])
                            company = CompanyData(
                                company_id=parsed[0],
                                company_name=parsed[1],
                                company_cnpj=parsed[0] if len(re.sub(r'\D', '', parsed[0])) == 14 else None,
                                total_contracts=0,
                                total_value=row_cells[1].strip() if len(row_cells) > 1 else None,
                            )
                            companies.append(company)
                    
                    logger.info("   → Reached bottom of grid")
                    break
                
                scroll_count += 1
                if scroll_count % 10 == 0:
                    logger.info(
                        f"   ... scrolled {scroll_count} times, "
                        f"collected {len(companies)} unique companies so far"
                    )
            
            # ── Post-collection validation ──
            self._validate_collection(companies, total_row_value, no_overlap_warnings)
            
            logger.info(f"   ✓ Total unique companies collected: {len(companies)}")
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

        processos = []
        
        try:
            navigator = PathNavigator(self.driver)
            processos = navigator.discover_company_paths(company)
            
            # Update company contract count
            company.total_contracts = len(processos)
            
        except Exception as e:
            logger.error(f"   ✗ Discovery failed for {company.company_name}: {e}")
        
        return processos

    def _find_grid_scroller(self, grid_css: str):
        """Locate the Vaadin grid's internal scrollable element."""
        return self.driver.execute_script("""
            var grid = document.querySelector(arguments[0]);
            if (!grid) return null;
            var s = grid.querySelector('.v-grid-scroller-vertical');
            if (s) return s;
            var w = grid.querySelector('.v-grid-tablewrapper');
            if (w) return w;
            return grid;
        """, grid_css)


    def _harvest_visible_rows(self, grid_css: str) -> List[List[str]]:
        """Read all currently visible rows from the Vaadin grid via JS."""
        rows_data = self.driver.execute_script("""
            var grid = document.querySelector(arguments[0]);
            if (!grid) return [];
            
            var tbody = grid.querySelector('table tbody')
                        || grid.querySelector('.v-grid-body');
            if (!tbody) return [];
            
            var rows = tbody.querySelectorAll('tr');
            var result = [];
            
            for (var i = 0; i < rows.length; i++) {
                var cells = rows[i].querySelectorAll('td.v-grid-cell[role="gridcell"]');
                if (cells.length === 0) continue;
                
                var rowData = [];
                for (var j = 0; j < cells.length; j++) {
                    rowData.push(cells[j].innerText.trim());
                }
                result.push(rowData);
            }
            
            return result;
        """, grid_css)
        
        return rows_data or []


    def _parse_favorecido(self, text: str) -> Optional[Tuple[str, str]]:
        """
        Parse the Favorecido column into (company_id, company_name).
        
        Format: '01282704000167 - GREMIO RECREATIVO ESCOLA DE SAMBA...'
        Separator: ' - ' (space-dash-space), split on first occurrence only.
        
        Returns:
            Tuple of (id, name) or None if unparseable
        """
        if not text or text.upper().startswith("TOTAL"):
            return None
        
        parts = text.split(" - ", maxsplit=1)
        
        if len(parts) == 2:
            company_id = parts[0].strip()
            company_name = parts[1].strip()
        elif len(parts) == 1:
            # No separator — treat entire text as name, generate synthetic ID
            company_id = re.sub(r'[^A-Za-z0-9]', '', text)[:30].upper()
            company_name = text
            logger.warning(f"   ⚠ No separator found in Favorecido: {text[:60]}")
        else:
            return None
        
        if not company_id or not company_name:
            return None
        
        # Normalize the ID: remove formatting characters, uppercase
        company_id_normalized = re.sub(r'[^A-Za-z0-9]', '', company_id).upper()
        
        return (company_id_normalized, company_name)


    def _validate_collection(
        self,
        companies: List[CompanyData],
        total_row_value: Optional[str],
        no_overlap_warnings: int
    ) -> None:
        """
        Post-collection validation and reporting.
        
        Checks:
        1. Were there any overlap gaps during scrolling?
        2. Does the count seem reasonable?
        3. Log summary for manual verification against CSV
        """
        logger.info("   ─── Collection Validation ───")
        logger.info(f"   Companies collected: {len(companies)}")
        
        if total_row_value:
            logger.info(f"   TOTAL row value: {total_row_value}")
        
        if no_overlap_warnings > 0:
            logger.warning(
                f"   ⚠ {no_overlap_warnings} overlap gaps detected during scrolling. "
                f"Some companies may have been missed. "
                f"Consider re-running with lower SCROLL_INCREMENT."
            )
        else:
            logger.info("   ✓ No overlap gaps — continuous coverage confirmed")
        
        # Count by ID type
        cnpj_count = 0
        cpf_count = 0
        other_count = 0
        for c in companies:
            digits = re.sub(r'\D', '', c.company_id)
            if len(digits) == 14:
                cnpj_count += 1
            elif len(digits) == 11:
                cpf_count += 1
            else:
                other_count += 1
        
        logger.info(f"   ID breakdown: CNPJ={cnpj_count}, CPF={cpf_count}, Other={other_count}")
        logger.info("   ────────────────────────────")