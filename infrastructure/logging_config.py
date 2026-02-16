"""
Logging configuration for the application.
Sets up file and console logging with appropriate formatting.
"""
import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional

from config.settings import LOGS_DIR


def setup_logging(
    stage_name: str = "discovery",
    log_level: int = logging.INFO,
    console_level: Optional[int] = None
) -> str:
    """
    Configure logging for the application.
    
    Creates both file and console handlers with appropriate formatting.
    
    Args:
        stage_name: Name of the stage/process (used in filename)
        log_level: Logging level for file output
        console_level: Logging level for console (defaults to log_level)
        
    Returns:
        Path to the created log file
    """
    # Use same level for console if not specified
    if console_level is None:
        console_level = log_level
    
    # Create logs directory
    logs_dir = Path(LOGS_DIR)
    logs_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate log filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = logs_dir / f"{stage_name}_{timestamp}.log"
    
    # Create formatters
    detailed_formatter = logging.Formatter(
        fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    console_formatter = logging.Formatter(
        fmt='%(levelname)s - %(message)s'
    )
    
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # Capture all levels
    
    # Remove existing handlers to avoid duplicates
    root_logger.handlers = []
    
    # File handler (detailed logging)
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(log_level)
    file_handler.setFormatter(detailed_formatter)
    root_logger.addHandler(file_handler)
    
    # Console handler (cleaner output)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(console_level)
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)
    
    # Log initialization
    logger = logging.getLogger(__name__)
    logger.info("=" * 70)
    logger.info(f"Logging initialized: {stage_name}")
    logger.info(f"Log file: {log_file}")
    logger.info(f"File log level: {logging.getLevelName(log_level)}")
    logger.info(f"Console log level: {logging.getLevelName(console_level)}")
    logger.info("=" * 70)
    
    return str(log_file)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance.
    
    Args:
        name: Logger name (typically __name__)
        
    Returns:
        Logger instance
    """
    return logging.getLogger(name)


def add_error_log_file(error_log_path: Optional[str] = None) -> str:
    """
    Add a separate error-only log file.
    
    Args:
        error_log_path: Custom path for error log (optional)
        
    Returns:
        Path to error log file
    """
    logs_dir = Path(LOGS_DIR)
    
    if error_log_path:
        error_file = Path(error_log_path)
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        error_file = logs_dir / f"error_{timestamp}.log"
    
    # Create error handler
    error_handler = logging.FileHandler(error_file, encoding='utf-8')
    error_handler.setLevel(logging.ERROR)
    
    error_formatter = logging.Formatter(
        fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s\n%(pathname)s:%(lineno)d\n',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    error_handler.setFormatter(error_formatter)
    
    # Add to root logger
    root_logger = logging.getLogger()
    root_logger.addHandler(error_handler)
    
    logger = logging.getLogger(__name__)
    logger.info(f"Error log file added: {error_file}")
    
    return str(error_file)