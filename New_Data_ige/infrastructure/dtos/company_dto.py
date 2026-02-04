"""
company_dto.py - Data Transfer Object for scraped company rows

Location: NEW_DATA_IGE/infrastructure/dtos/company_dto.py

Purpose: Raw data container from Selenium BEFORE domain validation.
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class CompanyRowDTO:
    """
    Raw scraped data from Selenium.
    
    NO validation, NO business logic.
    Just carries data from infrastructure → domain.
    
    Example:
        Raw text: "12.345.678/0001-99 - Empresa ABC 1.000,00 500,00 500,00 300,00 200,00"
        
        Becomes:
        CompanyRowDTO(
            raw_text="12.345.678/0001-99 - Empresa ABC 1.000,00...",
            id_part="12.345.678/0001-99",
            name_part="Empresa ABC",
            value_parts=["1.000,00", "500,00", "500,00", "300,00", "200,00"]
        )
    """
    
    # Core data
    raw_text: str                    # Original Selenium text
    id_part: str                     # Extracted ID (CNPJ/CPF)
    name_part: str                   # Extracted company name
    value_parts: list[str]           # All currency values found
    
    # Metadata
    source: str = "selenium"         # Data source
    scraped_at: str = ""             # ISO timestamp
    
    def __post_init__(self):
        """Auto-fill timestamp if not provided"""
        if not self.scraped_at:
            self.scraped_at = datetime.now().isoformat()
    
    @property
    def is_valid(self) -> bool:
        """Quick validation check (not enforced)"""
        return (
            bool(self.id_part) and 
            bool(self.name_part) and 
            len(self.value_parts) >= 5
        )
    
    def __repr__(self) -> str:
        """Debug-friendly representation"""
        return (
            f"CompanyRowDTO("
            f"id='{self.id_part}', "
            f"name='{self.name_part[:20]}...', "
            f"values={len(self.value_parts)}, "
            f"valid={self.is_valid}"
            f")"
        )


# ============================================================
# STANDALONE TEST
# ============================================================

if __name__ == "__main__":
    print("\n" + "="*70)
    print("🧪 TESTING CompanyRowDTO")
    print("="*70)
    
    # Test 1: Valid DTO
    print("\n✅ Test 1: Valid DTO")
    dto = CompanyRowDTO(
        raw_text="12.345.678/0001-99 - Empresa ABC 1.000,00 500,00 500,00 300,00 200,00",
        id_part="12.345.678/0001-99",
        name_part="Empresa ABC",
        value_parts=["1.000,00", "500,00", "500,00", "300,00", "200,00"]
    )
    print(f"   {dto}")
    print(f"   Valid: {dto.is_valid}")
    
    # Test 2: Invalid DTO (but still creates - no validation!)
    print("\n⚠️ Test 2: Invalid DTO (no validation in DTO layer)")
    invalid_dto = CompanyRowDTO(
        raw_text="invalid row",
        id_part="",  # Empty!
        name_part="",  # Empty!
        value_parts=[]  # No values!
    )
    print(f"   {invalid_dto}")
    print(f"   Valid: {invalid_dto.is_valid}")
    print(f"   ℹ️  DTO created successfully - validation happens in domain layer")
    
    print("\n" + "="*70)
    print("✅ DTO tests completed!")
    print("="*70)