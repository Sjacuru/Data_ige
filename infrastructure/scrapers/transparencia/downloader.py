"""
infrastructure/scrapers/transparencia/downloader.py

Stage 2: Download contract documents and extract raw text.

Flow for each processo link
───────────────────────────
1. Check if already extracted  →  skip if {processo_id}.json exists
2. Navigate to processo.rio URL
3. Handle CAPTCHA (auto then manual)
4. Locate and download the PDF
5. Extract raw text (PyMuPDF → OCR fallback)
6. Save {processo_id}.json to data/extractions/
7. Delete the temporary PDF
8. Move to next link

CAPTCHA strategy
────────────────
processo.rio shows a "Verificação de segurança" page on first access.
Once solved, the session typically stays valid for several minutes,
allowing multiple documents to be downloaded without re-solving.
When the captcha page reappears, the handler pauses for manual resolution.

Output JSON per contract
────────────────────────
{
  "processo_id":   "TUR-PRO-2025/01221",
  "url":           "https://acesso.processo.rio/...",
  "company_name":  "GREMIO RECREATIVO ...",
  "company_cnpj":  "01282704000167",
  "contract_value":"2.150.000,00",
  "discovery_path":["company", "orgao", "ug"],
  "pages":         12,
  "extraction_source": "native",
  "raw_text":      "...",
  "extracted_at":  "2026-02-20T..."
}
"""
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.common.exceptions import NoSuchElementException

from config.settings import EXTRACTIONS_DIR
from domain.models.processo_link import ProcessoLink
from infrastructure.extractors.pdf_text_extractor import extract_text
from infrastructure.web.captcha_handler import CaptchaHandler

logger = logging.getLogger(__name__)

# ── Paths ─────────────────────────────────────────────────────────────────────
EXTRACTIONS_DIR = Path(EXTRACTIONS_DIR)
TEMP_PDF_DIR    = Path("data/temp_downloads")

# ── Timing ────────────────────────────────────────────────────────────────────
PAGE_LOAD_WAIT  = 10   # seconds to wait after navigating to a URL
DOWNLOAD_WAIT   = 15   # seconds to wait for PDF download to complete
BETWEEN_DOCS    = 3    # seconds between consecutive downloads (be polite)


def _sanitize(processo_id: str) -> str:
    """Turn 'TUR-PRO-2025/01221' into 'TUR-PRO-2025_01221' for safe filenames."""
    return processo_id.replace("/", "_").replace("\\", "_")


def _extraction_path(processo_id: str) -> Path:
    return EXTRACTIONS_DIR / f"{_sanitize(processo_id)}.json"


def _is_already_extracted(processo_id: str) -> bool:
    return _extraction_path(processo_id).exists()


def _save_extraction(link: ProcessoLink, extraction: dict) -> bool:
    """
    Persist the extraction result to data/extractions/{processo_id}.json.

    Args:
        link:       The original ProcessoLink with discovery metadata.
        extraction: Result dict from pdf_text_extractor.extract_text().

    Returns:
        True if saved successfully.
    """
    record = {
        # Discovery metadata
        "processo_id":       link.processo_id,
        "url":               link.url,
        "company_name":      link.company_name,
        "company_cnpj":      link.company_cnpj,
        "contract_value":    link.contract_value,
        "discovery_path":    link.discovery_path,
        # Extraction results
        "pages":             extraction.get("pages", 0),
        "extraction_source": extraction.get("source", "unknown"),
        "raw_text":          extraction.get("text", ""),
        "extraction_error":  extraction.get("error"),
        # Timestamps
        "extracted_at":      datetime.now().isoformat(),
    }

    out_path = _extraction_path(link.processo_id)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
        logger.info(f"   💾 Saved: {out_path.name}")
        return True
    except Exception as e:
        logger.error(f"   ✗ Could not save extraction: {e}")
        return False


# ── PDF download from processo.rio ────────────────────────────────────────────

class ProcessoDownloader:
    """
    Downloads contract documents from processo.rio and extracts raw text.

    One instance is reused across all links so the browser session —
    and the solved CAPTCHA — persists between downloads.
    """

    def __init__(self, driver: webdriver.Chrome):
        self.driver       = driver
        self.captcha      = CaptchaHandler(driver)
        self._session_ok  = False    # True once CAPTCHA has been solved once

    # ── Public entry point ────────────────────────────────────────────────────

    def download_all(self, links: List[ProcessoLink]) -> dict:
        """
        Iterate through every ProcessoLink and extract its document text.

        Already-extracted links (JSON file exists) are skipped automatically.

        Args:
            links: List of ProcessoLink from discovery.

        Returns:
            Summary dict:
              {
                "total":     int,
                "skipped":   int,   # already extracted
                "success":   int,
                "failed":    int,
                "errors":    [{"processo_id": ..., "error": ...}]
              }
        """
        TEMP_PDF_DIR.mkdir(parents=True, exist_ok=True)
        EXTRACTIONS_DIR.mkdir(parents=True, exist_ok=True)

        total   = len(links)
        skipped = 0
        success = 0
        failed  = 0
        errors  = []

        logger.info("=" * 70)
        logger.info(f"📥 STAGE 2: DOWNLOADING {total} CONTRACTS")
        logger.info("=" * 70)

        for i, link in enumerate(links, 1):
            pid = link.processo_id
            label = f"[{i}/{total}] {pid}"

            # ── Skip already done ─────────────────────────────────────────────
            if _is_already_extracted(pid):
                logger.info(f"   ⏭  {label} — already extracted")
                skipped += 1
                continue

            logger.info(f"\n   {label}")
            logger.info(f"   🏢 {link.company_name[:60] if link.company_name else ''}")

            try:
                ok = self._process_one(link)
                if ok:
                    success += 1
                else:
                    failed += 1
                    errors.append({"processo_id": pid, "error": "extraction failed"})

            except Exception as e:
                failed += 1
                errors.append({"processo_id": pid, "error": str(e)})
                logger.error(f"   ✗ Unexpected error: {e}")

            time.sleep(BETWEEN_DOCS)

        logger.info("\n" + "=" * 70)
        logger.info("✅ DOWNLOAD COMPLETE")
        logger.info(f"   Total:   {total}")
        logger.info(f"   Skipped: {skipped} (already extracted)")
        logger.info(f"   Success: {success}")
        logger.info(f"   Failed:  {failed}")
        logger.info("=" * 70)

        return {
            "total":   total,
            "skipped": skipped,
            "success": success,
            "failed":  failed,
            "errors":  errors,
        }

    # ── Single document ───────────────────────────────────────────────────────

    def _process_one(self, link: ProcessoLink) -> bool:
        """
        Navigate → CAPTCHA → Download PDF → Extract text → Save JSON → Delete PDF.

        Returns True if a JSON file was saved successfully.
        """
        # Step 1: Navigate
        self.driver.get(link.url)
        time.sleep(PAGE_LOAD_WAIT)

        # Step 2: CAPTCHA handling
        if not self._ensure_past_captcha():
            logger.error("   ✗ Could not pass CAPTCHA — skipping this document")
            return False

        # Step 3: Find and download the PDF
        pdf_path = self._download_pdf(link.processo_id)
        if not pdf_path:
            logger.error("   ✗ PDF download failed")
            return False

        # Step 4: Extract text
        logger.info("   📄 Extracting text from PDF...")
        extraction = extract_text(str(pdf_path))

        if not extraction["success"]:
            logger.error(f"   ✗ Text extraction failed: {extraction.get('error')}")
            _delete_pdf(pdf_path)
            return False

        logger.info(
            f"   ✓ Extracted {len(extraction['text']):,} chars "
            f"from {extraction['pages']} page(s) [{extraction['source']}]"
        )

        # Step 5: Save JSON
        saved = _save_extraction(link, extraction)

        # Step 6: Delete temp PDF regardless of save result
        _delete_pdf(pdf_path)

        return saved

    # ── CAPTCHA helpers ───────────────────────────────────────────────────────

    def _ensure_past_captcha(self) -> bool:
        """
        Make sure we are past the CAPTCHA page.

        If the session is already valid (previous solve) and the page
        loaded directly, this returns immediately. Otherwise delegates
        to CaptchaHandler which will attempt auto-solve then ask for
        manual intervention.

        Returns:
            True if we are on the documents/content page.
        """
        # Already past captcha from this session?
        if self._session_ok and self.captcha.is_on_documents_page():
            return True

        # Need to go through captcha flow
        resolved = self.captcha.handle()

        if resolved:
            self._session_ok = True
            return True

        # One more check — sometimes handle() is conservative
        if self.captcha.is_on_documents_page():
            self._session_ok = True
            return True

        return False

    # ── PDF download ──────────────────────────────────────────────────────────

    def _download_pdf(self, processo_id: str) -> Optional[Path]:
        """
        Downloads the PDF(s). If multiple parts exist, it downloads all 
        but returns the primary path to satisfy existing code.
        """
        try:
            pdf_urls = self._find_pdf_urls()
        except FileNotFoundError:
            return None

        if not pdf_urls:
            logger.error("   ✗ No PDF link found on page")
            return None

        # Prepare session data (cookies/headers)
        cookies = {c["name"]: c["value"] for c in self.driver.get_cookies()}
        headers = {"User-Agent": self.driver.execute_script("return navigator.userAgent;")}
        
        primary_dest = None

        for index, url in enumerate(pdf_urls):
            # Create unique names: ID.pdf, ID_part2.pdf, etc.
            suffix = f"_part{index + 1}" if index > 0 else ""
            dest = TEMP_PDF_DIR / f"{_sanitize(processo_id)}{suffix}.pdf"
            
            # Save the first one as our main return value
            if index == 0:
                primary_dest = dest

            try:
                # Download using the URL string from the loop
                response = requests.get(
                    url, 
                    cookies=cookies, 
                    headers=headers, 
                    timeout=60, 
                    stream=True
                )
                response.raise_for_status()

                with open(dest, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                logger.info(f"   ✓ Downloaded: {dest.name}")

            except Exception as e:
                logger.error(f"   ✗ Download error for {dest.name}: {e}")

        return primary_dest # Returns a single Path to keep _delete_pdf happy

    def _find_pdf_urls(self) -> list[str]:
        """
        Finds one or multiple PDF download URLs.
        Raises FileNotFoundError if the 'No document' alert is present.
        """
        time.sleep(3) # Wait for SPA/Vaadin grid

        # 1. Check for the "No document" error alert
        error_alerts = self.driver.find_elements(By.CSS_SELECTOR, "p.alert.alert-danger")
        for alert in error_alerts:
            if "Não há documento associado" in alert.text:
                logger.warning("❌ No document found for this process.")
                raise FileNotFoundError("Não há documento associado.")

        # 2. Target the PDF icons specifically
        pdf_elements = self.driver.find_elements(
            By.XPATH, 
            "//a[img[contains(@src, 'page_white_acrobat.png')]]"
        )

        pdf_urls = []
        base_url = self.driver.current_url

        for el in pdf_elements:
            href = el.get_attribute("href")
            if href:
                full_url = urljoin(base_url, href)
                if full_url not in pdf_urls:
                    pdf_urls.append(full_url)

        return pdf_urls

# ── Utility ───────────────────────────────────────────────────────────────────

def _delete_pdf(path: Path) -> None:
    """Delete a temporary PDF file silently."""
    try:
        if path and path.exists():
            path.unlink()
            logger.debug(f"   🗑  Deleted temp PDF: {path.name}")
    except Exception as e:
        logger.warning(f"   ⚠ Could not delete {path}: {e}")


def load_links_from_discovery(
    discovery_file: str = "data/discovery/processo_links.json",
) -> List[ProcessoLink]:
    """
    Read the processo_links.json produced by Stage 1.

    Args:
        discovery_file: Path to the JSON file.

    Returns:
        List of ProcessoLink objects.
    """
    path = Path(discovery_file)
    if not path.exists():
        logger.error(f"Discovery file not found: {path}")
        return []

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    raw_links = data.get("processos", [])
    links = [ProcessoLink.from_dict(p) for p in raw_links]
    logger.info(f"   📂 Loaded {len(links)} processo links from {path.name}")
    return links