"""
Parsers for ContasRio portal data.
Extracts structured data from HTML elements.
"""
import re
import logging
from typing import Optional
from selenium.webdriver.remote.webelement import WebElement

from domain.models.processo_link import CompanyData

logger = logging.getLogger(__name__)


class CompanyRowParser:
    """
    Parses company row data from ContasRio table.
    """
    
    @staticmethod
    def parse_row(row_element: WebElement, row_index: int) -> Optional[CompanyData]:
        """
        Parse a single company row from the table.
        
        Args:
            row_element: Selenium WebElement representing a table row (tr)
            row_index: Row number (for logging and ID generation)
            
        Returns:
            CompanyData object or None if parsing failed
        """
        try:
            # Get all cells in the row
            cells = row_element.find_elements("tag name", "td")
            
            if len(cells) < 2:
                logger.debug(f"⚠ Row {row_index}: Insufficient cells ({len(cells)})")
                return None
            
            # Extract data from cells
            # Note: Adjust cell indices based on actual ContasRio table structure
            # This is a placeholder - will need to be adjusted during integration
            
            company_name = CompanyRowParser._extract_company_name(cells, row_index)
            if not company_name:
                logger.debug(f"⚠ Row {row_index}: Empty company name")
                return None
            
            company_cnpj = CompanyRowParser._extract_cnpj(cells)
            total_value = CompanyRowParser._extract_value(cells)
            
            # Generate unique company ID
            company_id = CompanyRowParser._generate_company_id(company_name, company_cnpj)
            
            company = CompanyData(
                company_id=company_id,
                company_name=company_name,
                company_cnpj=company_cnpj,
                total_value=total_value,
                total_contracts=0  # Will be updated during discovery
            )
            
            logger.debug(f"✓ Row {row_index}: {company_name}")
            return company
            
        except Exception as e:
            logger.error(f"✗ Row {row_index} parsing failed: {e}")
            return None
    
    @staticmethod
    def _extract_company_name(cells: list, row_index: int) -> Optional[str]:
        """
        Extract company name from table cells.
        
        Args:
            cells: List of table cells (td elements)
            row_index: Row number for logging
            
        Returns:
            Company name or None
        """
        try:
            # Typically first cell contains company name
            # Adjust index based on actual table structure
            name_cell = cells[0] if len(cells) > 0 else None
            if name_cell:
                name = name_cell.text.strip()
                
                # Clean up name
                name = CompanyRowParser._clean_text(name)
                
                if name and len(name) > 2:
                    return name
            
            return None
            
        except Exception as e:
            logger.debug(f"Name extraction failed for row {row_index}: {e}")
            return None
    
    @staticmethod
    def _extract_cnpj(cells: list) -> Optional[str]:
        """
        Extract CNPJ from table cells.
        
        CNPJ Pattern: XX.XXX.XXX/XXXX-XX
        
        Args:
            cells: List of table cells
            
        Returns:
            CNPJ string or None
        """
        try:
            # Search all cells for CNPJ pattern
            for cell in cells:
                text = cell.text.strip()
                cnpj = CompanyRowParser._find_cnpj_in_text(text)
                if cnpj:
                    return cnpj
            
            return None
            
        except Exception as e:
            logger.debug(f"CNPJ extraction failed: {e}")
            return None
    
    @staticmethod
    def _find_cnpj_in_text(text: str) -> Optional[str]:
        """
        Find CNPJ pattern in text.
        
        Args:
            text: Text to search
            
        Returns:
            CNPJ if found, None otherwise
        """
        # Standard CNPJ format: XX.XXX.XXX/XXXX-XX
        pattern = r'\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}'
        match = re.search(pattern, text)
        
        if match:
            return match.group(0)
        
        # Alternative: CNPJ without formatting: XXXXXXXXXXXXXX
        pattern_unformatted = r'\b\d{14}\b'
        match = re.search(pattern_unformatted, text)
        
        if match:
            # Format it
            cnpj = match.group(0)
            formatted = f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"
            return formatted
        
        return None
    
    @staticmethod
    def _extract_value(cells: list) -> Optional[str]:
        """
        Extract monetary value from table cells.
        
        Args:
            cells: List of table cells
            
        Returns:
            Value string (e.g., "R$ 1.234.567,89") or None
        """
        try:
            # Search all cells for currency pattern
            for cell in cells:
                text = cell.text.strip()
                value = CompanyRowParser._find_currency_in_text(text)
                if value:
                    return value
            
            return None
            
        except Exception as e:
            logger.debug(f"Value extraction failed: {e}")
            return None
    
    @staticmethod
    def _find_currency_in_text(text: str) -> Optional[str]:
        """
        Find Brazilian currency value in text.
        
        Patterns:
        - R$ 1.234.567,89
        - R$ 1234567,89
        - 1.234.567,89
        
        Args:
            text: Text to search
            
        Returns:
            Currency string or None
        """
        # Pattern: R$ followed by number with dots and comma
        pattern = r'R\$\s*[\d.,]+'
        match = re.search(pattern, text)
        
        if match:
            value = match.group(0).strip()
            # Normalize spacing
            value = re.sub(r'\s+', ' ', value)
            return value
        
        # Alternative: Just the number with comma
        pattern_number = r'\d{1,3}(?:\.\d{3})*,\d{2}'
        match = re.search(pattern_number, text)
        
        if match:
            return f"R$ {match.group(0)}"
        
        return None
    
    @staticmethod
    def _generate_company_id(name: str, cnpj: Optional[str]) -> str:
        """
        Generate unique company identifier.
        
        Strategy:
        1. Use CNPJ (without formatting) if available
        2. Otherwise, use normalized company name (first 30 chars)
        
        Args:
            name: Company name
            cnpj: Company CNPJ (optional)
            
        Returns:
            Unique identifier string
        """
        if cnpj:
            # Remove all non-digits from CNPJ
            cnpj_clean = re.sub(r'\D', '', cnpj)
            return cnpj_clean
        else:
            # Use normalized name
            normalized = re.sub(r'[^a-zA-Z0-9]', '', name.upper())
            return normalized[:30]
    
    @staticmethod
    def _clean_text(text: str) -> str:
        """
        Clean and normalize text.
        
        Args:
            text: Text to clean
            
        Returns:
            Cleaned text
        """
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text)
        
        # Remove leading/trailing whitespace
        text = text.strip()
        
        # Remove special characters at start/end
        text = text.strip('.-_')
        
        return text