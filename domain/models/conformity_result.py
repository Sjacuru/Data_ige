"""
conformity_result.py - Data models for conformity analysis.

Location: conformity/models/conformity_result.py
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict
from datetime import datetime
from enum import Enum

import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ConformityStatus(str, Enum):
    """Overall conformity status."""
    CONFORME = "DADOS PUBLICADOS"
    NAO_CONFORME = "NÃO CONFORME"
    PARCIAL = "PARCIAL"


class CheckStatus(str, Enum):
    """Status of individual field checks."""
    PASSED = "APROVADO"
    FAILED = "REPROVADO"
    PARTIAL = "PARCIAL"
    NOT_CHECKED = "NÃO VERIFICADO"


class MatchLevel(str, Enum):
    """Level of matching for fuzzy comparisons."""
    EXACT = "EXATO"           # 100% match
    HIGH = "ALTO"             # 80-99% match
    MEDIUM = "MÉDIO"          # 50-79% match
    LOW = "BAIXO"             # 20-49% match
    NONE = "NENHUM"           # <20% match


@dataclass
class FieldCheck:
    """
    Result of comparing a single field between contract and publication.
    """
    field_name: str                      # e.g., "valor", "objeto", "partes"
    field_label: str                     # e.g., "Valor do Contrato"
    
    contract_value: Optional[str]        # Value from contract
    publication_value: Optional[str]     # Value from publication
    
    status: CheckStatus                  # PASSED, FAILED, PARTIAL, NOT_CHECKED
    match_level: MatchLevel              # EXACT, HIGH, MEDIUM, LOW, NONE
    match_percentage: float              # 0.0 to 100.0
    
    observation: str = ""                # Additional notes
    
    def to_dict(self) -> dict:
        return {
            "field_name": self.field_name,
            "field_label": self.field_label,
            "contract_value": self.contract_value,
            "publication_value": self.publication_value,
            "status": self.status.value,
            "match_level": self.match_level.value,
            "match_percentage": round(self.match_percentage, 1),
            "observation": self.observation,
        }


@dataclass
class PublicationCheck:
    """
    Result of checking if contract was published.
    """
    was_published: bool
    publication_date: Optional[str] = None
    edition_number: Optional[str] = None
    page_number: Optional[str] = None
    download_link: Optional[str] = None
    
    # Timing
    contract_signature_date: Optional[str] = None
    days_to_publish: Optional[int] = None
    deadline_days: int = 20
    published_on_time: bool = False
    
    # Status
    status: CheckStatus = CheckStatus.NOT_CHECKED
    observation: str = ""
    
    def to_dict(self) -> dict:
        return {
            "was_published": self.was_published,
            "publication_date": self.publication_date,
            "edition_number": self.edition_number,
            "page_number": self.page_number,
            "download_link": self.download_link,
            "timing": {
                "contract_signature_date": self.contract_signature_date,
                "days_to_publish": self.days_to_publish,
                "deadline_days": self.deadline_days,
                "published_on_time": self.published_on_time,
            },
            "status": self.status.value,
            "observation": self.observation,
        }


@dataclass
class ConformityResult:
    """
    Complete conformity analysis result.
    
    Combines publication check with field comparisons.
    """
    # Identification
    processo: str
    analysis_timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    # Overall status
    overall_status: ConformityStatus = ConformityStatus.NAO_CONFORME
    
    # Publication check
    publication_check: Optional[PublicationCheck] = None
    
    # Field checks
    field_checks: List[FieldCheck] = field(default_factory=list)
    
    # Summary counts
    checks_total: int = 0
    checks_passed: int = 0
    checks_failed: int = 0
    checks_partial: int = 0
    
    # Score (0-100)
    conformity_score: float = 0.0
    
    # Raw data (for reference)
    contract_data: Optional[Dict] = None
    publication_data: Optional[Dict] = None
    
    # Error handling
    error: Optional[str] = None
    
    def calculate_summary(self) -> None:
        """Calculate summary statistics from field checks."""
        self.checks_total = len(self.field_checks)
        self.checks_passed = sum(1 for c in self.field_checks if c.status == CheckStatus.PASSED)
        self.checks_failed = sum(1 for c in self.field_checks if c.status == CheckStatus.FAILED)
        self.checks_partial = sum(1 for c in self.field_checks if c.status == CheckStatus.PARTIAL)
        
        # Calculate score
        if self.checks_total > 0:
            # Weight: PASSED=100, PARTIAL=50, FAILED=0
            score_sum = (
                self.checks_passed * 100 +
                self.checks_partial * 50 +
                self.checks_failed * 0
            )
            self.conformity_score = score_sum / self.checks_total
        else:
            self.conformity_score = 0.0
        
        # Determine overall status
        if not self.publication_check or not self.publication_check.was_published:
            self.overall_status = ConformityStatus.NAO_CONFORME
        elif self.checks_failed == 0 and self.checks_partial == 0:
            self.overall_status = ConformityStatus.CONFORME
        elif self.checks_failed == 0:
            self.overall_status = ConformityStatus.PARCIAL
        else:
            self.overall_status = ConformityStatus.NAO_CONFORME
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON export."""
        return {
            "processo": self.processo,
            "analysis_timestamp": self.analysis_timestamp,
            "overall_status": self.overall_status.value,
            "conformity_score": round(self.conformity_score, 1),
            "summary": {
                "checks_total": self.checks_total,
                "checks_passed": self.checks_passed,
                "checks_failed": self.checks_failed,
                "checks_partial": self.checks_partial,
            },
            "publication_check": self.publication_check.to_dict() if self.publication_check else None,
            "field_checks": [c.to_dict() for c in self.field_checks],
            "error": self.error,
        }
    
    def get_summary_text(self) -> str:
        """Get a human-readable summary."""
        lines = [
            f"═══════════════════════════════════════════════════",
            f"  RESULTADO DA ANÁLISE DE CONFORMIDADE",
            f"═══════════════════════════════════════════════════",
            f"  Processo: {self.processo}",
            f"  Status: {self.overall_status.value}",
            f"  Score: {self.conformity_score:.2f}%",
            f"───────────────────────────────────────────────────",
        ]
        
        if self.publication_check:
            pub = self.publication_check
            if pub.was_published:
                lines.append(f"  ✓ Publicado em: {pub.publication_date}")
                lines.append(f"    Edição {pub.edition_number}, Pág. {pub.page_number}")
                if pub.published_on_time:
                    lines.append(f"  ✓ Prazo: {pub.days_to_publish} dias (dentro do prazo)")
                else:
                    lines.append(f"  ✗ Prazo: {pub.days_to_publish} dias (FORA do prazo de {pub.deadline_days} dias)")
            else:
                lines.append(f"  ✗ Não foi encontrada publicação no D.O. Rio")
        
        lines.append(f"───────────────────────────────────────────────────")
        lines.append(f"  Verificações: {self.checks_passed}/{self.checks_total} aprovadas")
        
        for check in self.field_checks:
            status_icon = "✓" if check.status == CheckStatus.PASSED else "✗" if check.status == CheckStatus.FAILED else "◐"
            lines.append(f"  {status_icon} {check.field_label}: {check.match_level.value} ({check.match_percentage:.0f}%)")
        
        lines.append(f"═══════════════════════════════════════════════════")
        
        return "\n".join(lines)


# =========================================================================
# HELPER FUNCTIONS
# =========================================================================

def create_not_published_result(processo: str, reason: str = "") -> ConformityResult:
    """Create a result for when publication is not found."""
    pub_check = PublicationCheck(
        was_published=False,
        status=CheckStatus.FAILED,
        observation=reason or "Publicação não encontrada no D.O. Rio"
    )
    
    result = ConformityResult(
        processo=processo,
        overall_status=ConformityStatus.NAO_CONFORME,
        publication_check=pub_check,
        error=reason
    )
    
    return result


# =========================================================================
# STANDALONE TEST
# =========================================================================

if __name__ == "__main__":
    # Test creating a conformity result
    
    pub_check = PublicationCheck(
        was_published=True,
        publication_date="07/01/2026",
        edition_number="200",
        page_number="86",
        download_link="https://doweb.rio.rj.gov.br/portal/edicoes/download/13857/86",
        contract_signature_date="28/10/2025",
        days_to_publish=71,
        deadline_days=20,
        published_on_time=False,
        status=CheckStatus.FAILED,
        observation="Publicado 71 dias após assinatura (prazo: 20 dias)"
    )
    
    field_checks = [
        FieldCheck(
            field_name="valor",
            field_label="Valor do Contrato",
            contract_value="R$ 572.734,00",
            publication_value="R$ 572.734,00",
            status=CheckStatus.PASSED,
            match_level=MatchLevel.EXACT,
            match_percentage=100.0
        ),
        FieldCheck(
            field_name="objeto",
            field_label="Objeto",
            contract_value="Qualificação de lideranças mediante participação do Programa FabLearn",
            publication_value="Qualificação de lideranças mediante a participação do Programa FabLearn",
            status=CheckStatus.PASSED,
            match_level=MatchLevel.HIGH,
            match_percentage=95.0
        ),
    ]
    
    result = ConformityResult(
        processo="SME-PRO-2025/19222",
        publication_check=pub_check,
        field_checks=field_checks,
    )
    
    result.calculate_summary()
    
    logging.info(result.get_summary_text())
    logging.info("\n📋 JSON Output:")
    import json
    logging.info(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))