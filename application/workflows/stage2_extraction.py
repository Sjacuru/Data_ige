"""
application/workflows/stage2_extraction.py

Stage 2 Workflow: Download contracts and extract raw text.

Reads the processo links produced by Stage 1, navigates to each
document on processo.rio, handles CAPTCHA, extracts raw text from
the PDF, and saves one JSON file per contract to data/extractions/.

Usage
─────
    python application/workflows/stage2_extraction.py

    # Or from another script:
    from application.workflows.stage2_extraction import run_stage2_extraction
    summary = run_stage2_extraction(headless=False)
"""
import logging
import sys
from pathlib import Path

# Ensure project root is on the path when run directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from infrastructure.logging_config import setup_logging
from infrastructure.web.driver import create_driver, close_driver
from infrastructure.scrapers.transparencia.downloader import (
    ProcessoDownloader,
    load_links_from_discovery,
)

logger = logging.getLogger(__name__)

DISCOVERY_FILE = "data/discovery/processo_links.json"


def run_stage2_extraction(headless: bool = False) -> dict:
    """
    Execute the Stage 2 extraction workflow.

    Args:
        headless: Run the browser in headless mode.
                  Set to False (default) so the user can solve CAPTCHA.

    Returns:
        Summary dict from ProcessoDownloader.download_all().
    """
    setup_logging("stage2_extraction")

    logger.info("=" * 70)
    logger.info("🚀 STARTING STAGE 2: EXTRACTION WORKFLOW")
    logger.info("=" * 70)
    logger.info(
        "\n⚠  CAPTCHA NOTE\n"
        "   processo.rio requires a human CAPTCHA check.\n"
        "   The browser will open and pause when the CAPTCHA page appears.\n"
        "   Solve it once — the session usually stays valid for several minutes,\n"
        "   allowing all contracts to download without re-solving.\n"
        "   A sound alert will play when your attention is needed.\n"
    )

    # Load links from Stage 1
    links = load_links_from_discovery(DISCOVERY_FILE)
    if not links:
        logger.error("No links to process — run Stage 1 first.")
        return {}

    driver = None
    try:
        driver = create_driver(headless=headless, anti_detection=True)
        if not driver:
            logger.error("Failed to initialise WebDriver.")
            return {}

        downloader = ProcessoDownloader(driver)
        summary = downloader.download_all(links)
        return summary

    except KeyboardInterrupt:
        logger.warning("\n⚠  Interrupted by user — progress already saved to data/extractions/")
        return {}

    finally:
        if driver:
            close_driver(driver)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Stage 2: Contract extraction")
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run browser headless (not recommended — blocks CAPTCHA solving)",
    )
    args = parser.parse_args()

    result = run_stage2_extraction(headless=args.headless)

    if result:
        print(f"\nDone: {result['success']} extracted, "
              f"{result['skipped']} skipped, "
              f"{result['failed']} failed")