"""
infrastructure/scrapers/doweb/searcher.py

Stage 3 — Search DoWeb portal for publications linked to a processo ID.

Responsibility
──────────────
Given a processo ID, search DoWeb with Busca Exata (exact phrase mode)
and return ALL matching publication result rows as SearchResultItem objects.

This file does NOT download PDFs. That belongs to downloader.py.
This file does NOT save JSON. That belongs to downloader.py.
This file does NOT run OCR.  That belongs to publication_text_extractor.py.

Search strategy
───────────────
1. Detect ID format (A / B / C) and generate up to 8 ordered variations.
2. For each variation, execute a Busca Exata search on DoWeb.
3. On the first variation that returns ≥1 result, collect ALL pages.
4. If all variations return 0, the function returns an empty list
   (caller records this as NO_RESULTS_FOUND).

Why Busca Exata always?
───────────────────────
DoWeb tokenises queries using dots and slashes as delimiters. Without exact
mode, searching "006800.000136/2026-28" returns tens of thousands of results
containing any of the four tokens ["006800", "000136", "2026", "28"].
Busca Exata performs a phrase query — the only reliable way to find a
specific processo publication.

Discard policy
──────────────
ALL results returned by Busca Exata are returned to the caller.
The DoWeb engine guarantees the match — no client-side filtering is applied.
The content_hint field classifies results for downstream use (Epic 4)
but NEVER triggers a discard here.

DoWeb DOM references (confirmed via live inspection)
────────────────────────────────────────────────────
Homepage search input   : <input id="input2" ...>
Results page query field: <input id="q" ng-model="queryTerm" ...>
Busca Exata checkbox    : <input ng-model="fullSearch" ...>   (checked = exact)
Total results count     : <div class="total"><span class="bold">N</span> resultados...>
Page counter            : <div class="total mostrador-paginas"><span>página X de Y</span>
Publication metadata    : <span>publicado em: DD/MM/YYYY - Edição NNN - Pág. NN</span>
Snippet text            : <span ng-bind-html="high | sanitize">...</span>
Download toggle button  : <i class="fa fa-download"></i>  (click to reveal link)
Page-only PDF link      : <a class="link pdf-page" href="...">Baixar apenas a página</a>
Next page button        : <li class="next"><a class="page-link" href="javascript:void(0)"> »</a>

Three ID formats supported
──────────────────────────
Format A: 006800.000136/2026-28   → 8 variations (modern standard)
Format B: TUR-PRO-2025/01221      → 3 variations (organ-type-year)
Format C: 12/500.078/2021         → 3 variations (legacy two-slash)
"""

import logging
import re
import time
from dataclasses import dataclass
from typing import List, Optional, Tuple

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
)

from infrastructure.web.captcha_handler import CaptchaHandler

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ══════════════════════════════════════════════════════════════════════════════

DOWEB_HOME_URL   = "https://doweb.rio.rj.gov.br/"

# Timing — all in seconds
PAGE_LOAD_WAIT    = 8    # wait after navigation / search submission
DOWNLOAD_BTN_WAIT = 5    # wait for "Baixar apenas a página" link to appear (1–3s observed)
BETWEEN_SEARCHES  = 2    # polite pause between variation attempts
BETWEEN_PAGES     = 1.5  # polite pause between pagination clicks
ANGULAR_DIGEST    = 1.5  # wait for Angular to re-render after checkbox toggle


# ══════════════════════════════════════════════════════════════════════════════
# DATA MODEL
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class SearchResultItem:
    """
    One publication result row collected from a DoWeb search.

    All fields except pdf_page_url are populated by parsing the result list
    without any additional navigation.  pdf_page_url requires clicking the
    Download button to reveal the dropdown link.

    content_hint is metadata for Epic 4 (compliance engine).
    It NEVER triggers a download discard in this stage.
    """

    # ── Identity ──────────────────────────────────────────────────────────────
    processo_id:      str   # the ID that was searched
    query_used:       str   # the specific variation that produced this result
    document_index:   int   # 1-based position among ALL results for this ID
    total_documents:  int   # total results found for this search

    # ── From result row (populated without clicking) ──────────────────────────
    publication_date: str   # "03/02/2026"  — from "publicado em:" span
    edition_number:   str   # "218"          — from "Edição NNN"
    page_number:      str   # "38"           — from "Pág. NN"
    snippet:          str   # joined text from all ng-bind-html spans in this row

    # ── Populated after clicking Download button ──────────────────────────────
    pdf_page_url:     str = ""   # href from <a class="link pdf-page">

    # ── Content classification (metadata only — never discards) ───────────────
    content_hint:     str = "unknown"
    # Values:
    #   "structured_contract"  — snippet has Processo {id} 1-Objeto: 2-Partes: pattern
    #   "possible_addendum"    — snippet contains APROVO or AUTORIZO (no structured pattern)
    #   "unknown"              — insufficient context to classify

    def to_dict(self) -> dict:
        """Serialise to a plain dict for JSON storage."""
        return {
            "processo_id":      self.processo_id,
            "query_used":       self.query_used,
            "document_index":   self.document_index,
            "total_documents":  self.total_documents,
            "publication_date": self.publication_date,
            "edition_number":   self.edition_number,
            "page_number":      self.page_number,
            "snippet":          self.snippet,
            "pdf_page_url":     self.pdf_page_url,
            "content_hint":     self.content_hint,
        }


# ══════════════════════════════════════════════════════════════════════════════
# ID NORMALIZER — public functions
# ══════════════════════════════════════════════════════════════════════════════

def detect_format(processo_id: str) -> str:
    """
    Identify which of the three known ID formats applies.

    Format A: 006800.000136/2026-28   digits.digits/year[-check]
    Format B: TUR-PRO-2025/01221      LETTERS-LETTERS-year/number
    Format C: 12/500.078/2021         legacy number/number.number/year

    Returns "A", "B", "C", or "UNKNOWN".
    """
    pid = processo_id.strip()

    if re.match(r'^[A-Z]+-[A-Z]+-\d{4}/\d+$', pid):
        return "B"

    if re.match(r'^\d+/\d+\.\d+/\d{4}$', pid):
        return "C"

    if re.match(r'^\d+\.\d+/\d{4}(?:-\d+)?$', pid):
        return "A"

    return "UNKNOWN"


def normalize_processo_id(processo_id: str) -> List[str]:
    """
    Generate ordered search variations for a processo ID.

    Returns a deduplicated list of query strings to try against DoWeb
    with Busca Exata enabled.  The first variation is always the original
    (most specific).  Subsequent variations progressively relax the format
    to cover common transcription differences between systems.

    The caller tries each variation in order and stops on the first hit.
    """
    pid = processo_id.strip()
    fmt = detect_format(pid)

    if fmt == "A":
        variations = _normalize_format_a(pid)
    elif fmt == "B":
        variations = _normalize_format_b(pid)
    elif fmt == "C":
        variations = _normalize_format_c(pid)
    else:
        logger.warning(f"   ⚠  Unrecognised ID format: '{pid}' — using original only")
        variations = [pid]

    # Deduplicate while preserving order (variations can collapse when
    # there is no check digit or when the prefix has no leading zeros)
    seen: set = set()
    result: List[str] = []
    for v in variations:
        if v not in seen:
            seen.add(v)
            result.append(v)

    return result


# ══════════════════════════════════════════════════════════════════════════════
# FORMAT-SPECIFIC NORMALIZERS — private
# ══════════════════════════════════════════════════════════════════════════════

def _normalize_format_a(pid: str) -> List[str]:
    """
    006800.000136/2026-28 → up to 8 variations.

    Decomposition:
        PREFIX   = "006800"   (organ code, may have leading zeros)
        SEQUENCE = "000136"   (sequential number within year)
        YEAR     = "2026"
        CHECK    = "28"       (verification digit — sometimes omitted)

    Variations cover:
        • presence / absence of the check digit
        • presence / absence of the dot separating PREFIX and SEQUENCE
        • progressive stripping of leading zeros from the joined number

    Background: different systems store the same processo with different
    zero-padding and punctuation, so the gazette may have been published
    under any of these forms.
    """
    m = re.match(r'^(\d+)\.(\d+)/(\d{4})(?:-(\d+))?$', pid)
    if not m:
        return [pid]

    prefix   = m.group(1)   # "006800"
    sequence = m.group(2)   # "000136"
    year     = m.group(3)   # "2026"
    check    = m.group(4)   # "28"  or None

    # Join prefix and sequence (remove the dot)
    joined = prefix + sequence                     # "006800000136"

    # Progressive leading-zero stripping of the joined number
    # "006800000136" → "06800000136" → "6800000136"
    j1 = joined[1:] if joined.startswith("0") else joined
    j2 = j1[1:]     if j1.startswith("0")    else j1

    # Suffix: with and without the check digit
    suffix_full  = f"{year}-{check}" if check else year
    suffix_short = year

    return [
        f"{prefix}.{sequence}/{suffix_full}",    # 1: exact original
        f"{prefix}.{sequence}/{suffix_short}",   # 2: no check digit
        f"{joined}/{suffix_full}",               # 3: no dot
        f"{joined}/{suffix_short}",              # 4: no dot, no check digit
        f"{j1}/{suffix_full}",                   # 5: strip one leading zero
        f"{j1}/{suffix_short}",                  # 6: strip one zero, no check digit
        f"{j2}/{suffix_full}",                   # 7: strip two leading zeros
        f"{j2}/{suffix_short}",                  # 8: strip two zeros, no check digit
    ]


def _normalize_format_b(pid: str) -> List[str]:
    """
    TUR-PRO-2025/01221 → 3 variations.

    Decomposition:
        ORG    = "TUR"    (organ abbreviation)
        TYPE   = "PRO"    (document type)
        YEAR   = "2025"
        NUMBER = "01221"

    Variations cover presence/absence of dashes and the slash.
    """
    m = re.match(r'^([A-Z]+)-([A-Z]+)-(\d{4})/(\d+)$', pid)
    if not m:
        return [pid]

    org, kind, year, number = m.group(1), m.group(2), m.group(3), m.group(4)

    return [
        f"{org}-{kind}-{year}/{number}",    # 1: exact
        f"{org}{kind}{year}/{number}",       # 2: no dashes
        f"{org}{kind}{year}{number}",        # 3: no dashes, no slash
    ]


def _normalize_format_c(pid: str) -> List[str]:
    """
    12/500.078/2021 → 3 variations.

    Decomposition:
        NUM    = "12"     (may lack leading zero)
        SEQ    = "500"
        SUBSEQ = "078"
        YEAR   = "2021"

    Variations cover zero-padding of NUM and removal of the first slash.
    """
    m = re.match(r'^(\d+)/(\d+)\.(\d+)/(\d{4})$', pid)
    if not m:
        return [pid]

    num, seq, subseq, year = m.group(1), m.group(2), m.group(3), m.group(4)
    zero_padded = num.zfill(len(num) + 1)   # "12" → "012"

    return [
        f"{num}/{seq}.{subseq}/{year}",              # 1: exact
        f"{zero_padded}/{seq}.{subseq}/{year}",      # 2: zero-padded prefix
        f"{num}{seq}.{subseq}{year}",                # 3: no slashes
    ]


# ══════════════════════════════════════════════════════════════════════════════
# CONTENT CLASSIFIER — private helper
# ══════════════════════════════════════════════════════════════════════════════

# Structured contract pattern: "Processo {id} 1-Objeto: ... 2-Partes:"
# We compile this lazily per call because the ID varies.
_ADDENDUM_RE = re.compile(r'\b(APROVO|AUTORIZO)\b', re.IGNORECASE)


def _classify_content(snippet: str, processo_id: str) -> str:
    """
    Classify the publication type from the snippet text.

    "structured_contract"
        The snippet contains the full structured block anchored to THIS
        processo_id: "Processo {id} 1-Objeto: ... 2-Partes:".
        This is the original contract publication.

    "possible_addendum"
        The snippet contains APROVO or AUTORIZO but not the structured
        pattern anchored to this ID.  This may be an addendum, ratification,
        or authorisation act — or may belong to a neighbouring contract on
        the same gazette page.  Download anyway; Epic 4 decides.

    "unknown"
        Insufficient snippet content to classify.

    IMPORTANT: This classification is METADATA only.
    It never triggers a discard. All Busca Exata results are downloaded.
    """
    # Anchor the structured-contract pattern to the specific processo_id
    # so we don't misclassify a neighbour's block
    escaped = re.escape(processo_id)
    anchored_re = re.compile(
        rf'Processo\s+{escaped}\s+1-Objeto:.*?2-Partes:',
        re.IGNORECASE | re.DOTALL,
    )

    if anchored_re.search(snippet):
        return "structured_contract"

    if _ADDENDUM_RE.search(snippet):
        return "possible_addendum"

    return "unknown"


# ══════════════════════════════════════════════════════════════════════════════
# PUBLICATION METADATA PARSER — private helper
# ══════════════════════════════════════════════════════════════════════════════

def _parse_publication_metadata(text: str) -> Tuple[str, str, str]:
    """
    Parse the publication metadata string into its three components.

    Input:  "publicado em: 03/02/2026 - Edição 218 - Pág. 38"
    Output: ("03/02/2026", "218", "38")

    Returns ("", "", "") on any parse failure.
    """
    m = re.search(
        r'publicado\s+em:\s*(\d{2}/\d{2}/\d{4})'      # date
        r'\s*-\s*Edi[cç][aã]o\s+(\d+)'                # edition number
        r'\s*-\s*P[áa]g\.\s*(\d+)',                    # page number
        text,
        re.IGNORECASE,
    )
    if m:
        return m.group(1), m.group(2), m.group(3)
    return "", "", ""


# ══════════════════════════════════════════════════════════════════════════════
# MAIN SEARCHER CLASS
# ══════════════════════════════════════════════════════════════════════════════

class DoWebSearcher:
    """
    Searches DoWeb (doweb.rio.rj.gov.br) for publications linked to a
    processo ID and returns structured result rows.

    Lifecycle
    ─────────
    One instance is created per Stage 3 run and reused across all processo
    IDs.  The browser session — including any solved CAPTCHA — is shared
    for the full run so the human only needs to solve the challenge once.

    Usage
    ─────
        searcher = DoWebSearcher(driver)
        results  = searcher.search("006800.000136/2026-28")
        # results: List[SearchResultItem] — empty = NO_RESULTS_FOUND

    Architecture note
    ─────────────────
    This class only searches and parses.  It does not download PDFs,
    save JSON files, or track progress.  Those responsibilities belong
    to infrastructure/scrapers/doweb/downloader.py.
    """

    def __init__(self, driver: webdriver.Chrome):
        self.driver            = driver
        self.captcha           = CaptchaHandler(driver)
        self._on_results_page  = False   # True once we have loaded buscanova

    # ══════════════════════════════════════════════════════════
    # PUBLIC API
    # ══════════════════════════════════════════════════════════

    def search(self, processo_id: str) -> List[SearchResultItem]:
        """
        Search DoWeb for all publications linked to processo_id.

        Tries up to N ID variations with Busca Exata enabled.
        Returns ALL result rows from the first variation that succeeds.
        Returns an empty list if all variations produce 0 results
        (caller should mark as NO_RESULTS_FOUND).

        Args:
            processo_id: Raw processo ID as stored in discovery data.

        Returns:
            List[SearchResultItem] — may be empty.
        """
        if not self._is_driver_alive():
            raise RuntimeError("Browser session is no longer alive — restart required")

        variations = normalize_processo_id(processo_id)
        logger.info(
            f"   🔍 Searching DoWeb: '{processo_id}' "
            f"({len(variations)} variation(s) to try, Busca Exata)"
        )

        for idx, query in enumerate(variations, 1):
            logger.debug(f"      Variation {idx}/{len(variations)}: '{query}'")

            try:
                results = self._search_one_variation(processo_id, query)
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                logger.warning(f"      ✗ Variation '{query}' raised: {exc}")
                time.sleep(BETWEEN_SEARCHES)
                continue

            if results:
                logger.info(
                    f"   ✓ {len(results)} result(s) for '{processo_id}' "
                    f"via variation {idx}: '{query}'"
                )
                return results

            logger.debug(f"      0 results — trying next variation")
            time.sleep(BETWEEN_SEARCHES)

        logger.info(
            f"   ○ NO_RESULTS_FOUND for '{processo_id}' "
            f"(tried {len(variations)} variation(s))"
        )
        return []

    # ══════════════════════════════════════════════════════════
    # SEARCH EXECUTION
    # ══════════════════════════════════════════════════════════

    def _search_one_variation(
        self,
        processo_id: str,
        query: str,
    ) -> List[SearchResultItem]:
        """
        Execute one Busca Exata search and return all result pages.

        Navigation strategy:
        - First call ever → navigate to DoWeb homepage, type in #input2
        - Subsequent calls → reuse the buscanova session, update #q field
        - Session loss (TimeoutException on #q) → fall back to homepage
        """
        if not self._on_results_page:
            self._navigate_via_homepage(query)
        else:
            self._update_search_field(query)

        # Always verify Busca Exata is checked before reading results
        self._ensure_busca_exata_checked()

        total = self._get_total_results()
        if total == 0:
            return []

        total_pages = self._get_total_pages()
        logger.debug(f"      {total} result(s) across {total_pages} page(s)")

        all_results: List[SearchResultItem] = []
        current_page = 1

        while True:
            page_items = self._parse_current_page(
                processo_id = processo_id,
                query_used  = query,
                page_offset = len(all_results),
                total_docs  = total,
            )
            all_results.extend(page_items)

            if current_page >= total_pages:
                break

            if not self._go_to_next_page():
                logger.warning(
                    f"      ⚠ Could not advance past page {current_page} — "
                    f"returning {len(all_results)} result(s) collected so far"
                )
                break

            current_page += 1
            time.sleep(BETWEEN_PAGES)

        return all_results

    def _navigate_via_homepage(self, query: str) -> None:
        """
        Navigate to the DoWeb homepage, handle CAPTCHA if present,
        type the query into #input2, and press Enter to reach buscanova.

        Sets self._on_results_page = True on success.
        """
        logger.debug("   🌐 Navigating to DoWeb homepage")
        self.driver.get(DOWEB_HOME_URL)
        time.sleep(PAGE_LOAD_WAIT)

        # Handle CAPTCHA gate if present
        if self.captcha.is_on_captcha_page():
            logger.info("   🔐 CAPTCHA detected on DoWeb homepage — please solve it")
            self.captcha.wait_for_manual_with_input()

        # Locate the homepage search box and submit the query
        try:
            box = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "input2"))
            )
            box.clear()
            box.send_keys(query)
            box.send_keys(Keys.RETURN)
            time.sleep(PAGE_LOAD_WAIT)
            self._on_results_page = True
            logger.debug("   ✓ Arrived on buscanova results page")
        except TimeoutException as exc:
            raise RuntimeError(
                f"Could not locate #input2 on DoWeb homepage: {exc}"
            )

    def _update_search_field(self, query: str) -> None:
        """
        On an active buscanova session, update the #q field with the new
        query and press Enter to re-search without reloading the page.

        Falls back to homepage navigation if the session has been lost.
        """
        try:
            q_field = WebDriverWait(self.driver, 8).until(
                EC.presence_of_element_located((By.ID, "q"))
            )
            q_field.clear()
            q_field.send_keys(query)
            q_field.send_keys(Keys.RETURN)
            time.sleep(PAGE_LOAD_WAIT)
        except TimeoutException:
            logger.warning(
                "   ⚠ Lost buscanova session (#q not found) — "
                "re-navigating via homepage"
            )
            self._on_results_page = False
            self._navigate_via_homepage(query)

    def _ensure_busca_exata_checked(self) -> None:
        """
        Verify that the 'Busca exata' checkbox is in the checked (exact
        search) state.  If it is unchecked, click it and re-submit so the
        results reflect the exact-phrase mode.

        Checkbox HTML:
            <input type="checkbox" ng-model="fullSearch" ...>
            checked   = Busca Exata / exact phrase  ← we want this
            unchecked = broad / tokenised search    ← avoids this
        """
        try:
            checkbox = WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "input[ng-model='fullSearch']")
                )
            )

            if not checkbox.is_selected():
                logger.debug("   ☑ Busca Exata was unchecked — enabling exact mode")
                self.driver.execute_script("arguments[0].click();", checkbox)
                time.sleep(ANGULAR_DIGEST)

                # Re-submit to apply the exact-mode filter
                try:
                    q_field = self.driver.find_element(By.ID, "q")
                    q_field.send_keys(Keys.RETURN)
                    time.sleep(PAGE_LOAD_WAIT)
                except NoSuchElementException:
                    pass   # field disappeared — results may still be correct
            else:
                logger.debug("   ☑ Busca Exata is already checked")

        except TimeoutException:
            logger.warning(
                "   ⚠ Could not locate 'Busca Exata' checkbox — "
                "proceeding with current search mode"
            )

    # ══════════════════════════════════════════════════════════
    # RESULT COUNTING & PAGINATION
    # ══════════════════════════════════════════════════════════

    def _get_total_results(self) -> int:
        """
        Read the total number of results from the page counter.

        Target element:
            <div class="total">
              <span class="bold">2&nbsp;</span>resultados encontrados...
            </div>

        Returns 0 if the element is absent or not yet rendered.
        """
        try:
            WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "div.total span.bold")
                )
            )
            spans = self.driver.find_elements(
                By.CSS_SELECTOR, "div.total span.bold"
            )
            if spans:
                raw = spans[0].text.strip().replace("\xa0", "").replace(",", "")
                return int(raw) if raw.isdigit() else 0
        except (TimeoutException, ValueError):
            pass
        return 0

    def _get_total_pages(self) -> int:
        """
        Read the total page count from the pagination indicator.

        Target element:
            <div class="total mostrador-paginas">
              <span>página 1 de 5</span>
            </div>

        Returns 1 when the element is absent (single page of results).
        """
        try:
            span = self.driver.find_element(
                By.CSS_SELECTOR,
                "div.total.mostrador-paginas span"
            )
            m = re.search(r'\bde\s+(\d+)', span.text.strip())
            if m:
                return int(m.group(1))
        except (NoSuchElementException, ValueError):
            pass
        return 1

    def _go_to_next_page(self) -> bool:
        """
        Click the » button to advance to the next results page.

        The link uses javascript:void(0) so we use execute_script to
        guarantee the click is registered regardless of scroll position.

        Target:
            <li class="next"><a class="page-link" href="javascript:void(0)"> »</a>

        Returns True if the click succeeded, False if the button is absent.
        """
        try:
            btn = self.driver.find_element(
                By.CSS_SELECTOR, "li.next a.page-link"
            )
            self.driver.execute_script("arguments[0].click();", btn)
            time.sleep(PAGE_LOAD_WAIT)
            return True
        except NoSuchElementException:
            logger.debug("   ○ No 'next page' button found — already on last page")
            return False
        except Exception as exc:
            logger.warning(f"   ⚠ Pagination click failed: {exc}")
            return False

    # ══════════════════════════════════════════════════════════
    # RESULT ROW PARSING
    # ══════════════════════════════════════════════════════════

    def _parse_current_page(
        self,
        processo_id: str,
        query_used: str,
        page_offset: int,
        total_docs: int,
    ) -> List[SearchResultItem]:
        """
        Parse all result rows visible on the current buscanova page.

        Uses the "publicado em:" spans as anchors — one per result row.
        page_offset is the count of results already collected from
        previous pages, used to compute the correct document_index.
        """
        try:
            WebDriverWait(self.driver, PAGE_LOAD_WAIT).until(
                EC.presence_of_element_located(
                    (By.XPATH, "//span[contains(text(),'publicado em:')]")
                )
            )
        except TimeoutException:
            logger.warning("   ⚠ No 'publicado em' spans found — page may be empty")
            return []

        pub_spans = self.driver.find_elements(
            By.XPATH,
            "//span[contains(text(),'publicado em:')]"
        )

        items: List[SearchResultItem] = []
        for i, pub_span in enumerate(pub_spans):
            doc_index = page_offset + i + 1
            try:
                item = self._parse_one_result(
                    pub_span    = pub_span,
                    processo_id = processo_id,
                    query_used  = query_used,
                    doc_index   = doc_index,
                    total_docs  = total_docs,
                )
                items.append(item)
                logger.debug(
                    f"      [{doc_index}/{total_docs}] "
                    f"date={item.publication_date!r} "
                    f"ed={item.edition_number!r} "
                    f"pg={item.page_number!r} "
                    f"hint={item.content_hint!r}"
                )
            except Exception as exc:
                logger.warning(
                    f"      ⚠ Could not parse result row {doc_index}: {exc}"
                )

        return items

    def _parse_one_result(
        self,
        pub_span,
        processo_id: str,
        query_used: str,
        doc_index: int,
        total_docs: int,
    ) -> SearchResultItem:
        """
        Build one SearchResultItem from the result row anchored by pub_span.

        Steps:
        1. Parse date / edition / page from the span text.
        2. Walk up to the enclosing result container.
        3. Collect snippet text from all ng-bind-html spans in that container.
        4. Click the Download button, wait for the pdf-page link, capture href.
        5. Classify content from snippet.
        """
        # ── Step 1: metadata from the publication span ────────────────────
        pub_text = pub_span.text.strip()
        date, edition, page = _parse_publication_metadata(pub_text)

        # ── Step 2: find the enclosing result container ───────────────────
        # We walk up the DOM to find the nearest ancestor that also contains
        # a fa-download icon — this uniquely identifies one result block.
        container = self._find_result_container(pub_span)

        # ── Step 3: collect snippet text ──────────────────────────────────
        snippet = self._extract_snippet(container)

        # ── Step 4: extract PDF page URL ──────────────────────────────────
        pdf_url = self._extract_pdf_url(container)

        # ── Step 5: classify ──────────────────────────────────────────────
        hint = _classify_content(snippet, processo_id)

        return SearchResultItem(
            processo_id      = processo_id,
            query_used       = query_used,
            document_index   = doc_index,
            total_documents  = total_docs,
            publication_date = date,
            edition_number   = edition,
            page_number      = page,
            snippet          = snippet,
            pdf_page_url     = pdf_url,
            content_hint     = hint,
        )

    def _find_result_container(self, pub_span):
        """
        Walk up the DOM from pub_span to find the enclosing result block.

        We look for the closest ancestor element that contains a
        fa-download icon — this uniquely delimits one result row.
        Falls back to the direct parent if the ancestor is not found.
        """
        try:
            return pub_span.find_element(
                By.XPATH,
                "./ancestor::*[.//i[contains(@class,'fa-download')]][1]"
            )
        except NoSuchElementException:
            # Graceful fallback: return the immediate parent
            return pub_span.find_element(By.XPATH, "./..")

    def _extract_snippet(self, container) -> str:
        """
        Concatenate text from all ng-bind-html spans within the container.

        Each result row can have multiple snippet spans.  We join them
        with a space and strip HTML artefacts.
        """
        try:
            spans = container.find_elements(
                By.CSS_SELECTOR, "span[ng-bind-html]"
            )
            parts = [s.text.strip() for s in spans if s.text.strip()]
            return " ".join(parts)
        except Exception:
            return ""

    def _extract_pdf_url(self, container) -> str:
        """
        Click the Download toggle button within this result container,
        wait for the 'Baixar apenas a página' link to appear, capture
        its href, then dismiss the dropdown without following the link.

        Why we don't click the link:
            The <a> has target="_blank" — clicking it opens a new tab and
            triggers a browser download.  We only need the URL so we can
            download the PDF later with requests.get() in downloader.py.

        Timeout: DOWNLOAD_BTN_WAIT seconds (1–3s observed in the field).
        """
        try:
            # Locate and click the Download toggle button inside this container
            dl_toggle = container.find_element(
                By.XPATH,
                ".//i[contains(@class,'fa-download')]/.."
            )
            self.driver.execute_script("arguments[0].click();", dl_toggle)

            # Wait for the "Baixar apenas a página" link to appear anywhere
            # on the page (the dropdown is not constrained to the container)
            pdf_link = WebDriverWait(self.driver, DOWNLOAD_BTN_WAIT).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "a.link.pdf-page")
                )
            )
            href = pdf_link.get_attribute("href") or ""

            # Dismiss the dropdown by pressing Escape
            from selenium.webdriver.common.action_chains import ActionChains
            ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
            time.sleep(0.4)

            return href

        except TimeoutException:
            logger.warning(
                "      ⚠ 'Baixar apenas a página' link did not appear within "
                f"{DOWNLOAD_BTN_WAIT}s — pdf_page_url will be empty"
            )
            return ""
        except NoSuchElementException as exc:
            logger.warning(f"      ⚠ Download button not found in container: {exc}")
            return ""
        except Exception as exc:
            logger.warning(f"      ⚠ Unexpected error extracting pdf_page_url: {exc}")
            return ""

    # ══════════════════════════════════════════════════════════
    # DRIVER HEALTH
    # ══════════════════════════════════════════════════════════

    def _is_driver_alive(self) -> bool:
        """
        Check if the Chrome session is still responsive.

        Uses window_handles as a lightweight probe — no navigation,
        no page load.  Returns False on any Selenium exception.
        """
        try:
            _ = self.driver.window_handles
            return True
        except Exception:
            return False