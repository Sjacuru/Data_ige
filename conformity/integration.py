"""
integration.py - Orchestrates the full conformity check flow.

Location: conformity/integration.py

Flow:
1. Receives contract data (from contract_extractor.py)
2. Extracts processo number
3. Searches DOWEB for publication
4. Compares contract with publication
5. Returns conformity result
"""

import json
from pathlib import Path
from typing import Optional, Dict, Union
from datetime import datetime

# Add project root to path
import sys
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Import from conformity modules
from conformity.scraper.doweb_scraper import search_and_extract_publication
from conformity.analyzer.publication_conformity import analyze_publication_conformity
from conformity.models.conformity_result import (
    ConformityResult,
    ConformityStatus,
    create_not_published_result,
)
from conformity.models.publication import PublicationResult


# =========================================================================
# CONFIGURATION
# =========================================================================

# Default to headless mode for integration
DEFAULT_HEADLESS = True

# Keys to look for processo number in contract data
PROCESSO_KEYS = [
    "processo_administrativo",
    "numero_processo",
    "processo",
    "processo_instrutivo",
]


# =========================================================================
# HELPER FUNCTIONS
# =========================================================================

def extract_processo_from_contract(contract_data: Dict) -> Optional[str]:
    """
    Extract processo number from contract data.
    
    Tries multiple possible keys.
    
    Args:
        contract_data: Dictionary with contract information
        
    Returns:
        Processo number or None
    """
    for key in PROCESSO_KEYS:
        value = contract_data.get(key)
        if value and isinstance(value, str) and len(value) > 5:
            print(f"   📋 Found processo in '{key}': {value}")
            return value
    
    return None


def validate_contract_data(contract_data: Dict) -> tuple[bool, str]:
    """
    Validate that contract data has minimum required fields.
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not contract_data:
        return False, "Contract data is empty"
    
    if not isinstance(contract_data, dict):
        return False, "Contract data must be a dictionary"
    
    # Check for processo
    processo = extract_processo_from_contract(contract_data)
    if not processo:
        return False, "No processo number found in contract data"
    
    return True, ""


# =========================================================================
# MAIN INTEGRATION FUNCTION
# =========================================================================

def check_publication_conformity(
    contract_data: Dict,
    processo: Optional[str] = None,
    headless: bool = DEFAULT_HEADLESS,
    skip_doweb_search: bool = False,
    publication_result: Optional[PublicationResult] = None
) -> ConformityResult:
    """
    Main integration function: Check if contract was published and compare data.
    
    This is the entry point for conformity checking.
    
    Args:
        contract_data: Dictionary with contract information (from contract_extractor)
        processo: Optional processo number (if not provided, extracted from contract_data)
        headless: Run browser in headless mode (default: True)
        skip_doweb_search: If True, skip DOWEB search (use provided publication_result)
        publication_result: Pre-fetched publication result (optional)
        
    Returns:
        ConformityResult with full analysis
    
    Example:
        ```python
        from conformity.integration import check_publication_conformity
        
        contract_data = {
            "processo_administrativo": "SME-PRO-2025/19222",
            "numero_contrato": "215/2025",
            "valor_contrato": "R$ 572.734,00",
            ...
        }
        
        result = check_publication_conformity(contract_data)
        
        if result.overall_status == ConformityStatus.CONFORME:
            print("✅ Contract is conformant!")
        else:
            print(f"❌ Issues found: {result.overall_status.value}")
        ```
    """
    print("\n" + "=" * 60)
    print("🔍 CONFORMITY CHECK: Publication Verification")
    print("=" * 60)
    
    # Step 1: Validate contract data
    print("\n📋 Step 1: Validating contract data...")
    is_valid, error = validate_contract_data(contract_data)
    
    if not is_valid:
        print(f"   ❌ Validation failed: {error}")
        return ConformityResult(
            processo=processo or "UNKNOWN",
            overall_status=ConformityStatus.NAO_CONFORME,
            error=f"Invalid contract data: {error}"
        )
    
    # Step 2: Get processo number
    print("\n📋 Step 2: Extracting processo number...")
    if not processo:
        processo = extract_processo_from_contract(contract_data)
    
    if not processo:
        print("   ❌ No processo number found")
        return ConformityResult(
            processo="UNKNOWN",
            overall_status=ConformityStatus.NAO_CONFORME,
            error="Could not extract processo number from contract data"
        )
    
    print(f"   ✓ Processo: {processo}")
    
    # Step 3: Search DOWEB for publication
    print("\n📋 Step 3: Searching D.O. Rio for publication...")
    
    if skip_doweb_search and publication_result:
        print("   ⏭️ Skipping search (using provided publication_result)")
        pub_result = publication_result
    else:
        pub_result = search_and_extract_publication(
            processo=processo,
            headless=headless
        )
    
    # Step 4: Analyze conformity
    print("\n📋 Step 4: Analyzing conformity...")
    
    conformity_result = analyze_publication_conformity(
        contract_data=contract_data,
        publication_result=pub_result
    )
    
    # Step 5: Summary
    print("\n" + "=" * 60)
    print("📊 CONFORMITY CHECK COMPLETE")
    print("=" * 60)
    print(f"   Processo: {processo}")
    print(f"   Status: {conformity_result.overall_status.value}")
    print(f"   Score: {conformity_result.conformity_score:.1f}%")
    
    if conformity_result.publication_check:
        if conformity_result.publication_check.was_published:
            print(f"   Published: ✓ {conformity_result.publication_check.publication_date}")
            if conformity_result.publication_check.published_on_time:
                print(f"   On time: ✓ ({conformity_result.publication_check.days_to_publish} days)")
            else:
                print(f"   On time: ✗ ({conformity_result.publication_check.days_to_publish} days - exceeded {conformity_result.publication_check.deadline_days} day limit)")
        else:
            print(f"   Published: ✗ Not found in D.O. Rio")
    
    print("=" * 60)
    
    return conformity_result


# =========================================================================
# BATCH PROCESSING
# =========================================================================

def check_multiple_contracts(
    contracts: list[Dict],
    headless: bool = True
) -> list[ConformityResult]:
    """
    Check conformity for multiple contracts.
    
    Args:
        contracts: List of contract data dictionaries
        headless: Run browser in headless mode
        
    Returns:
        List of ConformityResult
    """
    results = []
    total = len(contracts)
    
    print(f"\n{'='*60}")
    print(f"📚 BATCH CONFORMITY CHECK: {total} contract(s)")
    print("=" * 60)
    
    for i, contract_data in enumerate(contracts, 1):
        processo = extract_processo_from_contract(contract_data) or f"Contract_{i}"
        print(f"\n[{i}/{total}] Processing: {processo}")
        
        result = check_publication_conformity(
            contract_data=contract_data,
            headless=headless
        )
        
        results.append(result)
        
        status_icon = "✅" if result.overall_status == ConformityStatus.CONFORME else "❌"
        print(f"   Result: {status_icon} {result.overall_status.value}")
    
    # Summary
    conforme = sum(1 for r in results if r.overall_status == ConformityStatus.CONFORME)
    parcial = sum(1 for r in results if r.overall_status == ConformityStatus.PARCIAL)
    nao_conforme = sum(1 for r in results if r.overall_status == ConformityStatus.NAO_CONFORME)
    
    print(f"\n{'='*60}")
    print(f"📊 BATCH COMPLETE")
    print(f"   ✅ Conforme: {conforme}")
    print(f"   ◐ Parcial: {parcial}")
    print(f"   ❌ Não Conforme: {nao_conforme}")
    print("=" * 60)
    
    return results


# =========================================================================
# EXPORT FUNCTIONS
# =========================================================================

def export_conformity_result(
    result: ConformityResult,
    output_path: str,
    format: str = "json"
) -> str:
    """
    Export conformity result to file.
    
    Args:
        result: ConformityResult to export
        output_path: Path to output file
        format: "json" or "txt"
        
    Returns:
        Path to created file
    """
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    
    if format == "json":
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result.to_dict(), f, ensure_ascii=False, indent=2)
    else:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(result.get_summary_text())
    
    print(f"📁 Exported to: {output_path}")
    return output_path


def export_batch_results(
    results: list[ConformityResult],
    output_dir: str
) -> list[str]:
    """
    Export multiple conformity results.
    
    Creates:
    - Individual JSON files for each result
    - Summary JSON with all results
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    created_files = []
    
    # Export individual results
    for result in results:
        filename = f"conformity_{result.processo.replace('/', '_')}.json"
        filepath = output_path / filename
        export_conformity_result(result, str(filepath), format="json")
        created_files.append(str(filepath))
    
    # Export summary
    summary = {
        "generated_at": datetime.now().isoformat(),
        "total_contracts": len(results),
        "summary": {
            "conforme": sum(1 for r in results if r.overall_status == ConformityStatus.CONFORME),
            "parcial": sum(1 for r in results if r.overall_status == ConformityStatus.PARCIAL),
            "nao_conforme": sum(1 for r in results if r.overall_status == ConformityStatus.NAO_CONFORME),
        },
        "results": [r.to_dict() for r in results]
    }
    
    summary_path = output_path / "conformity_summary.json"
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    
    created_files.append(str(summary_path))
    print(f"📁 Exported summary to: {summary_path}")
    
    return created_files


# =========================================================================
# STANDALONE TEST
# =========================================================================

if __name__ == "__main__":
    # Test with sample contract data
    
    print("🧪 Testing conformity integration...")
    
    # Sample contract data (simulating output from contract_extractor)
    sample_contract = {
        "processo_administrativo": "SME-PRO-2025/19222",
        "numero_contrato": "215/2025",
        "valor_contrato": "R$ 572.734,00",
        "data_assinatura": "28/10/2025",
        "contratante": "PCRJ/SME",
        "contratada": "ASSOCIACAO COLUMBIA GLOBAL CENTER/BRASIL",
        "objeto": "Qualificação de lideranças mediante participação do Programa FabLearn",
        "data_inicio": "30/12/2025",
        "data_fim": "29/12/2026",
    }
    
    # Run conformity check
    result = check_publication_conformity(
        contract_data=sample_contract,
        headless=False  # Visible for testing
    )
    
    # Print full result
    print("\n" + result.get_summary_text())
    
    # Export
    export_conformity_result(
        result,
        f"data/conformity/test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )

    