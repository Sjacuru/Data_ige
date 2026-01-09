"""
process_saved_links.py - Process previously saved company links.
Run this after main.py has collected and saved the links.

Usage: python process_saved_links.py
"""

import sys
sys.path.insert(0, 'src')

from src.reporter import load_companies_with_links
from src.downloader import download_document


def main():
    # Load previously saved data
    companies = load_companies_with_links()
    
    print(f"\n📋 {len(companies)} empresas carregadas\n")
    
    for company in companies:
        print(f"ID: {company['ID']}")
        print(f"   Empresa: {company['Company']}")
        print(f"   URL: {company.get('document_url', 'N/A')}")
        print()
        
        # Uncomment to download:
        # if company.get('document_url'):
        #     download_document(company['document_url'])


if __name__ == "__main__":
    main()