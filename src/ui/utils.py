import os  
import re  
import pandas as pd  
from pathlib import Path  
  
def format_file_size(size_mb: float) -> str:  
    """Format file size for display."""  
    if size_mb < 1:  
        return f"{size_mb * 1024:.0f} KB"  
    return f"{size_mb:.2f} MB"  
  
def get_status_emoji(success: bool) -> str:  
    """Get status emoji based on success."""  
    return "✅" if success else "❌"  
  
def normalize_id(value):  
    """Normalize ID/CNPJ for comparison (removes dots, dashes, etc)."""  
    if not value:  
        return ""  
    normalized = str(value).lower().strip()  
    normalized = re.sub(r'[.\-/\s]', '', normalized)  
    return normalized  
  
def load_analysis_summary(filepath: str) -> pd.DataFrame:  
    """Safely load the analysis summary CSV."""  
    if not os.path.exists(filepath):  
        return pd.DataFrame()  
    try:  
        return pd.read_csv(filepath)  
    except Exception:  
        return pd.DataFrame()  