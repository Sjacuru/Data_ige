"""
company_row_parser.py - Parses raw text into CompanyData

Location: NEW_DATA_IGE/domain/parsing/company_row_parser.py

This replaces the logic from your src/scraper.py::parse_row_data() function.
But now it's:
- Testable without Selenium
- Single Responsibility (only parsing)
- Returns domain objects (CompanyData)

UPDATED: Now uses DTOs as input instead of raw strings.
"""

import re
from typing import Optional
from New_Data_ige.domain.models.company import CompanyData
from New_Data_ige.infrastructure.dtos.company_dto import CompanyRowDTO

class CompanyRowParser:
    """
    Parses raw company row text into structured CompanyData objects.
    
    This is the "new way" to do what parse_row_data() did in your scraper.py.
    Key differences:
    - Returns CompanyData objects (not dicts)
    - No dependency on Selenium
    - Easy to test with plain strings

    NEW: Works with DTOs (structured data from Selenium)
    OLD: Used to parse raw text directly
    
    Benefits:
    - Clear separation: DTO = infrastructure, CompanyData = domain
    - Easier to test with mock DTOs
    - Domain layer doesn't know about Selenium

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

    def parse_from_dto(self, dto: CompanyRowDTO) -> Optional[CompanyData]:
        """
        Parse DTO → Domain object.
        
        Args:
            dto: CompanyRowDTO from Selenium
        
        Returns:
            CompanyData if valid, None if validation fails
        
        Example:
            >>> dto = CompanyRowDTO(
            ...     raw_text="...",
            ...     id_part="12.345.678/0001-99",
            ...     name_part="Empresa ABC",
            ...     value_parts=["1.000,00", "500,00", "500,00", "300,00", "200,00"]
            ... )
            >>> parser = CompanyRowParser()
            >>> company = parser.parse_from_dto(dto)
            >>> company.id
            '12.345.678/0001-99'
        """
        
        # ═══════════════════════════════════════════════════════════
        # VALIDATION: Domain layer enforces rules
        # ═══════════════════════════════════════════════════════════
        
        if not dto.id_part or not dto.id_part.strip():
            return None
        
        if not dto.name_part or not dto.name_part.strip():
            return None
        
        if len(dto.value_parts) < 5:
            return None
        
        # ═══════════════════════════════════════════════════════════
        # CREATE DOMAIN OBJECT
        # ═══════════════════════════════════════════════════════════
        
        try:
            return CompanyData(
                id=dto.id_part,
                name=dto.name_part,
                total_contratado=dto.value_parts[0],
                empenhado=dto.value_parts[1],
                saldo_executar=dto.value_parts[2],
                liquidado=dto.value_parts[3],
                pago=dto.value_parts[4],
                source_row=dto.raw_text  # Keep original for debugging
            )
        except ValueError as e:
            # CompanyData validation failed
            return None


# ============================================================
# STANDALONE TEST
# ============================================================

if __name__ == "__main__":
    print("\n" + "="*70)
    print("🧪 TESTING CompanyRowParser with DTOs")
    print("="*70)
    
    parser = CompanyRowParser()
    
    # Test 1: Valid DTO → Valid CompanyData
    print("\n✅ Test 1: Valid DTO")
    dto = CompanyRowDTO(
        raw_text="12.345.678/0001-99 - Empresa ABC 1.000,00 500,00 500,00 300,00 200,00",
        id_part="12.345.678/0001-99",
        name_part="Empresa ABC",
        value_parts=["1.000,00", "500,00", "500,00", "300,00", "200,00"]
    )
    
    company = parser.parse_from_dto(dto)
    
    if company:
        print(f"   ✅ Parsed successfully")
        print(f"   ID: {company.id}")
        print(f"   Name: {company.name}")
        print(f"   Total: {company.total_contratado}")
    else:
        print(f"   ❌ Failed to parse")
    
    # Test 2: Invalid DTO → None
    print("\n⚠️ Test 2: Invalid DTO (missing values)")
    invalid_dto = CompanyRowDTO(
        raw_text="invalid",
        id_part="12.345.678/0001-99",
        name_part="Empresa ABC",
        value_parts=["1.000,00"]  # Only 1 value (need 5)
    )
    
    company = parser.parse_from_dto(invalid_dto)
    
    if company:
        print(f"   ❌ Should not have parsed!")
    else:
        print(f"   ✅ Correctly rejected invalid DTO")
    
    print("\n" + "="*70)
    print("✅ Parser tests completed!")
    print("="*70)