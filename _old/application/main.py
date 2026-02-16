"""
main.py - Main entry point for the Contrato Analyzer tool.
Orchestrates the full workflow: retrieve, identify, analyze, answer.
"""

import sys
import os
import time

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)


from infrastructure.extractors.document_extractor import DocumentExtractor, extract_processo_documents
from infrastructure.web.driver import initialize_driver
#from application.workflows.conformity_workflow import check_conformity
from application.workflows.extract_contract import extract_contracts_for_company
from application.workflows.extract_publication import extract_publication_for_processo


# Add src to path
#sys.path.insert(0, 'src')

from infrastructure.scrapers.contasrio.scraper import (
    initialize_driver,
    navigate_to_home,
    navigate_to_contracts,
    scroll_and_collect_rows,
    parse_row_data,
    filter_by_company,
    click_company_button,
    discover_all_paths,
    follow_path_and_collect,
    get_all_document_links,
    reset_and_navigate_to_company,
    close_driver
)

from infrastructure.scrapers.contasrio.downloader import (
    download_document, 
    should_download
)
from infrastructure.scrapers.contasrio.parsers import (
    extract_text_from_pdf, 
    extract_text_from_url, 
    parse_contract_data
)
from infrastructure.extractors.analyzer import analyze_contract
from infrastructure.persistence.reporter import (
    generate_analysis_report,
    save_to_excel,
    save_to_csv,  
    create_summary_dataframe,
    save_companies_with_links
)
from config import CHROME_HEADLESS, FILTER_YEAR  # ✅ Original - no changes
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By

import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════
# NEW HELPER FUNCTIONS (additions only - nothing removed)
# ═══════════════════════════════════════════════════════════════════════

# Feature flag - set to True to enable CAPTCHA handling for processo pages
USE_DOCUMENT_EXTRACTOR = True  # Set to False to use original behavior only

def is_processo_page(url):
    """
    Check if URL is a processo.rio page that needs special handling.
    
    Args:
        url: URL to check
        
    Returns:
        bool: True if it's a processo page requiring CAPTCHA handling
    """
    if not url:
        return False
    
    url_lower = url.lower()
    
    # Direct PDF links don't need special handling
    if url_lower.endswith('.pdf'):
        return False
    
    # Check for processo.rio patterns
    processo_patterns = [
        'processo.rio',
        '/processo/',
        '/consulta/',
        'visualizar.action',
    ]
    
    return any(pattern in url_lower for pattern in processo_patterns)


def process_with_document_extractor(driver, processo_url, empresa_info):
    """
    Process a processo URL with CAPTCHA handling using DocumentExtractor.
    
    Args:
        driver: Selenium WebDriver
        processo_url: URL to processo page
        empresa_info: Dict with empresa 'id' and 'name'
    
    Returns:
        tuple: (text_content, extraction_metadata) or (None, None) on failure
    """
    logging.info(f"\n   🔐 Usando DocumentExtractor (com tratamento de CAPTCHA)...")
    
    try:
        results = extract_processo_documents(
            driver=driver,
            processo_url=processo_url,
            empresa_info=empresa_info,
            use_ai=False  # Set True for better quality (slower)
        )
        
        if results:
            # Combine all extracted texts
            text_parts = []
            for doc in results:
                if doc.get('texto_extraido'):
                    text_parts.append(doc['texto_extraido'])
            
            text_content = "\n\n---\n\n".join(text_parts) if text_parts else None
            
            if text_content:
                logging.info(f"   ✓ {len(results)} documento(s) extraído(s), {len(text_content):,} caracteres")
                return text_content, {"source": "document_extractor", "docs": results}
        
        logger.warning(f"   ⚠ Nenhum documento encontrado na página")
        return None, None
        
    except Exception as e:
        logger.error(f"   ❌ Erro no DocumentExtractor: {e}")
        return None, None


# ═══════════════════════════════════════════════════════════════════════
# ORIGINAL FUNCTIONS (preserved exactly as before, with additions marked)
# ═══════════════════════════════════════════════════════════════════════

def process_single_company(driver, company_data):
    """
    Process a single company: navigate, extract, analyze.
    Explores ALL branches and returns a LIST of reports (one per processo found).
    
    Args:
        company_data: CompanyData object (not dict anymore!)
    """
    # ═══════════════════════════════════════════════════════════
    # CHANGED: Access properties instead of dict keys
    # ═══════════════════════════════════════════════════════════
    company_id = company_data.id  # Was: company_data.get("ID")
    company_name = company_data.name  # Was: company_data.get("Company")
    
    logging.info(f"\n{'='*60}")
    logging.info(f"PROCESSANDO: {company_id} - {company_name}")
    logging.info(f"{'='*60}")
    
    # ═══════════════════════════════════════════════════════════
    # STEP 0: Reset to contracts page and click company
    # ═══════════════════════════════════════════════════════════
    if not reset_and_navigate_to_company(driver, company_id):
        logging.info("✗ Falha ao resetar e navegar para empresa")
        return []
    
    # Get company caption for path discovery
    original_caption = f"{company_id} - {company_name}"
    
    time.sleep(1)
    
    # ═══════════════════════════════════════════════════════════
    # STEP 1: Discover all paths
    # ═══════════════════════════════════════════════════════════
    all_paths = discover_all_paths(driver, company_id, original_caption)
    
    # ═══════════════════════════════════════════════════════════
    # STEP 2: Collect all processos from all paths
    # ═══════════════════════════════════════════════════════════
    all_doc_links = []
    
    if not all_paths:
        logger.warning("⚠️ Nenhum caminho descoberto, tentando coletar no nível atual...")
        doc_links = get_all_document_links(driver)
        all_doc_links.extend(doc_links)
    else:
        for path_idx, path in enumerate(all_paths, 1):
            logging.info(f"\n{'─'*40}")
            logging.info(f"CAMINHO {path_idx}/{len(all_paths)}: {' → '.join(path) if path else '(direto)'}")
            logging.info(f"{'─'*40}")
            
            doc_links = follow_path_and_collect(driver, company_id, path)
            
            for doc_link in doc_links:
                # Check for duplicates
                if any(d["href"] == doc_link["href"] for d in all_doc_links):
                    logging.info(f"   ⊘ Duplicado ignorado: {doc_link.get('processo', 'N/A')}")
                    continue
                all_doc_links.append(doc_link)
    
    # ═══════════════════════════════════════════════════════════
    # STEP 3: Create reports
    # ═══════════════════════════════════════════════════════════
    logging.info(f"\n{'='*60}")
    logging.info(f"GERANDO RELATÓRIOS: {len(all_doc_links)} processo(s) único(s)")
    logging.info(f"{'='*60}")
    
    all_reports = []
    
    if not all_doc_links:
        logger.warning("⚠️ Nenhum processo encontrado")
        
        # ═══════════════════════════════════════════════════════
        # CHANGED: Build dict from CompanyData for report
        # ═══════════════════════════════════════════════════════
        report_data = company_data.to_dict()  # Convert to dict for report
        report_data["document_url"] = None
        report_data["document_text"] = None
        
        analysis_results = {
            "flags": [{"type": "no_document", "message": "Documento não encontrado", "severity": "medium"}],
            "risk_level": "medium",
            "summary": "Não foi possível acessar o documento do contrato."
        }
        
        report = generate_analysis_report(report_data, analysis_results)
        all_reports.append(report)
    else:
        for i, doc_link in enumerate(all_doc_links, 1):
            logging.info(f"\n   --- Relatório {i}/{len(all_doc_links)} ---")
            
            # ═══════════════════════════════════════════════════════
            # CHANGED: Build dict from CompanyData for each report
            # ═══════════════════════════════════════════════════════
            report_data = company_data.to_dict()  # Convert to dict
            report_data["document_url"] = doc_link["href"]
            report_data["document_text"] = doc_link["processo"]
            
            logging.info(f"   📎 Processo: {report_data['document_text']}")
            logging.info(f"   🔗 URL: {report_data['document_url'][:60]}...")
            
            # Extract and analyze
            text_content = None
            
            # ═══════════════════════════════════════════════════════
            # NEW: Try DocumentExtractor for processo pages (if enabled)
            # ═══════════════════════════════════════════════════════
            used_document_extractor = False
            
            if USE_DOCUMENT_EXTRACTOR and is_processo_page(doc_link['href']):
                empresa_info = {
                    "id": company_id,
                    "name": company_name  # Use local variable
                }
                text_content, extraction_meta = process_with_document_extractor(
                    driver, doc_link['href'], empresa_info
                )
                if text_content:
                    used_document_extractor = True
            
            # ═══════════════════════════════════════════════════════
            # ORIGINAL: Fallback to original extraction method
            # ═══════════════════════════════════════════════════════
            if not text_content:
                if doc_link['href'].lower().endswith('.pdf'):
                    filepath = download_document(doc_link['href'])
                    if filepath:
                        text_content = extract_text_from_pdf(filepath)
                else:
                    text_content = extract_text_from_url(doc_link['href'])
            
            # ═══════════════════════════════════════════════════════
            # ORIGINAL: Analyze and generate report (unchanged)
            # ═══════════════════════════════════════════════════════
            if text_content:
                contract_data = parse_contract_data(text_content)
                analysis_results = analyze_contract(contract_data)
            else:
                analysis_results = {
                    "flags": [{"type": "parse_error", "message": "Não foi possível extrair texto", "severity": "low"}],
                    "risk_level": "low",
                    "summary": "Documento encontrado mas não foi possível extrair conteúdo."
                }
            
            report = generate_analysis_report(report_data, analysis_results)
            all_reports.append(report)
            
            logging.info(f"   ✓ Relatório gerado com document_text: {report.get('document_text', 'MISSING!')}")
    
    logging.info(f"\n✓ {len(all_reports)} relatório(s) gerado(s) para esta empresa")
    return all_reports


def main():
    """
    Main function - orchestrates the complete workflow.
    Processes ALL companies and saves all processos to Excel.
    """
    logging.info("\n" + "=" * 60)
    logging.info("     CONTRATO ANALYZER - Iniciando...")
    if USE_DOCUMENT_EXTRACTOR:
        logging.info("     (DocumentExtractor ATIVADO para páginas processo.rio)")
    logging.info("=" * 60 + "\n")
    
    # Initialize driver
    driver = initialize_driver(headless=CHROME_HEADLESS)
    if not driver:
        logging.info("✗ Não foi possível iniciar o navegador. Encerrando.")
        return
    
    all_reports = []
    try:
        # Navigate to home
        if not navigate_to_home(driver):
            logging.info("✗ Falha ao carregar página inicial. Encerrando.")
            return
        
        # Navigate to contracts
        if not navigate_to_contracts(driver, year=FILTER_YEAR):
            logging.info("✗ Falha ao carregar página de contratos. Encerrando.")
            return

        # Collect all data
        raw_rows = scroll_and_collect_rows(driver)
        all_companies = parse_row_data(raw_rows)
        
        if not all_companies:
            logging.info("✗ Nenhuma empresa encontrada. Encerrando.")
            return
        
        logging.info(f"\n✓ {len(all_companies)} empresas encontradas!")
        
        # ═══════════════════════════════════════════════════════════
        # PROCESS ALL COMPANIES
        # ═══════════════════════════════════════════════════════════

        total_companies = len(all_companies)
        
        for idx, company in enumerate(all_companies, 1):
            logging.info(f"\n{'#'*60}")
            logging.info(f"# EMPRESA {idx}/{total_companies}")
            logging.info(f"{'#'*60}")
            
            try:
                reports = process_single_company(driver, company)
                
                if reports:
                    all_reports.extend(reports)
                    logging.info(f"✓ {len(reports)} relatório(s) adicionado(s). Total: {len(all_reports)}")
                else:
                    logger.warning(f"⚠ Nenhum relatório gerado para esta empresa")
                    
            except Exception as e:
                logger.error(f"✗ Erro ao processar empresa {company.id}: {e}")
                # Continue with next company
                continue
            
            # ═══════════════════════════════════════════════════════════
            # SAVE PROGRESS PERIODICALLY (every 10 companies)
            # ═══════════════════════════════════════════════════════════
            if idx % 10 == 0 and all_reports:
                logging.info(f"\n→ Salvando progresso ({len(all_reports)} relatórios)...")
                summary_df = create_summary_dataframe(all_reports)
                save_to_excel(summary_df, "analysis_summary_progress.xlsx")
        
        # ═══════════════════════════════════════════════════════════
        # FINAL SAVE
        # ═══════════════════════════════════════════════════════════
        logging.info(f"\n{'='*60}")
        logging.info(f"PROCESSAMENTO CONCLUÍDO")
        logging.info(f"{'='*60}")
        logging.info(f"Total de empresas processadas: {total_companies}")
        logging.info(f"Total de relatórios gerados: {len(all_reports)}")
        
        if all_reports:
            # Create summary DataFrame
            summary_df = create_summary_dataframe(all_reports)
            
            # Save to Excel
            save_to_excel(summary_df, "analysis_summary.xlsx")
            
            # Also save as CSV for backup
            save_to_csv(summary_df, "analysis_summary.csv")
            
            logging.info(f"\n✓ Arquivos salvos com sucesso!")
        else:
            logger.warning("\n⚠ Nenhum relatório para salvar")
        
        # Save companies with links
        save_companies_with_links(all_companies)
        
        logging.info("\n✓ Processamento concluído!")

    except KeyboardInterrupt:
        logger.warning("\n\n⚠️ Interrompido pelo usuário.")
        # Save what we have so far
        if all_reports:
            logging.info("→ Salvando progresso antes de encerrar...")
            summary_df = create_summary_dataframe(all_reports)
            save_to_excel(summary_df, "analysis_summary_interrupted.xlsx")
        
    except Exception as e:
        logger.error(f"\n✗ Erro inesperado: {e}")
        import traceback
        traceback.print_exc()
        # Save what we have so far
        if 'all_reports' in locals() and all_reports:
            logging.info("→ Salvando progresso antes de encerrar...")
            summary_df = create_summary_dataframe(all_reports)
            save_to_excel(summary_df, "analysis_summary_error.xlsx")
        
    finally:
        # Always close the browser
        close_driver(driver)


# =============================================================================
# BATCH PROCESSING (for future use)
# =============================================================================
def process_batch(company_list=None, max_companies=None):
    """
    Process multiple companies in batch.
    
    Args:
        company_list: Optional list of company IDs to process
        max_companies: Maximum number of companies to process
    """
    logging.info("\n🔄 Modo batch ainda não implementado.")
    logging.info("   Use main() para processar uma empresa por vez.")
    # TODO: Implement batch processing loop


# =============================================================================
# ENTRY POINT
# =============================================================================
if __name__ == "__main__":
    main()