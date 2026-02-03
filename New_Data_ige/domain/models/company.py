"""
company.py - Domain model for Company data

Location: NEW_DATA_IGE/domain/models/company.py

This represents a company row from ContasRio in pure Python.
No Selenium, no databases - just business logic.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class CompanyData:
    """
    Represents a single company row from ContasRio portal.
    
    This is a "domain model" - it only knows about business concepts,
    not about how data is stored or displayed.
    
    Example row:
        "12.345.678/0001-99 - Empresa Teste LTDA 1.000,00 500,00 500,00 300,00 200,00"
    
    Becomes:
        CompanyData(
            id="12.345.678/0001-99",
            name="Empresa Teste LTDA",
            total_contratado="1.000,00",
            empenhado="500,00",
            saldo_executar="500,00",
            liquidado="300,00",
            pago="200,00"
        )
    """
    
    # Identity
    id: str                     # CNPJ, CPF, or process number
    name: str                   # Company name
    
    # Financial values (kept as strings to preserve formatting)
    total_contratado: str       # Total contracted
    empenhado: str              # Committed
    saldo_executar: str         # Balance to execute
    liquidado: str              # Liquidated
    pago: str                   # Paid
    
    # Optional metadata
    source_row: Optional[str] = None  # Original raw text (for debugging)
    
    def __post_init__(self):
        """Validate data after creation"""
        if not self.id or not self.id.strip():
            raise ValueError("Company ID cannot be empty")
        
        if not self.name or not self.name.strip():
            raise ValueError("Company name cannot be empty")
    
    def to_dict(self) -> dict:
        """Convert to dictionary for export/serialization"""
        return {
            "ID": self.id,
            "Company": self.name,
            "Total Contratado": self.total_contratado,
            "Empenhado": self.empenhado,
            "Saldo a Executar": self.saldo_executar,
            "Liquidado": self.liquidado,
            "Pago": self.pago,
        }
    
    @property
    def normalized_id(self) -> str:
        """
        Get normalized ID for comparison (removes dots, slashes, dashes).
        
        Examples:
            "12.345.678/0001-99" → "12345678000199"
            "SME-PRO-2025/19222" → "SMEPRO202519222"
        """
        return self.id.replace(".", "").replace("/", "").replace("-", "").replace(" ", "").upper()
    
    def __repr__(self) -> str:
        """Nice string representation for debugging"""
        return f"CompanyData(id='{self.id}', name='{self.name[:30]}...', total={self.total_contratado})"


# ═══════════════════════════════════════════════════════════
# STANDALONE TEST (optional - run this file directly to test)
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("\n" + "="*70)
    print("🧪 TESTING CompanyData Model")
    print("="*70)
    
    # Test 1: Create a valid company
    print("\n✅ Test 1: Creating valid company...")
    company = CompanyData(
        id="12.345.678/0001-99",
        name="Empresa Teste LTDA",
        total_contratado="1.000,00",
        empenhado="500,00",
        saldo_executar="500,00",
        liquidado="300,00",
        pago="200,00"
    )
    print(f"   Created: {company}")
    print(f"   Normalized ID: {company.normalized_id}")
    
    # Test 2: Convert to dictionary
    print("\n✅ Test 2: Converting to dictionary...")
    data_dict = company.to_dict()
    print(f"   Dictionary keys: {list(data_dict.keys())}")
    print(f"   Company value: {data_dict['Company']}")
    
    # Test 3: Invalid data (should raise error)
    print("\n❌ Test 3: Creating invalid company (empty ID)...")
    try:
        invalid_company = CompanyData(
            id="",
            name="Invalid Corp",
            total_contratado="0,00",
            empenhado="0,00",
            saldo_executar="0,00",
            liquidado="0,00",
            pago="0,00"
        )
        print("   ERROR: Should have raised ValueError!")
    except ValueError as e:
        print(f"   ✅ Correctly raised error: {e}")
    
    print("\n" + "="*70)
    print("✅ All model tests passed!")
    print("="*70)