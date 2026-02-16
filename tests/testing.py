from infrastructure.logging_config import setup_logging
import logging

# Setup logging
log_file = setup_logging("test", log_level=logging.INFO)
print(f"Log file: {log_file}")

# Test logging at different levels
logger = logging.getLogger(__name__)
logger.debug("This is a debug message")
logger.info("This is an info message")
logger.warning("This is a warning message")
logger.error("This is an error message")

# Check log file exists
from pathlib import Path
assert Path(log_file).exists()

print("✓ Logging test passed")