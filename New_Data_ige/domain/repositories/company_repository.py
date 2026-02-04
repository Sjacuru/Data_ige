"""
company_repository.py - Repository interface for CompanyData

Location: NEW_DATA_IGE/domain/repositories/company_repository.py

This is a PROTOCOL (interface) - it defines WHAT repositories must do,
not HOW they do it.
"""

from typing import Protocol, List, Optional
from New_Data_ige.domain.models.company import CompanyData


class ICompanyRepository(Protocol):
    """
    Repository contract for CompanyData persistence.
    
    Why Protocol?
    - Defines interface without inheritance
    - Any class with these methods is compatible
    - Easy to swap implementations (JSON → Database → API)
    
    Example implementations:
    - JsonCompanyRepository (save to JSON)
    - CsvCompanyRepository (save to CSV)
    - DatabaseCompanyRepository (save to PostgreSQL)
    """
    
    def save(self, company: CompanyData) -> bool:
        """
        Save a single company.
        
        Returns:
            True if saved successfully
        """
        ...
    
    def save_all(self, companies: List[CompanyData]) -> int:
        """
        Save multiple companies.
        
        Returns:
            Number of companies saved
        """
        ...
    
    def find_by_id(self, company_id: str) -> Optional[CompanyData]:
        """
        Find company by ID.
        
        Args:
            company_id: Company ID (CNPJ/CPF)
        
        Returns:
            CompanyData if found, None otherwise
        """
        ...
    
    def find_all(self) -> List[CompanyData]:
        """
        Load all companies.
        
        Returns:
            List of all CompanyData
        """
        ...
    
    def delete_by_id(self, company_id: str) -> bool:
        """
        Delete company by ID.
        
        Returns:
            True if deleted
        """
        ...
    
    def count(self) -> int:
        """
        Count total companies.
        
        Returns:
            Number of companies
        """
        ...
    
    def exists(self, company_id: str) -> bool:
        """
        Check if company exists.
        
        Returns:
            True if company exists
        """
        ...