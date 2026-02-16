"""
Integration tests for Stage 1 Discovery workflow.

These tests interact with the real ContasRio portal and require:
- Internet connection
- Chrome browser
- Actual portal access
"""
import pytest
from pathlib import Path
import json

from application.workflows.stage1_discovery import run_stage1_discovery
from infrastructure.persistence.json_storage import JSONStorage
from domain.models.processo_link import DiscoveryResult


class TestStage1Discovery:
    """Integration tests for Stage 1 discovery."""
    
    def test_full_discovery_workflow(self):
        """
        Test complete Stage 1 workflow.
        
        This is a long-running test that:
        1. Runs complete discovery
        2. Validates results
        3. Checks output files
        """
        # Run discovery
        result = run_stage1_discovery(headless=True)
        
        # Basic validations
        assert isinstance(result, DiscoveryResult), "Should return DiscoveryResult"
        assert result.total_processos > 0, "Should find at least some processos"
        assert result.total_companies > 0, "Should find at least some companies"
        
        print(f"\n✓ Discovery found:")
        print(f"  - {result.total_companies} companies")
        print(f"  - {result.total_processos} processos")
        
        # Validate processos
        for processo in result.processos[:5]:  # Check first 5
            assert processo.processo_id, "Processo should have ID"
            assert processo.url, "Processo should have URL"
            assert processo.company_name, "Processo should have company name"
            print(f"  ✓ {processo.processo_id}: {processo.company_name}")
        
        # Validate companies
        for company in result.companies[:5]:  # Check first 5
            assert company.company_name, "Company should have name"
            assert company.total_contracts > 0, "Company should have contracts"
            print(f"  ✓ {company.company_name}: {company.total_contracts} contracts")
    
    def test_output_files_created(self):
        """Test that all expected output files are created."""
        
        # Expected files
        expected_files = [
            "data/discovery/processo_links.json",
            "data/discovery/companies.json",
            "data/discovery/discovery_summary.json"
        ]
        
        for filepath in expected_files:
            path = Path(filepath)
            assert path.exists(), f"File should exist: {filepath}"
            
            # Validate JSON is loadable
            data = JSONStorage.load(path)
            assert data is not None, f"File should contain valid JSON: {filepath}"
            
            print(f"  ✓ {filepath} ({path.stat().st_size:,} bytes)")
    
    def test_processo_links_structure(self):
        """Test structure of processo_links.json."""
        
        filepath = Path("data/discovery/processo_links.json")
        data = JSONStorage.load(filepath)
        
        # Check top-level structure
        assert "discovery_date" in data
        assert "total_companies" in data
        assert "total_processos" in data
        assert "companies" in data
        assert "processos" in data
        
        # Check processos structure
        if len(data["processos"]) > 0:
            processo = data["processos"][0]
            assert "processo_id" in processo
            assert "url" in processo
            assert "company_name" in processo
            assert "discovery_path" in processo
            assert "discovered_at" in processo
            
            print(f"  ✓ Processo structure valid")
            print(f"  Sample: {processo['processo_id']}")
    
    def test_companies_structure(self):
        """Test structure of companies.json."""
        
        filepath = Path("data/discovery/companies.json")
        data = JSONStorage.load(filepath)
        
        # Check top-level structure
        assert "total" in data
        assert "discovery_date" in data
        assert "companies" in data
        
        # Check company structure
        if len(data["companies"]) > 0:
            company = data["companies"][0]
            assert "company_id" in company
            assert "company_name" in company
            assert "total_contracts" in company
            
            print(f"  ✓ Company structure valid")
            print(f"  Sample: {company['company_name']} ({company['total_contracts']} contracts)")
    
    def test_data_consistency(self):
        """Test consistency between different output files."""
        
        # Load files
        processo_links = JSONStorage.load("data/discovery/processo_links.json")
        companies = JSONStorage.load("data/discovery/companies.json")
        summary = JSONStorage.load("data/discovery/discovery_summary.json")
        
        # Check totals match
        assert processo_links["total_processos"] == len(processo_links["processos"])
        assert processo_links["total_companies"] == companies["total"]
        assert processo_links["total_processos"] == summary["total_processos"]
        assert processo_links["total_companies"] == summary["total_companies"]
        
        print(f"  ✓ Data consistency verified")
        print(f"  - Total processos: {summary['total_processos']}")
        print(f"  - Total companies: {summary['total_companies']}")


# Pytest fixtures
@pytest.fixture(scope="session")
def discovery_result():
    """
    Run discovery once for all tests.
    This is a session-scoped fixture to avoid running discovery multiple times.
    """
    return run_stage1_discovery(headless=True)


# Manual test runner (for running without pytest)
def run_manual_tests():
    """Run tests manually without pytest."""
    print("\n" + "=" * 70)
    print("RUNNING INTEGRATION TESTS - STAGE 1 DISCOVERY")
    print("=" * 70)
    
    tester = TestStage1Discovery()
    
    try:
        print("\n[1/5] Testing full discovery workflow...")
        tester.test_full_discovery_workflow()
        print("✓ PASSED")
    except AssertionError as e:
        print(f"✗ FAILED: {e}")
        return False
    
    try:
        print("\n[2/5] Testing output files created...")
        tester.test_output_files_created()
        print("✓ PASSED")
    except AssertionError as e:
        print(f"✗ FAILED: {e}")
        return False
    
    try:
        print("\n[3/5] Testing processo links structure...")
        tester.test_processo_links_structure()
        print("✓ PASSED")
    except AssertionError as e:
        print(f"✗ FAILED: {e}")
        return False
    
    try:
        print("\n[4/5] Testing companies structure...")
        tester.test_companies_structure()
        print("✓ PASSED")
    except AssertionError as e:
        print(f"✗ FAILED: {e}")
        return False
    
    try:
        print("\n[5/5] Testing data consistency...")
        tester.test_data_consistency()
        print("✓ PASSED")
    except AssertionError as e:
        print(f"✗ FAILED: {e}")
        return False
    
    print("\n" + "=" * 70)
    print("✅ ALL INTEGRATION TESTS PASSED")
    print("=" * 70)
    return True


if __name__ == "__main__":
    success = run_manual_tests()
    exit(0 if success else 1)