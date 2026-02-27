"""
tests/diagnose_stage1.py

1-minute diagnostic — runs against the LIVE portal, no full discovery.

What it does
------------
1. Opens browser and navigates to ContasRio contracts page
2. Waits for the grid to load
3. Probes 8 different DOM selectors to find what actually exists
4. Reads the first few company rows using the working selector
5. Checks current FILTER_YEAR setting
6. Reports everything — no writes to disk

Run from project root:
    python tests/diagnose_stage1.py

Expected duration: ~60-90 seconds (browser open the whole time)
The browser will stay open so you can inspect it yourself.
"""
import sys
import time
from pathlib import Path

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from infrastructure.web.driver import create_driver, close_driver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def ok(msg):   print(f"  {GREEN}✅ {msg}{RESET}")
def fail(msg): print(f"  {RED}❌ {msg}{RESET}")
def warn(msg): print(f"  {YELLOW}⚠  {msg}{RESET}")
def info(msg): print(f"  {CYAN}ℹ  {msg}{RESET}")
def head(msg): print(f"\n{BOLD}{CYAN}{'─'*60}\n  {msg}\n{'─'*60}{RESET}")


def main():
    from config.settings import CONTASRIO_CONTRACTS_URL, FILTER_YEAR

    print(f"\n{BOLD}{'='*60}")
    print("  STAGE 1 — DOM DIAGNOSTIC")
    print(f"{'='*60}{RESET}")

    # ── Config check ──────────────────────────────────────────────────────────
    head("1. CONFIG CHECK")
    info(f"CONTASRIO_CONTRACTS_URL = {CONTASRIO_CONTRACTS_URL}")
    info(f"FILTER_YEAR             = {FILTER_YEAR}")
    if not FILTER_YEAR:
        warn("FILTER_YEAR is empty — no year filter will be applied")

    # ── Browser + navigation ──────────────────────────────────────────────────
    head("2. NAVIGATION")
    driver = create_driver(headless=False, anti_detection=True)
    if not driver:
        fail("WebDriver failed to initialise — check Chrome + chromedriver")
        return

    try:
        info(f"Navigating to: {CONTASRIO_CONTRACTS_URL}")
        driver.get(CONTASRIO_CONTRACTS_URL)
        time.sleep(3)

        current_url = driver.current_url
        info(f"Current URL after navigation: {current_url}")

        if "#!Contratos/Contrato" in current_url:
            ok("URL contains expected fragment (#!Contratos/Contrato)")
        else:
            warn(f"Unexpected URL — may not be on contracts page")

        # Wait for any grid cell to appear
        info("Waiting up to 60s for td.v-grid-cell to appear...")
        try:
            WebDriverWait(driver, 60).until(
                lambda d: len(d.find_elements(
                    By.CSS_SELECTOR, "td.v-grid-cell[role='gridcell']"
                )) > 0
            )
            count = len(driver.find_elements(
                By.CSS_SELECTOR, "td.v-grid-cell[role='gridcell']"
            ))
            ok(f"Grid cells found: {count} td.v-grid-cell[role='gridcell'] elements")
        except TimeoutException:
            fail("No td.v-grid-cell appeared within 60s — grid did not load")
            return

        # ── Year filter state ─────────────────────────────────────────────────
        head("3. YEAR FILTER STATE")
        try:
            filter_inputs = driver.find_elements(
                By.CSS_SELECTOR,
                "input.v-filterselect-input"
            )
            info(f"Found {len(filter_inputs)} v-filterselect-input elements")
            for i, inp in enumerate(filter_inputs):
                val = inp.get_attribute("value") or "(empty)"
                placeholder = inp.get_attribute("placeholder") or ""
                info(f"  Input[{i}]: value='{val}' placeholder='{placeholder}'")
        except Exception as e:
            warn(f"Could not inspect filter inputs: {e}")

        # ── DOM selector probe ────────────────────────────────────────────────
        head("4. DOM SELECTOR PROBE — Finding the right row selector")

        selectors = {
            "table tbody tr":                            "Standard HTML table rows",
            ".v-grid-body tr":                          "Vaadin body via .v-grid-body",
            ".v-grid-body-row-container .v-grid-row":   "Vaadin 8 row container",
            ".v-grid-row.v-grid-row-has-data":           "Rows marked as has-data",
            "tr.v-grid-row":                             "tr elements with v-grid-row class",
            "div.v-grid-row":                            "div elements with v-grid-row class",
            ".v-grid-tablewrapper tr":                   "Rows inside tablewrapper",
            "td.v-grid-cell[role='gridcell']":           "Individual grid cells (known to work)",
        }

        working_row_selector = None
        for sel, desc in selectors.items():
            els = driver.find_elements(By.CSS_SELECTOR, sel)
            if els:
                ok(f"{len(els):>4} elements — {sel:<45} ({desc})")
                if "row" in sel.lower() and "cell" not in sel.lower():
                    working_row_selector = sel
            else:
                fail(f"   0 elements — {sel:<45} ({desc})")

        # ── _harvest_visible_rows simulation ──────────────────────────────────
        head("5. SIMULATING _harvest_visible_rows JS")

        result_current = driver.execute_script("""
            var grid = document.querySelector('div.v-grid');
            if (!grid) return {error: 'div.v-grid not found'};
            var tbody = grid.querySelector('table tbody')
                       || grid.querySelector('.v-grid-body');
            if (!tbody) return {error: 'tbody/v-grid-body not found inside grid', 
                                gridHTML: grid.outerHTML.substring(0, 500)};
            var rows = tbody.querySelectorAll('tr');
            return {found: rows.length, method: 'current code'};
        """)
        if result_current.get("error"):
            fail(f"Current _harvest_visible_rows fails: {result_current['error']}")
            if "gridHTML" in result_current:
                info(f"Grid outer HTML (first 500 chars):\n{result_current['gridHTML']}")
        else:
            ok(f"Current code finds {result_current['found']} rows")

        # ── Fixed selector simulation ─────────────────────────────────────────
        head("6. TESTING FIXED SELECTOR")

        fixed_result = driver.execute_script("""
            var rows = document.querySelectorAll('.v-grid-row.v-grid-row-has-data');
            var data = [];
            for (var i = 0; i < Math.min(rows.length, 5); i++) {
                var cells = rows[i].querySelectorAll(
                    'td.v-grid-cell[role="gridcell"]'
                );
                var rowData = [];
                for (var j = 0; j < cells.length; j++) {
                    rowData.push(cells[j].innerText.trim());
                }
                data.push(rowData);
            }
            return {total_rows: rows.length, sample: data};
        """)

        total_rows = fixed_result.get("total_rows", 0)
        sample = fixed_result.get("sample", [])

        if total_rows > 0:
            ok(f"Fixed selector finds {total_rows} rows — selector works!")
            info("Sample rows (first 5):")
            for i, row in enumerate(sample):
                if row:
                    info(f"  Row {i}: {' | '.join(str(c)[:30] for c in row[:4])}")
        else:
            warn("Fixed selector also finds 0 rows")
            warn("The grid may use a different structure — inspect browser DevTools")

        # ── _parse_favorecido simulation ──────────────────────────────────────
        head("7. TESTING _parse_favorecido PARSING")

        if sample:
            import re
            first_cell = sample[0][0] if sample[0] else ""
            info(f"First cell raw text: '{first_cell}'")

            # Try the current parse pattern
            # Pattern: "01282704000167 - GREMIO RECREATIVO..."
            m = re.match(r'^(\S+)\s*[-–]\s*(.+)$', first_cell.strip())
            if m:
                ok(f"_parse_favorecido pattern MATCHES: id='{m.group(1)}' name='{m.group(2)[:40]}'")
            else:
                fail(f"_parse_favorecido pattern does NOT match: '{first_cell[:60]}'")
                info("The cell content format differs from expected 'ID - NAME'")
                info("This is a secondary bug — fix _harvest_visible_rows first")
        else:
            warn("No sample rows to test parse pattern against")

        # ── Summary & recommendation ──────────────────────────────────────────
        head("8. DIAGNOSIS SUMMARY")

        if result_current.get("error"):
            print(f"""
  {RED}{BOLD}ROOT CAUSE CONFIRMED:{RESET}
  {RED}_harvest_visible_rows uses wrong JS selectors.{RESET}
  
  The fix: update _harvest_visible_rows in scraper.py to use:
    .v-grid-row.v-grid-row-has-data  (instead of table tbody tr)
  
  {YELLOW}Next step: tell Claude to patch scraper.py{RESET}
            """)
        elif total_rows == 0:
            print(f"""
  {YELLOW}{BOLD}UNUSUAL RESULT:{RESET}
  {YELLOW}Both selectors return 0 rows. Possible causes:{RESET}
  1. Year filter excluded all rows (check FILTER_YEAR = {FILTER_YEAR})
  2. Grid is still loading (try waiting longer)
  3. Portal structure has changed significantly
            """)
        else:
            print(f"""
  {GREEN}{BOLD}GRID READS CORRECTLY with fixed selector.{RESET}
  The only fix needed is updating _harvest_visible_rows in scraper.py.
            """)

        info("Browser staying open — inspect it yourself, then press ENTER to close")
        input()

    finally:
        close_driver(driver)
        print("Browser closed.")


if __name__ == "__main__":
    main()