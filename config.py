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
SCROLL_DELAY = 2  # seconds between scroll actions

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

from pathlib import Path

# Project root (Data_ige)
BASE_DIR = Path(__file__).resolve().parent

# Data directories
DATA_DIR = BASE_DIR / "data"

DOWNLOADS_DIR = DATA_DIR / "downloads"
PROCESSOS_DIR = DOWNLOADS_DIR / "processos"

OUTPUTS_DIR = DATA_DIR / "outputs"
EXTRACTIONS_DIR = DATA_DIR / "extractions"

# Files
ANALYSIS_SUMMARY_CSV = OUTPUTS_DIR / "analysis_summary.csv"


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

# =============================================================================
# Year Filter Options
# =============================================================================
_year_env = os.getenv("FILTER_YEAR", "")
FILTER_YEAR = int(_year_env) if _year_env.strip().isdigit() else None

# =============================================================================
# PROCESSO PORTAL SETTINGS
# =============================================================================
PROCESSO_BASE_URL = "https://acesso.processo.rio"
PROCESSO_TRANSPARENCY_URL = "https://acesso.processo.rio/sigaex/public/app/transparencia/processo"

# Target documents to extract
TARGET_DOCUMENTS = [
    {
        "pattern": "Íntegra do contrato/demais instrumentos jurídicos celebrados",
        "tipo": "contrato",
        "priority": 1
    },
    {
        "pattern": "Íntegra dos termos aditivos celebrados",
        "tipo": "aditivo", 
        "priority": 2
    }
]

# Temp download folder (files deleted after extraction)
TEMP_DOWNLOAD_PATH = os.path.join("data", "temp_downloads")
EXTRACTED_TEXTS_PATH = os.path.join("data", "extracted_texts")

# =============================================================================
# DOWEB (DIÁRIO OFICIAL) SETTINGS
# =============================================================================

DOWEB_BASE_URL = "https://doweb.rio.rj.gov.br"
DOWEB_SEARCH_URL = "https://doweb.rio.rj.gov.br/buscanova/#/p=1&q={processo}"

# Temp folder for downloaded PDFs (deleted after processing)
DOWEB_TEMP_PATH = os.path.join("data", "temp_doweb")

# Locators for DOWEB navigation
DOWEB_LOCATORS = {
    # Home page
    "search_input": "input#input2",
    "search_button_home": "input#btn-autenticidade",
    
    # Search results page
    "results_count": "//div[contains(text(), 'resultados encontrados')]",
    "result_cards": "//div[contains(@class, 'card') or contains(@class, 'result')]",
    "publication_info": "//span[contains(text(), 'publicado em:')]",
    "download_button": "//span[contains(text(), 'Download')]/parent::*",
    "download_page_only": "//a[contains(text(), 'Baixar apenas a página')]",
    
    # Pagination
    "pagination_links": "//ul[contains(@class, 'pagination')]//a",
    "current_page": "//a[contains(@class, 'active') or .//span[contains(@class, 'current')]]",
    "next_page": "//a[contains(text(), '›') or contains(text(), 'next')]",
}

# Processo number patterns
PROCESSO_PATTERNS = {
    "new": r"([A-Z]{2,4}-[A-Z]{2,4}-\d{4}/\d{4,6})",      # SME-PRO-2025/19222
    "old": r"([A-Z]{2,4}/\d{5,6}/\d{4})",                  # SME/001234/2019
    "old_prefix": r"\d{2,3}/([A-Z]{2,4}/\d{5,6}/\d{4})",  # 001/04/000123/2020
}

# Target publication types
TARGET_EXTRATO_TYPES = [
    "EXTRATO DO CONTRATO",
    "EXTRATO DE TERMO ADITIVO",
    "EXTRATO DE CONTRATO",
    "EXTRATO DO TERMO",
]