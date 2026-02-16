"""
application/workflows/extract_publication.py

Workflow: Extract publication data from DoWeb (Diário Oficial)
Orchestrates: DoWeb scraper → Search by processo → Download → Extract publication data
"""

import logging
from typing import Dict, Optional, List

logger = logging.getLogger(__name__)


class ExtractPublicationWorkflow:
    """
    Orchestrates the process of extracting publication data from DoWeb.
    
    Steps:
    1. Navigate to DoWeb portal
    2. Search for publication using processo number
    3. Handle CAPTCHA if present
    4. Download publication PDF
    5. Extract publication data
    6. Parse and structure data
    """
    
    def __init__(self, driver, scraper, extractor):
        """
        Args:
            driver: Selenium WebDriver instance
            scraper: DoWeb scraper module (from infrastructure)
            extractor: DoWeb extractor module (for parsing publications)
        """
        self.driver = driver
        self.scraper = scraper
        self.extractor = extractor
    
    
    def execute_for_processo(self, processo_number: str, contract_data: Optional[Dict] = None) -> Optional[Dict]:
        """
        Extract publication data for a specific processo number.
        
        Args:
            processo_number: Process number to search (e.g., "TUR-PRO-2025/00477")
            contract_data: Optional contract data for context/validation
            
        Returns:
            Dict containing:
            - processo: Process number
            - publication_found: bool
            - publication_data: Extracted data (if found)
            - publication_url: URL to publication (if found)
            - search_metadata: Search details
            
            Returns None if search fails completely
        """
        logger.info(f"\n{'='*60}")
        logger.info(f"EXTRACTING PUBLICATION: {processo_number}")
        logger.info(f"{'='*60}")
        
        # Step 1: Search for publication
        search_result = self._search_publication(processo_number)
        
        if not search_result or not search_result.get('found'):
            logger.warning("Publication not found in DoWeb")
            return {
                'processo': processo_number,
                'publication_found': False,
                'publication_data': None,
                'publication_url': None,
                'search_metadata': search_result or {}
            }
        
        # Step 2: Extract publication data
        publication_data = self._extract_publication_data(search_result)
        
        result = {
            'processo': processo_number,
            'publication_found': True,
            'publication_data': publication_data,
            'publication_url': search_result.get('url'),
            'search_metadata': search_result
        }
        
        logger.info("✓ Publication extracted successfully")
        return result
    
    
    def _search_publication(self, processo_number: str) -> Optional[Dict]:
        """
        Search for publication in DoWeb using processo number.
        
        Args:
            processo_number: Process number to search
            
        Returns:
            Dict with search results or None if search fails
        """
        logger.info(f"Searching DoWeb for: {processo_number}")
        
        try:
            # Use DoWeb scraper to search
            result = self.scraper.search_by_processo(
                driver=self.driver,
                processo_number=processo_number
            )
            
            if result and result.get('found'):
                logger.info(f"  ✓ Found publication")
                logger.info(f"    URL: {result.get('url', 'N/A')[:60]}...")
                return result
            else:
                logger.warning(f"  ⚠ Publication not found")
                return {'found': False}
                
        except Exception as e:
            logger.error(f"  ✗ Search failed: {e}")
            return None
    
    
    def _extract_publication_data(self, search_result: Dict) -> Optional[Dict]:
        """
        Extract and parse publication data from search result.
        
        Args:
            search_result: Result from DoWeb search
            
        Returns:
            Dict with parsed publication data
        """
        logger.info("Extracting publication data...")
        
        try:
            # Use extractor to parse publication content
            publication_data = self.extractor.extract_publication_info(
                url=search_result.get('url'),
                raw_content=search_result.get('content')
            )
            
            if publication_data:
                logger.info("  ✓ Publication data extracted")
                return publication_data
            else:
                logger.warning("  ⚠ No data could be extracted")
                return None
                
        except Exception as e:
            logger.error(f"  ✗ Extraction failed: {e}")
            return None


class ExtractPublicationBatchWorkflow:
    """
    Batch extraction of publications for multiple processos.
    
    Useful when processing multiple contracts from the same company.
    """
    
    def __init__(self, driver, scraper, extractor):
        self.driver = driver
        self.scraper = scraper
        self.extractor = extractor
        self.single_workflow = ExtractPublicationWorkflow(driver, scraper, extractor)
    
    
    def execute_for_processos(self, processo_numbers: List[str]) -> List[Dict]:
        """
        Extract publications for multiple processo numbers.
        
        Args:
            processo_numbers: List of process numbers
            
        Returns:
            List of extraction results (one per processo)
        """
        logger.info(f"\n{'='*60}")
        logger.info(f"BATCH EXTRACTION: {len(processo_numbers)} processo(s)")
        logger.info(f"{'='*60}")
        
        results = []
        
        for i, processo in enumerate(processo_numbers, 1):
            logger.info(f"\n[{i}/{len(processo_numbers)}] Processing: {processo}")
            
            result = self.single_workflow.execute_for_processo(processo)
            
            if result:
                results.append(result)
            else:
                logger.warning(f"  ⚠ Failed to process {processo}")
        
        found_count = sum(1 for r in results if r.get('publication_found'))
        logger.info(f"\n✓ Batch complete: {found_count}/{len(results)} publications found")
        
        return results


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def extract_publication_for_processo(driver, processo_number: str) -> Optional[Dict]:
    """
    Convenience function to extract a single publication.
    
    Args:
        driver: Selenium WebDriver
        processo_number: Process number to search
        
    Returns:
        Extraction result dict or None
    """
    # Import here to avoid circular dependencies
    from infrastructure.scrapers.doweb import scraper
    from infrastructure.scrapers.doweb import extractor
    
    workflow = ExtractPublicationWorkflow(
        driver=driver,
        scraper=scraper,
        extractor=extractor
    )
    
    return workflow.execute_for_processo(processo_number)


def extract_publications_batch(driver, processo_numbers: List[str]) -> List[Dict]:
    """
    Convenience function to extract multiple publications.
    
    Args:
        driver: Selenium WebDriver
        processo_numbers: List of process numbers
        
    Returns:
        List of extraction results
    """
    from infrastructure.scrapers.doweb import scraper
    from infrastructure.scrapers.doweb import extractor
    
    workflow = ExtractPublicationBatchWorkflow(
        driver=driver,
        scraper=scraper,
        extractor=extractor
    )
    
    return workflow.execute_for_processos(processo_numbers)
