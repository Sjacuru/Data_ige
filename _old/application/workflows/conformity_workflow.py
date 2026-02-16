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
import re
from pathlib import Path
from typing import Optional, Dict, Union, Tuple
from datetime import datetime

from typing import Tuple # for older Python versions

# Add project root to path
import sys
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from infrastructure.scrapers.doweb.scraper import search_and_extract_publication_v2

# Import from conformity modules
from infrastructure.scrapers.doweb.scraper import search_and_extract_publication
from domain.services.conformity_checker import analyze_publication_conformity
from domain.models.conformity_result import (
    ConformityResult,
    ConformityStatus,
    create_not_published_result,
)
from domain.models.publication import PublicationResult

import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# =========================================================================
# CONFIGURATION
# =========================================================================

# Default to headless mode for integration
DEFAULT_HEADLESS = True

# Keys to look for processo number in contract data
PROCESSO_KEYS = [
    "processo_id",             # Prioritize the cross-referenced ID from CSV
    "processo_administrativo",
    "numero_processo",
    "processo",
    "processo_instrutivo",
]

# =========================================================================
# HELPER FUNCTIONS
# =========================================================================

def normalize_processo_format(processo: str) -> str:
    """
    Normalize processo number to standard format.
    
    Handles:
    - SME-PRO-2025/19222 (keep as is)
    - SME/001234/2019 (keep as is)
    - 001/04/000123/2020 (keep as is)
    """
    if not processo:
        return ""
    
    # Remove extra whitespace
    processo = processo.strip()
    
    # Remove common prefixes like "Nº", "N°", "No."
    processo = re.sub(r'^(n[º°]?\.?\s*)', '', processo, flags=re.IGNORECASE)
    
    return processo


def extract_processo_from_contract(contract_data: Dict) -> Tuple[Optional[str], str]:
    """
    Extract processo number from contract data with better logic.
    
    Priority:
    1. processo_administrativo (main field from AI extraction)
    2. numero_processo (secondary field)
    3. processo_instrutivo (from DOWeb publication)
    4. processo (generic fallback)
    
    Returns:
        Tuple of (processo_number, source_field)
    """
    # Define search order with priorities
    search_order = [
        ("processo_administrativo", 1),  # Highest priority
        ("numero_processo", 2),
        ("processo_instrutivo", 3),
        ("processo", 4),
    ]
    
    found_processos = []
    
    for field_name, priority in search_order:
        value = contract_data.get(field_name)
        if value and isinstance(value, str) and len(value) > 5:
            normalized = normalize_processo_format(value)
            
            # Validate format (must contain letters and numbers)
            if re.search(r'[A-Z]{2,4}', normalized, re.IGNORECASE) and re.search(r'\d{4}', normalized):
                found_processos.append({
                    'value': normalized,
                    'field': field_name,
                    'priority': priority
                })
    
    if not found_processos:
        logging.warning("   ⚠️ No valid processo number found in contract data")
        logging.info(f"   Available fields: {list(contract_data.keys())}")
        return None, ""
    
    # Sort by priority and take the best one
    found_processos.sort(key=lambda x: x['priority'])
    best = found_processos[0]
    
    logging.info(f"   ✓ Using processo from '{best['field']}': {best['value']}")
    
    # Log if there are multiple different processos (potential issue)
    if len(found_processos) > 1:
        unique_values = set(p['value'] for p in found_processos)
        if len(unique_values) > 1:
            logging.warning(f"   ⚠️ Multiple different processos found:")
            for p in found_processos:
                logging.info(f"      - {p['field']}: {p['value']}")
            logging.info(f"   → Using highest priority: {best['value']}")
    
    return best['value'], best['field']


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
    processo, source = extract_processo_from_contract(contract_data)
    if not processo:
        available_keys = [k for k in contract_data.keys() if 'processo' in k.lower()]
        return False, f"No valid processo number found. Available processo fields: {available_keys}"
    
    return True, ""

# =========================================================================
# MAIN INTEGRATION FUNCTION
# =========================================================================

def check_publication_conformity(
    contract_data: Dict,
    processo: Optional[str] = None,
    headless: bool = True,
    skip_doweb_search: bool = False,
    publication_result = None
) -> 'ConformityResult':
    """
    Main integration function: Check if contract was published and compare data.
    
    IMPROVED: Better processo extraction and validation.
    
    Args:
        contract_data: Dictionary with contract information (from contract_extractor)
        processo: Optional processo number (if not provided, extracted from contract_data)
        headless: Run browser in headless mode (default: True)
        skip_doweb_search: If True, skip DOWEB search (use provided publication_result)
        publication_result: Pre-fetched publication result (optional)
        
    Returns:
        ConformityResult with full analysis
    """
    logging.info("\n" + "=" * 60)
    logging.info("🔍 CONFORMITY CHECK: Publication Verification")
    logging.info("=" * 60)
    
    # Step 1: Validate contract data
    logging.info("\n📋 Step 1: Validating contract data...")
    is_valid, error = validate_contract_data(contract_data)
    
    if not is_valid:
        logging.error(f"   ❌ Validation failed: {error}")
        return ConformityResult(
            processo=processo or "UNKNOWN",
            overall_status=ConformityStatus.NAO_CONFORME,
            error=f"Invalid contract data: {error}"
        )
    
    # Step 2: Get processo number with improved extraction
    logging.info("\n📋 Step 2: Extracting processo number...")
    
    if not processo:
        processo, source_field = extract_processo_from_contract(contract_data)
        if processo:
            logging.info(f"   ✓ Extracted from '{source_field}': {processo}")
    else:
        # User provided processo - normalize it
        processo = normalize_processo_format(processo)
        logging.info(f"   ✓ Using provided processo: {processo}")
        source_field = "user_provided"
    
    if not processo:
        logging.error("   ❌ No valid processo number found")
        return ConformityResult(
            processo="UNKNOWN",
            overall_status=ConformityStatus.NAO_CONFORME,
            error="Could not extract valid processo number from contract data"
        )
    
    # Validate processo format
    if not re.search(r'[A-Z]{2,4}', processo, re.IGNORECASE):
        logging.warning(f"   ⚠️ Processo format looks unusual: {processo}")
    
    # Step 3: Search DOWEB for publication
    logging.info(f"\n📋 Step 3: Searching D.O. Rio for: {processo}")
    
    if skip_doweb_search and publication_result:
        logging.info("   ⏭️ Skipping search (using provided publication_result)")
        pub_result = publication_result
    else:
        from infrastructure.scrapers.doweb.scraper import search_and_extract_publication
        pub_result = search_and_extract_publication_v2(
            processo=processo,
            contract_date=contract_data.get("data_assinatura"),  # Pass date for better scoring
            headless=headless
        )        


    # Step 4: Analyze conformity
    logging.info("\n📋 Step 4: Analyzing conformity...")
    
    from domain.services.conformity_checker import analyze_publication_conformity
    conformity_result = analyze_publication_conformity(
        contract_data=contract_data,
        publication_result=pub_result
    )
    
    # Step 5: Summary
    logging.info("\n" + "=" * 60)
    logging.info("📊 CONFORMITY CHECK COMPLETE")
    logging.info("=" * 60)
    logging.info(f"   Processo: {processo}")
    logging.info(f"   Source: {source_field}")
    logging.info(f"   Status: {conformity_result.overall_status.value}")
    logging.info(f"   Score: {conformity_result.conformity_score:.1f}%")
    
    if conformity_result.publication_check:
        if conformity_result.publication_check.was_published:
            logging.info(f"   Published: ✓ {conformity_result.publication_check.publication_date}")
            if conformity_result.publication_check.published_on_time:
                logging.info(f"   On time: ✓ ({conformity_result.publication_check.days_to_publish} days)")
            else:
                logging.info(f"   On time: ✗ ({conformity_result.publication_check.days_to_publish} days - exceeded {conformity_result.publication_check.deadline_days} day limit)")
        else:
            logging.info(f"   Published: ✗ Not found in D.O. Rio")
    
    logging.info("=" * 60)
    
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
    
    logging.info(f"\n{'='*60}")
    logging.info(f"📚 BATCH CONFORMITY CHECK: {total} contract(s)")
    logging.info("=" * 60)
    
    for i, contract_data in enumerate(contracts, 1):
        processo = extract_processo_from_contract(contract_data) or f"Contract_{i}"
        logging.info(f"\n[{i}/{total}] Processing: {processo}")
        
        result = check_publication_conformity(
            contract_data=contract_data,
            headless=headless
        )
        
        results.append(result)
        
        status_icon = "✅" if result.overall_status == ConformityStatus.CONFORME else "❌"
        logging.info(f"   Result: {status_icon} {result.overall_status.value}")
    
    # Summary
    conforme = sum(1 for r in results if r.overall_status == ConformityStatus.CONFORME)
    parcial = sum(1 for r in results if r.overall_status == ConformityStatus.PARCIAL)
    nao_conforme = sum(1 for r in results if r.overall_status == ConformityStatus.NAO_CONFORME)
    
    logging.info(f"\n{'='*60}")
    logging.info(f"📊 BATCH COMPLETE")
    logging.info(f"   ✅ Conforme: {conforme}")
    logging.info(f"   ◐ Parcial: {parcial}")
    logger.error(f"   ❌ Não Conforme: {nao_conforme}")
    logging.info("=" * 60)
    
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
    
    logging.info(f"📁 Exported to: {output_path}")
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
    logging.info(f"📁 Exported summary to: {summary_path}")
    
    return created_files


# =========================================================================
# STANDALONE TEST
# =========================================================================

if __name__ == "__main__":
    # Test with sample contract data
    
    logging.info("🧪 Testing conformity integration...")
    
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
    logging.info("\n" + result.get_summary_text())
    
    # Export
    export_conformity_result(
        result,
        f"data/conformity/test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )

# =========================================================================
# DEBUG HELPER
# =========================================================================

def debug_processo_extraction(contract_data: Dict) -> None:
    """
    Debug helper to see what processo values are in the contract data.
    """
    logging.info("\n" + "=" * 60)
    logging.info("🔍 DEBUG: Processo Fields in Contract Data")
    logging.info("=" * 60)
    
    processo_fields = {k: v for k, v in contract_data.items() if 'processo' in k.lower()}
    
    if not processo_fields:
        logging.info("   ❌ No processo fields found!")
        logging.info(f"   Available fields: {list(contract_data.keys())[:10]}")
    else:
        logging.info(f"   Found {len(processo_fields)} processo field(s):")
        for field, value in processo_fields.items():
            normalized = normalize_processo_format(str(value)) if value else ""
            logging.info(f"   • {field}: '{value}' → normalized: '{normalized}'")
    
    # Try extraction
    processo, source = extract_processo_from_contract(contract_data)
    logging.info(f"\n   ✅ Selected: {processo} (from '{source}')")
    logging.info("=" * 60)
    