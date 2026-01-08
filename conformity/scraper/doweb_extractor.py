"""
doweb_extractor.py - Extract and parse text from D.O. Rio PDFs.

Location: conformity/scraper/doweb_extractor.py

STANDALONE FILE - Can be tested independently.
"""

import re
import fitz  # PyMuPDF
from pathlib import Path
from typing import Optional, Dict, Tuple, List

# Add project root to path
import sys
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Import from config with fallback
try:
    from config import TARGET_EXTRATO_TYPES, PROCESSO_PATTERNS
except ImportError:
    # Fallback defaults if config not available
    TARGET_EXTRATO_TYPES = [
        "EXTRATO DO CONTRATO",
        "EXTRATO DE TERMO ADITIVO",
        "EXTRATO DE CONTRATO",
        "EXTRATO DO TERMO",
    ]
    PROCESSO_PATTERNS = {
        "new": r"([A-Z]{2,4}-[A-Z]{2,4}-\d{4}/\d{4,6})",
        "old": r"([A-Z]{2,4}/\d{5,6}/\d{4})",
        "old_prefix": r"\d{2,3}/([A-Z]{2,4}/\d{5,6}/\d{4})",
    }


# =========================================================================
# EXTRACTION PATTERNS
# =========================================================================

FIELD_PATTERNS = {
    "processo_instrutivo": [
        r"Processo\s+Instrutivo\s+n[º°]?\s*:?\s*([A-Z]{2,4}-[A-Z]{2,4}-\d{4}/\d{4,6})",
        r"Processo\s+Instrutivo\s+n[º°]?\s*:?\s*([A-Z]{2,4}/\d{5,6}/\d{4})",
        r"PROCESSO[:\s]+([A-Z]{2,4}-[A-Z]{2,4}-\d{4}/\d{4,6})",
    ],
    "numero_contrato": [
        r"Contrato\s+n[º°]?\s*:?\s*([\d]+/\d{4})",
        r"Contrato\s+MOBI\s+RIO\s+n[º°]?\s*:?\s*([\d]+/\d{4})",
        r"Instrumento\s+Contratual[:\s]+([\d]+/\d{4})",
    ],
    "data_assinatura": [
        r"Data\s+da\s+assinatura[:\s]+(\d{2}/\d{2}/\d{4})",
        r"Data\s+de\s+Assinatura[:\s]+(\d{2}/\d{2}/\d{4})",
        r"Assinatura[:\s]+(\d{2}/\d{2}/\d{4})",
    ],
    "partes": [
        r"Partes[:\s]+(.+?)(?=Objeto|$)",
    ],
    "objeto": [
        r"Objeto[:\s]+(.+?)(?=Prazo|Valor|$)",
    ],
    "prazo": [
        r"Prazo[:\s]+(.+?)(?=Valor|Programa|$)",
    ],
    "valor": [
        r"Valor(?:\s+total)?[:\s]+(R\$\s*[\d\.,]+(?:\s*\([^)]+\))?)",
    ],
    "programa_trabalho": [
        r"Programa[s]?\s+de\s+Trabalho[:\s]+([\d\.]+)",
    ],
    "natureza_despesa": [
        r"Natureza\s+da\s+Despesa[:\s]+([\d]+)",
    ],
    "nota_empenho": [
        r"Nota[s]?\s+de\s+Empenho[:\s]+([\w\d]+)",
    ],
    "fundamento": [
        r"Fundamento[:\s]+(.+?)(?=\n\n|$)",
    ],
}


# =========================================================================
# PDF TEXT EXTRACTION
# =========================================================================

def extract_text_from_pdf(pdf_path: str) -> Tuple[bool, str, str]:
    """
    Extract text from a PDF file.
    
    Args:
        pdf_path: Path to the PDF file
        
    Returns:
        Tuple of (success, text, error_message)
    """
    try:
        doc = fitz.open(pdf_path)
        full_text = ""
        
        for page in doc:
            text = page.get_text("text")
            full_text += text + "\n"
        
        doc.close()
        
        if not full_text.strip():
            return False, "", "PDF has no extractable text"
        
        return True, full_text, ""
        
    except Exception as e:
        return False, "", f"Error extracting PDF: {str(e)}"


# =========================================================================
# PUBLICATION FINDING
# =========================================================================

def find_extrato_sections(text: str) -> List[Dict]:
    """
    Find all EXTRATO sections in the PDF text.
    
    Returns:
        List of dicts with 'type', 'start', 'end', 'text'
    """
    sections = []
    
    # Pattern to find EXTRATO headers
    extrato_pattern = r"(EXTRATO\s+(?:DO\s+)?(?:CONTRATO|TERMO\s+ADITIVO|DE\s+TERMO\s+ADITIVO|DE\s+CONTRATO|DO\s+TERMO))"
    
    matches = list(re.finditer(extrato_pattern, text, re.IGNORECASE))
    
    for i, match in enumerate(matches):
        start = match.start()
        
        # End is either next EXTRATO or next major section or 2000 chars
        if i + 1 < len(matches):
            end = matches[i + 1].start()
        else:
            # Look for next major header or take 2000 chars
            next_header = re.search(
                r"\n\s*(SECRETARIA|TRIBUNAL|COMPANHIA|FUNDAÇÃO|AUTARQUIA)",
                text[start + 100:start + 2500]
            )
            if next_header:
                end = start + 100 + next_header.start()
            else:
                end = min(start + 2000, len(text))
        
        section_text = text[start:end].strip()
        
        sections.append({
            "type": match.group(1).upper(),
            "start": start,
            "end": end,
            "text": section_text
        })
    
    return sections


def normalize_processo(processo: str) -> str:
    """
    Normalize processo number for comparison.
    
    Handles:
    - SME-PRO-2025/19222 → smepro202519222
    - SME/001234/2019 → sme0012342019
    - 001/04/000123/2020 → 040001232020 (removes prefix)
    """
    # Remove common separators
    normalized = processo.upper().replace("-", "").replace("/", "").replace(" ", "")
    
    # If starts with 3 digits followed by more content, might be old prefix format
    prefix_match = re.match(r"^\d{3}(\w+)$", normalized)
    if prefix_match:
        normalized = prefix_match.group(1)
    
    return normalized.lower()


def find_matching_extrato(
    text: str,
    processo_searched: str
) -> Optional[Dict]:
    """
    Find the EXTRATO section that matches the searched processo.
    
    Args:
        text: Full PDF text
        processo_searched: The processo number we're looking for
        
    Returns:
        Dict with section info or None if not found
    """
    sections = find_extrato_sections(text)
    
    if not sections:
        return None
    
    # Normalize the searched processo for comparison
    processo_normalized = normalize_processo(processo_searched)
    
    for section in sections:
        section_text = section["text"]
        
        # Look for processo number in this section
        for pattern_name, pattern in PROCESSO_PATTERNS.items():
            matches = re.findall(pattern, section_text, re.IGNORECASE)
            for match in matches:
                if normalize_processo(match) == processo_normalized:
                    return section
    
    return None


# =========================================================================
# FIELD EXTRACTION
# =========================================================================

def extract_field(text: str, field_name: str) -> Optional[str]:
    """
    Extract a specific field from text using patterns.
    """
    patterns = FIELD_PATTERNS.get(field_name, [])
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            value = match.group(1).strip()
            # Clean up the value
            value = re.sub(r'\s+', ' ', value)
            value = value.rstrip('.')
            return value
    
    return None


def extract_orgao(text: str) -> Optional[str]:
    """
    Extract the órgão (government body) from the text.
    """
    # Look for SECRETARIA, COMPANHIA, etc. before EXTRATO
    pattern = r"((?:SECRETARIA|COMPANHIA|FUNDAÇÃO|AUTARQUIA|TRIBUNAL)[^\n]+?)[\n\s]+EXTRATO"
    match = re.search(pattern, text, re.IGNORECASE)
    
    if match:
        return match.group(1).strip()
    
    # Fallback: look for SECRETARIA anywhere
    pattern2 = r"(SECRETARIA\s+MUNICIPAL\s+DE\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ\s]+)"
    match2 = re.search(pattern2, text, re.IGNORECASE)
    
    if match2:
        return match2.group(1).strip()
    
    return None


def extract_all_fields(section_text: str) -> Dict:
    """
    Extract all fields from an EXTRATO section.
    """
    # Determine extrato type
    tipo_match = re.search(
        r"EXTRATO\s+(DO\s+CONTRATO|DE\s+TERMO\s+ADITIVO|DO\s+TERMO\s+ADITIVO|DE\s+CONTRATO|DO\s+TERMO)",
        section_text,
        re.IGNORECASE
    )
    tipo_extrato = f"EXTRATO {tipo_match.group(1).upper()}" if tipo_match else "EXTRATO"
    
    # Extract orgão
    orgao = extract_orgao(section_text)
    
    # Extract all other fields
    fields = {
        "tipo_extrato": tipo_extrato,
        "orgao": orgao,
        "processo_instrutivo": extract_field(section_text, "processo_instrutivo"),
        "numero_contrato": extract_field(section_text, "numero_contrato"),
        "data_assinatura": extract_field(section_text, "data_assinatura"),
        "partes": extract_field(section_text, "partes"),
        "objeto": extract_field(section_text, "objeto"),
        "prazo": extract_field(section_text, "prazo"),
        "valor": extract_field(section_text, "valor"),
        "programa_trabalho": extract_field(section_text, "programa_trabalho"),
        "natureza_despesa": extract_field(section_text, "natureza_despesa"),
        "nota_empenho": extract_field(section_text, "nota_empenho"),
        "fundamento": extract_field(section_text, "fundamento"),
        "raw_text": section_text,
    }
    
    return fields


# =========================================================================
# MAIN EXTRACTION FUNCTION
# =========================================================================

def extract_publication_from_pdf(
    pdf_path: str,
    processo_searched: str
) -> Tuple[bool, Dict, str]:
    """
    Extract publication data from a PDF if it contains the searched processo.
    
    Args:
        pdf_path: Path to the PDF file
        processo_searched: The processo number to look for
        
    Returns:
        Tuple of (found, extracted_data, error_message)
    """
    # Step 1: Extract text from PDF
    success, text, error = extract_text_from_pdf(pdf_path)
    
    if not success:
        return False, {}, error
    
    # Step 2: Find matching EXTRATO section
    matching_section = find_matching_extrato(text, processo_searched)
    
    if not matching_section:
        return False, {}, "No matching EXTRATO found for this processo"
    
    # Step 3: Extract all fields from the section
    extracted = extract_all_fields(matching_section["text"])
    
    return True, extracted, ""


# =========================================================================
# STANDALONE TEST
# =========================================================================

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 3:
        print("Usage: python doweb_extractor.py <pdf_path> <processo_number>")
        print("Example: python doweb_extractor.py ./test.pdf SME-PRO-2025/19222")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    processo = sys.argv[2]
    
    print(f"📄 Extracting from: {pdf_path}")
    print(f"🔍 Looking for processo: {processo}")
    print("=" * 50)
    
    found, data, error = extract_publication_from_pdf(pdf_path, processo)
    
    if found:
        print("✅ FOUND!")
        import json
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(f"❌ NOT FOUND: {error}")