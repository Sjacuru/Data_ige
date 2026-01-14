"""
process_saved_links.py - Process previously saved company links.
Run this after main.py has collected and saved the links.

Usage: python process_saved_links.py
"""

import sys
sys.path.insert(0, 'src')

from src.reporter import load_companies_with_links
from src.downloader import download_document

import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    # Load previously saved data
    companies = load_companies_with_links()
    
    logging.info(f"\n📋 {len(companies)} empresas carregadas\n")
    
    for company in companies:
        logging.info(f"ID: {company['ID']}")
        logging.info(f"   Empresa: {company['Company']}")
        logging.info(f"   URL: {company.get('document_url', 'N/A')}")
        logging.info()
        
        # Uncomment to download:
        # if company.get('document_url'):
        #     download_document(company['document_url'])


if __name__ == "__main__":
    main()