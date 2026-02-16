"""
Data models for discovered processo links and companies.
Pure Python dataclasses with no external dependencies.
"""
from dataclasses import dataclass, field, asdict
from typing import Optional, List
from datetime import datetime


@dataclass
class ProcessoLink:
    """
    Represents a discovered processo link from ContasRio.
    
    Attributes:
        processo_id: Unique processo identifier (e.g., "TURCAP202500477")
        url: Link to processo document or detail page
        company_name: Associated company name
        company_cnpj: Associated company CNPJ
        contract_value: Contract value (if available during discovery)
        contract_date: Contract date (if available)
        discovery_path: Navigation path taken to find this link
        discovered_at: Timestamp when link was discovered
    """
    processo_id: str
    url: str
    
    # Associated company
    company_name: Optional[str] = None
    company_cnpj: Optional[str] = None
    
    # Contract metadata (if available during discovery)
    contract_value: Optional[str] = None
    contract_date: Optional[str] = None
    
    # Discovery metadata
    discovery_path: List[str] = field(default_factory=list)
    discovered_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'ProcessoLink':
        """Create instance from dictionary."""
        return cls(**data)
    
    def __str__(self) -> str:
        """String representation."""
        return f"ProcessoLink({self.processo_id}, {self.company_name})"

@dataclass
class CompanyData:
    """
    Represents a company discovered in ContasRio.
    
    Attributes:
        company_id: Unique company identifier
        company_name: Company name
        company_cnpj: Company CNPJ (if available)
        total_contracts: Number of contracts found for this company
        total_value: Aggregated contract value (if available)
        discovered_at: Timestamp when company was discovered
    """
    company_id: str
    company_name: str
    company_cnpj: Optional[str] = None
    
    # Aggregated values
    total_contracts: int = 0
    total_value: Optional[str] = None
    
    # Discovery metadata
    discovered_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'CompanyData':
        """Create instance from dictionary."""
        return cls(**data)
    
    def __str__(self) -> str:
        """String representation."""
        return f"CompanyData({self.company_name}, {self.total_contracts} contracts)"


@dataclass
class DiscoveryResult:
    """
    Complete result of Stage 1 discovery process.
    
    Attributes:
        discovery_date: When discovery was performed
        total_companies: Number of unique companies found
        total_processos: Number of processo links found
        companies: List of discovered companies
        processos: List of discovered processo links
        errors: List of errors encountered during discovery
    """
    discovery_date: str = field(default_factory=lambda: datetime.now().isoformat())
    total_companies: int = 0
    total_processos: int = 0
    
    companies: List[CompanyData] = field(default_factory=list)
    processos: List[ProcessoLink] = field(default_factory=list)
    
    # Errors
    errors: List[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "discovery_date": self.discovery_date,
            "total_companies": self.total_companies,
            "total_processos": self.total_processos,
            "companies": [c.to_dict() for c in self.companies],
            "processos": [p.to_dict() for p in self.processos],
            "errors": self.errors,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'DiscoveryResult':
        """Create instance from dictionary."""
        return cls(
            discovery_date=data.get("discovery_date", datetime.now().isoformat()),
            total_companies=data.get("total_companies", 0),
            total_processos=data.get("total_processos", 0),
            companies=[CompanyData.from_dict(c) for c in data.get("companies", [])],
            processos=[ProcessoLink.from_dict(p) for p in data.get("processos", [])],
            errors=data.get("errors", []),
        )
    
    def add_error(self, error: str) -> None:
        """Add error to error list."""
        self.errors.append(error)
    
    def __str__(self) -> str:
        """String representation."""
        return f"DiscoveryResult({self.total_processos} processos, {self.total_companies} companies)"