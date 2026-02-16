"""
application/workflows/extract_contract.py

Workflow: Extract contract data from ContasRio portal
Orchestrates: ContasRio scraper → Download → Text extraction → Data parsing
"""

import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

class ExtractContractWorkflow:
    """
    Orchestrates the process of extracting contract data from ContasRio.
    
    Steps:
    1. Navigate to contracts page
    2. Collect company rows
    3. Navigate to company details
    4. Discover all navigation paths
    5. Collect all document links (processos)
    6. Download/extract text from documents
    7. Parse contract data
    """
    
    def __init__(self, driver, scraper, downloader, parser):
        """
        Args:
            driver: Selenium WebDriver instance
            scraper: ContasRio scraper module (from infrastructure)
            downloader: Document downloader module
            parser: Document parser module
        """
        self.driver = driver
        self.scraper = scraper
        self.downloader = downloader
        self.parser = parser
    
    
    def execute_for_company(self, company_data) -> List[Dict]:
        """
        Extract all contract documents for a single company.
        
        Args:
            company_data: CompanyData object with id and name
            
        Returns:
            List of dicts, each containing:
            - document_url: URL to the document
            - document_text: Extracted text content
            - contract_data: Parsed contract information
            - metadata: Extraction metadata
        """
        company_id = company_data.id
        company_name = company_data.name
        
        logger.info(f"\n{'='*60}")
        logger.info(f"EXTRACTING CONTRACTS: {company_id} - {company_name}")
        logger.info(f"{'='*60}")
        
        # Step 1: Navigate to company
        if not self.scraper.reset_and_navigate_to_company(self.driver, company_id):
            logger.error("Failed to navigate to company")
            return []
        
        # Step 2: Discover all paths
        original_caption = f"{company_id} - {company_name}"
        all_paths = self.scraper.discover_all_paths(self.driver, company_id, original_caption)
        
        # Step 3: Collect all document links from all paths
        all_doc_links = self._collect_all_document_links(company_id, all_paths)
        
        if not all_doc_links:
            logger.warning("No documents found for this company")
            return []
        
        logger.info(f"Found {len(all_doc_links)} unique document(s)")
        
        # Step 4: Extract text from each document
        results = []
        for i, doc_link in enumerate(all_doc_links, 1):
            logger.info(f"\nProcessing document {i}/{len(all_doc_links)}")
            logger.info(f"  Processo: {doc_link['processo']}")
            logger.info(f"  URL: {doc_link['href'][:60]}...")
            
            extraction_result = self._extract_single_document(doc_link, company_data)
            
            if extraction_result:
                results.append(extraction_result)
        
        logger.info(f"\n✓ Extracted {len(results)} document(s) successfully")
        return results
    
    def _collect_all_document_links(self, company_id: str, all_paths: List) -> List[Dict]:
        """
        Collect document links from all discovered paths.
        
        Args:
            company_id: Company identifier
            all_paths: List of navigation paths
            
        Returns:
            List of unique document links
        """
        all_doc_links = []
        
        if not all_paths:
            logger.warning("No paths discovered, trying current level...")
            doc_links = self.scraper.get_all_document_links(self.driver)
            all_doc_links.extend(doc_links)
        else:
            for path_idx, path in enumerate(all_paths, 1):
                logger.info(f"\nPath {path_idx}/{len(all_paths)}: {' → '.join(path) if path else '(direct)'}")
                
                doc_links = self.scraper.follow_path_and_collect(self.driver, company_id, path)
                
                # Add only unique links
                for doc_link in doc_links:
                    if any(d["href"] == doc_link["href"] for d in all_doc_links):
                        logger.info(f"  ⊘ Duplicate ignored: {doc_link.get('processo', 'N/A')}")
                        continue
                    all_doc_links.append(doc_link)
        
        return all_doc_links
    
    
    def _extract_single_document(self, doc_link: Dict, company_data) -> Optional[Dict]:
        """
        Extract text and parse data from a single document.
        
        Args:
            doc_link: Dict with 'href' and 'processo' keys
            company_data: CompanyData object
            
        Returns:
            Dict with extraction results or None on failure
        """
        url = doc_link['href']
        text_content = None
        
        # Try extraction based on URL type
        try:
            if url.lower().endswith('.pdf'):
                # Direct PDF download
                filepath = self.downloader.download_document(url)
                if filepath:
                    text_content = self.parser.extract_text_from_pdf(filepath)
            else:
                # Web page
                text_content = self.parser.extract_text_from_url(url)
        except Exception as e:
            logger.error(f"  ✗ Extraction failed: {e}")
            return None
        
        if not text_content:
            logger.warning("  ⚠ No text extracted")
            return None
        
        # Parse contract data from extracted text
        try:
            contract_data = self.parser.parse_contract_data(text_content)
        except Exception as e:
            logger.error(f"  ✗ Parsing failed: {e}")
            contract_data = {}
        
        result = {
            'company_id': company_data.id,
            'company_name': company_data.name,
            'document_url': url,
            'processo': doc_link['processo'],
            'text_content': text_content,
            'contract_data': contract_data,
            'metadata': {
                'extraction_method': 'pdf' if url.lower().endswith('.pdf') else 'web',
                'text_length': len(text_content)
            }
        }
        
        logger.info(f"  ✓ Extracted {len(text_content):,} characters")
        return result


# =============================================================================
# CONVENIENCE FUNCTION
# =============================================================================

def extract_contracts_for_company(driver, company_data) -> List[Dict]:
    """
    Convenience function to extract contracts for a single company.
    
    Args:
        driver: Selenium WebDriver
        company_data: CompanyData object
        
    Returns:
        List of extraction results
    """
    # Import here to avoid circular dependencies
    from infrastructure.scrapers.contasrio import scraper
    from infrastructure.scrapers.contasrio import downloader
    from infrastructure.scrapers.contasrio import parsers
    
    workflow = ExtractContractWorkflow(
        driver=driver,
        scraper=scraper,
        downloader=downloader,
        parser=parsers
    )
    
    return workflow.execute_for_company(company_data)
