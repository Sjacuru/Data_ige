"""
conformity - Contract conformity analysis module.

Submodules:
- models: Data models for publications and criteria
- scraper: Web scrapers for external data sources
"""

from conformity.models.publication import PublicationResult
from conformity.scraper.doweb_scraper import search_and_extract_publication

__all__ = [
    "PublicationResult",
    "search_and_extract_publication",
]