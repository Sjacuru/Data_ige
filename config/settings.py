
"""
Application settings loaded from environment variables.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Portal URLs
CONTASRIO_BASE_URL = os.getenv("CONTASRIO_BASE_URL", "https://www.rio.rj.gov.br/web/contasrio")
CONTASRIO_CONTRACTS_URL = os.getenv("CONTASRIO_CONTRACTS_URL", "https://contasrio.rio.rj.gov.br/ContasRio/#!Contratos/Contrato%20por%20Favorecido")

FILTER_YEAR = os.getenv("FILTER_YEAR", "2026")

# Browser settings
HEADLESS_MODE = os.getenv("HEADLESS_MODE", "false").lower() == "true"
TIMEOUT_SECONDS = int(os.getenv("TIMEOUT_SECONDS", "10"))

# Project paths
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
DISCOVERY_DIR = DATA_DIR / "discovery"
EXTRACTIONS_DIR = DATA_DIR / "extractions"
TEMP_DIR = DATA_DIR / "temp"
OUTPUTS_DIR = DATA_DIR / "outputs"
LOGS_DIR = BASE_DIR / "logs"

# Ensure directories exist
DISCOVERY_DIR.mkdir(parents=True, exist_ok=True)
EXTRACTIONS_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DIR.mkdir(parents=True, exist_ok=True)
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# %%
