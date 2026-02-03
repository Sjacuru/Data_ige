"""
test_parser.py - Pytest tests for CompanyRowParser

Location: NEW_DATA_IGE/tests/domain/test_parser.py

Run with: pytest NEW_DATA_IGE/tests/domain/test_parser.py -v

This tests the parser WITHOUT needing Selenium or a browser!
"""

import pytest
from New_Data_ige.domain.parsing.company_row_parser import CompanyRowParser


class TestCompanyRowParser:
    """Test suite for CompanyRowParser - No Selenium needed!"""
    
    @pytest.fixture
    def parser(self):
        """Create a parser for each test"""
        return CompanyRowParser()
    
    # ═══════════════════════════════════════════════════════════
    # VALID ROWS (should parse successfully)
    # ═══════════════════════════════════════════════════════════
    
    def test_parse_perfect_row(self, parser):
        """Test a perfect row with CNPJ"""
        row = "12.345.678/0001-99 - Empresa Teste LTDA 1.000,00 500,00 500,00 300,00 200,00"
        
        result = parser.parse(row)
        
        assert result is not None
        assert result.id == "12.345.678/0001-99"
        assert result.name == "Empresa Teste LTDA"
        assert result.total_contratado == "1.000,00"
        assert result.pago == "200,00"
    
    def test_parse_negative_values(self, parser):
        """Test rows with negative monetary values"""
        row = "98.765.432/0001-11 - Empresa Negativa -1.500,00 2.000,00 -500,00 1.000,00 900,00"
        
        result = parser.parse(row)
        
        assert result is not None
        assert result.total_contratado == "-1.500,00"
        assert result.saldo_executar == "-500,00"
    
    def test_parse_cpf_identifier(self, parser):
        """Test rows with CPF instead of CNPJ"""
        row = "123.456.789-00 - Pessoa Física 5.000,00 2.500,00 2.500,00 1.000,00 800,00"
        
        result = parser.parse(row)
        
        assert result is not None
        assert result.id == "123.456.789-00"
        assert "Pessoa Física" in result.name
    
    def test_parse_complex_name(self, parser):
        """Test company names with special characters"""
        row = "11.222.333/0001-44 - ACME Corp. & Cia LTDA - EPP 10.000,00 5.000,00 5.000,00 3.000,00 2.000,00"
        
        result = parser.parse(row)
        
        assert result is not None
        assert "ACME" in result.name
    
    # ═══════════════════════════════════════════════════════════
    # INVALID ROWS (should return None)
    # ═══════════════════════════════════════════════════════════
    
    def test_parse_empty_row(self, parser):
        """Empty rows should return None"""
        assert parser.parse("") is None
        assert parser.parse("   ") is None
    
    def test_parse_total_row(self, parser):
        """Summary rows with 'TOTAL' should return None"""
        assert parser.parse("TOTAL 100.000,00 50.000,00 50.000,00 30.000,00 20.000,00") is None
    
    def test_parse_numbers_only(self, parser):
        """Rows with only numbers should return None"""
        assert parser.parse("1.000,00 500,00 500,00 300,00 200,00") is None
    
    def test_parse_insufficient_values(self, parser):
        """Rows with fewer than 5 values should return None"""
        assert parser.parse("12.345.678/0001-99 - Empresa X 1.000,00 500,00") is None
    
    # ═══════════════════════════════════════════════════════════
    # EDGE CASES FROM YOUR REAL CODE
    # ═══════════════════════════════════════════════════════════
    
    def test_normalized_id(self, parser):
        """Test the normalized_id property"""
        row = "12.345.678/0001-99 - Empresa X 1.000,00 500,00 500,00 300,00 200,00"
        
        result = parser.parse(row)
        
        assert result.normalized_id == "12345678000199"
    
    def test_to_dict_export(self, parser):
        """Test converting to dictionary for CSV export"""
        row = "12.345.678/0001-99 - Empresa X 1.000,00 500,00 500,00 300,00 200,00"
        
        result = parser.parse(row)
        data_dict = result.to_dict()
        
        assert "ID" in data_dict
        assert "Company" in data_dict
        assert data_dict["Total Contratado"] == "1.000,00"