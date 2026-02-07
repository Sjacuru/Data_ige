"""
publication_conformity.py - Compare contract data with publication data.

Location: conformity/analyzer/publication_conformity.py

Implements fuzzy matching and conformity analysis.
"""

import re
from datetime import datetime
from typing import Optional, Dict, Tuple, List
from difflib import SequenceMatcher

# Add project root to path
import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from domain.models.conformity_result import (
    ConformityResult,
    ConformityStatus,
    FieldCheck,
    CheckStatus,
    MatchLevel,
    PublicationCheck,
    create_not_published_result,
)

import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# =========================================================================
# CONFIGURATION
# =========================================================================

# Deadline for publication (days after signature)
PUBLICATION_DEADLINE_DAYS = 20

# Match thresholds for MatchLevel
MATCH_THRESHOLDS = {
    "exact": 100.0,    # EXATO
    "high": 80.0,      # ALTO
    "medium": 50.0,    # MÉDIO
    "low": 20.0,       # BAIXO
}

# Fields to compare
FIELDS_TO_COMPARE = [
    {
        "name": "valor",
        "label": "Valor do Contrato",
        "contract_key": "valor_contrato",
        "publication_key": "valor",
        "type": "money",
    },
    {
        "name": "numero_contrato",
        "label": "Número do Contrato",
        "contract_key": "numero_contrato",
        "publication_key": "numero_contrato",
        "type": "text",
    },
    {
        "name": "objeto",
        "label": "Objeto do Contrato",
        "contract_key": "objeto",
        "publication_key": "objeto",
        "type": "text",
    },
    {
        "name": "partes",
        "label": "Partes Contratantes",
        "contract_key": ["contratante", "contratada"],  # Will be combined
        "publication_key": "partes",
        "type": "text",
    },
    {
        "name": "prazo",
        "label": "Prazo de Vigência",
        "contract_key": ["data_inicio", "data_fim"],  # Will be combined
        "publication_key": "prazo",
        "type": "text",
    },
]


# =========================================================================
# TEXT NORMALIZATION
# =========================================================================

def normalize_text(text: Optional[str]) -> str:
    """
    Normalize text for comparison.
    
    - Convert to lowercase
    - Remove extra whitespace
    - Remove punctuation
    - Remove accents (optional)
    """
    if not text:
        return ""
    
    # Convert to lowercase
    normalized = text.lower()
    
    # Replace multiple spaces with single space
    normalized = re.sub(r'\s+', ' ', normalized)
    
    # Remove common punctuation (keep letters, numbers, spaces)
    normalized = re.sub(r'[^\w\s]', ' ', normalized)
    
    # Trim
    normalized = normalized.strip()
    
    return normalized


def normalize_money(value: Optional[str]) -> float:
    """
    Normalize monetary value to float.
    
    Handles formats:
    - R$ 572.734,00
    - 572734.00
    - 572.734,00 (quinhentos...)
    """
    if not value:
        return 0.0
    
    # Extract just the numeric part
    # Remove R$, spaces, and text in parentheses
    cleaned = re.sub(r'R\$\s*', '', str(value))
    cleaned = re.sub(r'\([^)]*\)', '', cleaned)
    cleaned = cleaned.strip()
    
    # Handle Brazilian format: 1.234.567,89
    # Remove dots (thousands separator), replace comma with dot
    if ',' in cleaned:
        # Brazilian format
        cleaned = cleaned.replace('.', '')  # Remove thousand separators
        cleaned = cleaned.replace(',', '.')  # Convert decimal comma to dot
    
    # Extract numeric value
    match = re.search(r'[\d.]+', cleaned)
    if match:
        try:
            return float(match.group())
        except ValueError:
            return 0.0
    
    return 0.0


def format_money(value: float) -> str:
    """Format float as Brazilian currency."""
    # Format with thousand separators and 2 decimal places
    formatted = f"{value:,.2f}"
    # Convert to Brazilian format
    formatted = formatted.replace(',', 'X').replace('.', ',').replace('X', '.')
    return f"R$ {formatted}"


# =========================================================================
# MATCHING FUNCTIONS
# =========================================================================

def calculate_text_similarity(text1: str, text2: str) -> float:
    """
    Calculate similarity between two texts using SequenceMatcher.
    
    Returns:
        Percentage (0.0 to 100.0)
    """
    if not text1 and not text2:
        return 100.0  # Both empty = match
    
    if not text1 or not text2:
        return 0.0  # One empty, one not = no match
    
    # Normalize both texts
    norm1 = normalize_text(text1)
    norm2 = normalize_text(text2)
    
    if norm1 == norm2:
        return 100.0
    
    # Use SequenceMatcher for fuzzy comparison
    ratio = SequenceMatcher(None, norm1, norm2).ratio()
    
    return ratio * 100.0


def calculate_money_similarity(value1: str, value2: str) -> Tuple[float, str]:
    """
    Compare two monetary values.
    
    Returns:
        Tuple of (percentage, observation)
    """
    amount1 = normalize_money(value1)
    amount2 = normalize_money(value2)
    
    if amount1 == 0 and amount2 == 0:
        return 100.0, "Ambos valores são zero ou não informados"
    
    if amount1 == 0 or amount2 == 0:
        return 0.0, "Um dos valores não foi informado"
    
    # Exact match
    if amount1 == amount2:
        return 100.0, "Valores idênticos"
    
    # Calculate percentage difference
    diff = abs(amount1 - amount2)
    avg = (amount1 + amount2) / 2
    diff_percent = (diff / avg) * 100
    
    if diff_percent < 0.01:
        return 100.0, "Diferença desprezível (arredondamento)"
    elif diff_percent < 1:
        return 99.0, f"Diferença de {diff_percent:.2f}%"
    elif diff_percent < 5:
        return 95.0, f"Diferença de {diff_percent:.2f}%"
    elif diff_percent < 10:
        return 90.0, f"Diferença de {diff_percent:.2f}%"
    else:
        similarity = max(0, 100 - diff_percent)
        return similarity, f"Diferença significativa de {diff_percent:.1f}%"


def get_match_level(percentage: float) -> MatchLevel:
    """Convert percentage to MatchLevel."""
    if percentage >= MATCH_THRESHOLDS["exact"]:
        return MatchLevel.EXACT
    elif percentage >= MATCH_THRESHOLDS["high"]:
        return MatchLevel.HIGH
    elif percentage >= MATCH_THRESHOLDS["medium"]:
        return MatchLevel.MEDIUM
    elif percentage >= MATCH_THRESHOLDS["low"]:
        return MatchLevel.LOW
    else:
        return MatchLevel.NONE


def get_check_status(match_level: MatchLevel) -> CheckStatus:
    """Convert MatchLevel to CheckStatus."""
    if match_level in [MatchLevel.EXACT, MatchLevel.HIGH]:
        return CheckStatus.PASSED
    elif match_level == MatchLevel.MEDIUM:
        return CheckStatus.PARTIAL
    else:
        return CheckStatus.FAILED


# =========================================================================
# DATE FUNCTIONS
# =========================================================================

def parse_date(date_str: Optional[str]) -> Optional[datetime]:
    """
    Parse date string to datetime.
    
    Handles formats:
    - DD/MM/YYYY
    - YYYY-MM-DD
    - DD-MM-YYYY
    """
    if not date_str:
        return None
    
    formats = [
        "%d/%m/%Y",
        "%Y-%m-%d",
        "%d-%m-%Y",
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    
    return None


def calculate_days_between(date1_str: str, date2_str: str) -> Optional[int]:
    """
    Calculate days between two dates.
    
    Returns:
        Number of days (positive if date2 > date1)
    """
    date1 = parse_date(date1_str)
    date2 = parse_date(date2_str)
    
    if not date1 or not date2:
        return None
    
    delta = date2 - date1
    return delta.days


# =========================================================================
# FIELD EXTRACTION HELPERS
# =========================================================================

def get_contract_value(contract_data: Dict, key) -> Optional[str]:
    """
    Get value from contract data.
    Handles single key or list of keys (for combined fields).
    """
    if isinstance(key, list):
        # Combine multiple fields
        values = []
        for k in key:
            v = contract_data.get(k)
            if v:
                values.append(str(v))
        return " ".join(values) if values else None
    else:
        return contract_data.get(key)


def get_publication_value(publication_data: Dict, key: str) -> Optional[str]:
    """Get value from publication data."""
    return publication_data.get(key)


# =========================================================================
# MAIN COMPARISON FUNCTION
# =========================================================================

def compare_contract_with_publication(
    contract_data: Dict,
    publication_data: Dict,
    processo: str
) -> ConformityResult:
    """
    Compare contract data with publication data.
    
    Args:
        contract_data: Data extracted from contract PDF
        publication_data: Data extracted from D.O. publication
        processo: Processo number
        
    Returns:
        ConformityResult with all checks
    """
    logging.info(f"\n📊 Comparing contract with publication for {processo}")
    
    field_checks = []
    
    # Compare each configured field
    for field_config in FIELDS_TO_COMPARE:
        field_name = field_config["name"]
        field_label = field_config["label"]
        field_type = field_config["type"]
        
        # Get values
        contract_value = get_contract_value(contract_data, field_config["contract_key"])
        publication_value = get_publication_value(publication_data, field_config["publication_key"])
        
        # Compare based on type
        if field_type == "money":
            percentage, observation = calculate_money_similarity(contract_value, publication_value)
        else:
            percentage = calculate_text_similarity(contract_value, publication_value)
            observation = ""
        
        # Determine match level and status
        match_level = get_match_level(percentage)
        status = get_check_status(match_level)
        
        # Create field check
        check = FieldCheck(
            field_name=field_name,
            field_label=field_label,
            contract_value=contract_value,
            publication_value=publication_value,
            status=status,
            match_level=match_level,
            match_percentage=percentage,
            observation=observation
        )
        
        field_checks.append(check)
        
        # Log
        status_icon = "✓" if status == CheckStatus.PASSED else "✗" if status == CheckStatus.FAILED else "◐"
        logging.info(f"   {status_icon} {field_label}: {match_level.value} ({percentage:.1f}%)")
    
    # Check publication timing
    contract_signature = contract_data.get("data_assinatura") or contract_data.get("data_inicio")
    publication_date = publication_data.get("publication_date")
    
    days_to_publish = None
    published_on_time = False
    timing_observation = ""
    
    if contract_signature and publication_date:
        days_to_publish = calculate_days_between(contract_signature, publication_date)
        if days_to_publish is not None:
            published_on_time = days_to_publish <= PUBLICATION_DEADLINE_DAYS
            if published_on_time:
                timing_observation = f"Publicado em {days_to_publish} dias (dentro do prazo de {PUBLICATION_DEADLINE_DAYS} dias)"
            else:
                timing_observation = f"Publicado em {days_to_publish} dias (FORA do prazo de {PUBLICATION_DEADLINE_DAYS} dias)"
            
            logging.info(f"   {'✓' if published_on_time else '✗'} Prazo: {timing_observation}")
    
    # Create publication check
    pub_check = PublicationCheck(
        was_published=True,
        publication_date=publication_date,
        edition_number=publication_data.get("edition_number"),
        page_number=publication_data.get("page_number"),
        download_link=publication_data.get("download_link"),
        contract_signature_date=contract_signature,
        days_to_publish=days_to_publish,
        deadline_days=PUBLICATION_DEADLINE_DAYS,
        published_on_time=published_on_time,
        status=CheckStatus.PASSED if published_on_time else CheckStatus.FAILED,
        observation=timing_observation
    )
    
    # Create result
    result = ConformityResult(
        processo=processo,
        publication_check=pub_check,
        field_checks=field_checks,
        contract_data=contract_data,
        publication_data=publication_data,
    )
    
    # Calculate summary
    result.calculate_summary()
    
    logging.info(f"\n   📋 Overall: {result.overall_status.value} (Score: {result.conformity_score:.1f}%)")
    
    return result


def analyze_publication_conformity(
    contract_data: Dict,
    publication_result  # PublicationResult from doweb_scraper
) -> ConformityResult:
    """
    Main entry point for conformity analysis.
    
    Handles both found and not-found publications.
    
    Args:
        contract_data: Data extracted from contract PDF
        publication_result: Result from doweb_scraper.search_and_extract_publication()
        
    Returns:
        ConformityResult
    """
    # Get processo from contract data
    processo = (
        contract_data.get("processo_administrativo") or
        contract_data.get("numero_processo") or
        contract_data.get("processo") or
        "UNKNOWN"
    )
    
    # Check if publication was found
    if not publication_result.found:
        logger.error(f"\n❌ Publication not found for {processo}")
        logging.info(f"   Reason: {publication_result.error}")
        
        return create_not_published_result(
            processo=processo,
            reason=publication_result.error or "Publicação não encontrada no D.O. Rio"
        )
    
    # Build publication data dict for comparison
    publication_data = {
        "publication_date": publication_result.publication_date,
        "edition_number": publication_result.edition_number,
        "page_number": publication_result.page_number,
        "download_link": publication_result.download_link,
        "orgao": publication_result.orgao,
        "tipo_extrato": publication_result.tipo_extrato,
        "processo_instrutivo": publication_result.processo_instrutivo,
        "numero_contrato": publication_result.numero_contrato,
        "data_assinatura": publication_result.data_assinatura,
        "partes": publication_result.partes,
        "objeto": publication_result.objeto,
        "prazo": publication_result.prazo,
        "valor": publication_result.valor,
        "programa_trabalho": publication_result.programa_trabalho,
        "natureza_despesa": publication_result.natureza_despesa,
        "nota_empenho": publication_result.nota_empenho,
        "fundamento": publication_result.fundamento,
    }
    
    # Perform comparison
    return compare_contract_with_publication(
        contract_data=contract_data,
        publication_data=publication_data,
        processo=processo
    )


# =========================================================================
# STANDALONE TEST
# =========================================================================

if __name__ == "__main__":
    # Test data (simulating what we get from contract_extractor and doweb_scraper)
    
    contract_data = {
        "processo_administrativo": "SME-PRO-2025/19222",
        "numero_contrato": "215/2025",
        "valor_contrato": "R$ 572.734,00",
        "data_assinatura": "28/10/2025",
        "contratante": "PCRJ/SME",
        "contratada": "ASSOCIACAO COLUMBIA GLOBAL CENTER/BRASIL",
        "objeto": "Qualificação de lideranças mediante participação do Programa FabLearn",
        "data_inicio": "30/12/2025",
        "data_fim": "29/12/2026",
    }
    
    publication_data = {
        "publication_date": "07/01/2026",
        "edition_number": "200",
        "page_number": "86",
        "download_link": "https://doweb.rio.rj.gov.br/portal/edicoes/download/13857/86",
        "numero_contrato": "215/2025",
        "valor": "R$ 572.734,00 (quinhentos e setenta e dois mil, setecentos e trinta e quatro reais)",
        "data_assinatura": "28/10/2025",
        "partes": "PCRJ/SME e ASSOCIACAO COLUMBIA GLOBAL CENTER/BRASIL",
        "objeto": "Qualificação de lideranças mediante a participação do Programa FabLearn",
        "prazo": "30/12/2025 a 29/12/2026",
    }
    
    # Test comparison
    result = compare_contract_with_publication(
        contract_data=contract_data,
        publication_data=publication_data,
        processo="SME-PRO-2025/19222"
    )
    
    # Print results
    logging.info("\n" + result.get_summary_text())
    
    logging.info("\n📋 JSON Output:")
    import json
    logging.info(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))