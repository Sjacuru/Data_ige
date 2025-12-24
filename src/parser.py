"""
parser.py - Document parsing functionality.
Extracts text and data from PDFs, Word docs, and HTML.
"""

import os
from PyPDF2 import PdfReader
import requests
from bs4 import BeautifulSoup


def extract_text_from_pdf(filepath):
    """
    Extract text content from a PDF file.
    
    Args:
        filepath: Path to the PDF file
        
    Returns:
        Extracted text as string, or None if failed
    """
    try:
        print(f"\n→ Extraindo texto de: {filepath}")
        
        reader = PdfReader(filepath)
        text_content = []
        
        for page_num, page in enumerate(reader.pages, 1):
            page_text = page.extract_text()
            if page_text:
                text_content.append(page_text)
                print(f"  Página {page_num}: {len(page_text)} caracteres")
        
        full_text = "\n\n".join(text_content)
        print(f"✓ Total extraído: {len(full_text)} caracteres")
        
        return full_text
        
    except Exception as e:
        print(f"✗ Erro ao extrair texto do PDF: {e}")
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
        print(f"\n→ Extraindo texto de URL: {url[:50]}...")
        
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, "html.parser")
        
        # Remove script and style elements
        for element in soup(["script", "style"]):
            element.decompose()
        
        text = soup.get_text(separator="\n", strip=True)
        print(f"✓ Extraído: {len(text)} caracteres")
        
        return text
        
    except Exception as e:
        print(f"✗ Erro ao extrair texto da URL: {e}")
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
    import re
    
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