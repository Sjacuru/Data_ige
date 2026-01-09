"""
test_scraper.py - Unit tests for the scraper module.
Run with: python -m pytest tests/test_scraper.py -v
"""

import pytest
import sys
sys.path.insert(0, '..')

from src.scraper import parse_row_data


class TestParseRowData:
    """Tests for the parse_row_data function."""
    
    def test_parse_valid_row(self):
        """Test parsing a valid row."""
        raw_rows = {
            "12.345.678/0001-99 - Empresa Teste LTDA 1.000,00 500,00 500,00 300,00 200,00"
        }
        
        result = parse_row_data(raw_rows)
        
        assert len(result) == 1
        assert result[0]["ID"] == "12.345.678/0001-99"
        assert result[0]["Company"] == "Empresa Teste LTDA"
    
    def test_skip_total_rows(self):
        """Test that total/summary rows are skipped."""
        raw_rows = {
            "TOTAL 10.000,00 5.000,00 5.000,00 3.000,00 2.000,00",
            "Total Geral 10.000,00 5.000,00 5.000,00 3.000,00 2.000,00"
        }
        
        result = parse_row_data(raw_rows)
        
        assert len(result) == 0
    
    def test_empty_input(self):
        """Test with empty input."""
        raw_rows = set()
        
        result = parse_row_data(raw_rows)
        
        assert result == []


class TestConfig:
    """Tests for configuration loading."""
    
    def test_config_imports(self):
        """Test that config can be imported."""
        from config import TIMEOUT_SECONDS, MAX_RETRIES, BASE_URL
        
        assert TIMEOUT_SECONDS > 0
        assert MAX_RETRIES > 0
        assert BASE_URL.startswith("http")


# Run basic tests when executed directly
if __name__ == "__main__":
    print("Running basic tests...")
    
    # Test 1
    test = TestParseRowData()
    try:
        test.test_parse_valid_row()
        print("✓ test_parse_valid_row passed")
    except AssertionError as e:
        print(f"✗ test_parse_valid_row failed: {e}")
    
    # Test 2
    try:
        test.test_skip_total_rows()
        print("✓ test_skip_total_rows passed")
    except AssertionError as e:
        print(f"✗ test_skip_total_rows failed: {e}")
    
    # Test 3
    try:
        test.test_empty_input()
        print("✓ test_empty_input passed")
    except AssertionError as e:
        print(f"✗ test_empty_input failed: {e}")
    
    print("\nTests completed!")