"""
Stage 1 Discovery Workflow.
Orchestrates the complete discovery process from ContasRio portal.
"""
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict

from infrastructure.web.driver import create_driver, close_driver
from infrastructure.scrapers.contasrio.scraper import ContasRioScraper
from infrastructure.persistence.json_storage import JSONStorage
from infrastructure.health_check import run_preflight
from domain.models.processo_link import DiscoveryResult, ProcessoLink, CompanyData
from config.settings import DISCOVERY_DIR

logger = logging.getLogger(__name__)


class Stage1DiscoveryWorkflow:
    """
    Orchestrates Stage 1: Discovery of processo links from ContasRio.
    
    Workflow:
    1. Initialize WebDriver
    2. Run ContasRio scraper
    3. Discover all companies
    4. Discover all processo links
    5. Save results to JSON
    6. Clean up resources
    """
    
    def __init__(self, headless: bool = False):
        """
        Initialize workflow.
        
        Args:
            headless: Run browser in headless mode
        """
        self.headless = headless
        self.driver = None
    
    def execute(self) -> DiscoveryResult:
        """
        Execute complete Stage 1 workflow.
        
        Returns:
            DiscoveryResult with all discovered data
        """
        logger.info("\n" + "=" * 70)
        logger.info("🚀 STARTING STAGE 1: DISCOVERY WORKFLOW")
        logger.info("=" * 70)
        logger.info(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        result = DiscoveryResult()
        start_time = datetime.now()
        
        try:
            # Step 1: Initialize WebDriver
            logger.info("\n📋 Step 1: Initializing WebDriver...")
            self.driver = create_driver(headless=self.headless, anti_detection=True)
            
            if not self.driver:
                error_msg = "Failed to initialize WebDriver"
                logger.error(f"✗ {error_msg}")
                result.add_error(error_msg)
                return result
            
            logger.info("✓ WebDriver initialized successfully (function in Stage1_discovery file)")
            
            # Step 2: Create scraper
            logger.info("\n📋 Step 2: Creating ContasRio scraper...")
            scraper = ContasRioScraper(self.driver)
            logger.info("✓ Scraper created")
            
            # Step 3: Discover all processos
            logger.info("\n📋 Step 3: Running discovery process...")
            processos = scraper.discover_all_processos()
            
            result.processos = processos
            result.total_processos = len(processos)
            
            logger.info(f"\n✓ Discovery complete: {len(processos)} processos found")
            
            # Step 4: Extract unique companies
            logger.info("\n📋 Step 4: Extracting company information...")
            companies = self._extract_companies_from_processos(processos)
            
            result.companies = companies
            result.total_companies = len(companies)
            
            logger.info(f"✓ Extracted {len(companies)} unique companies")
            

            MIN_EXPECTED_PROCESSOS = 40

            if result.total_processos == MIN_EXPECTED_PROCESSOS:
                logger.warning("⚠ No processos found — skipping save to avoid overwriting valid data.")
                return result

            # Step 5: Save results
            logger.info("\n📋 Step 5: Saving discovery results...")
            self._save_results(result)
            logger.info("✓ Results saved successfully")
            
            # Calculate duration
            end_time = datetime.now()
            duration = end_time - start_time
            
            # Final summary
            logger.info("\n" + "=" * 70)
            logger.info("✅ STAGE 1 COMPLETE")
            logger.info("=" * 70)
            logger.info(f"   Companies discovered: {result.total_companies}")
            logger.info(f"   Processos discovered: {result.total_processos}")
            logger.info(f"   Duration: {duration}")
            logger.info(f"   End time: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info("=" * 70)
            
        except Exception as e:
            error_msg = f"Stage 1 workflow failed: {str(e)}"
            logger.error(f"\n❌ {error_msg}")
            result.add_error(error_msg)
            
            # Log stack trace for debugging
            import traceback
            logger.error(traceback.format_exc())
        
        finally:
            # Step 6: Cleanup
            logger.info("\n📋 Cleanup: Closing WebDriver...")
            if self.driver:
                close_driver(self.driver)
            logger.info("✓ Cleanup complete")
        
        return result
    
    def _extract_companies_from_processos(
        self,
        processos: List[ProcessoLink]
    ) -> List[CompanyData]:
        """
        Extract unique companies from processo list.
        
        Args:
            processos: List of ProcessoLink objects
            
        Returns:
            List of unique CompanyData objects
        """
        companies_dict = {}
        
        for processo in processos:
            if not processo.company_name:
                continue
            
            # Use CNPJ as key if available, otherwise company name
            key = processo.company_cnpj if processo.company_cnpj else processo.company_name
            
            if key not in companies_dict:
                # Create new company entry
                companies_dict[key] = CompanyData(
                    company_id=key,
                    company_name=processo.company_name,
                    company_cnpj=processo.company_cnpj,
                    total_contracts=1,
                    total_value=processo.contract_value
                )
            else:
                # Increment contract count
                companies_dict[key].total_contracts += 1
        
        # Convert to list and sort by contract count
        companies = list(companies_dict.values())
        companies.sort(key=lambda c: c.total_contracts, reverse=True)
        
        return companies
    
    def _save_results(self, result: DiscoveryResult) -> None:
        """
        Save discovery results to JSON files.
        
        Args:
            result: DiscoveryResult to save
        """
        discovery_dir = Path(DISCOVERY_DIR)
        discovery_dir.mkdir(parents=True, exist_ok=True)
        
        # Save complete discovery result
        processos_file = discovery_dir / "processo_links.json"
        JSONStorage.save(result.to_dict(), processos_file)
        logger.info(f"   ✓ Saved: {processos_file}")
        
        # Save companies separately for easier access
        companies_file = discovery_dir / "companies.json"
        companies_data = {
            "total": result.total_companies,
            "discovery_date": result.discovery_date,
            "companies": [c.to_dict() for c in result.companies]
        }
        JSONStorage.save(companies_data, companies_file)
        logger.info(f"   ✓ Saved: {companies_file}")
        
        # Save summary statistics
        summary_file = discovery_dir / "discovery_summary.json"
        summary_data = {
            "discovery_date": result.discovery_date,
            "total_companies": result.total_companies,
            "total_processos": result.total_processos,
            "errors_count": len(result.errors),
            "errors": result.errors,
            "top_companies": [
                {
                    "name": c.company_name,
                    "contracts": c.total_contracts,
                    "cnpj": c.company_cnpj
                }
                for c in result.companies[:10]  # Top 10
            ]
        }
        JSONStorage.save(summary_data, summary_file)
        logger.info(f"   ✓ Saved: {summary_file}")


def run_stage1_discovery(headless: bool = False) -> DiscoveryResult:
    """
    Convenience function to run Stage 1 discovery.
    
    Args:
        headless: Run browser in headless mode
        
    Returns:
        DiscoveryResult
    """
    preflight = run_preflight(
        "stage1_discovery",
        require_discovery=False,
        require_browser=True,
    )
    if not preflight.passed:
        logger.error("Aborting stage1_discovery — pre-flight failed.")
        result = DiscoveryResult()
        for err in preflight.errors:
            result.add_error(f"preflight: {err}")
        return result

    workflow = Stage1DiscoveryWorkflow(headless=headless)
    return workflow.execute()