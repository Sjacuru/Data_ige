"""
publication.py - Data models for D.O. Rio publications.

Location: conformity/models/publication.py
"""

from dataclasses import dataclass, field
from typing import Optional, List
from datetime import datetime

import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class PublicationResult:
    """
    Result of searching and extracting a publication from D.O. Rio.
    
    Stores extracted data + download link (not the PDF itself).
    """
    
    # =========================================================================
    # SEARCH METADATA
    # =========================================================================
    processo_searched: str
    search_timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    # Search outcome
    found: bool = False
    search_results_total: int = 0
    results_checked: int = 0
    pages_navigated: int = 0
    
    # =========================================================================
    # PUBLICATION METADATA (if found)
    # =========================================================================
    publication_date: Optional[str] = None       # "07/01/2026"
    edition_number: Optional[str] = None         # "200"
    page_number: Optional[str] = None            # "86"
    download_link: Optional[str] = None          # Full URL to download PDF
    
    # =========================================================================
    # EXTRACTED CONTENT (from PDF)
    # =========================================================================
    orgao: Optional[str] = None                  # "SECRETARIA MUNICIPAL DE EDUCAÇÃO"
    tipo_extrato: Optional[str] = None           # "EXTRATO DO CONTRATO"
    processo_instrutivo: Optional[str] = None    # "SME-PRO-2025/19222"
    numero_contrato: Optional[str] = None        # "215/2025"
    data_assinatura: Optional[str] = None        # "28/10/2025"
    partes: Optional[str] = None                 # "PCRJ/SME e ASSOCIACAO..."
    objeto: Optional[str] = None                 # "Qualificação de lideranças..."
    prazo: Optional[str] = None                  # "30/12/2025 a 29/12/2026"
    valor: Optional[str] = None                  # "R$ 572.734,00"
    programa_trabalho: Optional[str] = None      # "10.1601.12.368.0624.2294"
    natureza_despesa: Optional[str] = None       # "339039"
    nota_empenho: Optional[str] = None           # "2025NE004019"
    fundamento: Optional[str] = None             # "Art. 74, III, 'f'..."
    
    # =========================================================================
    # RAW DATA
    # =========================================================================
    raw_text: Optional[str] = None               # Full extracted text from PDF section
    
    # =========================================================================
    # ERROR HANDLING
    # =========================================================================
    error: Optional[str] = None
    error_stage: Optional[str] = None            # "search", "download", "extraction"
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON export."""
        return {
            "processo_searched": self.processo_searched,
            "search_timestamp": self.search_timestamp,
            "found": self.found,
            "search_results_total": self.search_results_total,
            "results_checked": self.results_checked,
            "pages_navigated": self.pages_navigated,
            "publication": {
                "date": self.publication_date,
                "edition": self.edition_number,
                "page": self.page_number,
                "download_link": self.download_link,
            } if self.found else None,
            "extracted_data": {
                "orgao": self.orgao,
                "tipo_extrato": self.tipo_extrato,
                "processo_instrutivo": self.processo_instrutivo,
                "numero_contrato": self.numero_contrato,
                "data_assinatura": self.data_assinatura,
                "partes": self.partes,
                "objeto": self.objeto,
                "prazo": self.prazo,
                "valor": self.valor,
                "programa_trabalho": self.programa_trabalho,
                "natureza_despesa": self.natureza_despesa,
                "nota_empenho": self.nota_empenho,
                "fundamento": self.fundamento,
            } if self.found else None,
            "error": self.error,
            "error_stage": self.error_stage,
        }


@dataclass
class SearchResultItem:
    """
    A single item from the search results page.
    
    Used internally during navigation.
    """
    index: int
    publication_date: str          # "07/01/2026"
    edition_number: str            # "200"
    page_number: str               # "86"
    preview_text: str              # Snippet shown in results
    download_link: Optional[str] = None
    has_extrato: bool = False      # True if preview contains EXTRATO


# =========================================================================
# HELPER FUNCTIONS
# =========================================================================

def create_not_found_result(
    processo: str,
    results_total: int = 0,
    results_checked: int = 0,
    pages_navigated: int = 0,
    reason: str = "Not found after checking all results"
) -> PublicationResult:
    """Create a standardized 'not found' result."""
    return PublicationResult(
        processo_searched=processo,
        found=False,
        search_results_total=results_total,
        results_checked=results_checked,
        pages_navigated=pages_navigated,
        error=reason,
        error_stage="search"
    )


def create_error_result(
    processo: str,
    error: str,
    stage: str
) -> PublicationResult:
    """Create a standardized error result."""
    return PublicationResult(
        processo_searched=processo,
        found=False,
        error=error,
        error_stage=stage
    )


# =========================================================================
# STANDALONE TEST
# =========================================================================

if __name__ == "__main__":
    # Test creating a result
    result = PublicationResult(
        processo_searched="SME-PRO-2025/19222",
        found=True,
        publication_date="07/01/2026",
        edition_number="200",
        page_number="86",
        download_link="https://doweb.rio.rj.gov.br/portal/edicoes/download/13857/86",
        orgao="SECRETARIA MUNICIPAL DE EDUCAÇÃO",
        tipo_extrato="EXTRATO DO CONTRATO",
        numero_contrato="215/2025",
    )
    
    logging.info("✅ PublicationResult created:")
    import json
    logging.info(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))