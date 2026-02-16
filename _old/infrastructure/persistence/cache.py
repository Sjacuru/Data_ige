"""
core/cache.py - Caching system to avoid re-processing contracts

This saves money by:
1. Not re-running OCR on already processed PDFs
2. Not re-calling Groq API for already extracted data
3. Not re-scraping DOWeb for already checked publications
4. Storing results in local JSON files

Usage:
    from infrastructure.persistence.cache import ContractCache
    
    cache = ContractCache()
    
    # Check if already processed
    if cache.has_extraction(pdf_path):
        result = cache.get_extraction(pdf_path)
    else:
        # Process and save
        result = extract_and_analyze(pdf_path)
        cache.save_extraction(pdf_path, result)
"""

import json
import hashlib
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# =========================================================================
# CONFIGURATION
# =========================================================================

CACHE_DIR = Path("data/cache")
EXTRACTION_CACHE_DIR = CACHE_DIR / "extractions"
CONFORMITY_CACHE_DIR = CACHE_DIR / "conformity"

# Ensure cache directories exist
EXTRACTION_CACHE_DIR.mkdir(parents=True, exist_ok=True)
CONFORMITY_CACHE_DIR.mkdir(parents=True, exist_ok=True)


# =========================================================================
# UTILITY FUNCTIONS
# =========================================================================

def get_file_hash(file_path: str) -> str:
    """
    Generate MD5 hash of a file for caching.
    
    This ensures we detect if the file has changed.
    """
    hash_md5 = hashlib.md5()
    
    with open(file_path, "rb") as f:
        # Read in chunks to handle large files
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    
    return hash_md5.hexdigest()


def sanitize_filename(text: str) -> str:
    """Create a safe filename from text."""
    import re
    # Remove invalid characters
    safe = re.sub(r'[<>:"/\\|?*]', '_', text)
    # Limit length
    return safe[:100]


# =========================================================================
# CACHE CLASS
# =========================================================================

class ContractCache:
    """
    Manages caching of extraction and conformity results.
    
    Cache structure:
    data/cache/
    ├── extractions/
    │   ├── abc123_TURCAP202500477.json     # Extraction result
    │   └── def456_SMEPRO202512345.json
    └── conformity/
        ├── TUR-PRO-2025-00350.json         # Conformity result
        └── SME-PRO-2025-12345.json
    """
    
    def __init__(self):
        self.extraction_dir = EXTRACTION_CACHE_DIR
        self.conformity_dir = CONFORMITY_CACHE_DIR
    
    # =====================================================================
    # EXTRACTION CACHE
    # =====================================================================
    
    def get_extraction_cache_path(self, pdf_path: str) -> Path:
        """Get cache file path for a PDF extraction."""
        file_hash = get_file_hash(pdf_path)[:8]
        filename = Path(pdf_path).stem
        cache_filename = f"{file_hash}_{sanitize_filename(filename)}.json"
        return self.extraction_dir / cache_filename
    
    def has_extraction(self, pdf_path: str) -> bool:
        """Check if extraction result is cached."""
        cache_path = self.get_extraction_cache_path(pdf_path)
        exists = cache_path.exists()
        
        if exists:
            logging.info(f"   💾 Cache hit: {Path(pdf_path).name}")
        
        return exists
    
    def get_extraction(self, pdf_path: str) -> Optional[Dict]:
        """Retrieve cached extraction result."""
        cache_path = self.get_extraction_cache_path(pdf_path)
        
        if not cache_path.exists():
            return None
        
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            logging.info(f"   ✓ Loaded from cache: {cache_path.name}")
            return data
            
        except Exception as e:
            logging.error(f"   ✗ Cache read error: {e}")
            return None
    
    def save_extraction(self, pdf_path: str, result: Dict) -> bool:
        """Save extraction result to cache."""
        cache_path = self.get_extraction_cache_path(pdf_path)
        
        try:
            # Add cache metadata
            result['_cache_metadata'] = {
                'cached_at': datetime.now().isoformat(),
                'pdf_path': str(pdf_path),
                'file_hash': get_file_hash(pdf_path),
            }
            
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            
            logging.info(f"   💾 Saved to cache: {cache_path.name}")
            return True
            
        except Exception as e:
            logging.error(f"   ✗ Cache write error: {e}")
            return False
    
    # =====================================================================
    # CONFORMITY CACHE
    # =====================================================================
    
    def get_conformity_cache_path(self, processo: str) -> Path:
        """Get cache file path for a conformity check."""
        safe_processo = sanitize_filename(processo)
        cache_filename = f"{safe_processo}.json"
        return self.conformity_dir / cache_filename
    
    def has_conformity(self, processo: str) -> bool:
        """Check if conformity result is cached."""
        cache_path = self.get_conformity_cache_path(processo)
        exists = cache_path.exists()
        
        if exists:
            logging.info(f"   💾 Conformity cache hit: {processo}")
        
        return exists
    
    def get_conformity(self, processo: str) -> Optional[Dict]:
        """Retrieve cached conformity result."""
        cache_path = self.get_conformity_cache_path(processo)
        
        if not cache_path.exists():
            return None
        
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            logging.info(f"   ✓ Conformity loaded from cache: {processo}")
            return data
            
        except Exception as e:
            logging.error(f"   ✗ Conformity cache read error: {e}")
            return None
    
    def save_conformity(self, processo: str, result: Dict) -> bool:
        """Save conformity result to cache."""
        cache_path = self.get_conformity_cache_path(processo)
        
        try:
            # Add cache metadata
            if isinstance(result, dict):
                result['_cache_metadata'] = {
                    'cached_at': datetime.now().isoformat(),
                    'processo': processo,
                }
            
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            
            logging.info(f"   💾 Conformity saved to cache: {processo}")
            return True
            
        except Exception as e:
            logging.error(f"   ✗ Conformity cache write error: {e}")
            return False
    
    # =====================================================================
    # CACHE MANAGEMENT
    # =====================================================================
    
    def clear_extraction_cache(self) -> int:
        """Clear all extraction cache files."""
        count = 0
        for cache_file in self.extraction_dir.glob("*.json"):
            cache_file.unlink()
            count += 1
        
        logging.info(f"   🗑️ Cleared {count} extraction cache files")
        return count
    
    def clear_conformity_cache(self) -> int:
        """Clear all conformity cache files."""
        count = 0
        for cache_file in self.conformity_dir.glob("*.json"):
            cache_file.unlink()
            count += 1
        
        logging.info(f"   🗑️ Cleared {count} conformity cache files")
        return count
    
    def clear_all_cache(self) -> int:
        """Clear all cache files."""
        count = self.clear_extraction_cache()
        count += self.clear_conformity_cache()
        return count
    
    def get_cache_stats(self) -> Dict:
        """Get cache statistics."""
        extraction_files = list(self.extraction_dir.glob("*.json"))
        conformity_files = list(self.conformity_dir.glob("*.json"))
        
        extraction_size = sum(f.stat().st_size for f in extraction_files)
        conformity_size = sum(f.stat().st_size for f in conformity_files)
        
        return {
            'extraction_count': len(extraction_files),
            'conformity_count': len(conformity_files),
            'extraction_size_mb': extraction_size / (1024 * 1024),
            'conformity_size_mb': conformity_size / (1024 * 1024),
            'total_size_mb': (extraction_size + conformity_size) / (1024 * 1024),
        }


# =========================================================================
# INTEGRATION EXAMPLE
# =========================================================================

def cached_contract_extraction(pdf_path: str, cache: ContractCache = None) -> Dict:
    """
    Example: Extract contract with caching.
    
    This wrapper checks cache first, only processes if needed.
    """
    if cache is None:
        cache = ContractCache()
    
    # Check cache
    if cache.has_extraction(pdf_path):
        logging.info(f"   📦 Using cached extraction")
        return cache.get_extraction(pdf_path)
    
    # Not in cache - process it
    logging.info(f"   🔄 Processing {Path(pdf_path).name}...")
    
    from infrastructure.extractors.contract_extractor import extract_text_from_pdf, analyze_contract_with_ai
    
    # Extract text
    extraction = extract_text_from_pdf(pdf_path)
    
    if not extraction["success"]:
        return extraction
    
    # AI analysis
    ai_result = analyze_contract_with_ai(extraction["full_text"])
    
    # Combine results
    result = {
        **extraction,
        'ai_extraction': ai_result,
    }
    
    # Save to cache
    cache.save_extraction(pdf_path, result)
    
    return result


def cached_conformity_check(contract_data: Dict, processo: Optional[str] = None, cache: Optional[ContractCache] = None) -> Dict:
    """
    Example: Conformity check with caching.
    """
    if cache is None:
        cache = ContractCache()
    
    # Extract processo if not provided
    if not processo:
        processo = (
            contract_data.get('processo_administrativo') or
            contract_data.get('numero_processo') or
            contract_data.get('processo')
        )
    
    if not processo:
        return {'error': 'No processo number found'}
    
    # Check cache
    if cache.has_conformity(processo):
        logging.info(f"   📦 Using cached conformity check")
        cached_result = cache.get_conformity(processo)
        # Convert dict back to ConformityResult if needed
        return cached_result
    
    # Not in cache - check it
    logging.info(f"   🔄 Checking conformity for {processo}...")
    
    from application.workflows.conformity_workflow import check_publication_conformity
    
    result = check_publication_conformity(
        contract_data=contract_data,
        processo=processo,
        headless=True
    )
    
    # Save to cache
    cache.save_conformity(processo, result.to_dict() if hasattr(result, 'to_dict') else result)
    
    return result


# =========================================================================
# CLI FOR CACHE MANAGEMENT
# =========================================================================

if __name__ == "__main__":
    import sys
    
    cache = ContractCache()
    
    if len(sys.argv) < 2:
        print("Cache Management Tool")
        print("\nUsage:")
        print("  python core/cache.py stats    # Show cache statistics")
        print("  python core/cache.py clear    # Clear all cache")
        print("  python core/cache.py clear-extraction  # Clear extraction cache only")
        print("  python core/cache.py clear-conformity  # Clear conformity cache only")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "stats":
        stats = cache.get_cache_stats()
        print("\n📊 Cache Statistics:")
        print(f"   Extractions: {stats['extraction_count']} files ({stats['extraction_size_mb']:.2f} MB)")
        print(f"   Conformity: {stats['conformity_count']} files ({stats['conformity_size_mb']:.2f} MB)")
        print(f"   Total: {stats['total_size_mb']:.2f} MB")
    
    elif command == "clear":
        count = cache.clear_all_cache()
        print(f"\n🗑️ Cleared {count} cache files")
    
    elif command == "clear-extraction":
        count = cache.clear_extraction_cache()
        print(f"\n🗑️ Cleared {count} extraction cache files")
    
    elif command == "clear-conformity":
        count = cache.clear_conformity_cache()
        print(f"\n🗑️ Cleared {count} conformity cache files")
    
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)