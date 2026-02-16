"""
Navigation logic for ContasRio portal hierarchy.
Handles path discovery and processo link collection.
"""
import time
import logging
from typing import List, Set, Tuple
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException, StaleElementReferenceException

from config.portals import CONTASRIO_LOCATORS
from infrastructure.web.navigation import (
    wait_for_element,
    wait_for_elements,
    click_element_safe,
    scroll_to_element,
    go_back
)
from domain.models.processo_link import ProcessoLink, CompanyData

logger = logging.getLogger(__name__)


class PathNavigator:
    """
    Handles navigation through ContasRio hierarchy to discover processo links.
    """
    
    def __init__(self, driver: webdriver.Chrome):
        """
        Initialize navigator.
        
        Args:
            driver: Selenium WebDriver instance
        """
        self.driver = driver
    
    def discover_company_paths(self, company: CompanyData) -> List[ProcessoLink]:
        """
        Discover all navigation paths for a company and collect processo links.
        
        Strategy:
        1. Click on company to enter hierarchy
        2. Recursively explore all navigation paths
        3. At deepest level (has processo links), collect them
        4. Backtrack to explore other branches
        
        Args:
            company: CompanyData object
            
        Returns:
            List of discovered ProcessoLink objects
        """
        logger.info(f"   → Starting path discovery for: {company.company_name}")
        
        all_processos = []
        
        # Click on company to enter its hierarchy
        if not self._click_company(company):
            logger.warning(f"   ⚠ Could not click on company: {company.company_name}")
            return []
        
        # Give page time to load
        time.sleep(2)
        
        # Recursively explore all paths
        processos = self._explore_level(
            current_path=[],
            company=company,
            visited_buttons=set()
        )
        
        all_processos.extend(processos)
        
        logger.info(f"   ✓ Path discovery complete: {len(all_processos)} processos found")
        
        return all_processos
    
    def _click_company(self, company: CompanyData) -> bool:
        """
        Click on company row to enter its hierarchy.
        
        Args:
            company: CompanyData object
            
        Returns:
            True if clicked successfully, False otherwise
        """
        try:
            # Find company rows
            rows = self.driver.find_elements(By.CSS_SELECTOR, CONTASRIO_LOCATORS["company_rows"])
            
            if not rows:
                rows = self.driver.find_elements(By.XPATH, "//table//tr")
            
            # Find row containing company name
            for row in rows:
                if company.company_name in row.text:
                    scroll_to_element(self.driver, row)
                    
                    if click_element_safe(self.driver, row, wait_after=2):
                        logger.info(f"   ✓ Clicked company: {company.company_name}")
                        return True
            
            logger.warning(f"   ⚠ Company row not found in table: {company.company_name}")
            return False
            
        except Exception as e:
            logger.error(f"   ✗ Failed to click company: {e}")
            return False
    
    def _explore_level(
        self,
        current_path: List[str],
        company: CompanyData,
        visited_buttons: Set[str]
    ) -> List[ProcessoLink]:
        """
        Recursively explore navigation level.
        
        Args:
            current_path: Path taken to reach this level (list of button texts)
            company: Current company being explored
            visited_buttons: Set of button texts already visited at this level
            
        Returns:
            List of ProcessoLink objects found in this branch
        """
        processos = []
        
        path_str = ' → '.join(current_path) if current_path else '(root)'
        logger.info(f"   → Exploring level: {path_str}")
        
        # Check if we've reached the deepest level (has processo links)
        if self._has_processo_links():
            logger.info(f"   ✓ Reached deepest level with processo links")
            processos = self._collect_processo_links(current_path, company)
            return processos
        
        # Get navigation buttons at this level
        buttons = self._get_navigation_buttons()
        logger.info(f"   → Found {len(buttons)} navigation options")
        
        if not buttons:
            logger.info(f"   ⚠ No navigation buttons found (dead end)")
            return []
        
        # Explore each button
        for button_text in buttons:
            # Skip if already visited at this level
            if button_text in visited_buttons:
                logger.debug(f"   ⏭️ Skipping visited button: {button_text}")
                continue
            
            # Mark as visited
            visited_buttons.add(button_text)
            
            # Click button to go deeper
            if self._click_button(button_text):
                new_path = current_path + [button_text]
                logger.info(f"   → Entered: {' → '.join(new_path)}")
                
                # Recursively explore this branch
                sub_processos = self._explore_level(
                    current_path=new_path,
                    company=company,
                    visited_buttons=set()  # New level = new visited set
                )
                
                processos.extend(sub_processos)
                
                # Go back to this level
                self._go_back_to_level()
                time.sleep(1)
                
                logger.info(f"   ← Back to level: {path_str}")
            else:
                logger.warning(f"   ⚠ Could not click button: {button_text}")
        
        return processos
    
    def _has_processo_links(self) -> bool:
        """
        Check if current page has processo links.
        
        Returns:
            True if processo links are present, False otherwise
        """
        try:
            # Look for links containing "processo" in href
            links = self.driver.find_elements(
                By.CSS_SELECTOR,
                CONTASRIO_LOCATORS["processo_links"]
            )
            
            if links:
                logger.debug(f"   ✓ Found {len(links)} processo links")
                return True
            
            # Alternative: Look for any external links
            links = self.driver.find_elements(
                By.XPATH,
                "//a[starts-with(@href, 'http')]"
            )
            
            # Filter for links that might be processos
            processo_links = [
                link for link in links
                if 'processo' in (link.get_attribute('href') or "").lower()
                or 'PRO-' in link.text
                or 'TUR' in link.text
            ]
            
            if processo_links:
                logger.debug(f"   ✓ Found {len(processo_links)} potential processo links")
                return True
            
            return False
            
        except Exception as e:
            logger.debug(f"   Processo link check failed: {e}")
            return False
    
    def _get_navigation_buttons(self) -> List[str]:
        """
        Get text of all navigation buttons at current level.
        
        Returns:
            List of button texts
        """
        button_texts = []
        
        try:
            # Find all clickable navigation elements
            buttons = self.driver.find_elements(
                By.CSS_SELECTOR,
                CONTASRIO_LOCATORS["navigation_buttons"]
            )
            
            if not buttons:
                # Alternative: find all buttons
                buttons = self.driver.find_elements(By.TAG_NAME, "button")
                buttons.extend(self.driver.find_elements(By.TAG_NAME, "a"))
            
            # Extract text from each button
            for btn in buttons:
                try:
                    text = btn.text.strip()
                    if text and len(text) > 0 and len(text) < 100:
                        # Avoid duplicate texts
                        if text not in button_texts:
                            button_texts.append(text)
                except StaleElementReferenceException:
                    continue
            
            return button_texts
            
        except Exception as e:
            logger.debug(f"   Button extraction failed: {e}")
            return []
    
    def _click_button(self, button_text: str) -> bool:
        """
        Click navigation button by its text.
        
        Args:
            button_text: Text of button to click
            
        Returns:
            True if clicked successfully, False otherwise
        """
        try:
            # Find all buttons
            buttons = self.driver.find_elements(
                By.CSS_SELECTOR,
                CONTASRIO_LOCATORS["navigation_buttons"]
            )
            
            if not buttons:
                buttons = self.driver.find_elements(By.TAG_NAME, "button")
                buttons.extend(self.driver.find_elements(By.TAG_NAME, "a"))
            
            # Find button with matching text
            for btn in buttons:
                try:
                    if btn.text.strip() == button_text:
                        scroll_to_element(self.driver, btn)
                        return click_element_safe(self.driver, btn, wait_after=2)
                except StaleElementReferenceException:
                    continue
            
            logger.debug(f"   ⚠ Button not found: {button_text}")
            return False
            
        except Exception as e:
            logger.debug(f"   Button click failed: {e}")
            return False
    
    def _go_back_to_level(self) -> None:
        """
        Navigate back to previous level.
        Uses browser back or back button if available.
        """
        try:
            # Try to find explicit back button first
            back_button = wait_for_element(
                self.driver,
                By.CSS_SELECTOR,
                CONTASRIO_LOCATORS["back_button"],
                timeout=2
            )
            
            if back_button:
                click_element_safe(self.driver, back_button, wait_after=1)
                logger.debug("   ← Used back button")
            else:
                # Use browser back
                go_back(self.driver, wait_after=1)
                logger.debug("   ← Used browser back")
                
        except Exception as e:
            logger.debug(f"   ⚠ Go back failed: {e}")
            # Try browser back as fallback
            go_back(self.driver, wait_after=1)
    
    def _collect_processo_links(
        self,
        path: List[str],
        company: CompanyData
    ) -> List[ProcessoLink]:
        """
        Collect all processo links from current page.
        
        Args:
            path: Navigation path taken to reach this page
            company: Current company
            
        Returns:
            List of ProcessoLink objects
        """
        processos = []
        
        try:
            # Find all processo links
            links = self.driver.find_elements(
                By.CSS_SELECTOR,
                CONTASRIO_LOCATORS["processo_links"]
            )
            
            if not links:
                # Alternative search
                links = self.driver.find_elements(
                    By.XPATH,
                    "//a[contains(@href, 'processo')]"
                )
            
            logger.info(f"   → Collecting {len(links)} processo links...")
            
            # Extract data from each link
            for link in links:
                try:
                    url = link.get_attribute("href")
                    text = link.text.strip()
                    
                    if not url:
                        continue
                    
                    # Extract processo ID
                    processo_id = self._extract_processo_id(text, url)
                    
                    if processo_id and url:
                        processo = ProcessoLink(
                            processo_id=processo_id,
                            url=url,
                            company_name=company.company_name,
                            company_cnpj=company.company_cnpj,
                            contract_value=company.total_value,
                            discovery_path=path.copy()
                        )
                        
                        processos.append(processo)
                        logger.debug(f"      ✓ {processo_id}")
                        
                except StaleElementReferenceException:
                    continue
                except Exception as e:
                    logger.debug(f"      ⚠ Link extraction failed: {e}")
                    continue
            
            logger.info(f"   ✓ Collected {len(processos)} valid processo links")
            
        except Exception as e:
            logger.error(f"   ✗ Link collection failed: {e}")
        
        return processos
    
    @staticmethod
    def _extract_processo_id(text: str, url: str) -> str:
        """
        Extract processo ID from link text or URL.
        
        Common patterns:
        - TURCAP202500477
        - SME-PRO-2025/19222
        - 01/04/000123/2020
        
        Args:
            text: Link text
            url: Link URL
            
        Returns:
            Processo ID string
        """
        import re
        
        # Pattern 1: Modern format (letters + numbers)
        # Examples: TURCAP202500477, SMEPRO202519222
        pattern1 = r'[A-Z]{2,6}\d{6,}'
        match = re.search(pattern1, text)
        if match:
            return match.group(0)
        
        # Pattern 2: With separators (hyphens, slashes)
        # Examples: SME-PRO-2025/19222, TUR-CAP-2025/00477
        pattern2 = r'[A-Z]{2,4}[\-][A-Z]{2,4}[\-]\d{4}/\d{4,6}'
        match = re.search(pattern2, text)
        if match:
            return match.group(0)
        
        # Pattern 3: Old format with slashes
        # Examples: 01/04/000123/2020
        pattern3 = r'\d{2}/\d{2}/\d{6}/\d{4}'
        match = re.search(pattern3, text)
        if match:
            return match.group(0)
        
        # Pattern 4: Extract from URL
        # Example: ...?processo=TURCAP202500477
        if 'processo' in url:
            pattern_url = r'processo[=/]([A-Z0-9\-/]+)'
            match = re.search(pattern_url, url, re.IGNORECASE)
            if match:
                return match.group(1)
        
        # Fallback: use text or last part of URL
        if text and len(text) > 5:
            return text[:50]  # Limit length
        
        # Last resort: extract from URL path
        url_parts = url.rstrip('/').split('/')
        return url_parts[-1][:50]