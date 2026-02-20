"""
domain/models/processo_link.py

Stage 1 data models: companies and processo links.

Design principle
----------------
ProcessoLink holds ONLY what is discoverable during navigation —
the processo number and its URL on processo.rio.
Contract content (objeto, situação, datas, valores) is Stage 2 work
and belongs in a separate extraction model.
"""
from dataclasses import dataclass, field, asdict
from typing import Optional, List
from datetime import datetime


@dataclass
class ProcessoLink:
    """
    One contract link discovered during ContasRio navigation.

    Fields set at discovery time
    ----------------------------
    processo_id    : Process number extracted from the Processo cell.
                     Example: "TUR-PRO-2025/01221"
    url            : Direct link to the process document on processo.rio.
                     Example: "https://acesso.processo.rio/sigaex/public/
                               app/transparencia/processo?n=TUR-PRO-2025/01221"
    company_name   : Favorecido name (navigation path level 0).
    company_cnpj   : Normalised CNPJ digits of the Favorecido.
    contract_value : "Total Contratado" string — available in the grid row
                     at no extra cost, so we keep it as lightweight metadata.
    discovery_path : [company_name, orgao_name, ug_name] — the breadcrumb
                     trail used to reach this contract row.
    discovered_at  : ISO timestamp.

    Everything else (objeto, descrição, situação, datas) is Stage 2.
    """
    processo_id: str
    url: str

    company_name: Optional[str] = None
    company_cnpj: Optional[str] = None
    contract_value: Optional[str] = None        # lightweight — already in grid

    discovery_path: List[str] = field(default_factory=list)
    discovered_at: str = field(
        default_factory=lambda: datetime.now().isoformat()
    )

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ProcessoLink":
        known = {k for k in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})

    def __str__(self) -> str:
        return f"ProcessoLink({self.processo_id} | {self.company_name})"


@dataclass
class CompanyData:
    """
    One Favorecido row from the ContasRio all-companies grid.

    company_id is the normalised CNPJ digit string (14 chars for most
    entries). When CNPJ is absent a sanitised name slug is used instead.
    """
    company_id: str
    company_name: str
    company_cnpj: Optional[str] = None

    total_contracts: int = 0
    total_value: Optional[str] = None

    discovered_at: str = field(
        default_factory=lambda: datetime.now().isoformat()
    )
    # Raw cell texts from the grid row — kept for debugging, excluded from repr
    raw_cells: Optional[List[str]] = field(default=None, repr=False)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "CompanyData":
        known = {k for k in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})

    def __str__(self) -> str:
        return (
            f"CompanyData({self.company_name} | "
            f"{self.total_contracts} contracts | {self.total_value})"
        )


@dataclass
class DiscoveryResult:
    """Aggregated output of the Stage 1 discovery workflow."""
    discovery_date: str = field(
        default_factory=lambda: datetime.now().isoformat()
    )
    total_companies: int = 0
    total_processos: int = 0

    companies: List[CompanyData] = field(default_factory=list)
    processos: List[ProcessoLink] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "discovery_date": self.discovery_date,
            "total_companies": self.total_companies,
            "total_processos": self.total_processos,
            "companies": [c.to_dict() for c in self.companies],
            "processos": [p.to_dict() for p in self.processos],
            "errors": self.errors,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DiscoveryResult":
        return cls(
            discovery_date=data.get("discovery_date", datetime.now().isoformat()),
            total_companies=data.get("total_companies", 0),
            total_processos=data.get("total_processos", 0),
            companies=[CompanyData.from_dict(c) for c in data.get("companies", [])],
            processos=[ProcessoLink.from_dict(p) for p in data.get("processos", [])],
            errors=data.get("errors", []),
        )

    def add_error(self, error: str) -> None:
        self.errors.append(error)

    def __str__(self) -> str:
        return (
            f"DiscoveryResult("
            f"{self.total_processos} processos, "
            f"{self.total_companies} companies)"
        )