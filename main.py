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
    discover_all_paths,
    follow_path_and_collect,
    get_all_document_links,
    reset_and_navigate_to_company,
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
    save_to_excel,
    save_to_csv,  
    create_summary_dataframe,
    save_companies_with_links
)
from config import CHROME_HEADLESS, FILTER_YEAR
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By

def process_single_company(driver, company_data):
    """
    Process a single company: navigate, extract, analyze.
    Explores ALL branches and returns a LIST of reports (one per processo found).
    """
    company_id = company_data.get("ID")
    print(f"\n{'='*60}")
    print(f"PROCESSANDO: {company_id} - {company_data.get('Company', 'N/A')}")
    print(f"{'='*60}")
    
    # ═══════════════════════════════════════════════════════════
    # STEP 0: Reset to contracts page and click company
    # ═══════════════════════════════════════════════════════════
    if not reset_and_navigate_to_company(driver, company_id):
        print("✗ Falha ao resetar e navegar para empresa")
        return []
    
    # Get company caption for path discovery
    original_caption = f"{company_id} - {company_data.get('Company', '')}"
    
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
        print("⚠️ Nenhum caminho descoberto, tentando coletar no nível atual...")
        doc_links = get_all_document_links(driver)
        all_doc_links.extend(doc_links)
    else:
        for path_idx, path in enumerate(all_paths, 1):
            print(f"\n{'─'*40}")
            print(f"CAMINHO {path_idx}/{len(all_paths)}: {' → '.join(path) if path else '(direto)'}")
            print(f"{'─'*40}")
            
            doc_links = follow_path_and_collect(driver, company_id, path)
            
            for doc_link in doc_links:
                # Check for duplicates
                if any(d["href"] == doc_link["href"] for d in all_doc_links):
                    print(f"   ⊘ Duplicado ignorado: {doc_link.get('processo', 'N/A')}")
                    continue
                all_doc_links.append(doc_link)
    
    # ═══════════════════════════════════════════════════════════
    # STEP 3: Create reports
    # ═══════════════════════════════════════════════════════════
    print(f"\n{'='*60}")
    print(f"GERANDO RELATÓRIOS: {len(all_doc_links)} processo(s) único(s)")
    print(f"{'='*60}")
    
    all_reports = []
    
    if not all_doc_links:
        print("⚠️ Nenhum processo encontrado")
        report_data = company_data.copy()
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
            print(f"\n   --- Relatório {i}/{len(all_doc_links)} ---")
            
            report_data = company_data.copy()
            report_data["document_url"] = doc_link["href"]
            report_data["document_text"] = doc_link["processo"]
            
            print(f"   📎 Processo: {report_data['document_text']}")
            print(f"   🔗 URL: {report_data['document_url'][:60]}...")
            
            # Extract and analyze
            text_content = None
            if doc_link['href'].lower().endswith('.pdf'):
                filepath = download_document(doc_link['href'])
                if filepath:
                    text_content = extract_text_from_pdf(filepath)
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
            
            print(f"   ✓ Relatório gerado com document_text: {report.get('document_text', 'MISSING!')}")
    
    print(f"\n✓ {len(all_reports)} relatório(s) gerado(s) para esta empresa")
    return all_reports

def main():
    """
    Main function - orchestrates the complete workflow.
    Processes ALL companies and saves all processos to Excel.
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
        
        # ═══════════════════════════════════════════════════════════
        # PROCESS ALL COMPANIES
        # ═══════════════════════════════════════════════════════════
        all_reports = []
        total_companies = len(all_companies)
        
        for idx, company in enumerate(all_companies, 1):
            print(f"\n{'#'*60}")
            print(f"# EMPRESA {idx}/{total_companies}")
            print(f"{'#'*60}")
            
            try:
                reports = process_single_company(driver, company)
                
                if reports:
                    all_reports.extend(reports)
                    print(f"✓ {len(reports)} relatório(s) adicionado(s). Total: {len(all_reports)}")
                else:
                    print(f"⚠ Nenhum relatório gerado para esta empresa")
                    
            except Exception as e:
                print(f"✗ Erro ao processar empresa {company.get('ID')}: {e}")
                # Continue with next company
                continue
            
            # ═══════════════════════════════════════════════════════════
            # SAVE PROGRESS PERIODICALLY (every 10 companies)
            # ═══════════════════════════════════════════════════════════
            if idx % 10 == 0 and all_reports:
                print(f"\n→ Salvando progresso ({len(all_reports)} relatórios)...")
                summary_df = create_summary_dataframe(all_reports)
                save_to_excel(summary_df, "analysis_summary_progress.xlsx")
        
        # ═══════════════════════════════════════════════════════════
        # FINAL SAVE
        # ═══════════════════════════════════════════════════════════
        print(f"\n{'='*60}")
        print(f"PROCESSAMENTO CONCLUÍDO")
        print(f"{'='*60}")
        print(f"Total de empresas processadas: {total_companies}")
        print(f"Total de relatórios gerados: {len(all_reports)}")
        
        if all_reports:
            # Create summary DataFrame
            summary_df = create_summary_dataframe(all_reports)
            
            # Save to Excel
            save_to_excel(summary_df, "analysis_summary.xlsx")
            
            # Also save as CSV for backup
            save_to_csv(summary_df, "analysis_summary.csv")
            
            print(f"\n✓ Arquivos salvos com sucesso!")
        else:
            print("\n⚠ Nenhum relatório para salvar")
        
        # Save companies with links
        save_companies_with_links(all_companies)
        
        print("\n✓ Processamento concluído!")

    except KeyboardInterrupt:
        print("\n\n⚠️ Interrompido pelo usuário.")
        # Save what we have so far
        if all_reports:
            print("→ Salvando progresso antes de encerrar...")
            summary_df = create_summary_dataframe(all_reports)
            save_to_excel(summary_df, "analysis_summary_interrupted.xlsx")
        
    except Exception as e:
        print(f"\n✗ Erro inesperado: {e}")
        import traceback
        traceback.print_exc()
        # Save what we have so far
        if 'all_reports' in locals() and all_reports:
            print("→ Salvando progresso antes de encerrar...")
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
    print("\n🔄 Modo batch ainda não implementado.")
    print("   Use main() para processar uma empresa por vez.")
    # TODO: Implement batch processing loop


# =============================================================================
# ENTRY POINT
# =============================================================================
if __name__ == "__main__":
    main()