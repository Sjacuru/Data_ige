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
  "processo_id":       "TUR-PRO-2025/01221",
  "url":               "https://acesso.processo.rio/...",
  "company_name":      "GREMIO RECREATIVO ...",
  "company_cnpj":      "01282704000167",
  "contract_value":    "2.150.000,00",
  "discovery_path":    ["company", "orgao", "ug"],
  "page_count":        12,
  "extraction_method": "pymupdf",
  "fallback_used":     false,
  "total_chars":       18423,
  "total_words":       3104,
  "quality_passes":    true,
  "quality_flags":     [],
  "raw_text":          "...",
  "extraction_error":  null,
  "extracted_at":      "2026-02-27T10:30:00",
  "metadata": {
    "pdf_size_bytes":          204857,
    "processing_time_seconds": 1.4
  }
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
from infrastructure.web.driver import create_driver, close_driver

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# CUSTOM EXCEPTIONS
# ═══════════════════════════════════════════════════════════════════════════════

class NoDocumentError(Exception):
    """
    Raised when processo.rio shows "Não há documento associado."

    This is NOT a technical failure — the document simply hasn't been
    uploaded to the portal yet. The processo should be retried on future
    runs and tracked separately from real failures (Selenium errors, etc.).
    """


# ── Paths ─────────────────────────────────────────────────────────────────────
EXTRACTIONS_DIR  = Path(EXTRACTIONS_DIR)
TEMP_PDF_DIR     = Path("data/temp")          # ← CHANGE 1: was "data/temp_downloads"
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
        "started_at":  datetime.now().isoformat(),
        "updated_at":  datetime.now().isoformat(),
        "completed":   [],
        "failed":      [],
        "no_document": [],   # ← portal shows "Não há documento associado"
        "pending":     [],   #   retried every run until document appears
        "stats":       {"total": 0, "success": 0, "failed": 0,
                        "skipped": 0, "no_document": 0},
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


def _mark_no_document(progress: dict, processo_id: str) -> None:
    """
    Record that the portal returned "Não há documento associado."

    The ID is stored in the no_document list so it can be reported
    separately from real failures. It is NOT added to completed or
    failed — on the next run it will be attempted again (the document
    may have been uploaded in the meantime).
    """
    entry = {
        "processo_id": processo_id,
        "at":          datetime.now().isoformat(),
    }
    # Avoid duplicate entries across re-runs
    existing_ids = [e["processo_id"] for e in progress.get("no_document", [])]
    if processo_id not in existing_ids:
        progress.setdefault("no_document", []).append(entry)
    progress["stats"]["no_document"] = progress["stats"].get("no_document", 0) + 1


# ═══════════════════════════════════════════════════════════════════════════════
# JSON PERSISTENCE
# ═══════════════════════════════════════════════════════════════════════════════

def _save_extraction(link: ProcessoLink, extraction: dict) -> bool:
    """
    Persist extraction result to data/extractions/{processo_id}_raw.json.

    CHANGE 2: schema aligned with confirmed Epic 2 spec —
      - "pages"            → "page_count"
      - "extraction_source"→ "extraction_method"
      - kept "raw_text" and "total_chars" (pre-processing not Epic 2 scope)
      - added "total_words", "fallback_used", "metadata" block
    """
    raw_text = extraction.get("text", "")

    record = {
        # ── Source A: discovery metadata (from Stage 1) ───────────────────────
        "processo_id":       link.processo_id,
        "url":               link.url,
        "company_name":      link.company_name,
        "company_cnpj":      link.company_cnpj,
        "contract_value":    link.contract_value,
        "discovery_path":    link.discovery_path,
        # ── Source B: extraction results ──────────────────────────────────────
        "page_count":        extraction.get("pages", 0),
        "extraction_method": extraction.get("source", "unknown"),
        "fallback_used":     extraction.get("source", "pymupdf") != "pymupdf",
        "total_chars":       extraction.get("total_chars", 0),
        "total_words":       len(raw_text.split()) if raw_text else 0,
        "quality_passes":    extraction.get("quality_passes", False),
        "quality_flags":     extraction.get("quality_flags", []),
        # ── Raw contract text (CRITICAL: complete, not truncated) ─────────────
        "raw_text":          raw_text,
        "extraction_error":  extraction.get("error"),
        # ── Timestamps ────────────────────────────────────────────────────────
        "extracted_at":      datetime.now().isoformat(),
        # ── PDF metadata ──────────────────────────────────────────────────────
        "metadata": {
            "pdf_size_bytes":          extraction.get("pdf_size_bytes"),
            "processing_time_seconds": extraction.get("processing_time_seconds"),
        },
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
    - Maximum 1 PDF in data/temp/ at any time
    - All extractions saved as {id}_raw.json
    - extraction_progress.json updated after every document
    - Quality validation run on every extraction
    """

    def __init__(self, driver: webdriver.Chrome):
        self.driver      = driver
        self.captcha     = CaptchaHandler(driver)
        self._session_ok = False

    # ── Driver health ────────────────────────────────────────────────────────

    def _is_driver_alive(self) -> bool:
        """
        Check whether the Chrome session is still responsive.

        Uses window_handles as the lightest possible probe — it requires
        a round-trip to the browser process but does not navigate anywhere
        or load any page. Returns False on any exception, which covers:
          - InvalidSessionIdException  (browser crashed)
          - WebDriverException         (process killed)
          - Any other Selenium error   (unexpected state)
        """
        try:
            _ = self.driver.window_handles
            return True
        except Exception:
            return False

    def _restart_driver(self) -> bool:
        """
        Quit the dead driver and create a fresh Chrome session.

        Resets all session state so the next _process_one call starts
        clean: new browser, new CAPTCHA handler, CAPTCHA flag cleared.

        Returns True if the new driver was created successfully,
        False if create_driver itself failed (rare — pipeline will stop).
        """
        logger.warning(
            "\n⚠  WebDriver session is dead — restarting browser...\n"
            "   Progress is saved. The pipeline will continue from the "
            "next unprocessed contract."
        )

        # Attempt graceful quit — ignore errors since driver is already dead
        try:
            self.driver.quit()
        except Exception:
            pass

        new_driver = create_driver(headless=False, anti_detection=True)
        if not new_driver:
            logger.error("   ✗ Could not restart WebDriver — stopping pipeline.")
            return False

        # Replace driver on this instance and reset all session state
        self.driver      = new_driver
        self.captcha     = CaptchaHandler(new_driver)
        self._session_ok = False

        logger.info("   ✓ WebDriver restarted successfully.")
        return True

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
        no_doc  = 0
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

            # ── Skip already done ──────────────────────────────────────────────
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

            # ── Driver health check before every contract ──────────────────
            if not self._is_driver_alive():
                if not self._restart_driver():
                    logger.error("   ✗ Driver restart failed — aborting pipeline.")
                    break   # progress already saved; re-run will resume here

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

            except NoDocumentError:
                # Document not yet uploaded — will be retried on next run
                no_doc += 1
                _mark_no_document(progress, pid)
                logger.warning(
                    f"   📭 {pid} — no document on portal yet "
                    f"(will retry on next run)"
                )

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
        logger.info(f"   Total       : {total}")
        logger.info(f"   Skipped     : {skipped} (already extracted)")
        logger.info(f"   Success     : {success}")
        logger.info(f"   No document : {no_doc} (portal pending — will retry)")
        logger.info(f"   Failed      : {failed} (technical errors)")
        logger.info(f"   Progress    : {PROGRESS_FILE}")
        logger.info("=" * 70)

        return {
            "total":       total,
            "skipped":     skipped,
            "success":     success,
            "no_document": no_doc,
            "failed":      failed,
            "errors":      errors,
        }

    # ── Single document ───────────────────────────────────────────────────────

    def _process_one(self, link: ProcessoLink) -> bool:
        """
        Navigate → CAPTCHA → Download PDF → Extract text → Save JSON → Delete PDF.

        Ensures PDF is deleted in all exit paths (success, failure, exception).
        Returns True if a JSON file was saved successfully.

        CHANGE 3: records pdf_size_bytes and processing_time_seconds before
        calling _save_extraction so the metadata block is populated.
        """
        pdf_path = None
        try:
            # Step 1: Navigate
            self.driver.get(link.url)
            time.sleep(PAGE_LOAD_WAIT)

            # Step 1.5: Early no-document check — BEFORE CAPTCHA handling.
            # If the portal already shows an error page, stop immediately.
            # Prevents the CAPTCHA handler interacting with an error page
            # and crashing the browser session (invalid session id).
            self._check_no_document_on_page()

            # Step 2: CAPTCHA
            if not self._ensure_past_captcha():
                logger.error("   ✗ Could not pass CAPTCHA — skipping")
                return False

            # Step 3 + 4: Download each matching PDF, OCR it, concatenate
            pdf_urls = self._find_pdf_urls()
            if not pdf_urls:
                logger.error("   ✗ No contract-body PDF found on page")
                return False

            logger.info(f"   📎 {len(pdf_urls)} contract document(s) to process")

            combined_text  = []
            total_pages    = 0
            total_size     = 0
            t_start        = time.time()
            pdf_paths      = []   # track for cleanup in finally

            try:
                for idx, url in enumerate(pdf_urls, 1):
                    part_id  = f"{_sanitize(link.processo_id)}_part{idx}"
                    pdf_path = self._download_one_pdf(url, part_id)
                    if not pdf_path:
                        logger.warning(f"   ⚠  Part {idx} download failed — skipping")
                        continue
                    pdf_paths.append(pdf_path)
                    total_size += pdf_path.stat().st_size

                    logger.info(f"   📄 OCR part {idx}/{len(pdf_urls)}...")
                    result = extract_text(str(pdf_path))
                    if result["success"]:
                        combined_text.append(result["text"])
                        total_pages += result["pages"]
                    else:
                        logger.warning(
                            f"   ⚠  Part {idx} OCR failed: {result.get('error')}"
                        )

            finally:
                # Delete ALL temp PDFs — max 1 on disk is per-document,
                # here we clean up all parts at once after extraction.
                for p in pdf_paths:
                    _delete_pdf(p)

            if not combined_text:
                logger.error("   ✗ All parts failed OCR — nothing to save")
                return False

            # Merge all parts with a clear separator
            merged_text = "\n\n--- DOCUMENT PART SEPARATOR ---\n\n".join(combined_text)
            elapsed     = round(time.time() - t_start, 2)

            # Build a single extraction dict for _save_extraction
            from infrastructure.extractors.pdf_text_extractor import _quality_check
            qc = _quality_check(merged_text)

            extraction = {
                "success":        True,
                "text":           merged_text,
                "pages":          total_pages,
                "source":         "ocr",
                "pdf_path":       f"{len(pdf_urls)} parts",
                "total_chars":    qc["total_chars"],
                "quality_passes": qc["passes"],
                "quality_flags":  qc["flags"],
                "error":          None,
                "pdf_size_bytes":          total_size,
                "processing_time_seconds": elapsed,
                "parts_count":             len(pdf_urls),
            }

            if qc["passes"]:
                logger.info(
                    f"   ✓ {qc['total_chars']:,} chars, {total_pages} page(s) "
                    f"[{len(pdf_urls)} part(s), OCR, {elapsed}s]"
                )
            else:
                logger.warning(
                    f"   ⚠ Low-quality OCR: {qc['flags']} — saving for manual review"
                )

            # Step 5: Save JSON
            # pdf_path is now None — cleanup already done in the try/finally above
            return _save_extraction(link, extraction)

        except FileNotFoundError as e:
            # Safety net: unexpected file-system or URL failure NOT caused
            # by the "Não há documento associado" portal message.
            # That case raises NoDocumentError and propagates to download_all.
            logger.error(f"   ✗ File not found (unexpected): {e}")
            return False

        # NoDocumentError intentionally NOT caught here.
        # It propagates up to download_all → _mark_no_document (retry later).

        # Note: PDF cleanup is now handled inside the multi-part loop above.
        # Each part PDF is deleted immediately after OCR in the try/finally
        # block within Step 3+4. No outer cleanup needed here.

    # ── CAPTCHA ───────────────────────────────────────────────────────────────

    # ── No-document detection ────────────────────────────────────────────────

    # All known portal messages that mean "no PDF exists yet".
    # Checked both on raw page text and on .alert-danger elements.
    _NO_DOCUMENT_MESSAGES = [
        "Não há documento associado",   # primary message
        "Documento não encontrado",     # alternate message observed in the wild
    ]

    def _check_no_document_on_page(self) -> None:
        """
        Scan the current page for any known "no document" portal messages.

        Called immediately after navigation, before CAPTCHA handling, so
        we never hand an error page to the CAPTCHA handler (which would
        crash the browser session with invalid session id).

        Raises NoDocumentError if any known message is detected.
        Does nothing if the page looks normal.
        """
        try:
            # Check 1: .alert-danger paragraph elements (most specific)
            alerts = self.driver.find_elements(
                By.CSS_SELECTOR, "p.alert.alert-danger, div.alert.alert-danger"
            )
            for alert in alerts:
                text = alert.text or ""
                for msg in self._NO_DOCUMENT_MESSAGES:
                    if msg in text:
                        raise NoDocumentError(
                            f"Portal error detected early: '{text.strip()}'"
                        )

            # Check 2: full page body text (catches different HTML structures)
            body_text = self.driver.find_element(By.TAG_NAME, "body").text or ""
            for msg in self._NO_DOCUMENT_MESSAGES:
                if msg in body_text:
                    raise NoDocumentError(
                        f"Portal no-document message in page body: '{msg}'"
                    )

        except NoDocumentError:
            raise   # re-raise — do NOT swallow our own exception
        except Exception:
            pass    # any Selenium error here means the page is loading normally

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

    def _download_one_pdf(self, url: str, safe_id: str) -> Optional[Path]:
        """
        Download a single PDF from a direct URL using the current session cookies.

        Args:
            url:     Full PDF download URL.
            safe_id: Sanitised filename stem (no extension).

        Returns:
            Path to the downloaded file, or None on failure.
        """
        out_path = TEMP_PDF_DIR / f"{safe_id}.pdf"
        TEMP_PDF_DIR.mkdir(parents=True, exist_ok=True)

        # Reuse browser session cookies so authenticated URLs work
        cookies = {c["name"]: c["value"] for c in self.driver.get_cookies()}
        headers = {
            "User-Agent": self.driver.execute_script("return navigator.userAgent;")
        }

        try:
            resp = requests.get(
                url,
                cookies=cookies,
                headers=headers,
                timeout=60,
                stream=True,
            )
            resp.raise_for_status()

            with open(out_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)

            logger.info(
                f"   📥 Downloaded: {out_path.name} "
                f"({out_path.stat().st_size / 1024:.1f} KB)"
            )
            return out_path

        except Exception as e:
            logger.error(f"   ✗ PDF download failed ({out_path.name}): {e}")
            _delete_pdf(out_path)
            return None

    # ── PDF URL discovery ─────────────────────────────────────────────────────

    # Label that identifies the contract body document.
    # Only <li> items whose visible text contains this string are downloaded.
    CONTRACT_BODY_LABEL = "Íntegra do contrato/demais instrumentos jurídicos celebrados"

    def _find_pdf_urls(self) -> List[str]:
        """
        Return PDF download URLs for contract-body documents only.

        Filters <li> elements by label text so that additive terms
        ("Termos Aditivos"), legal opinions, and other attachments are
        ignored. Only items whose visible text contains CONTRACT_BODY_LABEL
        are included.

        If multiple matching items exist (e.g. a contract with several
        consolidated versions) all their URLs are returned and their text
        will be concatenated by the caller.

        Second-line no-document defence: raises NoDocumentError if any
        known error message is still present after CAPTCHA handling.
        """
        time.sleep(3)

        # Belt-and-suspenders no-document check
        try:
            alerts = self.driver.find_elements(
                By.CSS_SELECTOR, "p.alert.alert-danger, div.alert.alert-danger"
            )
            for alert in alerts:
                text = alert.text or ""
                for msg in self._NO_DOCUMENT_MESSAGES:
                    if msg in text:
                        raise NoDocumentError(
                            f"No-document alert still present after CAPTCHA: '{text.strip()}'"
                        )
        except NoDocumentError:
            raise

        # Walk every <li> that contains an acrobat PDF icon.
        # Only keep those whose text matches the contract-body label.
        list_items = self.driver.find_elements(By.XPATH, "//li[.//img[contains(@src, 'page_white_acrobat.png')]]")

        pdf_urls = []
        base_url = self.driver.current_url

        for li in list_items:
            li_text = li.text or ""
            if self.CONTRACT_BODY_LABEL not in li_text:
                logger.debug(
                    f"   ⏭  Skipping non-contract document: "
                    f"{li_text[:80].strip()!r}"
                )
                continue

            # Extract the <a href> from this matched <li>
            try:
                anchor = li.find_element(
                    By.XPATH, ".//a[img[contains(@src, 'page_white_acrobat.png')]]"
                )
                href = anchor.get_attribute("href")
                if href:
                    full_url = urljoin(base_url, href)
                    if full_url not in pdf_urls:
                        pdf_urls.append(full_url)
                        logger.info(
                            f"   📎 Contract document found: "
                            f"{li_text[:80].strip()}"
                        )
            except NoSuchElementException:
                continue

        if not pdf_urls:
            logger.warning(
                f"   ⚠  No items matching contract label found on page. "
                f"Label searched: {self.CONTRACT_BODY_LABEL!r}"
            )

        return pdf_urls