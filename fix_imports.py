"""
Import Fixer Script
Automatically updates all import statements to match the new project structure
"""

import os
import re
from pathlib import Path

# Import mapping: old import -> new import
IMPORT_MAPPINGS = {
    # Domain models
    r'from conformity\.models\.publication import': 'from domain.models.publication import',
    r'from conformity\.models\.conformity_result import': 'from domain.models.conformity_result import',
    r'from conformity\.models import': 'from domain.models import',
    
    # Domain services
    r'from conformity\.analyzer\.publication_conformity import': 'from domain.services.conformity_checker import',
    r'from Contract_analisys\.text_preprocessor import': 'from domain.services.text_normalizer import',
    
    # Infrastructure - Scrapers
    r'from src\.scraper import': 'from infrastructure.scrapers.contasrio.scraper import',
    r'from src\.downloader import': 'from infrastructure.scrapers.contasrio.downloader import',
    r'from src\.parser import': 'from infrastructure.scrapers.contasrio.parser import',
    r'from conformity\.scraper\.doweb_scraper import': 'from infrastructure.scrapers.doweb.scraper import',
    r'from conformity\.scraper\.doweb_extractor import': 'from infrastructure.scrapers.doweb.extractor import',
    
    # Infrastructure - Extractors
    r'from Contract_analisys\.contract_extractor import': 'from infrastructure.extractors.contract_extractor import',
    r'from Contract_analisys\.cached_contract_extractor import': 'from infrastructure.extractors.cached_contract_extractor import',
    r'from src\.document_extractor import': 'from infrastructure.extractors.document_extractor import',
    
    # Infrastructure - Web utilities
    r'from core\.driver import': 'from infrastructure.web.driver import',
    r'from core\.captcha import': 'from infrastructure.web.captcha import',
    r'from core\.navigation import': 'from infrastructure.web.navigation import',
    r'from core\.cache import': 'from infrastructure.persistence.cache import',
    r'from core import': 'from infrastructure.web import',
    
    # Application
    r'from conformity\.integration import': 'from application.workflows.conformity_workflow import',
}


def fix_imports_in_file(filepath):
    """Fix imports in a single Python file"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        modified = False
        
        # Apply each import mapping
        for old_pattern, new_import in IMPORT_MAPPINGS.items():
            if re.search(old_pattern, content):
                content = re.sub(old_pattern, new_import, content)
                modified = True
        
        # Write back if modified
        if modified:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"✓ Fixed: {filepath}")
            return True
        
        return False
        
    except Exception as e:
        print(f"✗ Error fixing {filepath}: {e}")
        return False


def fix_all_imports(root_dir='.'):
    """Fix imports in all Python files in the project"""
    root_path = Path(root_dir)
    
    # Directories to scan
    scan_dirs = [
        'domain',
        'infrastructure',
        'application',
        'tests_new',
    ]
    
    fixed_count = 0
    total_count = 0
    
    print("=" * 60)
    print("FIXING IMPORTS IN NEW STRUCTURE")
    print("=" * 60)
    print()
    
    for scan_dir in scan_dirs:
        dir_path = root_path / scan_dir
        if not dir_path.exists():
            continue
        
        print(f"\nScanning: {scan_dir}/")
        print("-" * 60)
        
        # Find all .py files
        for py_file in dir_path.rglob('*.py'):
            if '__pycache__' in str(py_file):
                continue
            
            total_count += 1
            if fix_imports_in_file(py_file):
                fixed_count += 1
    
    print()
    print("=" * 60)
    print(f"SUMMARY: Fixed {fixed_count} out of {total_count} files")
    print("=" * 60)
    print()
    print("Next steps:")
    print("1. Review the changes")
    print("2. Test your application: python application/main.py")
    print("3. Run tests: pytest tests_new/")
    print()


if __name__ == '__main__':
    fix_all_imports()
