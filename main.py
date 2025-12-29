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
    get_all_document_links,
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
    Returns a LIST of reports (one per processo found).
    """
    company_id = company_data.get("ID")
    print(f"\n{'='*60}")
    print(f"PROCESSANDO: {company_id} - {company_data.get('Company', 'N/A')}")
    print(f"{'='*60}")
    
    # Step 1: Filter by company
    if not filter_by_company(driver, company_id):
        print("✗ Falha ao filtrar empresa")
        return []
    
    # Step 2: Click on company
    original_caption = click_company_button(driver, company_id)
    if not original_caption:
        print("✗ Falha ao clicar na empresa")
        return []
    
    time.sleep(1)
    
    # Step 3: Click next level (Org/Secretaria)
    next_level_caption = click_next_level(driver, original_caption)
    if not next_level_caption:
        print("⚠️ Continuando mesmo sem próximo nível...")
    
    time.sleep(1)
    
    # Step 4: Click UG button (navigates to deepest level)
    ug_caption = click_ug_button(driver)
    if not ug_caption:
        print("⚠️ Continuando mesmo sem UG...")
    
    time.sleep(1)
    
    # Step 5: Get ALL document links
    doc_links = get_all_document_links(driver)
    
    # ═══════════════════════════════════════════════════════════
    # Create one report per processo
    # ═══════════════════════════════════════════════════════════
    all_reports = []
    
    if not doc_links:
        print("⚠️ Nenhum link de documento encontrado")
        report_data = company_data.copy()
        report_data["document_url"] = None
        report_data["document_text"] = None  # ← CORRECT KEY
        
        analysis_results = {
            "flags": [{"type": "no_document", "message": "Documento não encontrado", "severity": "medium"}],
            "risk_level": "medium",
            "summary": "Não foi possível acessar o documento do contrato."
        }
        
        report = generate_analysis_report(report_data, analysis_results)
        all_reports.append(report)
    else:
        for i, doc_link in enumerate(doc_links, 1):
            print(f"\n   --- Processando processo {i}/{len(doc_links)} ---")
            
            report_data = company_data.copy()
            report_data["document_url"] = doc_link["href"]
            report_data["document_text"] = doc_link["processo"]  # ← CORRECT KEY
            
            print(f"   📎 Processo: {doc_link['processo']}")
            print(f"   🔗 URL: {doc_link['href']}")
            
            # Extract and analyze
            if doc_link['href'].lower().endswith('.pdf'):
                filepath = download_document(doc_link['href'])
                if filepath:
                    text_content = extract_text_from_pdf(filepath)
                else:
                    text_content = None
            else:
                text_content = extract_text_from_url(doc_link['href'])
            
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
    
    print(f"\n✓ {len(all_reports)} relatório(s) gerado(s) para esta empresa")
    return all_reports


def main():
    """
    Main function - orchestrates the complete workflow.
    """
    print("\n" + "=" * 60)
    print("     CONTRATO ANALYZER - Iniciando...")
    print("=" * 60 + "\n")
    
    driver = initialize_driver(headless=CHROME_HEADLESS)
    if not driver:
        print("✗ Não foi possível iniciar o navegador. Encerrando.")
        return
    
    try:
        if not navigate_to_home(driver):
            print("✗ Falha ao carregar página inicial. Encerrando.")
            return
        
        if not navigate_to_contracts(driver, year=FILTER_YEAR):
            print("✗ Falha ao carregar página de contratos. Encerrando.")
            return

        raw_rows = scroll_and_collect_rows(driver)
        all_companies = parse_row_data(raw_rows)
        
        if not all_companies:
            print("✗ Nenhuma empresa encontrada. Encerrando.")
            return
        
        print(f"\n✓ {len(all_companies)} empresas encontradas!")
        
        all_reports = []
        
        # Process first company as example
        company = all_companies[0]
        print(driver.current_url)
        print(f"\n→ Processando empresa: {company.get('ID')} - {company.get('Company', 'N/A')}")
        
        # ═══════════════════════════════════════════════════════════
        # Now returns a LIST of reports
        # ═══════════════════════════════════════════════════════════
        reports = process_single_company(driver, company)
        
        if reports:
            all_reports.extend(reports)  # ← extend, not append
            for report in reports:
                print_report(report)
        
        # Save results
        if all_reports:
            summary_df = create_summary_dataframe(all_reports)
            save_to_excel(summary_df, "analysis_summary.xlsx")
        
        # Save companies with links
        companies_processed = [company]
        save_companies_with_links(companies_processed)
        
        print("\n✓ Processamento concluído!")

    except KeyboardInterrupt:
        print("\n\n⚠️ Interrompido pelo usuário.")
        
    except Exception as e:
        print(f"\n✗ Erro inesperado: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
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