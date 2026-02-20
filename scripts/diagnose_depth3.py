"""
DIAGNOSTIC v3 — Depth-3 Content Inspector
==========================================
We know depth 3 has 0 v-button.link.small elements.
This script navigates to depth 3 and does a FULL DOM inventory
to find how contracts are actually rendered there.

Run with:
    python scripts/diagnose_depth3.py

Outputs:
    data/discovery/nav_diagnostic_v3.json
"""
import sys
import time
import json
import logging
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

from infrastructure.web.driver import create_driver, close_driver
from infrastructure.logging_config import setup_logging
from config.settings import CONTASRIO_CONTRACTS_URL, DISCOVERY_DIR

setup_logging("diagnosis_v3", log_level=logging.DEBUG)
logger = logging.getLogger(__name__)

CLICK_PAUSE = 3.0


def wait_for_settle(driver, timeout=15):
    try:
        WebDriverWait(driver, 1.5).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "div.v-loading-indicator[style*='display: block']")
            )
        )
    except TimeoutException:
        pass
    try:
        WebDriverWait(driver, timeout).until(
            EC.invisibility_of_element_located(
                (By.CSS_SELECTOR, "div.v-loading-indicator")
            )
        )
    except TimeoutException:
        pass
    time.sleep(1.0)


def click_button_by_text(driver, text):
    result = driver.execute_script("""
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
    if result:
        time.sleep(CLICK_PAUSE)
    return bool(result)


def full_dom_inventory(driver):
    """
    Capture EVERYTHING interactive or content-bearing on the current page.
    Cast the widest possible net.
    """
    return driver.execute_script("""
        var inventory = {
            all_buttons: [],
            all_links: [],
            all_grid_cells: [],
            all_grid_rows: [],
            vaadin_elements: [],
            any_text_with_numbers: [],
            page_text_summary: '',
        };

        // ── Every button regardless of class ───────────────────────────────
        document.querySelectorAll('button, [role="button"]').forEach(function(el) {
            var text = el.innerText.trim();
            if (text) inventory.all_buttons.push({
                text: text.substring(0, 100),
                class: el.className,
                tag: el.tagName,
                visible: el.offsetParent !== null
            });
        });

        // ── Every <a> tag ──────────────────────────────────────────────────
        document.querySelectorAll('a').forEach(function(el) {
            var text = el.innerText.trim();
            var href = el.getAttribute('href') || '';
            if (text || href) inventory.all_links.push({
                text: text.substring(0, 100),
                href: href.substring(0, 200),
                class: el.className
            });
        });

        // ── Every grid cell ────────────────────────────────────────────────
        document.querySelectorAll('td, .v-grid-cell, [role="gridcell"]').forEach(function(el) {
            var text = el.innerText.trim();
            if (text) inventory.all_grid_cells.push({
                text: text.substring(0, 150),
                class: el.className,
                role: el.getAttribute('role') || ''
            });
        });

        // ── Grid rows with all cells ───────────────────────────────────────
        var rows = document.querySelectorAll('tr, .v-grid-row, [role="row"]');
        for (var i = 0; i < Math.min(rows.length, 30); i++) {
            var cells = rows[i].querySelectorAll('td, .v-grid-cell');
            var rowData = Array.from(cells).map(function(c) {
                return c.innerText.trim().substring(0, 150);
            }).filter(Boolean);
            if (rowData.length > 0) {
                inventory.all_grid_rows.push({
                    cells: rowData,
                    class: rows[i].className,
                    role: rows[i].getAttribute('role') || ''
                });
            }
        }

        // ── Any Vaadin-specific elements ───────────────────────────────────
        var vaadinSelectors = [
            '.v-button', '.v-label', '.v-link', '.v-panel',
            '.v-accordion', '.v-tree', '.v-table-row',
            '.v-tabsheet-tabitem', '.v-window', '.v-form',
            '.v-nativebutton', '.v-customcomponent'
        ];
        vaadinSelectors.forEach(function(sel) {
            document.querySelectorAll(sel).forEach(function(el) {
                var text = el.innerText.trim();
                if (text && text.length < 200 && text.charCodeAt(0) < 0x2000) {
                    inventory.vaadin_elements.push({
                        selector: sel,
                        text: text.substring(0, 150),
                        class: el.className.substring(0, 100)
                    });
                }
            });
        });

        // ── Any text that looks like contract numbers ──────────────────────
        var allText = document.body.innerText;
        var matches = allText.match(/[A-Z]{2,8}\\d{6,12}|\\d{2}\\/\\d{2}\\/\\d{6}\\/\\d{4}/g);
        if (matches) inventory.any_text_with_numbers = [...new Set(matches)];

        // ── Page text summary (first 2000 chars of body) ──────────────────
        inventory.page_text_summary = allText.substring(0, 2000);

        return inventory;
    """)


def run():
    logger.info("=" * 70)
    logger.info("🔬 DIAGNOSTIC v3 — Full Depth-3 DOM Inventory")
    logger.info("=" * 70)

    driver = create_driver(headless=False)
    if not driver:
        logger.error("Driver init failed")
        return

    result = {
        "diagnostic_date": datetime.now().isoformat(),
        "depth3_inventory": None
    }

    try:
        # Navigate to contracts page
        driver.get(CONTASRIO_CONTRACTS_URL)
        time.sleep(5)
        driver.refresh()
        time.sleep(3)
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "td.v-grid-cell[role='gridcell']")
            )
        )
        wait_for_settle(driver)
        logger.info("✓ Contracts page loaded")

        # ── Step 1: Click first company ───────────────────────────────────────
        company_text = "01282704000167 - GREMIO RECREATIVO ESCOLA DE SAMBA UNIDOS DE VILA ISABEL"
        logger.info(f"\n→ [D0→D1] Clicking company: {company_text[:50]}")
        if not click_button_by_text(driver, company_text):
            logger.error("Could not click company. Trying prefix match...")
            # Fallback: click any company button
            driver.execute_script("""
                var btns = document.querySelectorAll('.v-button.link.small');
                for (var i = 0; i < btns.length; i++) {
                    if (btns[i].innerText.charCodeAt(0) < 0x2000) {
                        btns[i].click(); break;
                    }
                }
            """)
            time.sleep(CLICK_PAUSE)
        wait_for_settle(driver)

        # ── Step 2: Click first Órgão ─────────────────────────────────────────
        orgao_text = "3351 - RIOTUR EMPRESA DE TURISMO DO MUNICÍPIO DO RIO DE JANEIRO S/A"
        logger.info(f"→ [D1→D2] Clicking órgão: {orgao_text[:50]}")
        if not click_button_by_text(driver, orgao_text):
            logger.warning("Exact match failed, trying any available button at D1...")
            driver.execute_script("""
                var btns = document.querySelectorAll('.v-button.link.small');
                for (var i = 0; i < btns.length; i++) {
                    if (btns[i].innerText.charCodeAt(0) < 0x2000) {
                        btns[i].click(); break;
                    }
                }
            """)
            time.sleep(CLICK_PAUSE)
        wait_for_settle(driver)

        # ── Step 3: Click first UG ────────────────────────────────────────────
        ug_text = "330051 - EMPRESA DE TURISMO DO MUNICÍPIO DO RIO DE JANEIRO - RIOTUR"
        logger.info(f"→ [D2→D3] Clicking UG: {ug_text[:50]}")
        if not click_button_by_text(driver, ug_text):
            logger.warning("Exact match failed, trying any available button at D2...")
            driver.execute_script("""
                var btns = document.querySelectorAll('.v-button.link.small');
                for (var i = 0; i < btns.length; i++) {
                    if (btns[i].innerText.charCodeAt(0) < 0x2000) {
                        btns[i].click(); break;
                    }
                }
            """)
            time.sleep(CLICK_PAUSE)
        wait_for_settle(driver)

        # ── We are now at Depth 3 — FULL INVENTORY ────────────────────────────
        logger.info("\n📸 At Depth 3 — Running full DOM inventory...")
        time.sleep(2)  # Extra settle time

        inventory = full_dom_inventory(driver)
        result["depth3_inventory"] = inventory

        # ── Print findings ────────────────────────────────────────────────────
        print("\n" + "=" * 70)
        print("📊 DEPTH-3 DOM INVENTORY")
        print("=" * 70)

        print(f"\n🔘 All Buttons ({len(inventory['all_buttons'])} total):")
        for btn in inventory['all_buttons']:
            print(f"   [{btn['class'][:50]}]")
            print(f"   text: '{btn['text'][:80]}'")
            print()

        print(f"\n🔗 All Links ({len(inventory['all_links'])} total):")
        for lnk in inventory['all_links']:
            if lnk['text'] or lnk['href']:
                print(f"   text: '{lnk['text'][:60]}' | href: '{lnk['href'][:80]}'")

        print(f"\n📋 Grid Rows ({len(inventory['all_grid_rows'])} total):")
        for row in inventory['all_grid_rows']:
            print(f"   [{row['class'][:40]}] {row['cells']}")

        print(f"\n🎯 Contract Number Patterns Found:")
        print(f"   {inventory['any_text_with_numbers']}")

        print(f"\n📄 Page Text (first 800 chars):")
        print(inventory['page_text_summary'][:800])

        print(f"\n🏗️ Vaadin Elements ({len(inventory['vaadin_elements'])} total):")
        for el in inventory['vaadin_elements'][:20]:
            print(f"   [{el['selector']}] '{el['text'][:80]}'")
            print(f"     class: {el['class'][:60]}")

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
    finally:
        out_dir = Path(DISCOVERY_DIR)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "nav_diagnostic_v3.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        logger.info(f"\n✓ Full inventory saved: {out_path}")

        input("\n⏸️  Browser is open. Press ENTER to close and exit...")
        close_driver(driver)


if __name__ == "__main__":
    run()