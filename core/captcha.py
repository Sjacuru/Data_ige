"""
core/captcha.py - Unified CAPTCHA handling for all scrapers.

Merged from:
- src/document_extractor.py (DocumentExtractor.handle_captcha)
- scripts/extract_processo_documents.py (CaptchaHandler)

Usage:
    from core.captcha import CaptchaHandler
    
    handler = CaptchaHandler(driver)
    if handler.handle():
        print("CAPTCHA resolved!")
    else:
        print("CAPTCHA failed")
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
    Unified CAPTCHA handler for processo.rio and similar sites.
    
    Features:
    - Detects CAPTCHA presence
    - Auto-clicks reCAPTCHA checkbox
    - Clicks "Consultar" button
    - Detects image challenges
    - Waits for manual resolution when needed
    - Plays alert sound (Windows)
    
    Usage:
        handler = CaptchaHandler(driver)
        
        # Full automatic handling with manual fallback
        if handler.handle():
            print("Success!")
        
        # Or use individual methods
        if handler.detect_captcha():
            handler.click_recaptcha_checkbox()
    """
    
    def __init__(self, driver):
        """
        Initialize with Selenium WebDriver.
        
        Args:
            driver: Selenium WebDriver instance
        """
        self.driver = driver
        self.captcha_solved = False
    
    # =====================================================================
    # DETECTION METHODS
    # =====================================================================
    
    def detect_captcha(self) -> bool:
        """
        Detect if CAPTCHA is present on the page.
        
        Returns:
            bool: True if CAPTCHA detected
        """
        captcha_indicators = [
            "//iframe[contains(@src, 'recaptcha')]",
            "//div[contains(@class, 'g-recaptcha')]",
            "//*[contains(text(), 'não sou um robô')]",
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
        ]
        try:
            page_text = self.driver.find_element(By.TAG_NAME, "body").text
            for indicator in indicators:
                if indicator in page_text:
                    return True
        except Exception:
            pass
        return False
    
    def is_on_documents_page(self) -> bool:
        """
        Check if we're already on the documents page (CAPTCHA passed).
        
        Returns:
            bool: True if on documents page
        """
        indicators = [
            "Últimos documentos",
            "Documento capturado",
        ]
        try:
            page_text = self.driver.find_element(By.TAG_NAME, "body").text
            for indicator in indicators:
                if indicator in page_text:
                    return True
        except Exception:
            pass
        return False
    
    def is_image_challenge_visible(self) -> bool:
        """
        Check if there's a visible image challenge (select pictures).
        
        Returns:
            bool: True if image challenge is visible
        """
        try:
            iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
            for iframe in iframes:
                src = iframe.get_attribute('src') or ''
                if 'bframe' in src:
                    if iframe.is_displayed():
                        size = iframe.size
                        if size.get('height', 0) > 200 and size.get('width', 0) > 200:
                            return True
            return False
        except Exception:
            return False
    
    # =====================================================================
    # ACTION METHODS
    # =====================================================================
    
    def click_recaptcha_checkbox(self) -> bool:
        """
        Find and click the reCAPTCHA checkbox.
        
        Returns:
            bool: True if clicked successfully
        """
        try:
            # Find reCAPTCHA iframe
            iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
            recaptcha_iframe = None
            
            for iframe in iframes:
                src = iframe.get_attribute('src') or ''
                if 'recaptcha' in src.lower() and 'anchor' in src.lower():
                    recaptcha_iframe = iframe
                    break
            
            if not recaptcha_iframe:
                return False
            
            # Switch to iframe
            self.driver.switch_to.frame(recaptcha_iframe)
            
            try:
                # Find and click checkbox
                checkbox = WebDriverWait(self.driver, 5).until(
                    EC.element_to_be_clickable((
                        By.CSS_SELECTOR,
                        ".recaptcha-checkbox-border, #recaptcha-anchor"
                    ))
                )
                
                # Use ActionChains for more reliable click
                actions = ActionChains(self.driver)
                actions.move_to_element(checkbox)
                actions.pause(0.3)
                actions.click()
                actions.perform()
                
                return True
                
            finally:
                # Always switch back to main content
                self.driver.switch_to.default_content()
                
        except Exception as e:
            # Ensure we're back in main content
            try:
                self.driver.switch_to.default_content()
            except:
                pass
            return False
    
    def click_consultar_button(self) -> bool:
        """
        Click the "Consultar" button on security verification pages.
        
        Returns:
            bool: True if clicked successfully
        """
        selectors = [
            ("css", "button.btn-primary.btn-block[type='submit']"),
            ("css", "button.btn-primary[type='submit']"),
            ("css", "button[type='submit'].btn-primary"),
            ("xpath", "//button[contains(., 'Consultar')]"),
            ("xpath", "//button[@type='submit'][contains(@class, 'btn-primary')]"),
            ("xpath", "//button[.//i[contains(@class, 'fa-stamp')]]"),
        ]
        
        for selector_type, selector in selectors:
            try:
                if selector_type == "css":
                    button = self.driver.find_element(By.CSS_SELECTOR, selector)
                else:
                    button = self.driver.find_element(By.XPATH, selector)
                
                # Scroll into view
                self.driver.execute_script(
                    "arguments[0].scrollIntoView({block: 'center'});", 
                    button
                )
                time.sleep(0.3)
                
                if not button.is_enabled():
                    continue
                
                # Try to click
                try:
                    button.click()
                except (ElementClickInterceptedException, ElementNotInteractableException):
                    self.driver.execute_script("arguments[0].click();", button)
                
                return True
                
            except NoSuchElementException:
                continue
            except Exception:
                continue
        
        return False
    
    # =====================================================================
    # MANUAL RESOLUTION
    # =====================================================================
    
    def play_alert_sound(self) -> None:
        """Play alert sound to notify user (Windows only)."""
        try:
            import winsound
            winsound.Beep(1000, 500)
            winsound.Beep(1500, 500)
        except:
            pass
    
    def wait_for_manual_resolution(self, timeout: int = None) -> bool:
        """
        Wait for user to manually resolve CAPTCHA.
        
        Uses polling (not blocking input) so it works in all environments.
        
        Args:
            timeout: Maximum wait time in seconds (default: CAPTCHA_MANUAL_TIMEOUT)
            
        Returns:
            bool: True if CAPTCHA was resolved
        """
        if timeout is None:
            timeout = CAPTCHA_MANUAL_TIMEOUT
        
        print("\n" + "=" * 60)
        print("🔐 MANUAL INTERVENTION REQUIRED")
        print("=" * 60)
        print("\n📋 Please resolve the CAPTCHA in the browser")
        print("   The script will detect when you're done")
        print(f"\n⏱️  Maximum wait: {timeout // 60} minutes")
        print("=" * 60)
        
        self.play_alert_sound()
        
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            # Check if we made it to the documents page
            if self.is_on_documents_page():
                print("\n\n✅ Documents page loaded!")
                self.captcha_solved = True
                return True
            
            # Check if we left the CAPTCHA page
            if not self.is_on_captcha_page():
                print("\n\n✅ Left CAPTCHA page!")
                self.captcha_solved = True
                return True
            
            # Show countdown
            elapsed = int(time.time() - start_time)
            remaining = timeout - elapsed
            print(f"\r⏳ Waiting... {remaining}s remaining    ", end='', flush=True)
            
            time.sleep(2)
        
        print("\n\n❌ Timeout!")
        return False
    
    def wait_for_manual_with_input(self) -> bool:
        """
        Alternative: Wait for user to press Enter.
        
        Use this if you prefer blocking behavior.
        
        Returns:
            bool: True (assumes user resolved it)
        """
        print("\n" + "=" * 60)
        print("🔐 MANUAL INTERVENTION REQUIRED")
        print("=" * 60)
        print("\n📋 Please resolve the CAPTCHA in the browser.")
        print("=" * 60)
        
        self.play_alert_sound()
        
        input("\n   Press ENTER when done...")
        
        time.sleep(1)
        
        if self.detect_captcha():
            print("   ⚠ CAPTCHA still present. Continuing anyway...")
            return False
        
        print("   ✓ CAPTCHA resolved!")
        self.captcha_solved = True
        return True
    
    # =====================================================================
    # MAIN HANDLER
    # =====================================================================
    
    def handle(self) -> bool:
        """
        Main CAPTCHA handling flow.
        
        Attempts automatic resolution, falls back to manual if needed.
        
        Returns:
            bool: True if CAPTCHA was resolved (or wasn't present)
        """
        # Step 1: Check if already on documents page
        if self.is_on_documents_page():
            self.captcha_solved = True
            return True
        
        # Step 2: Check if on CAPTCHA page
        if not self.is_on_captcha_page() and not self.detect_captcha():
            return True  # No CAPTCHA present
        
        print("\n🔐 CAPTCHA detected, attempting resolution...")
        
        # Step 3: Try clicking Consultar directly (maybe checkbox already checked)
        if self.click_consultar_button():
            time.sleep(CAPTCHA_AUTO_WAIT)
            if self.is_on_documents_page():
                print("✅ Success! Page loaded after clicking Consultar")
                self.captcha_solved = True
                return True
        
        # Step 4: Click reCAPTCHA checkbox
        print("   → Clicking reCAPTCHA checkbox...")
        if self.click_recaptcha_checkbox():
            time.sleep(2)
            
            # Step 5: Try clicking Consultar again
            if self.click_consultar_button():
                time.sleep(CAPTCHA_AUTO_WAIT)
                
                # Step 6: Check result
                if self.is_on_documents_page():
                    print("✅ Success! CAPTCHA resolved automatically")
                    self.captcha_solved = True
                    return True
                
                # Step 7: Check for image challenge
                if self.is_on_captcha_page():
                    if self.is_image_challenge_visible():
                        print("   🖼️ Image challenge detected - manual resolution needed")
                        return self.wait_for_manual_resolution()
                    else:
                        # Try one more time
                        time.sleep(2)
                        if self.click_consultar_button():
                            time.sleep(CAPTCHA_AUTO_WAIT)
                            if self.is_on_documents_page():
                                self.captcha_solved = True
                                return True
                else:
                    # Left CAPTCHA page
                    self.captcha_solved = True
                    return True
        
        # Step 8: Final check
        time.sleep(2)
        if self.is_on_documents_page():
            self.captcha_solved = True
            return True
        
        # Step 9: Manual intervention needed
        print("⚠️ Automatic resolution failed")
        return self.wait_for_manual_resolution()


# =========================================================================
# CONVENIENCE FUNCTION
# =========================================================================

def handle_captcha(driver) -> bool:
    """
    Convenience function for quick CAPTCHA handling.
    
    Usage:
        from core.captcha import handle_captcha
        
        if handle_captcha(driver):
            print("Ready to continue!")
    
    Args:
        driver: Selenium WebDriver instance
        
    Returns:
        bool: True if CAPTCHA resolved or not present
    """
    handler = CaptchaHandler(driver)
    return handler.handle()