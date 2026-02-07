"""
conformity.scraper - Web scrapers for external data sources.
"""

from .doweb_scraper import search_and_extract_publication, search_multiple_processos
from .doweb_extractor import extract_publication_from_pdf

__all__ = [
    "search_and_extract_publication",
    "search_multiple_processos", 
    "extract_publication_from_pdf",
]