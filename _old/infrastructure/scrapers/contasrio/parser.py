"""
parser.py - Document parsing functionality.
Extracts text and data from PDFs, Word docs, and HTML.
"""

import os
import requests
import re
from bs4 import BeautifulSoup
from pdf2image import convert_from_path, pdfinfo_from_path
import pytesseract
import traceback
from typing import Optional
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def extract_text_from_pdf(filepath: str) -> Optional[str]:
    """
    Extract text content from a PDF file.

    Args:
        filepath: Path to the PDF file

    Returns:
        Extracted text as string, or None if failed
    """
    try:
        logging.info(f"\n→ Extraindo texto de: {filepath}")

        # Get total number of pages without loading them
        info = pdfinfo_from_path(filepath)
        total_pages = info["Pages"]

        text_content = []

        # Process one page at a time to avoid high memory usage
        for page_num in range(1, total_pages + 1):
            pages = convert_from_path(
                filepath,
                first_page=page_num,
                last_page=page_num
            )  # loads only one page

            page_image = pages[0]
            page_text = pytesseract.image_to_string(page_image, lang='por')

            if page_text.strip():
                text_content.append(page_text)
                logging.info(f"  Página {page_num}: {len(page_text)} caracteres")
            else:
                logging.info(f"  Página {page_num}: sem texto detectado")

        full_text = "\n\n".join(text_content)
        logging.info(f"✓ Total extraído: {len(full_text)} caracteres")

        return full_text

    except Exception as e:
        logger.error(f"✗ Erro ao extrair texto do PDF: {e}")
        traceback.print_exc()
        return None 

def extract_text_from_url(url):
    """
    Extract text content from an HTML page.
    
    Args:
        url: URL of the page
        
    Returns:
        Extracted text as string, or None if failed
    """
    try:
        logging.info(f"\n→ Extraindo texto de URL: {url[:50]}...")
        
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, "html.parser")
        
        # Remove script and style elements
        for element in soup(["script", "style"]):
            element.decompose()
        
        text = soup.get_text(separator="\n", strip=True)
        logging.info(f"✓ Extraído: {len(text)} caracteres")
        
        return text
        
    except Exception as e:
        logger.error(f"✗ Erro ao extrair texto da URL: {e}")
        return None

def parse_contract_data(text):
    """
    Parse extracted text to find contract information.
    
    Args:
        text: Raw text from document
        
    Returns:
        Dictionary with parsed contract data
    """
    # This is a template - customize based on your document structure
    
    
    contract_data = {
        "raw_text": text,
        "values_found": [],
        "dates_found": [],
        "cnpj_found": []
    }
    
    # Example patterns - adjust to your documents
    # Find currency values
    value_pattern = r"R\$\s*[\d\.,]+(?:\.\d{2})?"
    contract_data["values_found"] = re.findall(value_pattern, text)
    
    # Find dates (DD/MM/YYYY format)
    date_pattern = r"\d{2}/\d{2}/\d{4}"
    contract_data["dates_found"] = re.findall(date_pattern, text)
    
    # Find CNPJ
    cnpj_pattern = r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}"
    contract_data["cnpj_found"] = re.findall(cnpj_pattern, text)
    
    return contract_data

class CompanyRowParser:
    def parse_from_dto(self, dto: CompanyRowDTO) -> Optional[CompanyData]:
        """
        NEW: Parse from DTO instead of raw text.
        
        Benefits:
        - Clear separation: DTO = infrastructure, CompanyData = domain
        - Easier to test with mock DTOs
        - Can validate DTO separately before parsing
        """
        if len(dto.value_parts) < 5:
            return None
        
        return CompanyData(
            id=dto.id_part,
            name=dto.name_part,
            total_contratado=dto.value_parts[0],
            empenhado=dto.value_parts[1],
            saldo_executar=dto.value_parts[2],
            liquidado=dto.value_parts[3],
            pago=dto.value_parts[4],
        )


@dataclass
class CompanyRowDTO:
    """
    Raw scraped data from Selenium.
    
    NO validation, NO business logic.
    Just carries data from infrastructure → domain.
    
    Example:
        Raw text: "12.345.678/0001-99 - Empresa ABC 1.000,00 500,00 500,00 300,00 200,00"
        
        Becomes:
        CompanyRowDTO(
            raw_text="12.345.678/0001-99 - Empresa ABC 1.000,00...",
            id_part="12.345.678/0001-99",
            name_part="Empresa ABC",
            value_parts=["1.000,00", "500,00", "500,00", "300,00", "200,00"]
        )
    """
    
    # Core data
    raw_text: str                    # Original Selenium text
    id_part: str                     # Extracted ID (CNPJ/CPF)
    name_part: str                   # Extracted company name
    value_parts: list[str]           # All currency values found
    
    # Metadata
    source: str = "selenium"         # Data source
    scraped_at: str = ""             # ISO timestamp
    
    def __post_init__(self):
        """Auto-fill timestamp if not provided"""
        if not self.scraped_at:
            self.scraped_at = datetime.now().isoformat()
    
    @property
    def is_valid(self) -> bool:
        """Quick validation check (not enforced)"""
        return (
            bool(self.id_part) and 
            bool(self.name_part) and 
            len(self.value_parts) >= 5
        )
    
    def __repr__(self) -> str:
        """Debug-friendly representation"""
        return (
            f"CompanyRowDTO("
            f"id='{self.id_part}', "
            f"name='{self.name_part[:20]}...', "
            f"values={len(self.value_parts)}, "
            f"valid={self.is_valid}"
            f")"
        )
    
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
