"""
infrastructure/web/captcha_handler.py

Unified CAPTCHA handler for processo.rio.

Key change vs previous version
───────────────────────────────
All manual fallback paths now use wait_for_manual_with_input() (blocking
input() call) instead of the countdown-timer approach. This is necessary
because reCAPTCHA v2 image challenges often render an empty grid inside
an automated Chrome session — the user needs unlimited time and clear
instructions on how to force the images to load.
"""
import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    ElementClickInterceptedException,
    ElementNotInteractableException,
)
from selenium.webdriver.common.action_chains import ActionChains

import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# =========================================================================
# CONFIGURATION
# =========================================================================

CAPTCHA_AUTO_WAIT = 3          # Seconds to wait after auto-actions
CAPTCHA_MANUAL_TIMEOUT = 300   # 5 minutes for manual resolution


# =========================================================================
# CAPTCHA HANDLER CLASS
# =========================================================================

class CaptchaHandler:
    """
    Handles reCAPTCHA on processo.rio.

    Strategy
    ────────
    1. If already on documents page → done, no CAPTCHA needed.
    2. Auto-click the "não sou um robô" checkbox.
    3. Auto-click "Consultar".
    4. If documents page loads → done.
    5. If image challenge appears (or checkbox was clicked but grid is empty)
       → pause and ask the user to resolve it manually.
    6. The manual pause uses input() (blocking) so the user has unlimited
       time — important when the challenge grid renders blank.
    """
    
    def __init__(self, driver):
        """
        Initialize with Selenium WebDriver.
        
        Args:
            driver: Selenium WebDriver instance
        """
        self.driver         = driver
        self.captcha_solved = False
    
    # =====================================================================
    # DETECTION METHODS
    # =====================================================================
    
    def detect_captcha(self) -> bool:
        """
        Detect if CAPTCHA is present on the page.

        """
        captcha_indicators = [
            "//iframe[contains(@src, 'recaptcha')]",
            "//div[contains(@class, 'g-recaptcha')]",
            "//*[contains(text(), 'não sou um robô')]",
            "//*[contains(text(), 'Não sou um robô')]",
            "//*[contains(text(), 'not a robot')]",
            "//div[@class='recaptcha-checkbox-border']",
        ]
        
        for xpath in captcha_indicators:
            try:
                element = self.driver.find_element(By.XPATH, xpath)
                if element.is_displayed():
                    return True
            except NoSuchElementException:
                continue
        return False
    
    def is_on_captcha_page(self) -> bool:
        """
        Check if we're on a CAPTCHA/security verification page.
        
        Returns:
            bool: True if on CAPTCHA page
        """
        indicators = [
            "Verificação de segurança",
            "Verificação de seguranca",
            "Verificaçao de seguranca",
            "Verificacão de seguranca",
            "Verificacao de seguranca",
            "Verificacão de segurança",
        ]
        try:
            page_text = self.driver.find_element(By.TAG_NAME, "body").text
            return any(ind in page_text for ind in indicators)
        except Exception:
            return False
    
    def is_on_documents_page(self) -> bool:
        """
        True if the CAPTCHA gate was passed — regardless of what the portal
        shows on the other side.

        Three valid post-CAPTCHA states all return True:
          1. Documents are listed ("Últimos documentos", "Documento capturado")
          2. Portal shows a no-document alert — the alert itself is proof
             the security gate was cleared; the downloader handles it next.
          3. (Future states can be added here without touching handle())
        """
        try:
            page_text = self.driver.find_element(By.TAG_NAME, "body").text

            # State 1: documents present
            if any(ind in page_text for ind in ["Últimos documentos", "Documento capturado"]):
                return True

            # State 2: portal error alert — CAPTCHA was solved, just no file
            alerts = self.driver.find_elements(
                By.CSS_SELECTOR, "p.alert.alert-danger, div.alert.alert-danger"
            )
            if alerts:
                return True

        except Exception:
            pass
        return False
    
    def is_image_challenge_visible(self) -> bool:
        """
        Check if the reCAPTCHA image challenge iframe (bframe) is visible.

        Returns:
            bool: True if the image challenge iframe is present and displayed
        """
        try:
            for iframe in self.driver.find_elements(By.TAG_NAME, "iframe"):
                src = iframe.get_attribute("src") or ""
                if "bframe" in src and iframe.is_displayed():
                    return True
            return False
        except Exception:
            return False

    def is_grid_empty(self) -> bool:
        """
        Switch into the reCAPTCHA bframe and check whether images rendered.

        A visible bframe with 0 <img> elements (or all images with no src)
        means the challenge grid is blank — the user cannot solve it without
        additional steps.

        Returns True  → grid is present but empty (needs intervention).
        Returns False → images loaded normally, or bframe not found.
        """
        try:
            bframe = None
            for iframe in self.driver.find_elements(By.TAG_NAME, "iframe"):
                src = iframe.get_attribute("src") or ""
                if "bframe" in src and iframe.is_displayed():
                    bframe = iframe
                    break

            if bframe is None:
                return False

            self.driver.switch_to.frame(bframe)
            try:
                imgs = self.driver.find_elements(By.TAG_NAME, "img")
                visible_imgs = [
                    img for img in imgs
                    if img.is_displayed() and img.get_attribute("src")
                ]
                return len(visible_imgs) == 0
            finally:
                self.driver.switch_to.default_content()

        except Exception:
            try:
                self.driver.switch_to.default_content()
            except Exception:
                pass
            return False
    
    # =====================================================================
    # ACTION METHODS
    # =====================================================================
    
    def play_alert_sound(self) -> None:
        """Two-beep alert on Windows; silent on other platforms."""
        try:
            import winsound
            winsound.Beep(1000, 500)
            winsound.Beep(1500, 500)
        except Exception:
            pass


    def click_recaptcha_checkbox(self) -> bool:
        """Switch into the reCAPTCHA iframe and click the checkbox."""
        try:
            iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
            recaptcha_iframe = None
            for iframe in iframes:
                src = iframe.get_attribute("src") or ""
                if "recaptcha" in src.lower() and "anchor" in src.lower():
                    recaptcha_iframe = iframe
                    break

            if not recaptcha_iframe:
                return False

            self.driver.switch_to.frame(recaptcha_iframe)
            try:
                checkbox = WebDriverWait(self.driver, 5).until(
                    EC.element_to_be_clickable((
                        By.CSS_SELECTOR,
                        ".recaptcha-checkbox-border, #recaptcha-anchor",
                    ))
                )
                ActionChains(self.driver)\
                    .move_to_element(checkbox)\
                    .pause(0.3)\
                    .click()\
                    .perform()
                return True
            finally:
                self.driver.switch_to.default_content()

        except Exception:
            try:
                self.driver.switch_to.default_content()
            except Exception:
                pass
            return False
            
    def click_consultar_button(self) -> bool:
        """Click the 'Consultar' submit button on the security-check page."""
        selectors = [
            ("css",   "button.btn-primary.btn-block[type='submit']"),
            ("css",   "button.btn-primary[type='submit']"),
            ("css",   "button[type='submit'].btn-primary"),
            ("xpath", "//button[contains(., 'Consultar')]"),
            ("xpath", "//button[@type='submit'][contains(@class, 'btn-primary')]"),
            ("xpath", "//button[.//i[contains(@class, 'fa-stamp')]]"),
        ]
        for selector_type, selector in selectors:
            try:
                btn = (
                    self.driver.find_element(By.CSS_SELECTOR, selector)
                    if selector_type == "css"
                    else self.driver.find_element(By.XPATH, selector)
                )
                self.driver.execute_script(
                    "arguments[0].scrollIntoView({block: 'center'});", btn
                )
                time.sleep(0.3)
                if not btn.is_enabled():
                    continue
                try:
                    btn.click()
                except (ElementClickInterceptedException, ElementNotInteractableException):
                    self.driver.execute_script("arguments[0].click();", btn)
                return True
            except NoSuchElementException:
                continue
            except Exception:
                continue
        return False
    
    # =====================================================================
    # MANUAL RESOLUTION
    # =====================================================================
    
    def wait_for_manual_with_input(self, reason: str = "") -> bool:
        """
        Block until the user presses ENTER after solving the CAPTCHA.

        Uses input() so there is NO timeout — the user can take as long
        as needed. This is the correct approach when the image challenge
        grid renders blank inside an automated Chrome session.

        Empty-grid troubleshooting steps shown to the user:
          1. Click the reload (↺) icon inside the challenge box.
          2. If the grid stays empty, right-click the CAPTCHA → Inspect,
             scroll to the bframe iframe src, and open it in a new tab.
          3. As a last resort: close this browser, open a real Chrome,
             navigate to the URL manually, solve CAPTCHA, then re-run
             with the session cookies.
        """
        self.play_alert_sound()

        sep = "=" * 65
        print(f"\n{sep}")
        print("🔐  MANUAL CAPTCHA RESOLUTION REQUIRED")
        if reason:
            print(f"    Reason: {reason}")
        print(sep)
        print("""
  The browser has paused. Please solve the CAPTCHA now.

  ── If the image grid is EMPTY ──────────────────────────────
  This happens when reCAPTCHA detects automation. Try these in order:

    1. Click the RELOAD icon (↺) inside the challenge box.
       A new set of images should appear.

    2. If the grid stays blank after reloading:
       - Right-click anywhere on the CAPTCHA → "Inspect"
       - Find the <iframe src="...bframe..."> element
       - Copy that URL and open it in a NEW normal Chrome tab
       - Solve the challenge there; the result carries back here.

    3. Still blank? Close this browser window, open a regular Chrome,
       navigate to the processo.rio URL manually, solve the CAPTCHA,
       and then re-run the script.

  ── Once you can see the images ─────────────────────────────
    Select all matching images, then click "Verificar".
    Wait until the documents page loads in THIS browser.
    Then press ENTER below to continue.
""")
        print(sep)
        input("  ▶  Press ENTER after the documents page has loaded... ")

        time.sleep(1)
        if self.is_on_documents_page():
            logging.info("✅ Documents page confirmed — continuing.")
            self.captcha_solved = True
            return True

        # User pressed ENTER but page isn't there yet
        logging.warning(
            "⚠  Documents page not detected after ENTER. "
            "The CAPTCHA may not have been fully solved. Continuing anyway."
        )
        self.captcha_solved = True   # optimistic — pipeline will fail fast if wrong
        return True

    # ── Main handler ──────────────────────────────────────────────────────────

    def handle(self) -> bool:
        """
        Full CAPTCHA resolution flow.

        Returns True if we end up on the documents page (or reasonably
        believe the CAPTCHA is resolved).
        """
        # Already past CAPTCHA?
        if self.is_on_documents_page():
            self.captcha_solved = True
            return True

        # Not on CAPTCHA page at all?
        if not self.is_on_captcha_page() and not self.detect_captcha():
            return True

        logging.info("\n🔐 CAPTCHA detected — attempting auto-resolution...")

        # Try Consultar directly (checkbox may already be ticked from a
        # previous navigate on the same session)
        if self.click_consultar_button():
            time.sleep(CAPTCHA_AUTO_WAIT)
            if self.is_on_documents_page():
                logging.info("✅ Auto-resolved (Consultar click).")
                self.captcha_solved = True
                return True

        # Click the "não sou um robô" checkbox
        logging.info("   → Clicking reCAPTCHA checkbox...")
        clicked = self.click_recaptcha_checkbox()
        if clicked:
            time.sleep(2)

        # Click Consultar
        if self.click_consultar_button():
            time.sleep(CAPTCHA_AUTO_WAIT)

            if self.is_on_documents_page():
                logging.info("✅ Auto-resolved (checkbox + Consultar).")
                self.captcha_solved = True
                return True

            # Still on CAPTCHA page — inspect what kind of challenge appeared
            if self.is_on_captcha_page():
                if self.is_image_challenge_visible():
                    if self.is_grid_empty():
                        # bframe present but no images rendered → empty grid
                        logging.warning(
                            "   🕳  Challenge grid is EMPTY — "
                            "reCAPTCHA is blocking automated Chrome. "
                            "Showing empty-grid recovery instructions."
                        )
                        return self.wait_for_manual_with_input(
                            reason="image challenge grid rendered blank"
                        )
                    else:
                        # Images loaded normally — user can solve it
                        logging.info(
                            "   🖼  Image challenge detected with images — "
                            "manual resolution needed."
                        )
                        return self.wait_for_manual_with_input(
                            reason="image challenge appeared — please select and verify"
                        )
                else:
                    # On CAPTCHA page but no bframe — may need another click
                    time.sleep(2)
                    if self.click_consultar_button():
                        time.sleep(CAPTCHA_AUTO_WAIT)
                        if self.is_on_documents_page():
                            self.captcha_solved = True
                            return True

        # Checkbox click failed or Consultar not found — check once more
        time.sleep(2)
        if self.is_on_documents_page():
            self.captcha_solved = True
            return True

        # Fall through to manual
        logging.warning("⚠  Auto-resolution unsuccessful — manual input required.")
        return self.wait_for_manual_with_input(
            reason="automatic steps did not reach the documents page"
        )


# ── Convenience function ──────────────────────────────────────────────────────

def handle_captcha(driver) -> bool:
    return CaptchaHandler(driver).handle()