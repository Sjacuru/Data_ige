"""
infrastructure/scrapers/contasrio/scraper.py

ContasRio portal scraper — Stage 1 only.

Responsibilities
----------------
1. Navigate to the contracts page and apply year filter.
2. Scroll and collect all CompanyData rows from the Favorecidos grid.
3. For each company, call PathNavigator to collect ProcessoLink objects.
4. Save progress after every company so a crash never loses work.

Resilience design
-----------------
- Each company is processed inside a try/except. A failed company is
  logged, skipped, and the run continues with the next one.
- Progress is saved incrementally to data/discovery/progress.json.
  On restart the scraper reads that file and skips already-processed
  companies, so it always resumes rather than starts over.
- An invalid Selenium session (browser crash) is caught at the
  company loop level and re-raises so the workflow can decide whether
  to restart the driver.
"""
import re
import time
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    InvalidSessionIdException,
    WebDriverException,
)

from config.settings import (
    CONTASRIO_BASE_URL,
    CONTASRIO_CONTRACTS_URL,
    FILTER_YEAR,
    DISCOVERY_DIR,
)
from config.portals import CONTASRIO_LOCATORS
from infrastructure.scrapers.contasrio.navigation import PathNavigator
from infrastructure.scrapers.contasrio.parsers import CompanyRowParser
from domain.models.processo_link import CompanyData, ProcessoLink

logger = logging.getLogger(__name__)

PROGRESS_FILE = Path(DISCOVERY_DIR) / "progress.json"


# ─── Progress persistence ─────────────────────────────────────────────────────

def _load_progress() -> dict:
    """
    Load incremental progress from the previous run.

    Returns a dict:
      {
        "completed_company_ids": ["01282704...", ...],
        "processos": [{...}, ...],
        "errors": ["...", ...]
      }
    """
    if PROGRESS_FILE.exists():
        try:
            with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            logger.info(
                f"   📂 Resuming from progress file: "
                f"{len(data.get('completed_company_ids', []))} companies already done, "
                f"{len(data.get('processos', []))} processos already collected"
            )
            return data
        except Exception as e:
            logger.warning(f"   ⚠ Could not read progress file: {e} — starting fresh")

    return {"completed_company_ids": [], "processos": [], "errors": []}


def _save_progress(
    completed_ids: List[str],
    processos: List[ProcessoLink],
    errors: List[str],
) -> None:
    """Persist incremental progress to disk after each company."""
    try:
        PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "last_updated": datetime.now().isoformat(),
            "completed_company_ids": completed_ids,
            "processos": [p.to_dict() for p in processos],
            "errors": errors,
        }
        with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"   ✗ Could not save progress: {e}")


def clear_progress() -> None:
    """Delete the progress file to force a fresh run."""
    if PROGRESS_FILE.exists():
        PROGRESS_FILE.unlink()
        logger.info("   🗑 Progress file cleared — will start from scratch")


# ─── ContasRioScraper ─────────────────────────────────────────────────────────

class ContasRioScraper:
    """
    Stage 1 scraper for the ContasRio portal.

    Orchestrates:
      _navigate_to_contracts()  →  open the right page
      _apply_filters()          →  set year filter
      _collect_companies()      →  scroll and harvest all company rows
      _discover_company_processos() →  delegate to PathNavigator per company
    """

    def __init__(self, driver: webdriver.Chrome):
        self.driver = driver

    # ─── Main entry point ─────────────────────────────────────────────────────

    def discover_all_processos(self) -> List[ProcessoLink]:
        """
        Full Stage 1 discovery workflow.

        Returns:
            All ProcessoLink objects found across all companies,
            including any collected in a previous interrupted run.

        Raises:
            InvalidSessionIdException / WebDriverException if the
            browser session dies — caller should restart the driver.
        """
        logger.info("=" * 70)
        logger.info("🔍 STAGE 1: DISCOVERY")
        logger.info("=" * 70)

        # Load any previous progress
        progress = _load_progress()
        completed_ids: List[str] = progress["completed_company_ids"]
        all_processos: List[ProcessoLink] = [
            ProcessoLink.from_dict(p) for p in progress["processos"]
        ]
        errors: List[str] = progress["errors"]

        # Step 1: Navigate
        logger.info("\n📋 Step 1: Navigating to contracts page...")
        if not self._navigate_to_contracts():
            logger.error("✗ Navigation failed")
            return all_processos

        # Step 2: Apply filter
        logger.info("\n📋 Step 2: Applying year filter...")
        if not self._apply_filters():
            logger.warning("⚠ Filter application failed — continuing without filter")

        # Step 3: Collect companies
        logger.info("\n📋 Step 3: Collecting company list...")
        companies = self._collect_companies()
        if not companies:
            logger.error("✗ No companies found")
            return all_processos

        # Filter out already-completed companies
        remaining = [
            c for c in companies
            if c.company_id not in completed_ids
        ]
        logger.info(
            f"✓ {len(companies)} companies total | "
            f"{len(companies) - len(remaining)} already done | "
            f"{len(remaining)} to process"
        )

        # Step 4: Process each company
        logger.info("\n📋 Step 4: Discovering processo links...")
        navigator = PathNavigator(self.driver)

        for i, company in enumerate(remaining, 1):
            label = f"[{i}/{len(remaining)}] {company.company_name[:50]}"
            logger.info(f"\n   {label}")

            try:
                processos = navigator.discover_company_paths(company)
                company.total_contracts = len(processos)
                all_processos.extend(processos)
                completed_ids.append(company.company_id)

                logger.info(
                    f"   ✓ {len(processos)} processo(s) | "
                    f"running total: {len(all_processos)}"
                )

            except (InvalidSessionIdException, WebDriverException) as e:
                # Browser session died — cannot continue without a new driver
                msg = f"Browser session error on '{company.company_name}': {e}"
                logger.error(f"   ✗ FATAL SESSION ERROR — {msg}")
                errors.append(msg)
                _save_progress(completed_ids, all_processos, errors)
                raise   # Re-raise so workflow can restart the driver

            except Exception as e:
                # Non-fatal error — log, skip, and move on
                msg = f"Failed '{company.company_name}': {e}"
                logger.error(f"   ✗ {msg}")
                errors.append(msg)

            finally:
                # Save progress after every company (success or failure)
                _save_progress(completed_ids, all_processos, errors)

        # Summary
        logger.info("\n" + "=" * 70)
        logger.info("✅ DISCOVERY COMPLETE")
        logger.info(f"   Companies processed : {len(completed_ids)}")
        logger.info(f"   Processos found     : {len(all_processos)}")
        logger.info(f"   Errors              : {len(errors)}")
        logger.info("=" * 70)

        return all_processos

    # ─── Navigation ───────────────────────────────────────────────────────────

    def _navigate_to_contracts(self) -> bool:
        """Load the contracts page and wait for the grid to populate."""
        try:

            # self.driver.get(CONTASRIO_BASE_URL)
            # time.sleep(2)
            self.driver.get(CONTASRIO_CONTRACTS_URL)
            time.sleep(2)
            # self.driver.refresh()

            if "#!Contratos/Contrato" not in self.driver.current_url:
                logger.error("✗ Unexpected URL after navigation")
                return False

            WebDriverWait(self.driver, 60).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "div.v-grid")
                )
            )
            WebDriverWait(self.driver, 120).until(
                lambda d: len(
                    d.find_elements(By.CSS_SELECTOR, "td.v-grid-cell[role='gridcell']")
                ) > 0
            )
            logger.info("✓ Contracts grid loaded")
            return True

        except Exception as e:
            logger.error(f"✗ Navigation failed: {e}")
            return False

    # ─── Year filter ──────────────────────────────────────────────────────────

    def _apply_filters(self) -> bool:
        """Apply the year filter configured in settings."""
        if not FILTER_YEAR:
            logger.info("   ⏭ No year filter configured")
            return True

        try:
            year_filter = WebDriverWait(self.driver, 30).until(
                EC.element_to_be_clickable((
                    By.XPATH,
                    "//div[contains(@class,'v-label') and "
                    "contains(text(),'ANO DE CELEBRAÇÃO')]"
                    "/following::input[contains(@class,'v-filterselect-input')][1]"
                ))
            )

            current = year_filter.get_attribute("value") or ""
            if current.strip() == str(FILTER_YEAR):
                logger.info(f"   ✓ Filter already set to {FILTER_YEAR}")
                return True

            # Clear field
            self.driver.execute_script("arguments[0].click();", year_filter)
            time.sleep(0.3)
            year_filter.send_keys(Keys.END)
            for _ in range(len(current)):
                year_filter.send_keys(Keys.BACKSPACE)
                time.sleep(0.05)

            # Type year and confirm
            year_filter.send_keys(str(FILTER_YEAR))
            time.sleep(0.5)
            year_filter.send_keys(Keys.ENTER)
            time.sleep(1.0)

            final = year_filter.get_attribute("value") or ""
            if str(FILTER_YEAR) not in final:
                return self._apply_filter_via_dropdown(year_filter, str(FILTER_YEAR))

            # Wait for grid to reload
            WebDriverWait(self.driver, 120).until(
                lambda d: len(
                    d.find_elements(By.CSS_SELECTOR, "td.v-grid-cell[role='gridcell']")
                ) > 0
            )
            logger.info(f"   ✓ Filter set to {FILTER_YEAR}")
            return True

        except Exception as e:
            logger.error(f"   ✗ Filter application failed: {e}")
            return False

    def _apply_filter_via_dropdown(self, filter_input, year: str) -> bool:
        """Fallback: select year by clicking the Vaadin filterselect dropdown."""
        try:
            dropdown_btn = self.driver.execute_script("""
                var input = arguments[0];
                var parent = input.closest('.v-filterselect');
                return parent ? parent.querySelector('.v-filterselect-button') : null;
            """, filter_input)

            if not dropdown_btn:
                return False

            self.driver.execute_script("arguments[0].click();", dropdown_btn)
            time.sleep(1.0)

            option = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((
                    By.XPATH,
                    f"//div[contains(@class,'v-filterselect-suggestmenu')]"
                    f"//span[text()='{year}']"
                ))
            )
            option.click()
            time.sleep(1.0)

            WebDriverWait(self.driver, 120).until(
                lambda d: len(
                    d.find_elements(By.CSS_SELECTOR, "td.v-grid-cell[role='gridcell']")
                ) > 0
            )
            return True

        except Exception as e:
            logger.warning(f"   ⚠ Dropdown fallback failed: {e}")
            return False

    # ─── Company collection ───────────────────────────────────────────────────

    def _collect_companies(self) -> List[CompanyData]:
        """
        Scroll through the Favorecidos grid and harvest all company rows.

        Uses JavaScript to read rendered rows, scrolls incrementally,
        and stops when two consecutive scroll steps yield no new companies
        or when the bottom is reached.

        Returns:
            Deduplicated list of CompanyData objects.
        """
        GRID_CSS = "div.v-grid"
        SCROLL_INCREMENT = 200
        SCROLL_PAUSE_S = 2.0
        STALE_ROUNDS = 5

        seen_ids: set = set()
        companies: List[CompanyData] = []

        try:
            WebDriverWait(self.driver, 60).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, f"{GRID_CSS} td.v-grid-cell[role='gridcell']")
                )
            )

            scroller = self.driver.execute_script("""
                var grid = document.querySelector(arguments[0]);
                if (!grid) return null;
                return grid.querySelector('.v-grid-scroller-vertical')
                    || grid.querySelector('.v-grid-tablewrapper')
                    || grid;
            """, GRID_CSS)

            if not scroller:
                logger.error("   ✗ Grid scroller not found")
                return []

            self.driver.execute_script("arguments[0].scrollTop = 0;", scroller)
            time.sleep(SCROLL_PAUSE_S)

            stale_count = 0
            scroll_count = 0
            no_overlap_warnings = 0
            previous_ids: set = set()

            while scroll_count < 300:
                rows_data = self._harvest_visible_rows(GRID_CSS)
                current_ids: set = set()
                new_this_round = 0

                for row_cells in rows_data:
                    if not row_cells or not row_cells[0].strip():
                        continue

                    favorecido = row_cells[0].strip()
                    if favorecido.upper().startswith("TOTAL"):
                        continue

                    parsed = self._parse_favorecido(favorecido)
                    if not parsed:
                        continue

                    company_id, company_name = parsed
                    current_ids.add(company_id)

                    if company_id not in seen_ids:
                        seen_ids.add(company_id)
                        companies.append(CompanyData(
                            company_id=company_id,
                            company_name=company_name,
                            company_cnpj=(
                                company_id
                                if len(re.sub(r'\D', '', company_id)) == 14
                                else None
                            ),
                            total_contracts=0,
                            total_value=(
                                row_cells[1].strip() if len(row_cells) > 1 else None
                            ),
                            raw_cells=row_cells,
                        ))
                        new_this_round += 1

                # Overlap check
                if previous_ids and current_ids and not (previous_ids & current_ids):
                    no_overlap_warnings += 1
                    logger.warning(
                        f"   ⚠ No row overlap at scroll step {scroll_count} "
                        f"(#{no_overlap_warnings}) — possible gap"
                    )
                    if no_overlap_warnings >= 2:
                        SCROLL_INCREMENT = max(50, SCROLL_INCREMENT // 2)

                previous_ids = current_ids.copy()

                # Staleness check
                stale_count = 0 if new_this_round > 0 else stale_count + 1
                if stale_count >= STALE_ROUNDS:
                    logger.info(
                        f"   → No new rows for {STALE_ROUNDS} consecutive scrolls"
                    )
                    break

                time.sleep(0.5)

                old_top = self.driver.execute_script(
                    "return arguments[0].scrollTop;", scroller
                )
                self.driver.execute_script(
                    "arguments[0].scrollTop += arguments[1];",
                    scroller, SCROLL_INCREMENT
                )
                time.sleep(SCROLL_PAUSE_S)
                new_top = self.driver.execute_script(
                    "return arguments[0].scrollTop;", scroller
                )

                if new_top == old_top:
                    # Final harvest at bottom
                    for row_cells in self._harvest_visible_rows(GRID_CSS):
                        if not row_cells or not row_cells[0].strip():
                            continue
                        if row_cells[0].strip().upper().startswith("TOTAL"):
                            continue
                        parsed = self._parse_favorecido(row_cells[0].strip())
                        if parsed and parsed[0] not in seen_ids:
                            seen_ids.add(parsed[0])
                            companies.append(CompanyData(
                                company_id=parsed[0],
                                company_name=parsed[1],
                                company_cnpj=(
                                    parsed[0]
                                    if len(re.sub(r'\D', '', parsed[0])) == 14
                                    else None
                                ),
                                total_contracts=0,
                                total_value=(
                                    row_cells[1].strip()
                                    if len(row_cells) > 1 else None
                                ),
                            ))
                    logger.info("   → Reached grid bottom")
                    break

                scroll_count += 1
                if scroll_count % 10 == 0:
                    logger.info(
                        f"   ... scroll step {scroll_count} | "
                        f"{len(companies)} companies so far"
                    )

            logger.info(f"   ✓ {len(companies)} unique companies collected")
            if no_overlap_warnings > 0:
                logger.warning(
                    f"   ⚠ {no_overlap_warnings} overlap gap(s) detected — "
                    f"some companies may be missing"
                )
            return companies

        except Exception as e:
            logger.error(f"   ✗ Company collection failed: {e}")
            return companies   # Return whatever was collected before the failure

    def _harvest_visible_rows(self, grid_css: str) -> List[List[str]]:
        """Read cell text from all currently rendered grid rows via JS."""
        return self.driver.execute_script("""
            var grid = document.querySelector(arguments[0]);
            if (!grid) return [];
            var tbody = grid.querySelector('table tbody')
                       || grid.querySelector('.v-grid-body');
            if (!tbody) return [];
            var rows = tbody.querySelectorAll('tr');
            var result = [];
            for (var i = 0; i < rows.length; i++) {
                var cells = rows[i].querySelectorAll(
                    'td.v-grid-cell[role="gridcell"]'
                );
                if (cells.length === 0) continue;
                var rowData = [];
                for (var j = 0; j < cells.length; j++) {
                    rowData.push(cells[j].innerText.trim());
                }
                result.push(rowData);
            }
            return result;
        """, grid_css) or []

    @staticmethod
    def _parse_favorecido(text: str) -> Optional[Tuple[str, str]]:
        """
        Parse "01282704000167 - GREMIO RECREATIVO ..." into (id, name).

        Returns None if the text cannot be parsed.
        """
        if not text or text.upper().startswith("TOTAL"):
            return None

        parts = text.split(" - ", maxsplit=1)
        if len(parts) == 2:
            company_id = parts[0].strip()
            company_name = parts[1].strip()
        else:
            company_id = re.sub(r'[^A-Za-z0-9]', '', text)[:30].upper()
            company_name = text
            logger.warning(f"   ⚠ No ' - ' separator in Favorecido: {text[:60]}")

        if not company_id or not company_name:
            return None

        company_id = re.sub(r'[^A-Za-z0-9]', '', company_id).upper()
        return (company_id, company_name)