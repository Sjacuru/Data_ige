"""
JSON storage utilities.
Handles saving and loading JSON files with proper error handling.
"""
import json
import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class JSONStorage:
    """
    Handles saving and loading JSON files.
    """
    
    @staticmethod
    def save(data: Any, filepath: str | Path, indent: int = 2) -> bool:
        """
        Save data to JSON file.
        
        Args:
            data: Data to save (must be JSON-serializable)
            filepath: Path to save file
            indent: JSON indentation (default: 2)
            
        Returns:
            True if saved successfully, False otherwise
        """
        try:
            filepath = Path(filepath)
            
            # Create parent directories if they don't exist
            filepath.parent.mkdir(parents=True, exist_ok=True)
            
            # Write JSON file
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=indent, ensure_ascii=False)
            
            # Get file size
            file_size = filepath.stat().st_size
            logger.info(f"✓ Saved: {filepath} ({file_size:,} bytes)")
            return True
            
        except TypeError as e:
            logger.error(f"✗ Data is not JSON-serializable: {e}")
            return False
        except Exception as e:
            logger.error(f"✗ Failed to save {filepath}: {e}")
            return False
    
    @staticmethod
    def load(filepath: str | Path) -> Optional[Any]:
        """
        Load data from JSON file.
        
        Args:
            filepath: Path to load from
            
        Returns:
            Loaded data or None if failed
        """
        try:
            filepath = Path(filepath)
            
            if not filepath.exists():
                logger.warning(f"⚠ File not found: {filepath}")
                return None
            
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            file_size = filepath.stat().st_size
            logger.info(f"✓ Loaded: {filepath} ({file_size:,} bytes)")
            return data
            
        except json.JSONDecodeError as e:
            logger.error(f"✗ Invalid JSON in {filepath}: {e}")
            return None
        except Exception as e:
            logger.error(f"✗ Failed to load {filepath}: {e}")
            return None
    
    @staticmethod
    def exists(filepath: str | Path) -> bool:
        """
        Check if file exists.
        
        Args:
            filepath: Path to check
            
        Returns:
            True if file exists, False otherwise
        """
        return Path(filepath).exists()
    
    @staticmethod
    def delete(filepath: str | Path) -> bool:
        """
        Delete file if it exists.
        
        Args:
            filepath: Path to file to delete
            
        Returns:
            True if deleted (or didn't exist), False if error
        """
        try:
            filepath = Path(filepath)
            if filepath.exists():
                filepath.unlink()
                logger.info(f"✓ Deleted: {filepath}")
            return True
        except Exception as e:
            logger.error(f"✗ Failed to delete {filepath}: {e}")
            return False