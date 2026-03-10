"""
application/workflows/stage3_publication.py

Stage 3 Workflow: Search DoWeb and extract publication texts.

Reads the processo IDs produced by Stage 1, searches DoWeb for each
one using Busca Exata, downloads the gazette page PDFs, extracts text
using the digital layer (PyMuPDF) or column-aware OCR fallback, and
saves one JSON file per processo to data/extractions/.

Usage
─────
    python application/workflows/stage3_publication.py

    # Force-reprocess all (including already completed):
    python application/workflows/stage3_publication.py --force

    # Or from another script:
    from application.workflows.stage3_publication import run_stage3_publication
    summary = run_stage3_publication(headless=False)

Output files
────────────
    data/extractions/{PROCESSO_ID}_publications_raw.json  — one per processo
    data/publication_extraction_progress.json             — resume state
    logs/extraction_publications_YYYYMMDD_HHMMSS.log

Prerequisites
─────────────
    Stage 1 must have run and produced:
        data/discovery/processo_links.json

Notes
─────
    DoWeb may show a CAPTCHA on first access.
    Solve it once — the session persists for the full run.
    Keep headless=False (default) so the CAPTCHA page renders correctly.
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
from infrastructure.scrapers.doweb.downloader import (
    DoWebDownloader,
    load_processo_ids,
    load_discovery_metadata,
)

logger = logging.getLogger(__name__)

DISCOVERY_FILE = "data/discovery/processo_links.json"


def run_stage3_publication(
    headless: bool = False,
    force:    bool = False,
) -> dict:
    """
    Execute the Stage 3 publication extraction workflow.

    Args:
        headless: Run the browser in headless mode.
                  Keep False (default) — required for manual CAPTCHA solving.
        force:    Reprocess IDs already marked as completed or partial.
                  Use when new publications may have appeared since last run.

    Returns:
        Summary dict:
        {
          "total":      int,
          "success":    int,
          "skipped":    int,
          "failed":     int,
          "no_results": int,
          "partial":    int,
        }
    """
    preflight = run_preflight(
        "stage3_publication",
        require_discovery=True,
        require_browser=True,
    )
    if not preflight.passed:
        logger.error("Aborting stage3_publication — pre-flight failed.")
        return {
            "total": 0,
            "success": 0,
            "skipped": 0,
            "failed": 0,
            "no_results": 0,
            "partial": 0,
            "preflight_failed": True,
            "preflight_errors": preflight.errors,
        }

    log_file = setup_logging("extraction_publications")
    error_log_path = add_error_log_file()
    logger.info("Stage 3 error log: %s", error_log_path)

    logger.info("=" * 70)
    logger.info("🚀 STARTING STAGE 3: PUBLICATION EXTRACTION WORKFLOW")
    logger.info("=" * 70)
    logger.info(f"Log file  : {log_file}")
    logger.info(f"Started   : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Force mode: {force}")
    logger.info(
        "\n⚠  CAPTCHA NOTE\n"
        "   DoWeb may show a security check on first access.\n"
        "   The browser will pause when the CAPTCHA page appears.\n"
        "   Solve it once — the session stays valid for the full run,\n"
        "   allowing all searches to complete without re-solving.\n"
    )

    # ── Load processo IDs from Stage 1 ────────────────────────────────────────
    processo_ids = load_processo_ids(DISCOVERY_FILE)
    if not processo_ids:
        logger.error(
            "No processo IDs to process — run Stage 1 first.\n"
            f"Expected file: {DISCOVERY_FILE}"
        )
        return {}

    # ── Load discovery metadata (company name, CNPJ, value) ──────────────────
    discovery_meta = load_discovery_metadata(DISCOVERY_FILE)
    logger.info(
        f"   Loaded {len(processo_ids)} processo IDs "
        f"({len(discovery_meta)} with discovery metadata)"
    )

    driver = None
    try:
        driver = create_driver(headless=headless, anti_detection=True)
        if not driver:
            logger.error("Failed to initialise WebDriver.")
            return {}

        downloader = DoWebDownloader(driver)
        summary    = downloader.download_all(
            processo_ids   = processo_ids,
            force          = force,
            discovery_meta = discovery_meta,
        )

        # ── Final summary ─────────────────────────────────────────────────────
        logger.info("\n" + "=" * 70)
        logger.info("📊 FINAL SUMMARY")
        logger.info(f"   Total      : {summary.get('total', 0)}")
        logger.info(f"   Success    : {summary.get('success', 0)}")
        logger.info(f"   Skipped    : {summary.get('skipped', 0)}")
        logger.info(f"   Partial    : {summary.get('partial', 0)}")
        logger.info(f"   No results : {summary.get('no_results', 0)}")
        logger.info(f"   Failed     : {summary.get('failed', 0)}")
        logger.info(f"   Log        : {log_file}")
        logger.info("=" * 70)

        # ── Audit note for no_results ─────────────────────────────────────────
        if summary.get("no_results", 0) > 0:
            logger.info(
                f"\n⚠  AUDIT NOTE: {summary['no_results']} processo(s) returned "
                f"no publications from DoWeb.\n"
                f"   This may indicate a Rule R001 violation (publication not made\n"
                f"   within 20 days of contract signing).\n"
                f"   Review data/publication_extraction_progress.json → 'no_results'\n"
                f"   for the complete list."
            )

        return summary

    except KeyboardInterrupt:
        logger.warning(
            "\n⚠  Interrupted by user.\n"
            "   Progress saved to data/publication_extraction_progress.json\n"
            "   Re-run to resume from where it stopped."
        )
        return {}

    finally:
        if driver:
            close_driver(driver)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Stage 3: Publication extraction from DoWeb"
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run browser headless (not recommended — blocks CAPTCHA solving)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Reprocess IDs already marked completed or partial",
    )
    args = parser.parse_args()

    result = run_stage3_publication(headless=args.headless, force=args.force)

    if result:
        print(
            f"\nDone: {result.get('success', 0)} extracted, "
            f"{result.get('skipped', 0)} skipped, "
            f"{result.get('no_results', 0)} no results, "
            f"{result.get('partial', 0)} partial, "
            f"{result.get('failed', 0)} failed"
        )