"""
test_improved_doweb.py - Test the new AI-powered DOWeb search

Usage:
    python test_improved_doweb.py TUR-PRO-2025/00350 28/02/2025
    
    First arg: processo number
    Second arg (optional): contract signature date for better scoring
"""

import sys
from pathlib import Path

# Add project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent   
sys.path.insert(0, str(PROJECT_ROOT))

def test_new_strategy(processo: str, contract_date: str = None):
    """Test the new AI-powered strategy."""
    
    print("\n" + "=" * 70)
    print("🧪 TESTING IMPROVED DOWEB STRATEGY")
    print("=" * 70)
    print(f"   Processo: {processo}")
    if contract_date:
        print(f"   Contract date: {contract_date}")
    print("=" * 70)

    # Import the new function
    from conformity.scraper.doweb_scraper import search_and_extract_publication_v2
    
    # Run search
    result = search_and_extract_publication_v2(
        processo=processo,
        contract_date=contract_date,
        headless=False,  # Keep browser visible for debugging
        max_candidates=5  # Check top 5 candidates
    )
    
    # Show results
    print("\n" + "=" * 70)
    print("📊 RESULTS")
    print("=" * 70)
    
    if result.found:
        print("✅ PUBLICATION FOUND!")
        print(f"\n   Published: {result.publication_date}")
        print(f"   Edition: {result.edition_number}")
        print(f"   Page: {result.page_number}")
        print(f"   Link: {result.download_link}")
        
        print(f"\n   📋 Extracted Data:")
        print(f"      Órgão: {result.orgao}")
        print(f"      Tipo: {result.tipo_extrato}")
        print(f"      Processo: {result.processo_instrutivo}")
        print(f"      Contrato: {result.numero_contrato}")
        print(f"      Valor: {result.valor}")
        print(f"      Assinatura: {result.data_assinatura}")
        print(f"      Partes: {result.partes[:100]}...")
        
    else:
        print("❌ PUBLICATION NOT FOUND")
        print(f"\n   Results checked: {result.results_checked}")
        print(f"   Total results: {result.search_results_total}")
        print(f"   Reason: {result.error}")
    
    print("\n" + "=" * 70)
    
    # Export result
    import json
    output_file = f"doweb_test_{processo.replace('/', '_')}.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result.to_dict(), f, indent=2, ensure_ascii=False)
    
    print(f"📁 Result saved to: {output_file}")
    print("=" * 70)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python test_improved_doweb.py <processo> [contract_date]")
        print("\nExamples:")
        print("  python test_improved_doweb.py TUR-PRO-2025/00350")
        print("  python test_improved_doweb.py TUR-PRO-2025/00350 28/02/2025")
        sys.exit(1)
    
    processo = sys.argv[1]
    contract_date = sys.argv[2] if len(sys.argv) > 2 else None
    
    test_new_strategy(processo, contract_date)