"""
main.py - Main entry point for the Contrato Analyzer tool.
Orchestrates the full workflow: retrieve, identify, analyze, answer.
"""

import sys
import time
from src.reporter import save_companies_with_links  

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
    click_next_level,
    click_ug_button,
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
from config import CHROME_HEADLESS, FILTER_YEAR

def process_single_company(driver, company_data):
    """
    Process a single company: navigate, extract, analyze.
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
    
    time.sleep(1)
    
    # Step 3: Click next level (Org/Secretaria) ← NEW
    next_level_caption = click_next_level(driver, original_caption)
    if not next_level_caption:
        print("⚠️ Continuando mesmo sem próximo nível...")
    
    time.sleep(1)
    
    # Step 4: Click UG button ← NEW
    ug_caption = click_ug_button(driver)
    if not ug_caption:
        print("⚠️ Continuando mesmo sem UG...")
    
    time.sleep(1)
    
    # Step 5: Get document link
    doc_link = get_document_link(driver)
    
    # Store link in company data
    if doc_link:
        company_data["document_url"] = doc_link["href"]
        company_data["document_text"] = doc_link["processo"]  # ← NEW KEY

        # DEBUG: Confirm data is stored    
        print(f"   DEBUG - processo: {company_data['document_text']}") # DEBUG: Confirm data is stored
        print(f"   DEBUG - url: {company_data['document_url']}") # DEBUG: Confirm data is stored
    
    else:
        company_data["document_url"] = None
        company_data["document_text"] = None

    print(f"📎 Link armazenado: {company_data.get('document_url', 'N/A')}")
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
        
        # =============================================================================
        ## Process first company as example !!!!!@@@@@!!!!!!@@@@!!!!!
        # =============================================================================

        company = all_companies[0]
        print(driver.current_url)
        print(f"\n→ Processando empresa: {company.get('ID')} - {company.get('Company', 'N/A')}")
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
            
        
        # ═══════════════════════════════════════════════════════════════
        # NEW: Save companies with document links
        # ═══════════════════════════════════════════════════════════════
        
        
        # The company dict now has document_url added by process_single_company
        companies_processed = [company]  # Add more when batch processing
        save_companies_with_links(companies_processed)
        # ═══════════════════════════════════════════════════════════════
        
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