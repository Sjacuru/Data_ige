"""
downloader.py - Document download functionality.
Downloads PDFs and other documents from URLs.
"""

import os
import requests
from datetime import datetime
from config import DATA_RAW_PATH


def download_document(url, filename=None):
    """
    Download a document from a URL.
    
    Args:
        url: URL of the document
        filename: Optional filename, auto-generated if not provided
        
    Returns:
        Path to downloaded file, or None if failed
    """
    try:
        print(f"\n→ Baixando documento de: {url[:50]}...")
        
        # Generate filename if not provided
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            # Try to get filename from URL
            url_filename = url.split("/")[-1].split("?")[0]
            if url_filename and "." in url_filename:
                filename = f"{timestamp}_{url_filename}"
            else:
                filename = f"{timestamp}_document.pdf"
        
        # Ensure download directory exists
        os.makedirs(DATA_RAW_PATH, exist_ok=True)
        
        # Full path
        filepath = os.path.join(DATA_RAW_PATH, filename)
        
        # Download with requests
        response = requests.get(url, stream=True, timeout=60)
        response.raise_for_status()
        
        # Save file
        with open(filepath, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        file_size = os.path.getsize(filepath)
        print(f"✓ Arquivo salvo: {filepath} ({file_size:,} bytes)")
        
        return filepath
        
    except Exception as e:
        print(f"✗ Erro ao baixar documento: {e}")
        return None


def should_download(analysis_result):
    """
    Determine if a document should be downloaded based on analysis flags.
    
    Args:
        analysis_result: Dictionary with analysis flags
        
    Returns:
        True if document should be downloaded
    """
    # Add your flag logic here
    flags_that_require_download = [
        "high_value",
        "irregular",
        "needs_review",
        "expired"
    ]
    
    for flag in flags_that_require_download:
        if analysis_result.get(flag, False):
            return True
    
    return False