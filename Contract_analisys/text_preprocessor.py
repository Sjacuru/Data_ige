"""
Text Preprocessor for OCR Contract Output
==========================================
Cleans and structures OCR text from municipal contracts.

STANDALONE FILE - Can be tested independently.
Location: Contract_analisys/text_preprocessor.py
"""

import re
from typing import Tuple, List, Dict
from dataclasses import dataclass, field


@dataclass
class PreprocessingResult:
    """Result of text preprocessing."""
    clean_text: str
    structured_text: str
    original_length: int
    final_length: int
    reduction_percent: float
    corrections_made: List[Dict] = field(default_factory=list)
    sections_found: List[Dict] = field(default_factory=list)
    metadata_removed: List[str] = field(default_factory=list)


# ============================================================
# PATTERNS TO REMOVE - GENERIC METADATA
# ============================================================

METADATA_PATTERNS = [
    # Authentication block (generic)
    r'Autenticado com senha por\s+.+?/\s*\d+\s*[-–]\s*\d{2}/\d{2}/\d{4}\s*[àa]s?\s*\d{2}:\d{2}:\d{2}\.?',
    
    # Document authentication reference
    r'Documento\s+N[º°]:?\s*[\d\-]+\s*[-–]?\s*consulta\s+[àa]\s+autenticidade\s+em\s+\S+',
    
    # SIGA system marker
    r'\d+\s+SIGA\s*[ÀA]?"?',
    r'SIGA\s*[ÀA]"?\s*$',
    
    # processo.rio URLs
    r'https?://[^\s]*processo\.rio[^\s]*',
]


# ============================================================
# GARBAGE PATTERNS - GENERIC CLEANUP
# ============================================================

GARBAGE_PATTERNS = [
    # Equal signs as separators
    (r'\s*={2,}\s*', ' '),
    (r'\s*=\s*(?=[A-Z])', '\n\n'),
    
    # Multiple dashes
    (r'[—–\-]{3,}', ' — '),
    
    # Pipe separators
    (r'\s*\|\s*', ' '),
    
    # Orphan quotes
    (r'[""](?!\w)', ''),
    (r'(?<!\w)[""]', ''),
    
    # Multiple spaces → single space
    (r'[ \t]+', ' '),
    
    # Multiple newlines → max 2
    (r'\n{3,}', '\n\n'),
    
    # Leading/trailing whitespace per line
    (r'^\s+', '', re.MULTILINE),
    (r'\s+$', '', re.MULTILINE),
]


# ============================================================
# GENERIC CORRECTIONS - LAW REFERENCES ONLY
# ============================================================

GENERIC_CORRECTIONS = [
    # Normalize law references
    (r'Lei\s+Federal\s+n\s*[º°]\s*', 'Lei Federal nº '),
    (r'Lei\s+Municipal\s+n\s*[º°]\s*', 'Lei Municipal nº '),
    (r'Lei\s+Complementar\s+n\s*[º°]\s*', 'Lei Complementar nº '),
    (r'Decreto\s+n\s*[º°]\s*', 'Decreto nº '),
    
    # Article references
    (r'art\s*\.\s*(\d+)', r'art. \1'),
    (r'arts\s*\.\s*(\d+)', r'arts. \1'),
    
    # Paragraph symbol
    (r'§\s+', '§'),
]


# ============================================================
# STRUCTURE PATTERNS - GENERIC
# ============================================================

STRUCTURE_PATTERNS = {
    'clausula': r'(CLÁUSULA\s+\w+(?:\s+\w+)?(?:\s*[-—–:])?\s*[^\.]*)',
    'paragrafo': r'(Parágrafo\s+\w+\s*[-—–:]?)',
}


# ============================================================
# FUNCTIONS
# ============================================================

def remove_metadata(text: str) -> Tuple[str, List[str]]:
    """Remove repetitive metadata blocks."""
    removed = []
    result = text
    
    for pattern in METADATA_PATTERNS:
        matches = re.findall(pattern, result, re.IGNORECASE | re.DOTALL)
        for match in matches:
            if len(match.strip()) > 10:
                snippet = match.strip()[:80] + "..." if len(match) > 80 else match.strip()
                removed.append(snippet)
        result = re.sub(pattern, ' ', result, flags=re.IGNORECASE | re.DOTALL)
    
    return result.strip(), removed


def clean_garbage(text: str) -> Tuple[str, List[Dict]]:
    """Remove garbage characters and normalize whitespace."""
    corrections = []
    result = text
    
    for item in GARBAGE_PATTERNS:
        pattern = item[0]
        replacement = item[1]
        flags = item[2] if len(item) > 2 else 0
        
        count = len(re.findall(pattern, result, flags))
        if count > 0:
            corrections.append({"pattern": pattern[:25], "count": count})
            result = re.sub(pattern, replacement, result, flags=flags)
    
    return result.strip(), corrections


def apply_generic_corrections(text: str) -> Tuple[str, List[Dict]]:
    """Apply generic formatting corrections (law references)."""
    corrections = []
    result = text
    
    for pattern, replacement in GENERIC_CORRECTIONS:
        count = len(re.findall(pattern, result))
        if count > 0:
            corrections.append({"pattern": pattern[:30], "count": count})
            result = re.sub(pattern, replacement, result)
    
    return result, corrections


def restore_structure(text: str) -> Tuple[str, List[Dict]]:
    """Restore document structure (clauses, paragraphs)."""
    sections = []
    result = text
    
    # Add breaks before CLÁUSULA
    result = re.sub(r'(?<!\n\n)\s*(CLÁUSULA\s+)', r'\n\n\1', result, flags=re.IGNORECASE)
    
    # Add breaks before Parágrafo
    result = re.sub(r'(?<!\n)\s*(Parágrafo\s+)', r'\n\n\1', result, flags=re.IGNORECASE)
    
    # Find clauses
    for match in re.finditer(STRUCTURE_PATTERNS['clausula'], result, re.IGNORECASE):
        sections.append({
            "type": "clausula",
            "title": match.group(1).strip()[:60],
            "position": match.start()
        })
    
    # Find paragraphs
    for match in re.finditer(STRUCTURE_PATTERNS['paragrafo'], result, re.IGNORECASE):
        sections.append({
            "type": "paragrafo",
            "title": match.group(1).strip()[:40],
            "position": match.start()
        })
    
    sections.sort(key=lambda x: x["position"])
    result = re.sub(r'\n{3,}', '\n\n', result)
    
    return result.strip(), sections


def preprocess_contract_text(raw_text: str) -> PreprocessingResult:
    """
    Full preprocessing pipeline.
    
    Steps:
    1. Remove metadata
    2. Clean garbage
    3. Apply generic corrections
    4. Restore structure
    """
    original_length = len(raw_text)
    all_corrections = []
    
    text, metadata_removed = remove_metadata(raw_text)
    text, garbage_corrections = clean_garbage(text)
    all_corrections.extend(garbage_corrections)
    
    text, format_corrections = apply_generic_corrections(text)
    all_corrections.extend(format_corrections)
    
    structured_text, sections = restore_structure(text)
    
    final_length = len(structured_text)
    reduction = ((original_length - final_length) / original_length * 100) if original_length > 0 else 0
    
    return PreprocessingResult(
        clean_text=text,
        structured_text=structured_text,
        original_length=original_length,
        final_length=final_length,
        reduction_percent=round(reduction, 2),
        corrections_made=all_corrections,
        sections_found=sections,
        metadata_removed=metadata_removed
    )


def print_summary(result: PreprocessingResult) -> None:
    """Print preprocessing summary to console."""
    print("=" * 50)
    print("📄 PREPROCESSING RESULT")
    print("=" * 50)
    print(f"Original:  {result.original_length:,} chars")
    print(f"Final:     {result.final_length:,} chars")
    print(f"Reduced:   {result.reduction_percent:.1f}%")
    print(f"Metadata:  {len(result.metadata_removed)} removed")
    print(f"Sections:  {len(result.sections_found)} found")
    print("=" * 50)


# ============================================================
# STANDALONE TEST
# ============================================================

if __name__ == "__main__":
    test_text = """
    CONTRATO Nº 02/2025 === Termo de Contrato celebrado entre...
    === CLÁUSULA PRIMEIRA - LEGISLAÇÃO APLICÁVEL
    Este Contrato se rege por toda a legislação...
    Lei Federal n º 14.133/2021
    
    CLÁUSULA SEGUNDA — OBJETO
    O objeto do presente Contrato é...
    
    Parágrafo Primeiro — Os pagamentos serão...
    
    Autenticado com senha por NOME DA PESSOA - CARGO / 12345 - 14/03/2025 às 10:06:35.
    Documento Nº: 9552697-8834 - consulta à autenticidade em https://acesso.processo.rio/test
    8834 SIGA À
    """
    
    result = preprocess_contract_text(test_text)
    print_summary(result)
    
    print("\n📄 STRUCTURED TEXT:")
    print("-" * 50)
    print(result.structured_text)