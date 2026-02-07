"""
Contract_analisys/cached_contract_extractor.py - Cached version of contract extractor

Add this to your contract_extractor.py or use as a wrapper.

This version checks cache BEFORE doing expensive OCR and AI calls.
"""

from pathlib import Path
from typing import Dict, Optional
from datetime import datetime

# Import original functions
from Contract_analisys.contract_extractor import (
    extract_text_from_pdf as _original_extract_text,
    analyze_contract_with_ai as _original_analyze_ai,
    process_single_contract as _original_process_single,
)

# Import cache
from core.cache import ContractCache

import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global cache instance
_cache = ContractCache()


def process_single_contract_cached(pdf_path: str, processo_id: str = "") -> Dict:
    """
    Process a single contract with caching.
    
    COST SAVINGS:
    - ✅ Skips OCR if already processed (saves 30-60 seconds)
    - ✅ Skips AI call if already processed (saves API costs)
    - ✅ Returns cached result instantly
    
    Args:
        pdf_path: Path to PDF file
        processo_id: Optional processo identifier
        
    Returns:
        Dict with all extraction and analysis results
    """
    logging.info(f"\n{'='*60}")
    logging.info(f"Processing: {Path(pdf_path).name}")
    logging.info(f"{'='*60}")
    
    # ═══════════════════════════════════════════════════════════
    # STEP 1: Check cache first
    # ═══════════════════════════════════════════════════════════
    if _cache.has_extraction(pdf_path):
        logging.info("💰 USING CACHED RESULT (No OCR, No AI call, No cost!)")
        cached = _cache.get_extraction(pdf_path)
        
        # Add cache indicator
        if cached:
            cached['from_cache'] = True
            cached['cache_hit_at'] = datetime.now().isoformat()
            logging.info(f"   ✓ Loaded from cache (saved ~$0.01-0.05)")
            return cached
    
    # ═══════════════════════════════════════════════════════════
    # STEP 2: Not in cache - process normally
    # ═══════════════════════════════════════════════════════════
    logging.info("🔄 Processing fresh (will cache result)...")
    
    result = _original_process_single(pdf_path, processo_id)
    
    # ═══════════════════════════════════════════════════════════
    # STEP 3: Save to cache for next time
    # ═══════════════════════════════════════════════════════════
    if result and result.get('success'):
        result['from_cache'] = False
        _cache.save_extraction(pdf_path, result)
        logging.info("   💾 Saved to cache for next time")
    
    return result


def check_conformity_cached(contract_data: Dict, processo: str = None) -> Dict:
    """
    Check conformity with caching.
    
    COST SAVINGS:
    - ✅ Skips DOWeb scraping if already checked (saves 15-30 seconds)
    - ✅ Skips PDF downloads if already checked
    - ✅ Skips AI verification if already checked
    
    Args:
        contract_data: Extracted contract data
        processo: Processo number (auto-detected if not provided)
        
    Returns:
        ConformityResult
    """
    # Extract processo if not provided
    if not processo:
        processo = (
            contract_data.get('processo_administrativo') or
            contract_data.get('numero_processo') or
            contract_data.get('processo')
        )
    
    if not processo:
        return {'error': 'No processo number found', 'from_cache': False}
    
    # ═══════════════════════════════════════════════════════════
    # STEP 1: Check cache
    # ═══════════════════════════════════════════════════════════
    if _cache.has_conformity(processo):
        logging.info(f"💰 USING CACHED CONFORMITY (No scraping, No cost!)")
        cached = _cache.get_conformity(processo)
        
        if cached:
            cached['from_cache'] = True
            cached['cache_hit_at'] = datetime.now().isoformat()
            logging.info(f"   ✓ Loaded conformity from cache")
            return cached
    
    # ═══════════════════════════════════════════════════════════
    # STEP 2: Not in cache - check normally
    # ═══════════════════════════════════════════════════════════
    logging.info(f"🔄 Checking conformity fresh (will cache result)...")
    
    from conformity.integration import check_publication_conformity
    
    result = check_publication_conformity(
        contract_data=contract_data,
        processo=processo,
        headless=True
    )
    
    # ═══════════════════════════════════════════════════════════
    # STEP 3: Save to cache
    # ═══════════════════════════════════════════════════════════
    result_dict = result.to_dict() if hasattr(result, 'to_dict') else result
    result_dict['from_cache'] = False
    _cache.save_conformity(processo, result_dict)
    logging.info("   💾 Saved conformity to cache")
    
    return result


def get_cache_stats() -> Dict:
    """Get cache statistics for display in UI."""
    return _cache.get_cache_stats()


def clear_cache(cache_type: str = "all") -> int:
    """
    Clear cache.
    
    Args:
        cache_type: "all", "extraction", or "conformity"
        
    Returns:
        Number of files cleared
    """
    if cache_type == "extraction":
        return _cache.clear_extraction_cache()
    elif cache_type == "conformity":
        return _cache.clear_conformity_cache()
    else:
        return _cache.clear_all_cache()


# =========================================================================
# USAGE EXAMPLES
# =========================================================================

"""
# In your Streamlit app or main script:

from Contract_analisys.cached_contract_extractor import (
    process_single_contract_cached,
    check_conformity_cached,
    get_cache_stats,
    clear_cache
)

# Process with caching (automatically uses cache if available)
result = process_single_contract_cached("path/to/contract.pdf")

# Check conformity with caching
conformity = check_conformity_cached(result['ai_extraction'])

# Show cache stats in UI
stats = get_cache_stats()
st.write(f"Cached extractions: {stats['extraction_count']}")
st.write(f"Cached conformity checks: {stats['conformity_count']}")
st.write(f"Total cache size: {stats['total_size_mb']:.2f} MB")

# Clear cache button
if st.button("Clear Cache"):
    cleared = clear_cache()
    st.success(f"Cleared {cleared} cache files")
"""