"""
application/workflows/stage2_extraction.py

Stage 2 Workflow: Download contracts and extract raw text.

Reads the processo links produced by Stage 1, navigates to each
document on processo.rio, handles CAPTCHA, extracts COMPLETE raw text
from the PDF using a 3-method cascade, and saves one JSON file per
contract to data/extractions/.

Usage
─────
    python application/workflows/stage2_extraction.py

    # Or from another script:
    from application.workflows.stage2_extraction import run_stage2_extraction
    summary = run_stage2_extraction(headless=False)

Output files
────────────
    data/extractions/{PROCESSO_ID}_raw.json   — one per contract
    data/extraction_progress.json             — resume state
    logs/extraction_contracts_YYYYMMDD_HHMMSS.log
"""
import logging
import sys
from datetime import datetime
from pathlib import Path

# Ensure project root is on the path when run directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from infrastructure.logging_config import setup_logging, add_error_log_file
from infrastructure.health_check import run_preflight
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
                  Keep False (default) — required for manual CAPTCHA solving.

    Returns:
        Summary dict:
        {
          "total":    int,
          "skipped":  int,
          "success":  int,
          "failed":   int,
          "errors":   [{"processo_id": ..., "error": ...}]
        }
    """
    preflight = run_preflight(
        "stage2_extraction",
        require_discovery=True,
        require_browser=True,
    )
    if not preflight.passed:
        logger.error("Aborting stage2_extraction — pre-flight failed.")
        return {
            "total": 0,
            "skipped": 0,
            "success": 0,
            "failed": 0,
            "errors": [],
            "preflight_failed": True,
            "preflight_errors": preflight.errors,
        }

    # CHANGE: single logging call — produces
    # logs/extraction_contracts_YYYYMMDD_HHMMSS.log
    # (removed _setup_extraction_logging() which created a duplicate handler)
    log_file = setup_logging("extraction_contracts")
    error_log_path = add_error_log_file()
    logger.info("Stage 2 error log: %s", error_log_path)

    logger.info("=" * 70)
    logger.info("🚀 STARTING STAGE 2: EXTRACTION WORKFLOW")
    logger.info("=" * 70)
    logger.info(f"Log file : {log_file}")
    logger.info(f"Started  : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(
        "\n⚠  CAPTCHA NOTE\n"
        "   processo.rio shows a security check on first access.\n"
        "   The browser will pause when the CAPTCHA page appears.\n"
        "   Solve it once — the session stays valid for several minutes,\n"
        "   allowing all contracts to download without re-solving.\n"
        "   A sound alert will play when your attention is needed.\n"
    )

    # Load links from Stage 1
    links = load_links_from_discovery(DISCOVERY_FILE)
    if not links:
        logger.error(
            "No links to process — run Stage 1 first.\n"
            f"Expected file: {DISCOVERY_FILE}"
        )
        return {}

    logger.info(f"   Loaded {len(links)} processo links")

    driver = None
    try:
        driver = create_driver(headless=headless, anti_detection=True)
        if not driver:
            logger.error("Failed to initialise WebDriver.")
            return {}

        downloader = ProcessoDownloader(driver)
        summary    = downloader.download_all(links)

        # Log final summary
        logger.info("\n" + "=" * 70)
        logger.info("📊 FINAL SUMMARY")
        logger.info(f"   Total   : {summary.get('total', 0)}")
        logger.info(f"   Success : {summary.get('success', 0)}")
        logger.info(f"   Skipped : {summary.get('skipped', 0)}")
        logger.info(f"   Failed  : {summary.get('failed', 0)}")
        logger.info(f"   Log     : {log_file}")
        logger.info("=" * 70)

        return summary

    except KeyboardInterrupt:
        logger.warning(
            "\n⚠  Interrupted by user.\n"
            "   Progress saved to data/extraction_progress.json\n"
            "   Re-run to resume from where it stopped."
        )
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
        print(
            f"\nDone: {result['success']} extracted, "
            f"{result['skipped']} skipped, "
            f"{result['failed']} failed"
        )