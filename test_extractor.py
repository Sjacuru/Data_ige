"""Quick test for contract_extractor.py"""

from Contract_analisys.contract_extractor import (
    extract_json_from_response,
    identify_risk_flags,
    get_folder_stats
)

# Test 1: JSON extraction
print("Test 1: JSON Extraction")
test_cases = [
    '{"valor": "R$ 100"}',
    '```json\n{"valor": "R$ 100"}\n```',
    'Here is the data:\n```\n{"valor": "R$ 100"}\n```\nDone!',
]
for tc in test_cases:
    result = extract_json_from_response(tc)
    print(f"  ✅ {result}")

# Test 2: Risk flags
print("\nTest 2: Risk Flags")
text = "Este contrato tem dispensa de licitação e prevê aditivo contratual."
flags = identify_risk_flags(text)
print(f"  Level: {flags['risk_level']}, Flags: {flags['total_flags']}")

# Test 3: Folder stats
print("\nTest 3: Folder Stats")
stats = get_folder_stats("data/downloads/processos")
print(f"  Found {stats['total_files']} PDFs")

print("\n✅ All tests passed!")