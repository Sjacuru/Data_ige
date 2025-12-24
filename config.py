"""
config.py - Central configuration for the Contrato Analyzer tool.
Loads settings from .env file and provides constants used across the project.
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# =============================================================================
# BROWSER SETTINGS
# =============================================================================
CHROME_HEADLESS = os.getenv("CHROME_HEADLESS", "false").lower() == "true"
TIMEOUT_SECONDS = int(os.getenv("TIMEOUT_SECONDS", 20))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", 3))
SCROLL_DELAY = 0.8  # seconds between scroll actions

# =============================================================================
# URLs
# =============================================================================
BASE_URL = os.getenv(
    "BASE_URL", 
    "https://contasrio.rio.rj.gov.br/ContasRio/#!Home"
)
CONTRACTS_URL = os.getenv(
    "CONTRACTS_URL",
    "https://contasrio.rio.rj.gov.br/ContasRio/#!Contratos/Contrato%20por%20Favorecido"
)

# =============================================================================
# DATA COLUMNS
# =============================================================================
VALUE_COLUMNS = [
    "Total Contratado",
    "Empenhado", 
    "Saldo a Executar",
    "Liquidado",
    "Pago"
]

# =============================================================================
# FILE PATHS
# =============================================================================
DATA_RAW_PATH = os.path.join("data", "raw")
DATA_PROCESSED_PATH = os.path.join("data", "processed")
DATA_OUTPUTS_PATH = os.path.join("data", "outputs")

# =============================================================================
# XPATH LOCATORS (centralized for easy maintenance)
# =============================================================================
LOCATORS = {
    "home_menu": "//*[@id='menu-do-portal-container']/div[1]/ul/li[5]/a",
    "table_rows": "//table//tbody//tr",
    "grid_scroller": ".v-grid-scroller",
    "grid_row": ".v-grid-row",
    "filter_input": "//input[@placeholder='Digite para filtrar']",
    "button_caption": "//span[contains(@class,'v-button-caption')]",
    "grid_wrapper": "//div[contains(@class,'v-grid-tablewrapper')]/table",
    "column_header": "//div[contains(@class,'v-grid-column-header-content')]",
}