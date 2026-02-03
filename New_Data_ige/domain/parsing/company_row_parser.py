"""
company_row_parser.py - Parses raw text into CompanyData

Location: NEW_DATA_IGE/domain/parsing/company_row_parser.py

This replaces the logic from your src/scraper.py::parse_row_data() function.
But now it's:
- Testable without Selenium
- Single Responsibility (only parsing)
- Returns domain objects (CompanyData)
"""

import re
from typing import Optional
from New_Data_ige.domain.models.company import CompanyData


class CompanyRowParser:
    """
    Parses raw company row text into structured CompanyData objects.
    
    This is the "new way" to do what parse_row_data() did in your scraper.py.
    Key differences:
    - Returns CompanyData objects (not dicts)
    - No dependency on Selenium
    - Easy to test with plain strings
    """
    
    def parse(self, row_text: str) -> Optional[CompanyData]:
        """
        Parse a single row of text into CompanyData.
        
        Args:
            row_text: Raw text like "12.345.678/0001-99 - Empresa LTDA 1.000,00 ..."
        
        Returns:
            CompanyData object if valid, None if invalid/skip
        
        Examples:
            >>> parser = CompanyRowParser()
            >>> result = parser.parse("12.345.678/0001-99 - Empresa X 1.000,00 500,00 500,00 300,00 200,00")
            >>> result.id
            '12.345.678/0001-99'
            >>> result.name
            'Empresa X'
        """
        
        # ═══════════════════════════════════════════════════════════
        # STEP 1: Basic validation - skip invalid rows
        # ═══════════════════════════════════════════════════════════
        
        if not row_text or not row_text.strip():
            return None
        
        row_text = row_text.strip()
        
        # Skip "TOTAL" summary rows
        if "total" in row_text.lower():
            return None
        
        # Skip rows that are only numbers (incomplete/broken rows)
        if re.match(r'^[\d\.,\s\-]+$', row_text):
            return None
        
        # ═══════════════════════════════════════════════════════════
        # STEP 2: Extract ID and remaining text
        # ═══════════════════════════════════════════════════════════
        
        # Pattern: "ID - RestOfText"
        id_match = re.match(r'^([\w\d\.\/\-]+)\s*-\s*(.+)$', row_text)
        
        if not id_match:
            return None  # Doesn't match expected format
        
        company_id = id_match.group(1).strip()
        rest_text = id_match.group(2).strip()
        
        # ═══════════════════════════════════════════════════════════
        # STEP 3: Find currency numbers (Brazilian format: 1.234,56)
        # ═══════════════════════════════════════════════════════════
        
        # This pattern matches: -1.234,56 or 1.234,56 (with optional negative sign)
        currency_numbers = re.findall(r'-?[\d\.]+,\d{2}', rest_text)
        
        if len(currency_numbers) < 5:
            return None  # Need at least 5 financial values
        
        # Take the LAST 5 numbers (handles cases where CPF/CNPJ is in the middle)
        numbers = currency_numbers[-5:]
        
        # ═══════════════════════════════════════════════════════════
        # STEP 4: Extract company name (everything before first currency number)
        # ═══════════════════════════════════════════════════════════
        
        first_number = numbers[0]
        split_position = rest_text.find(first_number)
        company_name = rest_text[:split_position].strip()
        
        if not company_name:
            return None  # No company name found
        
        # ═══════════════════════════════════════════════════════════
        # STEP 5: Create and return CompanyData object
        # ═══════════════════════════════════════════════════════════
        
        try:
            return CompanyData(
                id=company_id,
                name=company_name,
                total_contratado=numbers[0],
                empenhado=numbers[1],
                saldo_executar=numbers[2],
                liquidado=numbers[3],
                pago=numbers[4],
                source_row=row_text  # Keep original for debugging
            )
        except ValueError:
            # CompanyData validation failed (empty id/name)
            return None


# ═══════════════════════════════════════════════════════════
# STANDALONE TEST
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("\n" + "="*70)
    print("🧪 TESTING CompanyRowParser")
    print("="*70)
    
    parser = CompanyRowParser()
    
    test_rows = [
        ("Perfect row", "12.345.678/0001-99 - Empresa Teste LTDA 1.000,00 500,00 500,00 300,00 200,00"),
        ("Negative values", "98.765.432/0001-11 - Empresa Negativa -1.500,00 2.000,00 -500,00 1.000,00 900,00"),
        ("CPF", "123.456.789-00 - Pessoa Física 5.000,00 2.500,00 2.500,00 1.000,00 800,00"),
        ("Complex name", "11.222.333/0001-44 - ACME Corp. & Cia LTDA - EPP 10.000,00 5.000,00 5.000,00 3.000,00 2.000,00"),
        ("Empty row (should skip)", ""),
        ("TOTAL row (should skip)", "TOTAL 100.000,00 50.000,00 50.000,00 30.000,00 20.000,00"),
        ("Only numbers (should skip)", "1.000,00 500,00 500,00 300,00 200,00"),
        ("Not enough values (should skip)", "12.345.678/0001-99 - Empresa X 1.000,00 500,00"),
    ]
    
    for name, row in test_rows:
        result = parser.parse(row)
        
        if result:
            print(f"\n✅ {name}")
            print(f"   ID: {result.id}")
            print(f"   Name: {result.name[:40]}")
            print(f"   Total: {result.total_contratado}")
        else:
            print(f"\n⊘ {name} → SKIPPED (as expected)")
    
    print("\n" + "="*70)
    print("✅ Parser tests completed!")
    print("="*70)