"""
main.py - Main entry point for the Contrato Analyzer tool.
Orchestrates the full workflow: retrieve, identify, analyze, answer.
"""

import sys
import time
from config import FILTER_YEAR

# Add src to path
sys.path.insert(0, 'src')

from src.scraper import (
    initialize_driver,
    navigate_to_home,
    navigate_to_contracts,
    scroll_and_collect_rows,
    parse_row_data,
    filter_by_company,
    click_company_button,
    get_document_link,
    close_driver
)
from src.downloader import (
    download_document, 
    should_download
)
from src.parser import (
    extract_text_from_pdf, 
    extract_text_from_url, 
    parse_contract_data
)
from src.analyzer import analyze_contract
from src.reporter import (
    generate_analysis_report,
    print_report,
    save_to_excel,
    create_summary_dataframe
)
from config import CHROME_HEADLESS


def process_single_company(driver, company_data):
    """
    Process a single company: navigate, extract, analyze.
    
    Args:
        driver: WebDriver instance
        company_data: Dictionary with company info
        
    Returns:
        Analysis report dictionary
    """
    company_id = company_data.get("ID")
    print(f"\n{'='*60}")
    print(f"PROCESSANDO: {company_id} - {company_data.get('Company', 'N/A')}")
    print(f"{'='*60}")
    
    # Step 1: Filter by company
    if not filter_by_company(driver, company_id):
        print("✗ Falha ao filtrar empresa")
        return None
    
    # Step 2: Click on company
    original_caption = click_company_button(driver, company_id)
    if not original_caption:
        print("✗ Falha ao clicar na empresa")
        return None
    
    time.sleep(2)
    
    # Step 3: Get document link
    doc_link = get_document_link(driver)
    
    if not doc_link:
        print("⚠️ Nenhum link de documento encontrado")
        # Still generate report with available data
        analysis_results = {
            "flags": [{"type": "no_document", "message": "Documento não encontrado", "severity": "medium"}],
            "risk_level": "medium",
            "summary": "Não foi possível acessar o documento do contrato."
        }
    else:
        # Step 4: Extract text (read online first)
        print(f"\n→ Lendo documento online: {doc_link['href'][:50]}...")
        
        # Try to extract text from URL (for HTML) or download PDF
        if doc_link['href'].lower().endswith('.pdf'):
            # Download and extract from PDF
            filepath = download_document(doc_link['href'])
            if filepath:
                text_content = extract_text_from_pdf(filepath)
            else:
                text_content = None
        else:
            # Try to extract from HTML page
            text_content = extract_text_from_url(doc_link['href'])
        
        # Step 5: Parse and analyze
        if text_content:
            contract_data = parse_contract_data(text_content)
            analysis_results = analyze_contract(contract_data)
            
            # Check if we need to download (based on flags)
            if should_download({"high_value": analysis_results.get("risk_level") == "high"}):
                print("⚠️ Flag de risco alto - garantindo download do documento")
                if not doc_link['href'].lower().endswith('.pdf'):
                    # Already downloaded if PDF, otherwise download now
                    download_document(doc_link['href'])
        else:
            analysis_results = {
                "flags": [{"type": "parse_error", "message": "Não foi possível extrair texto", "severity": "low"}],
                "risk_level": "low",
                "summary": "Documento encontrado mas não foi possível extrair conteúdo."
            }
    
    # Step 6: Generate report
    report = generate_analysis_report(company_data, analysis_results)
    
    return report


def main():
    """
    Main function - orchestrates the complete workflow.
    """
    print("\n" + "=" * 60)
    print("     CONTRATO ANALYZER - Iniciando...")
    print("=" * 60 + "\n")
    
    # Initialize driver
    driver = initialize_driver(headless=CHROME_HEADLESS)
    if not driver:
        print("✗ Não foi possível iniciar o navegador. Encerrando.")
        return
    
    try:
        # Navigate to home
        if not navigate_to_home(driver):
            print("✗ Falha ao carregar página inicial. Encerrando.")
            return
        
        # Navigate to contracts
        # Navigate to contracts (with optional year filter)

        if not navigate_to_contracts(driver, year=FILTER_YEAR):
            print("✗ Falha ao carregar página de contratos. Encerrando.")
            return

        # Collect all data
        raw_rows = scroll_and_collect_rows(driver)
        all_companies = parse_row_data(raw_rows)
        
        if not all_companies:
            print("✗ Nenhuma empresa encontrada. Encerrando.")
            return
        
        print(f"\n✓ {len(all_companies)} empresas encontradas!")
        
        # For now, process only the first company (single processing mode)
        # Later you can change this to a loop for batch processing
        all_reports = []
        
        # Process first company as example
        company = all_companies[0]
        report = process_single_company(driver, company)
        
        if report:
            all_reports.append(report)
            print_report(report)
        
        # Save results
        if all_reports:
            # Create summary DataFrame
            summary_df = create_summary_dataframe(all_reports)
            
            # Save to Excel
            save_to_excel(summary_df, "analysis_summary.xlsx")
            
            print("\n✓ Processamento concluído!")
        
    except KeyboardInterrupt:
        print("\n\n⚠️ Interrompido pelo usuário.")
        
    except Exception as e:
        print(f"\n✗ Erro inesperado: {e}")
        import traceback
        traceback.print_exc()
        
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
    print("\n🔄 Modo batch ainda não implementado.")
    print("   Use main() para processar uma empresa por vez.")
    # TODO: Implement batch processing loop


# =============================================================================
# ENTRY POINT
# =============================================================================
if __name__ == "__main__":
    main()