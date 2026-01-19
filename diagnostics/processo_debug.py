"""
diagnostics/processo_debug.py - Diagnostic tool to check processo extraction.

Usage:
    python diagnostics/processo_debug.py
    
Or import and use:
    from diagnostics.processo_debug import diagnose_extraction
    diagnose_extraction(contract_data)
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Tuple

def normalize_processo_format(processo: str) -> str:
    """Normalize processo number to standard format."""
    if not processo:
        return ""
    
    processo = processo.strip()
    processo = re.sub(r'^(n[º°]?\.?\s*)', '', processo, flags=re.IGNORECASE)
    return processo


def extract_all_processo_like_fields(data: Dict) -> List[Tuple[str, str, bool]]:
    """
    Find all fields that might contain processo numbers.
    
    Returns:
        List of (field_name, value, is_valid_format)
    """
    results = []
    
    # Common patterns
    patterns = {
        'new': r'[A-Z]{2,4}-[A-Z]{2,4}-\d{4}/\d{4,6}',  # SME-PRO-2025/19222
        'old': r'[A-Z]{2,4}/\d{5,6}/\d{4}',              # SME/001234/2019
        'old_prefix': r'\d{2,3}/[A-Z]{2,4}/\d{5,6}/\d{4}' # 001/04/000123/2020
    }
    
    for key, value in data.items():
        if not value or not isinstance(value, str):
            continue
        
        # Check if field name suggests it's a processo field
        is_processo_field = any(x in key.lower() for x in ['processo', 'process', 'proc'])
        
        # Check if value matches any pattern
        matches_pattern = False
        for pattern_name, pattern in patterns.items():
            if re.search(pattern, value, re.IGNORECASE):
                matches_pattern = True
                break
        
        if is_processo_field or matches_pattern:
            normalized = normalize_processo_format(value)
            is_valid = bool(re.search(r'[A-Z]{2,4}', normalized, re.IGNORECASE) and 
                          re.search(r'\d{4}', normalized))
            
            results.append((key, value, is_valid))
    
    return results


def diagnose_extraction(contract_data: Dict) -> None:
    """
    Full diagnostic report on processo extraction from contract data.
    """
    print("\n" + "=" * 70)
    print("🔬 DIAGNOSTIC REPORT: Processo Extraction")
    print("=" * 70)
    
    # 1. Check what we have
    print(f"\n📋 Contract Data Overview:")
    print(f"   Total fields: {len(contract_data)}")
    print(f"   Field names: {list(contract_data.keys())[:15]}")
    if len(contract_data) > 15:
        print(f"   ... and {len(contract_data) - 15} more")
    
    # 2. Find all processo-like fields
    print(f"\n🔍 Searching for processo fields...")
    processo_fields = extract_all_processo_like_fields(contract_data)
    
    if not processo_fields:
        print("   ❌ NO PROCESSO FIELDS FOUND!")
        print("\n   💡 Suggestions:")
        print("   1. Check if AI extraction is working correctly")
        print("   2. Verify the contract PDF contains processo information")
        print("   3. Check if field names match expected patterns")
        return
    
    print(f"   ✓ Found {len(processo_fields)} potential processo field(s):")
    print()
    
    for field, value, is_valid in processo_fields:
        status = "✅ VALID" if is_valid else "⚠️  INVALID"
        normalized = normalize_processo_format(value)
        
        print(f"   {status} Field: '{field}'")
        print(f"      Raw value: '{value}'")
        print(f"      Normalized: '{normalized}'")
        print()
    
    # 3. Show which one would be selected
    print("=" * 70)
    print("📊 SELECTION LOGIC:")
    print("=" * 70)
    
    search_order = [
        "processo_administrativo",
        "numero_processo", 
        "processo_instrutivo",
        "processo"
    ]
    
    print("\n   Priority order:")
    for i, field in enumerate(search_order, 1):
        value = contract_data.get(field)
        if value:
            normalized = normalize_processo_format(value)
            is_valid = any(f[0] == field and f[2] for f in processo_fields)
            status = "✅" if is_valid else "⚠️"
            marker = "👈 SELECTED" if i == 1 and is_valid else ""
            print(f"   {i}. {status} {field}: '{normalized}' {marker}")
        else:
            print(f"   {i}. ❌ {field}: (not present)")
    
    # 4. Check for conflicts
    print("\n" + "=" * 70)
    print("⚠️  CONFLICT CHECK:")
    print("=" * 70)
    
    valid_fields = [f for f in processo_fields if f[2]]
    if len(valid_fields) > 1:
        unique_values = set(normalize_processo_format(f[1]) for f in valid_fields)
        if len(unique_values) > 1:
            print("\n   🚨 MULTIPLE DIFFERENT PROCESSOS DETECTED!")
            print("   This might cause issues. Values found:")
            for field, value, _ in valid_fields:
                print(f"      • {field}: {normalize_processo_format(value)}")
        else:
            print("\n   ✓ All valid fields contain the same processo")
    else:
        print("\n   ✓ Only one valid processo field found")
    
    # 5. Final recommendation
    print("\n" + "=" * 70)
    print("💡 RECOMMENDATION:")
    print("=" * 70)
    
    best_field = None
    for field in search_order:
        if any(f[0] == field and f[2] for f in processo_fields):
            best_field = field
            break
    
    if best_field:
        value = normalize_processo_format(contract_data[best_field])
        print(f"\n   ✅ Use processo from '{best_field}': {value}")
    else:
        print(f"\n   ❌ No valid processo found!")
        print(f"   → Manual intervention required")
    
    print("\n" + "=" * 70)


def test_with_sample_data():
    """Test the diagnostic with sample data."""
    
    # Good case
    print("\n" + "🧪 TEST 1: Well-formed contract data")
    good_data = {
        "processo_administrativo": "SME-PRO-2025/19222",
        "numero_contrato": "215/2025",
        "valor_contrato": "R$ 572.734,00",
        "contratante": "PCRJ/SME",
    }
    diagnose_extraction(good_data)
    
    # Conflicting case
    print("\n" + "🧪 TEST 2: Conflicting processo numbers")
    conflict_data = {
        "processo_administrativo": "SME-PRO-2025/19222",
        "numero_processo": "SME-PRO-2024/12345",  # Different!
        "valor_contrato": "R$ 100.000,00",
    }
    diagnose_extraction(conflict_data)
    
    # Missing case
    print("\n" + "🧪 TEST 3: Missing processo")
    missing_data = {
        "numero_contrato": "215/2025",
        "valor_contrato": "R$ 572.734,00",
    }
    diagnose_extraction(missing_data)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        # Load JSON file
        json_path = sys.argv[1]
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if isinstance(data, list):
            print(f"📂 Loaded array with {len(data)} items, diagnosing first...")
            diagnose_extraction(data[0])
        else:
            diagnose_extraction(data)
    else:
        # Run tests
        test_with_sample_data()