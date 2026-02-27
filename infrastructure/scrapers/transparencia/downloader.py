"""
infrastructure/scrapers/transparencia/downloader.py

Stage 2: Download contract documents and extract raw text.

Flow for each processo link
───────────────────────────
1. Check progress file → skip if already done or permanently failed
2. Navigate to processo.rio URL
3. Handle CAPTCHA (auto then manual)
4. Locate and download PDF to data/temp/
5. Extract COMPLETE raw text (PyMuPDF → pdfplumber → OCR)
6. Validate text quality (500 chars min, readable)
7. Save {processo_id}_raw.json to data/extractions/
8. Delete temp PDF immediately (max 1 PDF on disk at any time)
9. Update extraction_progress.json
10. Move to next link

CAPTCHA strategy
────────────────
processo.rio shows a "Verificação de segurança" page on first access.
Once solved, the session typically stays valid for several minutes.
When the captcha page reappears, the handler pauses for manual resolution.

Output JSON per contract
────────────────────────
{
  "processo_id":      "TUR-PRO-2025/01221",
  "url":              "https://acesso.processo.rio/...",
  "company_name":     "GREMIO RECREATIVO ...",
  "company_cnpj":     "01282704000167",
  "contract_value":   "2.150.000,00",
  "discovery_path":   ["company", "orgao", "ug"],
  "pages":            12,
  "extraction_source":"pymupdf",
  "total_chars":      18423,
  "quality_passes":   true,
  "quality_flags":    [],
  "raw_text":         "...",
  "extracted_at":     "2026-02-20T..."
}
"""
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from urllib.parse import urljoin

import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from config.settings import EXTRACTIONS_DIR
from domain.models.processo_link import ProcessoLink
from infrastructure.extractors.pdf_text_extractor import extract_text
from infrastructure.web.captcha_handler import CaptchaHandler

logger = logging.getLogger(__name__)

# ── Paths ─────────────────────────────────────────────────────────────────────
EXTRACTIONS_DIR  = Path(EXTRACTIONS_DIR)
TEMP_PDF_DIR     = Path("data/temp_downloads")
PROGRESS_FILE    = Path("data/extraction_progress.json")

# ── Timing ────────────────────────────────────────────────────────────────────
PAGE_LOAD_WAIT  = 10   # seconds after navigating to a URL
DOWNLOAD_WAIT   = 15   # seconds to wait for PDF download
BETWEEN_DOCS    = 3    # polite pause between documents


# ═══════════════════════════════════════════════════════════════════════════════
# FILE NAMING  (Epic 2: PROCESSO_ID_raw.json)
# ═══════════════════════════════════════════════════════════════════════════════

def _sanitize(processo_id: str) -> str:
    """'TUR-PRO-2025/01221'  →  'TUR-PRO-2025_01221'  (safe filename)"""
    return processo_id.replace("/", "_").replace("\\", "_")


def _extraction_path(processo_id: str) -> Path:
    """Returns data/extractions/{id}_raw.json"""
    return EXTRACTIONS_DIR / f"{_sanitize(processo_id)}_raw.json"


def _is_already_extracted(processo_id: str) -> bool:
    return _extraction_path(processo_id).exists()


# ═══════════════════════════════════════════════════════════════════════════════
# PROGRESS TRACKING  (data/extraction_progress.json)
# ═══════════════════════════════════════════════════════════════════════════════

def _load_progress() -> dict:
    """
    Load the extraction progress file.

    Schema:
    {
      "started_at":   str,
      "updated_at":   str,
      "completed":    [processo_id, ...],
      "failed":       [{"processo_id": ..., "error": ..., "at": ...}, ...],
      "pending":      [processo_id, ...],   # populated on first load
      "stats": {
        "total":    int,
        "success":  int,
        "failed":   int,
        "skipped":  int
      }
    }
    """
    if PROGRESS_FILE.exists():
        try:
            with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            logger.info(
                f"   📂 Resuming: {len(data.get('completed', []))} done, "
                f"{len(data.get('failed', []))} failed"
            )
            return data
        except Exception as e:
            logger.warning(f"   ⚠ Could not read progress file: {e} — starting fresh")

    return {
        "started_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "completed":  [],
        "failed":     [],
        "pending":    [],
        "stats":      {"total": 0, "success": 0, "failed": 0, "skipped": 0},
    }


def _save_progress(progress: dict) -> None:
    """Persist progress to disk — called after every document."""
    try:
        PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
        progress["updated_at"] = datetime.now().isoformat()
        with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
            json.dump(progress, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"   ✗ Could not save progress: {e}")


def _mark_completed(progress: dict, processo_id: str) -> None:
    if processo_id not in progress["completed"]:
        progress["completed"].append(processo_id)
    progress["stats"]["success"] = progress["stats"].get("success", 0) + 1


def _mark_failed(progress: dict, processo_id: str, error: str) -> None:
    progress["failed"].append({
        "processo_id": processo_id,
        "error":       error,
        "at":          datetime.now().isoformat(),
    })
    progress["stats"]["failed"] = progress["stats"].get("failed", 0) + 1


# ═══════════════════════════════════════════════════════════════════════════════
# JSON PERSISTENCE
# ═══════════════════════════════════════════════════════════════════════════════

def _save_extraction(link: ProcessoLink, extraction: dict) -> bool:
    """
    Persist extraction result to data/extractions/{processo_id}_raw.json.

    Includes full text, metadata, quality flags, and timestamps.
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
        "total_chars":       extraction.get("total_chars", 0),
        "quality_passes":    extraction.get("quality_passes", False),
        "quality_flags":     extraction.get("quality_flags", []),
        # Full contract text (CRITICAL: complete, not truncated)
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
        size_kb = out_path.stat().st_size / 1024
        logger.info(f"   💾 Saved: {out_path.name} ({size_kb:.1f} KB)")
        return True
    except Exception as e:
        logger.error(f"   ✗ Could not save extraction: {e}")
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# PDF CLEANUP
# ═══════════════════════════════════════════════════════════════════════════════

def _delete_pdf(path: Optional[Path]) -> None:
    """Delete temp PDF silently — ensures max 1 PDF on disk at any time."""
    try:
        if path and path.exists():
            path.unlink()
            logger.debug(f"   🗑  Deleted temp PDF: {path.name}")
    except Exception as e:
        logger.warning(f"   ⚠ Could not delete {path}: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# DISCOVERY FILE LOADER
# ═══════════════════════════════════════════════════════════════════════════════

def load_links_from_discovery(
    discovery_file: str = "data/discovery/processo_links.json",
) -> List[ProcessoLink]:
    """
    Read the processo_links.json produced by Stage 1.

    Returns:
        List of ProcessoLink objects, or empty list if file not found.
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


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN DOWNLOADER CLASS
# ═══════════════════════════════════════════════════════════════════════════════

class ProcessoDownloader:
    """
    Downloads contract documents from processo.rio and extracts raw text.

    One instance is reused across all links so the browser session —
    and the solved CAPTCHA — persists between downloads.

    Guarantees (Epic 2):
    - Maximum 1 PDF in data/temp_downloads/ at any time
    - All extractions saved as {id}_raw.json
    - extraction_progress.json updated after every document
    - Quality validation run on every extraction
    """

    def __init__(self, driver: webdriver.Chrome):
        self.driver      = driver
        self.captcha     = CaptchaHandler(driver)
        self._session_ok = False

    # ── Public entry point ────────────────────────────────────────────────────

    def download_all(self, links: List[ProcessoLink]) -> dict:
        """
        Iterate through every ProcessoLink and extract its document text.

        Skips already-extracted links (progress file + file-exists check).
        Persists progress after every document for zero data loss on crash.

        Returns:
            {
              "total":    int,
              "skipped":  int,
              "success":  int,
              "failed":   int,
              "errors":   [{"processo_id": ..., "error": ...}]
            }
        """
        TEMP_PDF_DIR.mkdir(parents=True, exist_ok=True)
        EXTRACTIONS_DIR.mkdir(parents=True, exist_ok=True)

        progress = _load_progress()
        completed_set = set(progress.get("completed", []))

        total   = len(links)
        skipped = 0
        success = 0
        failed  = 0
        errors  = []

        # Update pending list and total in progress file
        progress["pending"] = [
            lk.processo_id for lk in links
            if lk.processo_id not in completed_set
        ]
        progress["stats"]["total"] = total
        _save_progress(progress)

        logger.info("=" * 70)
        logger.info(f"📥 STAGE 2: EXTRACTING {total} CONTRACTS")
        logger.info(f"   Already done : {len(completed_set)}")
        logger.info(f"   To process   : {len(progress['pending'])}")
        logger.info("=" * 70)

        for i, link in enumerate(links, 1):
            pid   = link.processo_id
            label = f"[{i}/{total}] {pid}"

            # ── Skip already done ─────────────────────────────────────────────
            if pid in completed_set or _is_already_extracted(pid):
                logger.info(f"   ⏭  {label} — already extracted")
                skipped += 1
                # Keep completed_set in sync in case file exists but not in progress
                completed_set.add(pid)
                if pid not in progress["completed"]:
                    _mark_completed(progress, pid)
                continue

            logger.info(f"\n   {label}")
            logger.info(f"   🏢 {link.company_name[:60] if link.company_name else ''}")

            try:
                ok = self._process_one(link)
                if ok:
                    success += 1
                    completed_set.add(pid)
                    _mark_completed(progress, pid)
                    # Remove from pending
                    if pid in progress["pending"]:
                        progress["pending"].remove(pid)
                else:
                    failed += 1
                    err = "extraction failed"
                    errors.append({"processo_id": pid, "error": err})
                    _mark_failed(progress, pid, err)

            except Exception as e:
                failed += 1
                err = str(e)
                errors.append({"processo_id": pid, "error": err})
                _mark_failed(progress, pid, err)
                logger.error(f"   ✗ Unexpected error: {e}")

            finally:
                # Save progress after EVERY document
                _save_progress(progress)

            time.sleep(BETWEEN_DOCS)

        # Final summary
        logger.info("\n" + "=" * 70)
        logger.info("✅ EXTRACTION COMPLETE")
        logger.info(f"   Total   : {total}")
        logger.info(f"   Skipped : {skipped} (already extracted)")
        logger.info(f"   Success : {success}")
        logger.info(f"   Failed  : {failed}")
        logger.info(f"   Progress: {PROGRESS_FILE}")
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

        Ensures PDF is deleted in all exit paths (success, failure, exception).
        Returns True if a JSON file was saved successfully.
        """
        pdf_path = None
        try:
            # Step 1: Navigate
            self.driver.get(link.url)
            time.sleep(PAGE_LOAD_WAIT)

            # Step 2: CAPTCHA
            if not self._ensure_past_captcha():
                logger.error("   ✗ Could not pass CAPTCHA — skipping")
                return False

            # Step 3: Download PDF
            pdf_path = self._download_pdf(link.processo_id)
            if not pdf_path:
                logger.error("   ✗ PDF download failed")
                return False

            # Step 4: Extract COMPLETE text
            logger.info("   📄 Extracting text...")
            extraction = extract_text(str(pdf_path))

            if not extraction["success"]:
                logger.error(f"   ✗ Text extraction failed: {extraction.get('error')}")
                return False

            # Log quality result
            if extraction.get("quality_passes"):
                logger.info(
                    f"   ✓ {extraction['total_chars']:,} chars, "
                    f"{extraction['pages']} page(s) [{extraction['source']}]"
                )
            else:
                logger.warning(
                    f"   ⚠ Low-quality extraction: {extraction.get('quality_flags')} "
                    f"— saving anyway for manual review"
                )

            # Step 5: Save JSON
            return _save_extraction(link, extraction)

        except FileNotFoundError:
            # Raised by _find_pdf_urls when "Não há documento associado"
            logger.warning("   ⚠ No document associated — marking as skipped")
            return False

        finally:
            # Step 6: Delete PDF in ALL exit paths (Epic 2: max 1 PDF at a time)
            _delete_pdf(pdf_path)

    # ── CAPTCHA ───────────────────────────────────────────────────────────────

    def _ensure_past_captcha(self) -> bool:
        """Pass the CAPTCHA page, reusing the session if already solved."""
        if self._session_ok and self.captcha.is_on_documents_page():
            return True

        resolved = self.captcha.handle()
        if resolved:
            self._session_ok = True
            return True

        if self.captcha.is_on_documents_page():
            self._session_ok = True
            return True

        return False

    # ── PDF download ──────────────────────────────────────────────────────────

    def _download_pdf(self, processo_id: str) -> Optional[Path]:
        """
        Locate and download the PDF(s) for this processo.

        If multiple parts exist, downloads all but returns path to first
        (primary) file. Caller deletes all temp files via _delete_pdf.
        """
        try:
            pdf_urls = self._find_pdf_urls()
        except FileNotFoundError:
            return None

        if not pdf_urls:
            logger.error("   ✗ No PDF link found on page")
            return None

        cookies = {c["name"]: c["value"] for c in self.driver.get_cookies()}
        headers = {
            "User-Agent": self.driver.execute_script("return navigator.userAgent;")
        }

        primary_dest = None

        for index, url in enumerate(pdf_urls):
            suffix = f"_part{index + 1}" if index > 0 else ""
            dest   = TEMP_PDF_DIR / f"{_sanitize(processo_id)}{suffix}.pdf"

            if index == 0:
                primary_dest = dest

            try:
                response = requests.get(
                    url, cookies=cookies, headers=headers,
                    timeout=60, stream=True
                )
                response.raise_for_status()

                with open(dest, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)

                size_kb = dest.stat().st_size / 1024
                logger.info(f"   ✓ Downloaded: {dest.name} ({size_kb:.0f} KB)")

            except Exception as e:
                logger.error(f"   ✗ Download error for {dest.name}: {e}")

        return primary_dest

    def _find_pdf_urls(self) -> list:
        """
        Find PDF download URLs on the current page.

        Raises FileNotFoundError if "Não há documento associado" alert present.
        Returns list of URL strings (empty list if no PDF icons found).
        """
        time.sleep(3)

        # Check for the "no document" error alert
        error_alerts = self.driver.find_elements(
            By.CSS_SELECTOR, "p.alert.alert-danger"
        )
        for alert in error_alerts:
            if "Não há documento associado" in alert.text:
                logger.warning("   ⚠ No document associated with this process")
                raise FileNotFoundError("Não há documento associado.")

        # Target the PDF acrobat icons specifically
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