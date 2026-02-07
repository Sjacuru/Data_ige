"""
json_company_repository.py - Save companies to JSON file

Location: NEW_DATA_IGE/infrastructure/persistence/json_company_repository.py

Implements ICompanyRepository using JSON storage.
"""

import json
from pathlib import Path
from typing import List, Optional
from datetime import datetime

from New_Data_ige.domain.models.company import CompanyData


class JsonCompanyRepository:
    """
    Repository that saves CompanyData to JSON file.
    
    File format:
    {
        "saved_at": "2025-02-04T10:30:00",
        "count": 100,
        "companies": [
            {"id": "12.345.678/0001-99", "name": "Empresa ABC", ...},
            ...
        ]
    }
    
    Example:
        >>> repo = JsonCompanyRepository("data/companies.json")
        >>> repo.save_all(companies)
        100
        >>> loaded = repo.find_all()
        >>> len(loaded)
        100
    """
    
    def __init__(self, file_path: str | Path):
        """
        Initialize repository.
        
        Args:
            file_path: Path to JSON file
        """
        self.file_path = Path(file_path)
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
    
    def save(self, company: CompanyData) -> bool:
        """Save a single company (appends to existing)."""
        companies = self.find_all()
        
        # Update if exists, add if new
        existing_ids = {c.id for c in companies}
        if company.id in existing_ids:
            companies = [c if c.id != company.id else company for c in companies]
        else:
            companies.append(company)
        
        return self.save_all(companies) > 0
    
    def save_all(self, companies: List[CompanyData]) -> int:
        """Save all companies (overwrites file)."""
        data = {
            "saved_at": datetime.now().isoformat(),
            "count": len(companies),
            "companies": [c.to_dict() for c in companies]
        }
        
        with open(self.file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        return len(companies)
    
    def find_by_id(self, company_id: str) -> Optional[CompanyData]:
        """Find company by ID."""
        companies = self.find_all()
        
        # Normalize ID for comparison
        normalized_id = company_id.replace(".", "").replace("/", "").replace("-", "").upper()
        
        for company in companies:
            if company.normalized_id == normalized_id:
                return company
        
        return None
    
    def find_all(self) -> List[CompanyData]:
        """Load all companies from JSON."""
        if not self.file_path.exists():
            return []
        
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            companies = []
            for item in data.get("companies", []):
                try:
                    company = CompanyData(
                        id=item["ID"],
                        name=item["Company"],
                        total_contratado=item["Total Contratado"],
                        empenhado=item["Empenhado"],
                        saldo_executar=item["Saldo a Executar"],
                        liquidado=item["Liquidado"],
                        pago=item["Pago"]
                    )
                    companies.append(company)
                except (KeyError, ValueError):
                    continue  # Skip invalid entries
            
            return companies
        
        except (json.JSONDecodeError, IOError):
            return []
    
    def delete_by_id(self, company_id: str) -> bool:
        """Delete company by ID."""
        companies = self.find_all()
        normalized_id = company_id.replace(".", "").replace("/", "").replace("-", "").upper()
        
        original_count = len(companies)
        companies = [c for c in companies if c.normalized_id != normalized_id]
        
        if len(companies) < original_count:
            self.save_all(companies)
            return True
        
        return False
    
    def count(self) -> int:
        """Count total companies."""
        return len(self.find_all())
    
    def exists(self, company_id: str) -> bool:
        """Check if company exists."""
        return self.find_by_id(company_id) is not None


# ============================================================
# STANDALONE TEST
# ============================================================

if __name__ == "__main__":
    print("\n" + "="*70)
    print("🧪 TESTING JsonCompanyRepository")
    print("="*70)
    
    # Test file
    test_file = Path("data/test_companies.json")
    
    # Clean up if exists
    if test_file.exists():
        test_file.unlink()
    
    # Create repository
    repo = JsonCompanyRepository(test_file)
    
    # Test 1: Save companies
    print("\n✅ Test 1: Save companies")
    companies = [
        CompanyData(
            id="12.345.678/0001-99",
            name="Empresa A",
            total_contratado="1.000,00",
            empenhado="500,00",
            saldo_executar="500,00",
            liquidado="300,00",
            pago="200,00"
        ),
        CompanyData(
            id="98.765.432/0001-11",
            name="Empresa B",
            total_contratado="2.000,00",
            empenhado="1.000,00",
            saldo_executar="1.000,00",
            liquidado="600,00",
            pago="400,00"
        )
    ]
    
    saved = repo.save_all(companies)
    print(f"   Saved: {saved} companies")
    
    # Test 2: Load companies
    print("\n✅ Test 2: Load companies")
    loaded = repo.find_all()
    print(f"   Loaded: {len(loaded)} companies")
    
    # Test 3: Find by ID
    print("\n✅ Test 3: Find by ID")
    company = repo.find_by_id("12.345.678/0001-99")
    if company:
        print(f"   Found: {company.name}")
    else:
        print(f"   Not found")
    
    # Test 4: Count
    print("\n✅ Test 4: Count")
    count = repo.count()
    print(f"   Total: {count} companies")
    
    # Test 5: Delete
    print("\n✅ Test 5: Delete company")
    deleted = repo.delete_by_id("12.345.678/0001-99")
    print(f"   Deleted: {deleted}")
    print(f"   Remaining: {repo.count()} companies")
    
    # Clean up
    test_file.unlink()
    
    print("\n" + "="*70)
    print("✅ Repository tests completed!")
    print("="*70)