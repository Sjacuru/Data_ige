"""
infrastructure/scrapers/contasrio/navigation.py

Stage 1 responsibility: navigate ContasRio's Vaadin hierarchy and
collect processo URLs. Nothing more.

Confirmed portal structure (diagnostics 2026-02-19):
═══════════════════════════════════════════════════════════════════

DEPTH 0  All-companies grid
         Clickable: v-button.link.small  →  "CNPJ - Company Name"

    ↓ click company button

DEPTH 1  Órgão list  (1..N órgãos per company)
         Clickable: v-button.link.small  →  "3351 - RIOTUR ..."
         Breadcrumb index 0 = Favorecido → click to return here

    ↓ click each órgão button

DEPTH 2  Unidade Gestora list  (1..N UGs per órgão)
         Clickable: v-button.link.small  →  "330051 - EMPRESA ..."
         Breadcrumb index 1 = Órgão → click to return here

    ↓ click each UG button

DEPTH 3  *** LEAF — contracts grid (no more drillable buttons) ***
         Columns: Contrato | Objeto | Descrição | Situação |
                  Processo | Data Início | Data Fim | Total | …
         "Processo" cell contains: <a href="https://acesso.processo.rio/
           sigaex/public/app/transparencia/processo?n=TUR-PRO-2025/01221">
         Breadcrumb index 0 = Favorecido, index 1 = Órgão, index 2 = UG

═══════════════════════════════════════════════════════════════════

Backtrack rule
  D3 → D2 : click breadcrumb index 1  (Órgão label)
  D2 → D1 : click breadcrumb index 0  (Favorecido label)
  D1 → D0 : full page reload           (no breadcrumbs exist at D0)

Virtual DOM note
  The Vaadin grid only renders rows currently visible in the viewport.
  After a page reload the grid shows the first ~8 companies.
  _scroll_grid_to_find() scrolls the grid until the target company
  button appears in the DOM before attempting to click it.
"""
import re
import time
import logging
from typing import List, Optional, Set, Tuple

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException
from selenium.webdriver.common.keys import Keys 


from config.settings import CONTASRIO_CONTRACTS_URL
from domain.models.processo_link import ProcessoLink, CompanyData

logger = logging.getLogger(__name__)


# ─── Timing ───────────────────────────────────────────────────────────────────
CLICK_PAUSE    = 2.5    # seconds to wait after a navigation click
LOAD_TIMEOUT   = 20     # seconds to wait for loading indicator
SETTLE_PAUSE   = 0.8    # extra pause after loading indicator clears
SCROLL_PAUSE   = 1.0    # pause between grid scroll steps
MAX_SCROLL_STEPS = 150  # hard cap for any scrolling loop

# ─── CSS selectors (all confirmed from diagnostics) ───────────────────────────
SEL_DRILLABLE  = ".v-button.link.small, .v-button-link.v-button-small"
SEL_BREADCRUMB = ".v-slot-query-breadcrumbs-item .v-button"
SEL_LOADING    = "div.v-loading-indicator"
SEL_GRID_CELL  = "td.v-grid-cell[role='gridcell']"
SEL_DATA_ROW   = ".v-grid-row.v-grid-row-has-data"

# Column index of "Processo" in the depth-3 contracts grid
COL_PROCESSO   = 4
COL_TOTAL      = 7


class PathNavigator:
    """
    Navigates ContasRio's 3-level Vaadin hierarchy for one company at a time
    and collects all processo URLs from the leaf grid.

    Each level may have more than one option:
    - A company can belong to multiple Órgãos
    - Each Órgão can have multiple Unidades Gestoras
    - Each UG can have multiple processo rows

    The DFS visits every branch, collecting all links before backtracking.
    """

    def __init__(self, driver: webdriver.Chrome):
        self.driver = driver
        self._visited: Set[Tuple[str, ...]] = set()

    # ─── Public entry point ───────────────────────────────────────────────────

    def discover_company_paths(self, company: CompanyData) -> List[ProcessoLink]:
        """
        Collect all ProcessoLink objects for one company.

        Args:
            company: CompanyData with company_id containing CNPJ digits.

        Returns:
            List of ProcessoLink — one per contract row found across all
            Órgão → UG branches for this company.
        """
        self._visited.clear()
        logger.info(f"   🏢 {company.company_name[:65]}")

        if not self._enter_company(company):
            logger.warning("   ⚠ Could not enter company — skipping")
            return []

        self._wait_for_settle()

        processos = self._dfs(
            path=(company.company_name,),
            depth=1,
            company=company,
        )

        self._go_to_root()
        logger.info(f"   ✓ {len(processos)} processo link(s) collected")
        return processos

    # ─── D0 → D1: Enter company ───────────────────────────────────────────────

    def _enter_company(self, company: CompanyData) -> bool:
        """
        Click the company's v-button.link.small in the all-companies grid.

        Attempt order (fastest to slowest):
        1. Filter field — type CNPJ into "Digite para filtrar", wait for
            the grid to narrow to one row, then click the button.
        2. Direct DOM click — company already visible without filtering.
        3. Virtual DOM scroll — scroll grid until button appears, then click.
        """
        cnpj_digits = re.sub(r'\D', '', company.company_id)

        # ── Attempt 1: filter field ───────────────────────────────────────────
        if self._filter_and_click_company(cnpj_digits, company.company_name):
            time.sleep(CLICK_PAUSE)
            return True

        # ── Attempt 2: already in DOM without filtering ───────────────────────
        if self._js_click_drillable_by_prefix(cnpj_digits):
            time.sleep(CLICK_PAUSE)
            return True

        # ── Attempt 3: scroll until button appears, then click ────────────────
        logger.debug(
            f"   → Company not visible — scrolling grid to find: {cnpj_digits[:14]}"
        )
        if self._scroll_grid_to_find_and_click(cnpj_digits, company.company_name):
            time.sleep(CLICK_PAUSE)
            return True

        logger.warning(
            f"   ✗ Company button not found after all attempts — "
            f"CNPJ={cnpj_digits[:14]} name={company.company_name[:30]}"
        )
        return False
    
    def _filter_and_click_company(
        self, cnpj_digits: str, company_name: str
    ) -> bool:
        """
        Use the "Digite para filtrar" text field to narrow the company grid,
        then click the matching v-button.link.small that appears.

        Steps:
        1. Locate the filter input by its placeholder text.
        2. Clear any previous value and type the CNPJ digits.
        3. Wait for the grid to reload (loading indicator clears).
        4. Click the first drillable button whose digits match the CNPJ.
            If no CNPJ match, fall back to name prefix match.
        5. On any failure, clear the filter before returning False so
            the grid is restored to full view for the next attempt.

        Args:
            cnpj_digits:  Normalised CNPJ digit string (14 chars typical).
            company_name: Full company name for fallback matching.

        Returns:
            True if the company button was clicked successfully.
        """
        FILTER_SEL = "input[v-button-caption]"
        clicked = False

        try:
            # Locate filter input
            filter_input = WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, FILTER_SEL))
            )

            # Clear any previous filter value
            self.driver.execute_script("arguments[0].value = '';", filter_input)
            filter_input.click()
            filter_input.send_keys(cnpj_digits)

            # Wait for grid to narrow (loading indicator, then settle)
            self._wait_for_settle()

            # Check for success
            if self._js_click_drillable_by_prefix(cnpj_digits) or \
            self._js_click_drillable_containing(company_name[:15].upper()):
                logger.debug(f"   ✓ Found and clicked: {cnpj_digits}")
                clicked = True # Mark as successful
                return True
            
            # Click matching button
            if self._js_click_drillable_by_prefix(cnpj_digits):
                logger.debug(f"   ✓ Found via filter (CNPJ): {cnpj_digits[:14]}")
                return True



            # Fallback: name prefix (in case CNPJ format differs)
            name_prefix = company_name[:15].upper()
            if self._js_click_drillable_containing(name_prefix):
                logger.debug(f"   ✓ Found via filter (name): {name_prefix}")
                return True

            return False

        except Exception as e:
            logger.debug(f"   → Filter attempt failed: {e}")
            return False


        finally:
        # ONLY clear the filter if we DID NOT click the company.
        # If we clicked, we want to allow the page to navigate away.
            if not clicked:
                try:
                    filter_input = self.driver.find_element(By.CSS_SELECTOR, FILTER_SEL)
                    self.driver.execute_script("arguments[0].value = '';", filter_input)
                    filter_input.send_keys(Keys.ENTER)
                    self._wait_for_settle()
                except Exception:
                    pass

    def _scroll_grid_to_find_and_click(
        self, cnpj_digits: str, company_name: str
    ) -> bool:
        """
        Scroll the all-companies grid downward step by step until the
        target company's v-button.link.small appears in the DOM, then click it.

        Args:
            cnpj_digits:  Normalised CNPJ digits to match against button text.
            company_name: Company name for fallback text matching.

        Returns:
            True if the button was found and clicked.
        """
        scroller = self._find_grid_scroller()
        if not scroller:
            logger.warning("   ⚠ Grid scroller not found — cannot scroll to company")
            return False

        name_prefix = company_name[:15].upper()

        for step in range(MAX_SCROLL_STEPS):
            # Try both match strategies on currently rendered buttons
            if self._js_click_drillable_by_prefix(cnpj_digits):
                return True
            if self._js_click_drillable_containing(name_prefix):
                return True

            # Scroll down and check if we've hit the bottom
            old_top = self.driver.execute_script(
                "return arguments[0].scrollTop;", scroller
            )
            self.driver.execute_script(
                "arguments[0].scrollTop += 200;", scroller
            )
            time.sleep(SCROLL_PAUSE)
            new_top = self.driver.execute_script(
                "return arguments[0].scrollTop;", scroller
            )

            if new_top == old_top:
                # Reached the bottom — one final attempt
                if self._js_click_drillable_by_prefix(cnpj_digits):
                    return True
                break

        return False

    # ─── DFS through D1 and D2 ────────────────────────────────────────────────

    def _dfs(
        self,
        path: Tuple[str, ...],
        depth: int,
        company: CompanyData,
    ) -> List[ProcessoLink]:
        """
        Depth-first traversal of Órgão (D1) and Unidade Gestora (D2) levels.

        At each level we read all v-button.link.small elements and iterate
        through every one of them — there can be multiple Órgãos per company
        and multiple UGs per Órgão.

        When no drillable buttons are found we have reached the leaf (D3)
        and harvest the contracts grid instead of recursing further.

        Args:
            path:    Navigation breadcrumb tuple (for dedup + metadata).
            depth:   1 = Órgão list, 2 = UG list, 3 = contracts (leaf).
            company: Original CompanyData (for CNPJ metadata on links).

        Returns:
            All ProcessoLink objects found in this subtree.
        """
        if path in self._visited:
            return []
        self._visited.add(path)

        self._wait_for_settle()
        indent = "      " + "  " * depth

        options = self._read_drillable_buttons()

        if not options:
            # No drillable buttons → leaf node (D3 contracts grid)
            logger.info(f"{indent}🎯 Leaf (D{depth}) — reading contracts grid")
            return self._harvest_leaf(list(path), company)

        logger.info(
            f"{indent}[D{depth}] {len(options)} option(s) "
            f"| path: {' → '.join(p[:20] for p in path[-2:])}"
        )

        all_processos: List[ProcessoLink] = []

        for option_text in options:
            child_path = path + (option_text,)
            if child_path in self._visited:
                logger.debug(f"{indent}  ⏭ Already visited: {option_text[:40]}")
                continue

            logger.info(f"{indent}  → '{option_text[:60]}'")

            if not self._click_drillable(option_text):
                logger.warning(f"{indent}  ⚠ Click failed: '{option_text[:40]}'")
                continue

            self._wait_for_settle()

            child_results = self._dfs(child_path, depth + 1, company)
            all_processos.extend(child_results)

            logger.info(f"{indent}  ← Backtrack to D{depth}")
            if not self._backtrack_to_depth(depth):
                # Breadcrumb click failed — abort the rest of this subtree
                logger.error(
                    f"{indent}  ✗ Backtrack failed — "
                    f"aborting remaining options at D{depth}"
                )
                break

            self._wait_for_settle()

        return all_processos

    # ─── D3: Harvest contracts grid ───────────────────────────────────────────

    def _harvest_leaf(
        self,
        path: List[str],
        company: CompanyData,
    ) -> List[ProcessoLink]:
        """
        Read every row from the D3 contracts grid and return one ProcessoLink
        per row. Scrolls the grid to capture rows that are off-screen.

        Only the processo ID and its URL are stored. All other contract
        content (objeto, situação, datas) is deferred to Stage 2.

        Args:
            path:    Navigation path [company, orgao, ug] for metadata.
            company: For CNPJ metadata on the returned links.

        Returns:
            List of ProcessoLink objects.
        """
        processos: List[ProcessoLink] = []
        seen_ids: Set[str] = set()
        cnpj = re.sub(r'\D', '', company.company_id) if company.company_id else None

        scroller = self._find_grid_scroller()

        for _ in range(MAX_SCROLL_STEPS):
            rows = self._js_read_leaf_rows()

            for row in rows:
                pid = row.get("processo_id", "").strip()
                url = row.get("processo_url", "").strip()

                if not pid or pid.upper() == "TOTAL" or pid in seen_ids:
                    continue
                seen_ids.add(pid)

                processos.append(ProcessoLink(
                    processo_id=pid,
                    url=url,
                    company_name=company.company_name,
                    company_cnpj=cnpj,
                    contract_value=row.get("total", ""),
                    discovery_path=path.copy(),
                ))
                logger.debug(f"         🔗 {pid} | {row.get('total', '')}")

            # Scroll and check bottom
            if scroller:
                old_top = self.driver.execute_script(
                    "return arguments[0].scrollTop;", scroller
                )
                self.driver.execute_script(
                    "arguments[0].scrollTop += 300;", scroller
                )
                time.sleep(SCROLL_PAUSE)
                new_top = self.driver.execute_script(
                    "return arguments[0].scrollTop;", scroller
                )
                if new_top == old_top:
                    break
            else:
                break   # Single-screen grid — already read everything

        logger.info(
            f"         ✓ {len(processos)} processo link(s) at this leaf"
        )
        return processos

    def _js_read_leaf_rows(self) -> List[dict]:
        """
        Extract visible rows from the D3 contracts grid.
        Returns [{processo_id, processo_url, total}] per row.
        TOTAL rows are included — caller filters them out.
        """
        return self.driver.execute_script("""
            var results = [];
            var rows = document.querySelectorAll(
                '.v-grid-row.v-grid-row-has-data'
            );
            for (var i = 0; i < rows.length; i++) {
                var cells = rows[i].querySelectorAll(
                    'td.v-grid-cell[role="gridcell"]'
                );
                if (cells.length < 5) continue;

                var processoCell = cells[4];
                var link = processoCell ? processoCell.querySelector('a') : null;

                results.push({
                    processo_id:  processoCell ? processoCell.innerText.trim() : '',
                    processo_url: link ? link.href : '',
                    total:        cells[7] ? cells[7].innerText.trim() : '',
                });
            }
            return results;
        """) or []

    # ─── Backtracking ─────────────────────────────────────────────────────────

    def _backtrack_to_depth(self, target_depth: int) -> bool:
        """
        Navigate back to target_depth by clicking a breadcrumb button.

        Breadcrumb index mapping (confirmed from diagnostics):
          index 0  =  Favorecido label  →  restores D1 (órgão list)
          index 1  =  Órgão label       →  restores D2 (UG list)

        To return to depth N, click breadcrumb index N-1.

        Args:
            target_depth: 1 to return to órgão list, 2 to return to UG list.

        Returns:
            True if the breadcrumb was clicked successfully.
        """
        bc_index = target_depth - 1

        result = self.driver.execute_script("""
            var idx = arguments[0];
            var items = document.querySelectorAll(
                '.v-slot-query-breadcrumbs-item .v-button'
            );
            if (idx >= items.length) {
                return {ok: false, count: items.length};
            }
            items[idx].click();
            return {ok: true, count: items.length};
        """, bc_index)

        if result and result.get("ok"):
            time.sleep(CLICK_PAUSE)
            return True

        count = result.get("count", 0) if result else 0

        # At D1 with no breadcrumbs we may already be at root — treat as ok
        if target_depth == 1 and count == 0:
            logger.debug("   → No breadcrumbs present — assuming already at root")
            return True

        logger.warning(
            f"   ⚠ Breadcrumb index {bc_index} not available "
            f"({count} found) — triggering emergency reload"
        )
        self._emergency_reload()
        return False

    def _go_to_root(self) -> None:
        """
        Return to the all-companies grid (D0) between companies.
        Uses a direct URL reload — the only reliable method since the URL
        never changes and driver.back() has no effect on Vaadin navigation.
        After reload, waits for the grid data cells to be present.
        """
        try:
            self.driver.get(CONTASRIO_CONTRACTS_URL)
            self._wait_for_settle(timeout=30)
            WebDriverWait(self.driver, 30).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, SEL_GRID_CELL)
                )
            )
        except Exception as e:
            logger.error(f"   ✗ _go_to_root failed: {e}")

    def _emergency_reload(self) -> None:
        """Last-resort reload when breadcrumb navigation fails."""
        try:
            self.driver.get(CONTASRIO_CONTRACTS_URL)
            self._wait_for_settle(timeout=30)
        except Exception as e:
            logger.error(f"   ✗ Emergency reload failed: {e}")

    # ─── Drillable button helpers ──────────────────────────────────────────────

    def _read_drillable_buttons(self) -> List[str]:
        """
        Return the text of all v-button.link.small elements currently in the DOM.
        Deduplicates and preserves DOM order.
        Excludes icon glyphs, blanks, and TOTAL.
        """
        raw = self.driver.execute_script("""
            var seen = {};
            var results = [];
            var buttons = document.querySelectorAll(
                '.v-button.link.small, .v-button-link.v-button-small'
            );
            for (var i = 0; i < buttons.length; i++) {
                var text = buttons[i].innerText.trim();
                if (!text || text.length < 3 || text.length > 200) continue;
                if (text.charCodeAt(0) > 0x2000) continue;
                if (text.toUpperCase() === 'TOTAL') continue;
                if (!seen[text]) {
                    seen[text] = true;
                    results.push(text);
                }
            }
            return results;
        """) or []
        return raw

    def _click_drillable(self, text: str) -> bool:
        """Click a v-button.link.small by exact visible text."""
        clicked = self.driver.execute_script("""
            var target = arguments[0];
            var buttons = document.querySelectorAll(
                '.v-button.link.small, .v-button-link.v-button-small'
            );
            for (var i = 0; i < buttons.length; i++) {
                if (buttons[i].innerText.trim() === target) {
                    buttons[i].click();
                    return true;
                }
            }
            return false;
        """, text)

        if clicked:
            time.sleep(CLICK_PAUSE)
            return True

        # XPath fallback for subtle encoding differences
        try:
            safe = text.replace("'", "\\'")
            xpath = (
                f"//*[contains(@class,'v-button') and contains(@class,'link') "
                f"and contains(@class,'small') and normalize-space(.)='{safe}']"
            )
            el = WebDriverWait(self.driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, xpath))
            )
            self.driver.execute_script("arguments[0].click();", el)
            time.sleep(CLICK_PAUSE)
            return True
        except (TimeoutException, StaleElementReferenceException):
            return False

    def _js_click_drillable_by_prefix(self, prefix: str) -> bool:
        """Click first drillable button whose digit-only text starts with prefix."""
        return bool(self.driver.execute_script("""
            var prefix = arguments[0];
            var buttons = document.querySelectorAll(
                '.v-button.link.small, .v-button-link.v-button-small'
            );
            for (var i = 0; i < buttons.length; i++) {
                var digits = buttons[i].innerText.replace(/\\D/g, '');
                if (digits.indexOf(prefix) === 0) {
                    buttons[i].click();
                    return true;
                }
            }
            return false;
        """, prefix))

    def _js_click_drillable_containing(self, fragment: str) -> bool:
        """Click first drillable button whose text contains fragment (case-insensitive)."""
        return bool(self.driver.execute_script("""
            var frag = arguments[0].toUpperCase();
            var buttons = document.querySelectorAll(
                '.v-button.link.small, .v-button-link.v-button-small'
            );
            for (var i = 0; i < buttons.length; i++) {
                if (buttons[i].innerText.toUpperCase().indexOf(frag) >= 0) {
                    buttons[i].click();
                    return true;
                }
            }
            return false;
        """, fragment))

    # ─── Grid scroller ─────────────────────────────────────────────────────────

    def _find_grid_scroller(self):
        """Locate the Vaadin grid's internal scrollable element."""
        return self.driver.execute_script("""
            var grid = document.querySelector('div.v-grid');
            if (!grid) return null;
            return grid.querySelector('.v-grid-scroller-vertical')
                || grid.querySelector('.v-grid-tablewrapper')
                || grid;
        """)

    # ─── Page readiness ────────────────────────────────────────────────────────

    def _wait_for_settle(self, timeout: int = LOAD_TIMEOUT) -> None:
        """
        Wait for the Vaadin loading indicator to vanish, then a short pause.
        The indicator is display:none when the server round-trip is complete.
        """
        try:
            WebDriverWait(self.driver, 1.5).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR,
                     f"{SEL_LOADING}[style*='display: block']")
                )
            )
        except TimeoutException:
            pass

        try:
            WebDriverWait(self.driver, timeout).until(
                EC.invisibility_of_element_located(
                    (By.CSS_SELECTOR, SEL_LOADING)
                )
            )
        except TimeoutException:
            logger.debug("   ⚠ Loading indicator timeout — continuing anyway")

        time.sleep(SETTLE_PAUSE)