"""
infrastructure/scrapers/doweb/downloader.py

Stage 3 — Download publication PDFs from DoWeb and save structured JSON.

Responsibility
──────────────
Orchestrates the full Stage 3 pipeline for every processo ID:

    1. Check for embedded publication flag (Gap 4) — skip DoWeb if found
    2. Call DoWebSearcher.search() to get result rows
    3. For each result: download the PDF page with requests.get()
    4. Run OCR via publication_extractor.extract_text()
    5. Delete the PDF immediately (max 1 PDF in temp/ at any time)
    6. Bundle all publication texts into one JSON per processo
    7. Track progress so any crash is resumable with zero data loss

This file does NOT search DoWeb — that belongs to searcher.py.
This file does NOT run OCR logic — that belongs to publication_extractor.py.

Gap 4 — Embedded publication short-circuit
──────────────────────────────────────────
contract_preprocessor.py writes:
    data/preprocessed/{sanitized_pid}_pub_embedded.flag
when it finds a gazette EXTRATO inside the contract PDF itself.
download_all() checks for this flag before any DoWeb network activity.
If present, the processo is marked completed and DoWeb is skipped entirely.

Output JSON per processo
────────────────────────
{
  "processo_id":        "TUR-PRO-2025/01221",
  "discovery_metadata": { "company_name": ..., "company_cnpj": ..., ... },
  "search_metadata":    { "searched_at": ..., "query_used": ..., "results_found": ... },
  "publications": [
    {
      "document_index":  1,
      "total_documents": 2,
      "publication_metadata": {
        "source_url":       "https://doweb.rio.rj.gov.br/portal/edicoes/download/13894/38",
        "publication_date": "03/02/2026",
        "edition_number":   "218",
        "page_number":      "38",
        "content_hint":     "structured_contract"
      },
      "extraction_metadata": {
        "method": "ocr", "pages": 1, "text_length": 4823,
        "printable_ratio": 0.97, "extracted_at": "..."
      },
      "validation": {
        "quality_passes": true, "quality_flags": [],
        "processo_found_in_text": true, "extraction_error": null
      },
      "raw_text": "...complete OCR text..."
    }
  ]
}

Progress file: data/publication_extraction_progress.json
Output files:  data/extractions/{PROCESSO_ID}_publications_raw.json
Temp folder:   data/temp_downloads/  (max 1 PDF at any time)
"""

import json
import logging
import re
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import requests
from selenium import webdriver

from config.settings import EXTRACTIONS_DIR
from infrastructure.scrapers.doweb.searcher import DoWebSearcher, SearchResultItem
from infrastructure.extractors.publication_extractor import extract_text

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# PATHS & CONSTANTS
# ══════════════════════════════════════════════════════════════════════════════

EXTRACTIONS_DIR      = Path(EXTRACTIONS_DIR)
TEMP_PDF_DIR         = Path("data/temp_downloads")
PROGRESS_FILE        = Path("data/publication_extraction_progress.json")
DISCOVERY_FILE       = Path("data/discovery/processo_links.json")
PREPROCESSED_DIR     = Path("data/preprocessed")

BETWEEN_PROCESSOS    = 2    # polite pause between processo searches
BETWEEN_DOWNLOADS    = 1    # polite pause between publication downloads
PDF_DOWNLOAD_TIMEOUT = 30   # requests.get timeout in seconds

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept":  "application/pdf,*/*",
    "Referer": "https://doweb.rio.rj.gov.br/",
}


# ══════════════════════════════════════════════════════════════════════════════
# FILE NAMING
# ══════════════════════════════════════════════════════════════════════════════

def _sanitize(processo_id: str) -> str:
    """'TUR-PRO-2025/01221' → 'TUR-PRO-2025_01221'  (safe filename)."""
    return processo_id.replace("/", "_").replace("\\", "_")


def _publications_path(processo_id: str) -> Path:
    """Returns data/extractions/{id}_publications_raw.json."""
    return EXTRACTIONS_DIR / f"{_sanitize(processo_id)}_publications_raw.json"


def _temp_pdf_path(processo_id: str, doc_index: int) -> Path:
    """Returns data/temp_downloads/{id}_pub_{N}.pdf."""
    return TEMP_PDF_DIR / f"{_sanitize(processo_id)}_pub_{doc_index}.pdf"


def _is_already_extracted(processo_id: str) -> bool:
    return _publications_path(processo_id).exists()


# ══════════════════════════════════════════════════════════════════════════════
# GAP 4 — EMBEDDED PUBLICATION CHECK
# ══════════════════════════════════════════════════════════════════════════════

def _has_embedded_publication(processo_id: str) -> bool:
    """
    Return True if the preprocessor found a gazette EXTRATO inside the
    contract PDF for this processo_id.

    The flag file is written by contract_preprocessor._save() when
    embedded_publication["found"] is True:
        data/preprocessed/{sanitized_pid}_pub_embedded.flag
    """
    flag = PREPROCESSED_DIR / f"{_sanitize(processo_id)}_pub_embedded.flag"
    return flag.exists()


def _mark_embedded(progress: dict, processo_id: str) -> None:
    """
    Record this processo_id as resolved via embedded publication.
    Added to both the 'embedded' list and 'completed' so standard
    skip logic catches it on all future runs.
    """
    if "embedded" not in progress:
        progress["embedded"] = []
    if processo_id not in progress["embedded"]:
        progress["embedded"].append(processo_id)
    if processo_id not in progress.get("completed", []):
        progress.setdefault("completed", []).append(processo_id)
    progress["stats"]["embedded"] = len(progress["embedded"])
    progress["updated_at"] = datetime.now().isoformat()


# ══════════════════════════════════════════════════════════════════════════════
# DISCOVERY LOADERS
# ══════════════════════════════════════════════════════════════════════════════

def load_processo_ids(
    discovery_file: str = str(DISCOVERY_FILE),
) -> List[str]:
    """
    Load the list of processo IDs produced by Stage 1.
    Returns a deduplicated list preserving discovery order.
    """
    path = Path(discovery_file)
    if not path.exists():
        logger.error(
            f"Discovery file not found: {path}\n"
            f"Run Stage 1 first to produce processo_links.json."
        )
        return []

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    processos = data.get("processos", [])
    seen: set = set()
    ids: List[str] = []
    for p in processos:
        pid = p.get("processo_id", "").strip()
        if pid and pid not in seen:
            seen.add(pid)
            ids.append(pid)

    logger.info(
        f"   📂 Loaded {len(ids)} unique processo IDs "
        f"({len(processos) - len(ids)} duplicates removed)"
    )
    return ids


def load_discovery_metadata(
    discovery_file: str = str(DISCOVERY_FILE),
) -> dict:
    """
    Load company metadata keyed by processo_id from Stage 1 discovery.
    Returns dict: { processo_id: { company_name, company_cnpj, ... } }
    """
    path = Path(discovery_file)
    if not path.exists():
        return {}

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    metadata: dict = {}
    for p in data.get("processos", []):
        pid = p.get("processo_id", "").strip()
        if pid:
            metadata[pid] = {
                "company_name":   p.get("company_name", ""),
                "company_cnpj":   p.get("company_cnpj", ""),
                "contract_value": p.get("contract_value", ""),
                "discovery_path": p.get("discovery_path", []),
            }
    return metadata


# ══════════════════════════════════════════════════════════════════════════════
# PROGRESS TRACKING
# ══════════════════════════════════════════════════════════════════════════════

def _load_progress() -> dict:
    """
    Load Stage 3 progress file, or return a fresh skeleton.

    Progress states:
        completed   — all publications extracted successfully
        failed      — technical error (retried next run)
        no_results  — DoWeb returned 0 results (retried every run)
        partial     — some publications failed OCR (retried with --force)
        embedded    — publication found inside contract PDF; DoWeb skipped
    """
    if PROGRESS_FILE.exists():
        try:
            with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            logger.info(
                f"   📂 Resuming Stage 3: "
                f"{len(data.get('completed', []))} completed, "
                f"{len(data.get('failed', []))} failed, "
                f"{len(data.get('no_results', []))} no_results, "
                f"{len(data.get('partial', []))} partial, "
                f"{len(data.get('embedded', []))} embedded"
            )
            return data
        except Exception as e:
            logger.warning(f"   ⚠ Could not read progress file: {e} — starting fresh")

    return {
        "started_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "completed":  [],
        "failed":     [],
        "no_results": [],
        "partial":    [],
        "embedded":   [],
        "stats": {
            "total":      0,
            "success":    0,
            "failed":     0,
            "no_results": 0,
            "partial":    0,
            "skipped":    0,
            "embedded":   0,
        },
    }


def _save_progress(progress: dict) -> None:
    """Persist progress to disk — called after EVERY processo."""
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


def _mark_no_results(progress: dict, processo_id: str) -> None:
    """
    Record that DoWeb returned 0 results for all ID variations.
    NOT added to completed/failed — retried on every future run.
    May indicate an R001 compliance violation.
    """
    progress["no_results"].append({
        "processo_id": processo_id,
        "at":          datetime.now().isoformat(),
    })
    progress["stats"]["no_results"] = progress["stats"].get("no_results", 0) + 1


def _mark_partial(
    progress:    dict,
    processo_id: str,
    successful:  int,
    failed:      int,
) -> None:
    """
    Record that some (but not all) publications were extracted.
    NOT added to completed — skipped on reruns unless --force is used.
    """
    progress["partial"].append({
        "processo_id": processo_id,
        "successful":  successful,
        "failed":      failed,
        "at":          datetime.now().isoformat(),
    })
    progress["stats"]["partial"] = progress["stats"].get("partial", 0) + 1


# ══════════════════════════════════════════════════════════════════════════════
# PDF DOWNLOAD & CLEANUP
# ══════════════════════════════════════════════════════════════════════════════

def _download_pdf(url: str, dest_path: Path) -> bool:
    """
    Download a gazette page PDF using requests.get().
    Uses requests (not Selenium) because pdf_page_url is a direct public link
    that requires no session state or CAPTCHA.
    """
    if not url:
        logger.warning("   ⚠ pdf_page_url is empty — cannot download")
        return False

    try:
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        response = requests.get(
            url,
            headers=REQUEST_HEADERS,
            timeout=PDF_DOWNLOAD_TIMEOUT,
            stream=True,
        )
        response.raise_for_status()

        with open(dest_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

        size_kb = dest_path.stat().st_size / 1024
        logger.debug(f"   📥 Downloaded: {dest_path.name} ({size_kb:.1f} KB)")
        return True

    except requests.exceptions.Timeout:
        logger.error(f"   ✗ Download timed out after {PDF_DOWNLOAD_TIMEOUT}s: {url}")
        return False
    except requests.exceptions.HTTPError as e:
        logger.error(f"   ✗ HTTP error downloading {url}: {e}")
        return False
    except requests.exceptions.RequestException as e:
        logger.error(f"   ✗ Network error downloading {url}: {e}")
        return False
    except OSError as e:
        logger.error(f"   ✗ File system error saving PDF: {e}")
        return False


def _delete_pdf(path: Optional[Path]) -> None:
    """
    Delete temp PDF — called in finally blocks to guarantee max 1 PDF on disk.
    Silent on missing files (already deleted or never created).
    """
    if path is None:
        return
    try:
        if path.exists():
            path.unlink()
            logger.debug(f"   🗑  Deleted temp PDF: {path.name}")
    except Exception as e:
        logger.warning(f"   ⚠ Could not delete temp PDF {path}: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# JSON STORAGE
# ══════════════════════════════════════════════════════════════════════════════

def _build_publication_record(
    result:      "SearchResultItem",
    ocr_result:  dict,
    processo_id: str,
) -> dict:
    """
    Build a single publication record for the publications list.
    Called for every SearchResultItem — including failures (stub records).
    """
    raw_text  = ocr_result.get("text", "")
    error     = ocr_result.get("error")
    qc_passes = ocr_result.get("quality_passes", False)
    qc_flags  = ocr_result.get("quality_flags", [])

    processo_found = bool(
        re.search(re.escape(processo_id), raw_text, re.IGNORECASE)
    ) if raw_text else False

    return {
        "document_index":   result.document_index,
        "total_documents":  result.total_documents,
        "publication_metadata": {
            "source_url":       result.pdf_page_url,
            "publication_date": result.publication_date,
            "edition_number":   result.edition_number,
            "page_number":      result.page_number,
            "content_hint":     result.content_hint,
            "snippet":          result.snippet,
        },
        "extraction_metadata": {
            "method":          ocr_result.get("source", "failed"),
            "pages":           ocr_result.get("pages", 0),
            "text_length":     len(raw_text),
            "printable_ratio": ocr_result.get("printable_ratio",
                                   ocr_result.get("quality_ratio", 0.0)),
            "extracted_at":    datetime.now().isoformat(),
        },
        "validation": {
            "quality_passes":         qc_passes,
            "quality_flags":          qc_flags,
            "processo_found_in_text": processo_found,
            "extraction_error":       error,
        },
        "raw_text": raw_text,
    }


def _save_publications_json(
    processo_id:         str,
    discovery_meta:      dict,
    search_meta:         dict,
    publication_records: List[dict],
) -> bool:
    """
    Write the multi-document publications JSON for one processo.
    Called once per processo after ALL publications have been processed.
    """
    out_path = _publications_path(processo_id)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    document = {
        "processo_id":        processo_id,
        "discovery_metadata": discovery_meta,
        "search_metadata":    search_meta,
        "publications":       publication_records,
    }

    try:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(document, f, ensure_ascii=False, indent=2)
        size_kb = out_path.stat().st_size / 1024
        logger.info(
            f"   💾 Saved: {out_path.name} "
            f"({len(publication_records)} publication(s), {size_kb:.1f} KB)"
        )
        return True
    except Exception as e:
        logger.error(f"   ✗ Could not save publications JSON: {e}")
        return False


# ══════════════════════════════════════════════════════════════════════════════
# MAIN DOWNLOADER CLASS
# ══════════════════════════════════════════════════════════════════════════════

class DoWebDownloader:
    """
    Downloads and extracts all publications for a list of processo IDs.

    One instance is created per Stage 3 run. The shared browser session
    (and any solved CAPTCHA) is preserved across all searches.

    Usage
    ─────
        driver     = create_driver(headless=False, anti_detection=True)
        downloader = DoWebDownloader(driver)
        summary    = downloader.download_all(processo_ids, force=False)
        close_driver(driver)
    """

    def __init__(self, driver: webdriver.Chrome):
        self.driver   = driver
        self.searcher = DoWebSearcher(driver)

    # ══════════════════════════════════════════════════════
    # PUBLIC ENTRY POINT
    # ══════════════════════════════════════════════════════

    def download_all(
        self,
        processo_ids:   List[str],
        force:          bool = False,
        discovery_meta: Optional[dict] = None,
    ) -> dict:
        """
        Run the full Stage 3 pipeline for every processo ID.

        Skip rules (in priority order):
            1. embedded flag exists  → skip DoWeb entirely (Gap 4)
            2. completed + extracted → skip (unless force=True)
            3. partial               → skip (unless force=True)
            4. no_results            → retry every run
            5. failed                → retry every run
        """
        TEMP_PDF_DIR.mkdir(parents=True, exist_ok=True)
        EXTRACTIONS_DIR.mkdir(parents=True, exist_ok=True)

        if discovery_meta is None:
            discovery_meta = {}

        progress    = _load_progress()
        completed   = set(progress.get("completed", []))
        partial_ids = {e["processo_id"] for e in progress.get("partial", [])}

        total            = len(processo_ids)
        skipped          = 0
        success          = 0
        failed           = 0
        no_results_count = 0
        partial_count    = 0
        embedded_count   = 0

        progress["stats"]["total"] = total
        _save_progress(progress)

        logger.info("=" * 70)
        logger.info(f"📰 STAGE 3: PUBLICATION EXTRACTION — {total} processo(s)")
        logger.info(f"   Completed : {len(completed)}")
        logger.info(f"   Partial   : {len(partial_ids)}")
        logger.info(f"   Embedded  : {len(progress.get('embedded', []))}")
        logger.info(f"   Force mode: {force}")
        logger.info("=" * 70)

        for i, pid in enumerate(processo_ids, 1):
            label = f"[{i}/{total}] {pid}"

            # ── Skip: embedded publication (Gap 4) ───────────────────────────
            # Check BEFORE the completed/partial skip so a previously-failed
            # processo that now has a flag is resolved without a DoWeb attempt.
            if _has_embedded_publication(pid):
                logger.info(
                    f"   📎 {label} — publication embedded in contract PDF "
                    f"(preprocessor flag) — skipping DoWeb"
                )
                _mark_embedded(progress, pid)
                _save_progress(progress)
                skipped       += 1
                embedded_count += 1
                progress["stats"]["skipped"] = (
                    progress["stats"].get("skipped", 0) + 1
                )
                continue

            # ── Skip: already completed or partial ───────────────────────────
            if not force:
                if pid in completed and _is_already_extracted(pid):
                    logger.info(f"   ⏭  {label} — already completed")
                    skipped += 1
                    progress["stats"]["skipped"] = (
                        progress["stats"].get("skipped", 0) + 1
                    )
                    continue

                if pid in partial_ids:
                    logger.info(
                        f"   ⏭  {label} — partial (use --force to retry)"
                    )
                    skipped += 1
                    progress["stats"]["skipped"] = (
                        progress["stats"].get("skipped", 0) + 1
                    )
                    continue

            logger.info(f"\n   {label}")

            # ── Driver health check ──────────────────────────────────────────
            if not self._is_driver_alive():
                logger.error(
                    "   ✗ Browser session is dead — cannot continue Stage 3.\n"
                    "     Progress is saved. Restart the script to resume."
                )
                break

            # ── Process this processo ────────────────────────────────────────
            try:
                outcome = self._process_one(
                    processo_id    = pid,
                    discovery_meta = discovery_meta.get(pid, {}),
                    progress       = progress,
                )
            except KeyboardInterrupt:
                logger.info("\n   ⚠ Interrupted by user — progress saved")
                _save_progress(progress)
                raise
            except Exception as exc:
                logger.error(f"   ✗ Unexpected error on '{pid}': {exc}")
                _mark_failed(progress, pid, str(exc))
                outcome = "failed"

            # ── Tally outcomes ───────────────────────────────────────────────
            if outcome == "completed":
                success += 1
                completed.add(pid)
            elif outcome == "no_results":
                no_results_count += 1
            elif outcome == "partial":
                partial_count += 1
            else:
                failed += 1

            _save_progress(progress)
            time.sleep(BETWEEN_PROCESSOS)

        # ── Final summary ────────────────────────────────────────────────────
        summary = {
            "total":      total,
            "success":    success,
            "failed":     failed,
            "no_results": no_results_count,
            "partial":    partial_count,
            "skipped":    skipped,
            "embedded":   embedded_count,
        }
        logger.info("\n" + "=" * 70)
        logger.info("✅ STAGE 3 COMPLETE")
        for k, v in summary.items():
            logger.info(f"   {k:12}: {v}")
        logger.info("=" * 70)

        return summary

    # ══════════════════════════════════════════════════════
    # SINGLE PROCESSO PROCESSING
    # ══════════════════════════════════════════════════════

    def _process_one(
        self,
        processo_id:    str,
        discovery_meta: dict,
        progress:       dict,
    ) -> str:
        """
        Full pipeline for a single processo ID.

        Flow:
            1. Search DoWeb → List[SearchResultItem]
            2. If empty → mark no_results, return
            3. For each result → download PDF, OCR, delete PDF
            4. Build publication records (stubs for failures too)
            5. Save publications JSON
            6. Mark completed or partial

        Returns:
            "completed"  — all publications extracted and saved
            "no_results" — DoWeb returned 0 results
            "partial"    — some publications failed; partial JSON saved
            "failed"     — could not save JSON or other fatal error
        """
        # ── Step 1: Search ────────────────────────────────────────────────────
        try:
            results = self.searcher.search(processo_id)
        except Exception as exc:
            msg = f"Search failed: {exc}"
            logger.error(f"   ✗ {msg}")
            _mark_failed(progress, processo_id, msg)
            return "failed"

        # ── Step 2: No results ────────────────────────────────────────────────
        if not results:
            logger.info(
                f"   ○ No publications found — marking as no_results\n"
                f"     (audit note: may indicate R001 violation)"
            )
            _mark_no_results(progress, processo_id)
            return "no_results"

        logger.info(f"   📄 {len(results)} publication(s) to download")

        search_meta = {
            "searched_at":   datetime.now().isoformat(),
            "query_used":    results[0].query_used if results else "",
            "results_found": len(results),
        }

        # ── Step 3: Download and extract each publication ─────────────────────
        publication_records: List[dict] = []
        ocr_successes = 0
        ocr_failures  = 0

        for result in results:
            logger.info(
                f"   [{result.document_index}/{result.total_documents}] "
                f"ed={result.edition_number} pg={result.page_number} "
                f"date={result.publication_date}"
            )
            record = self._download_and_extract(result, processo_id)
            publication_records.append(record)

            if record["validation"]["extraction_error"] is None:
                ocr_successes += 1
            else:
                ocr_failures += 1

            time.sleep(BETWEEN_DOWNLOADS)

        # ── Step 4: Save JSON ─────────────────────────────────────────────────
        saved = _save_publications_json(
            processo_id          = processo_id,
            discovery_meta       = discovery_meta,
            search_meta          = search_meta,
            publication_records  = publication_records,
        )

        if not saved:
            _mark_failed(progress, processo_id, "Could not write publications JSON")
            return "failed"

        # ── Step 5: Mark outcome ──────────────────────────────────────────────
        if ocr_failures == 0:
            _mark_completed(progress, processo_id)
            logger.info(f"   ✓ Completed: {ocr_successes} publication(s) extracted")
            return "completed"
        else:
            _mark_partial(progress, processo_id, ocr_successes, ocr_failures)
            logger.warning(
                f"   ⚠ Partial: {ocr_successes} OK, {ocr_failures} failed\n"
                f"     Run with --force to retry failed publications"
            )
            return "partial"

    # ══════════════════════════════════════════════════════
    # DOWNLOAD + OCR FOR ONE PUBLICATION
    # ══════════════════════════════════════════════════════

    def _download_and_extract(
        self,
        result:      "SearchResultItem",
        processo_id: str,
    ) -> dict:
        """
        Download the PDF page, run OCR, delete the PDF, return a record.

        PDF is always deleted in the finally block — guarantees max 1 PDF
        in temp_downloads/ at any time, even if OCR crashes.
        Returns a stub record on any failure so the publications list
        in the output JSON is always complete.
        """
        pdf_path = _temp_pdf_path(processo_id, result.document_index)

        try:
            # ── Download ─────────────────────────────────────────────────────
            downloaded = _download_pdf(result.pdf_page_url, pdf_path)

            if not downloaded:
                return _build_publication_record(
                    result      = result,
                    ocr_result  = {
                        "text": "", "error": "PDF download failed",
                        "source": "failed", "pages": 0,
                        "quality_passes": False,
                        "quality_flags":  ["download_failed"],
                    },
                    processo_id = processo_id,
                )

            # ── OCR ───────────────────────────────────────────────────────────
            ocr_result = extract_text(str(pdf_path), processo_id)

            if not ocr_result.get("success"):
                error_msg = ocr_result.get("error", "OCR returned no text")
                logger.warning(f"   ⚠ OCR failed: {error_msg}")
                return _build_publication_record(
                    result      = result,
                    ocr_result  = {
                        "text": "", "error": error_msg,
                        "source": "failed", "pages": 0,
                        "quality_passes": False,
                        "quality_flags":  ["ocr_failed"],
                    },
                    processo_id = processo_id,
                )

            if ocr_result.get("quality_passes"):
                logger.info(
                    f"   ✓ OCR OK: {ocr_result.get('total_chars', 0):,} chars, "
                    f"{ocr_result.get('pages', 0)} page(s)"
                )
            else:
                logger.warning(
                    f"   ⚠ Low-quality OCR: {ocr_result.get('quality_flags', [])} "
                    f"— saving for manual review"
                )

            return _build_publication_record(
                result      = result,
                ocr_result  = ocr_result,
                processo_id = processo_id,
            )

        except Exception as exc:
            logger.error(
                f"   ✗ Unexpected error on publication "
                f"{result.document_index}/{result.total_documents}: {exc}"
            )
            return _build_publication_record(
                result      = result,
                ocr_result  = {
                    "text": "", "error": str(exc),
                    "source": "failed", "pages": 0,
                    "quality_passes": False,
                    "quality_flags":  ["unexpected_error"],
                },
                processo_id = processo_id,
            )

        finally:
            _delete_pdf(pdf_path)

    # ══════════════════════════════════════════════════════
    # DRIVER HEALTH
    # ══════════════════════════════════════════════════════

    def _is_driver_alive(self) -> bool:
        """
        Check if the Chrome session is still responsive.
        Uses window_handles as a lightweight probe — no navigation.
        """
        try:
            _ = self.driver.window_handles
            return True
        except Exception:
            return False