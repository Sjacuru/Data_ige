#!/usr/bin/env python3
"""
Processo Document Extractor - Complete Version
Downloads contract documents from processo.rio
"""

import os
import sys
import time
import json
import hashlib
import re
import logging
import requests
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional, Any

import pandas as pd
import fitz  # PyMuPDF

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    ElementClickInterceptedException,
    ElementNotInteractableException,
    StaleElementReferenceException
)
from selenium.webdriver.common.action_chains import ActionChains
from webdriver_manager.chrome import ChromeDriverManager

# ============================================================
# CONFIGURATION
# ============================================================

INPUT_CSV = Path("data/outputs/analysis_summary.csv")
INPUT_XLSX = Path("data/outputs/analysis_summary.xlsx")

DOWNLOADS_DIR = Path("data/downloads/processos")
EXTRACTIONS_DIR = Path("data/extractions")

HEADLESS = False
TIMEOUT = 30
DELAY_BETWEEN_REQUESTS = 2
CAPTCHA_AUTO_WAIT = 3
CAPTCHA_MANUAL_TIMEOUT = 300

# Keywords to identify contract documents
CONTRACT_KEYWORDS = [
    "Íntegra do contrato",
    "Integra do contrato",
    "instrumentos jurídicos celebrados",
    "instrumentos juridicos celebrados",
]

# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('extraction_processo.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class ExtractedProcesso:
    """Represents an extracted processo with its documents."""
    processo_id: str
    empresa: str
    empresa_cnpj: str
    url: str
    documents: List[Dict[str, Any]]
    total_documents: int
    extraction_status: str
    extracted_at: str = ""
    error_message: str = ""

    def __post_init__(self):
        if not self.extracted_at:
            self.extracted_at = datetime.now().isoformat()


class CaptchaHandler:
    """Handles CAPTCHA detection and resolution."""

    def __init__(self, driver):
        self.driver = driver
        self.captcha_solved = False

    def is_on_documents_page(self) -> bool:
        """Check if we're already on the documents page."""
        indicators = [
            "Últimos documentos",
            "Documento capturado",
        ]
        try:
            page_text = self.driver.find_element(By.TAG_NAME, "body").text
            for indicator in indicators:
                if indicator in page_text:
                    logger.info(f"   ✅ Página de documentos detectada")
                    return True
        except Exception:
            pass
        return False

    def is_on_captcha_page(self) -> bool:
        """Check if we're on the CAPTCHA page."""
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

    def click_consultar_button(self) -> bool:
        """Click the Consultar button."""
        logger.info("   🖱️ Clicando no botão 'Consultar'...")

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

                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
                time.sleep(0.3)

                if not button.is_enabled():
                    continue

                try:
                    button.click()
                except (ElementClickInterceptedException, ElementNotInteractableException):
                    self.driver.execute_script("arguments[0].click();", button)

                logger.info("   ✅ Botão 'Consultar' clicado!")
                return True

            except NoSuchElementException:
                continue
            except Exception as e:
                logger.debug(f"   Erro: {e}")
                continue

        logger.warning("   ⚠️ Botão 'Consultar' não encontrado")
        return False

    def click_recaptcha_checkbox(self) -> bool:
        """Find and click the reCAPTCHA checkbox."""
        logger.info("   🔍 Procurando checkbox do reCAPTCHA...")

        try:
            iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
            recaptcha_iframe = None

            for iframe in iframes:
                src = iframe.get_attribute('src') or ''
                if 'recaptcha' in src.lower() and 'anchor' in src.lower():
                    recaptcha_iframe = iframe
                    break

            if not recaptcha_iframe:
                logger.warning("   ⚠️ iframe do reCAPTCHA não encontrado")
                return False

            self.driver.switch_to.frame(recaptcha_iframe)

            try:
                checkbox = WebDriverWait(self.driver, 5).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR,
                        ".recaptcha-checkbox-border, #recaptcha-anchor"
                    ))
                )

                actions = ActionChains(self.driver)
                actions.move_to_element(checkbox)
                actions.pause(0.3)
                actions.click()
                actions.perform()

                logger.info("   ✅ Clicou no checkbox do reCAPTCHA")
                return True

            finally:
                self.driver.switch_to.default_content()

        except Exception as e:
            logger.error(f"   ❌ Erro ao clicar checkbox: {e}")
            self.driver.switch_to.default_content()
            return False

    def is_image_challenge_visible(self) -> bool:
        """Check if there's actually a visible image challenge."""
        try:
            # Look for bframe iframe (image challenge)
            iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
            for iframe in iframes:
                src = iframe.get_attribute('src') or ''
                if 'bframe' in src:
                    # Check if it's actually visible
                    if iframe.is_displayed():
                        # Check size - challenge iframe is large
                        size = iframe.size
                        if size.get('height', 0) > 200 and size.get('width', 0) > 200:
                            logger.info("   🖼️ Desafio de imagens VISÍVEL detectado")
                            return True
            return False
        except Exception:
            return False

    def wait_for_manual_resolution(self) -> bool:
        """Wait for manual CAPTCHA resolution."""
        print("\n" + "=" * 60)
        print("🔐 INTERVENÇÃO MANUAL NECESSÁRIA")
        print("=" * 60)
        print("\n📋 Resolva o CAPTCHA no navegador (desafio de imagens)")
        print("   O script detectará automaticamente quando concluir")
        print(f"\n⏱️  Tempo máximo: {CAPTCHA_MANUAL_TIMEOUT // 60} minutos")
        print("=" * 60)

        start_time = time.time()

        while time.time() - start_time < CAPTCHA_MANUAL_TIMEOUT:
            # Check if already on documents page
            if self.is_on_documents_page():
                print("\n\n✅ Página de documentos carregada!")
                self.captcha_solved = True
                return True

            # Check if no longer on captcha page
            if not self.is_on_captcha_page():
                print("\n\n✅ Saiu da página de CAPTCHA!")
                self.captcha_solved = True
                return True

            elapsed = int(time.time() - start_time)
            remaining = CAPTCHA_MANUAL_TIMEOUT - elapsed
            print(f"\r⏳ Aguardando... {remaining}s restantes    ", end='', flush=True)
            time.sleep(2)

        print("\n\n❌ Tempo esgotado!")
        return False

    def handle(self) -> bool:
        """Main CAPTCHA handling logic - improved flow."""
        logger.info("🔐 Verificando estado da página...")

        # Step 1: Check if already on documents page
        if self.is_on_documents_page():
            logger.info("✅ Já na página de documentos")
            self.captcha_solved = True
            return True

        # Step 2: Check if on CAPTCHA page
        if not self.is_on_captcha_page():
            logger.info("✅ Não está na página de CAPTCHA")
            return True

        logger.info("🔐 Página de CAPTCHA detectada")

        # Step 3: Try clicking Consultar first (maybe checkbox already checked)
        logger.info("   Tentando clicar em 'Consultar' diretamente...")
        if self.click_consultar_button():
            time.sleep(3)
            if self.is_on_documents_page():
                logger.info("✅ Sucesso! Página de documentos carregada")
                self.captcha_solved = True
                return True
            logger.info("   Ainda na mesma página, tentando resolver CAPTCHA...")

        # Step 4: Click reCAPTCHA checkbox
        logger.info("🤖 Clicando no checkbox do reCAPTCHA...")
        if self.click_recaptcha_checkbox():
            time.sleep(2)  # Brief wait

            # Step 5: IMMEDIATELY try to click Consultar
            logger.info("   Tentando clicar em 'Consultar' após checkbox...")
            if self.click_consultar_button():
                time.sleep(3)

                # Step 6: Check if we're on documents page
                if self.is_on_documents_page():
                    logger.info("✅ Sucesso! CAPTCHA resolvido e página carregada")
                    self.captcha_solved = True
                    return True

                # Step 7: Still on same page? Check if there's an image challenge
                if self.is_on_captcha_page():
                    if self.is_image_challenge_visible():
                        logger.info("   🖼️ Desafio de imagens requer intervenção manual")
                        return self.wait_for_manual_resolution()
                    else:
                        # No image challenge visible, try clicking again
                        logger.info("   Tentando clicar em 'Consultar' novamente...")
                        time.sleep(2)
                        if self.click_consultar_button():
                            time.sleep(3)
                            if self.is_on_documents_page():
                                self.captcha_solved = True
                                return True
                else:
                    # Not on captcha page anymore
                    logger.info("✅ Saiu da página de CAPTCHA")
                    self.captcha_solved = True
                    return True

        # Step 8: If nothing worked, check one more time
        time.sleep(2)
        if self.is_on_documents_page():
            self.captcha_solved = True
            return True

        # Step 9: Last resort - ask for manual intervention
        logger.info("⚠️ Todas as tentativas automáticas falharam")
        return self.wait_for_manual_resolution()

class ProcessoDocumentExtractor:
    """Extracts and downloads documents from processo.rio."""

    def __init__(self, headless: bool = False):
        self.headless = headless
        self.driver = None
        self.captcha_handler = None
        self.results: List[ExtractedProcesso] = []
        self.session_valid = False

        DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
        EXTRACTIONS_DIR.mkdir(parents=True, exist_ok=True)

    def setup_driver(self):
        """Initialize Chrome WebDriver."""
        chrome_options = Options()

        if self.headless:
            logger.warning("⚠️ Modo headless pode falhar com CAPTCHA")

        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--window-size=1920,1080")

        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)

        prefs = {
            "download.default_directory": str(DOWNLOADS_DIR.absolute()),
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "plugins.always_open_pdf_externally": True,
        }
        chrome_options.add_experimental_option("prefs", prefs)

        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=chrome_options)

        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        self.driver.implicitly_wait(10)
        self.captcha_handler = CaptchaHandler(self.driver)

        logger.info("✅ Chrome WebDriver inicializado")

    def close_driver(self):
        """Close the WebDriver."""
        if self.driver:
            self.driver.quit()
            logger.info("WebDriver fechado")

    def load_input_data(self) -> pd.DataFrame:
        """Load the analysis summary."""
        if INPUT_CSV.exists():
            df = pd.read_csv(INPUT_CSV)
            logger.info(f"📂 Carregados {len(df)} registros de {INPUT_CSV}")
        elif INPUT_XLSX.exists():
            df = pd.read_excel(INPUT_XLSX)
            logger.info(f"📂 Carregados {len(df)} registros de {INPUT_XLSX}")
        else:
            raise FileNotFoundError(f"Arquivo não encontrado: {INPUT_CSV} ou {INPUT_XLSX}")

        required_cols = ['Processo', 'Link Documento', 'Empresa', 'ID']
        missing = [col for col in required_cols if col not in df.columns]
        if missing:
            raise ValueError(f"Colunas ausentes: {missing}")

        return df

    def sanitize_filename(self, name: str) -> str:
        """Create a safe filename."""
        safe_name = re.sub(r'[<>:"/\\|?*]', '_', name)
        safe_name = re.sub(r'\s+', '_', safe_name)
        return safe_name[:100]

    def find_contract_links(self) -> List[Dict[str, Any]]:
        """Find ALL contract document links on the page."""
        logger.info("   📄 Procurando TODOS os documentos 'Íntegra do contrato'...")

        # Keywords to identify contract documents
        contract_keywords = [
            "Íntegra do contrato/demais instrumentos jurídicos celebrados",
            "Íntegra do contrato",
            "Integra do contrato",
            "instrumentos jurídicos celebrados",
        ]

        found_contracts = []
        found_hrefs = set()  # To avoid duplicates

        try:
            time.sleep(2)

            # Strategy 1: Find all PDF icons and check for contract text nearby
            logger.info("   🔍 Buscando todos os ícones PDF com texto do contrato...")
            
            pdf_links = self.driver.find_elements(By.XPATH,
                "//a[.//img[contains(@src, 'acrobat') or contains(@src, 'pdf')]]"
            )
            
            logger.info(f"   📋 Total de ícones PDF na página: {len(pdf_links)}")
            
            for i, pdf_link in enumerate(pdf_links):
                try:
                    href = pdf_link.get_attribute('href') or ''
                    
                    # Skip if already found (avoid duplicates)
                    if href in found_hrefs:
                        continue
                    
                    # Get parent and nearby text
                    parent = pdf_link.find_element(By.XPATH, "./..")
                    parent_text = parent.text.strip()
                    
                    # Try grandparent for more context
                    try:
                        grandparent = parent.find_element(By.XPATH, "./..")
                        grandparent_text = grandparent.text.strip()
                    except:
                        grandparent_text = ""
                    
                    # Also check previous sibling
                    try:
                        prev_sibling = pdf_link.find_element(By.XPATH, "./preceding-sibling::*[1]")
                        sibling_text = prev_sibling.text.strip()
                    except:
                        sibling_text = ""
                    
                    combined_text = f"{parent_text} {sibling_text} {grandparent_text}".lower()
                    
                    # Check if contract keywords are nearby
                    for keyword in contract_keywords:
                        if keyword.lower() in combined_text:
                            # Extract document ID
                            doc_id = self.extract_doc_id_near_element(parent)
                            if not doc_id or doc_id.startswith("doc_"):
                                doc_id = self.extract_doc_id_from_url(href)
                            
                            contract_info = {
                                'element': pdf_link,
                                'text': keyword,
                                'href': href,
                                'doc_id': doc_id,
                                'full_text': parent_text[:100]
                            }
                            
                            found_contracts.append(contract_info)
                            found_hrefs.add(href)
                            
                            logger.info(f"   ✅ [{len(found_contracts)}] Encontrado: {doc_id}")
                            logger.info(f"      Texto: {parent_text[:60]}...")
                            break  # Found match for this link, move to next
                            
                except StaleElementReferenceException:
                    continue
                except Exception as e:
                    logger.debug(f"   Erro no ícone [{i}]: {e}")
                    continue

            # Strategy 2: Find by text elements if Strategy 1 missed any
            logger.info("   🔍 Verificando por elementos de texto...")
            
            for keyword in contract_keywords:
                try:
                    xpath_text = f"//*[contains(text(), '{keyword}')]"
                    text_elements = self.driver.find_elements(By.XPATH, xpath_text)
                    
                    for text_elem in text_elements:
                        try:
                            # Get parent element
                            parent = text_elem.find_element(By.XPATH, "./..")
                            
                            # Look for PDF icon nearby
                            pdf_icons = parent.find_elements(By.XPATH, 
                                ".//a[.//img[contains(@src, 'acrobat') or contains(@src, 'pdf')]]"
                            )
                            
                            if not pdf_icons:
                                # Try grandparent
                                grandparent = parent.find_element(By.XPATH, "./..")
                                pdf_icons = grandparent.find_elements(By.XPATH,
                                    ".//a[.//img[contains(@src, 'acrobat') or contains(@src, 'pdf')]]"
                                )
                            
                            for pdf_link in pdf_icons:
                                href = pdf_link.get_attribute('href') or ''
                                
                                if href and href not in found_hrefs:
                                    doc_id = self.extract_doc_id_near_element(parent)
                                    
                                    contract_info = {
                                        'element': pdf_link,
                                        'text': keyword,
                                        'href': href,
                                        'doc_id': doc_id,
                                        'full_text': text_elem.text[:100]
                                    }
                                    
                                    found_contracts.append(contract_info)
                                    found_hrefs.add(href)
                                    
                                    logger.info(f"   ✅ [{len(found_contracts)}] Encontrado (via texto): {doc_id}")
                                    
                        except Exception as e:
                            logger.debug(f"   Erro ao processar elemento de texto: {e}")
                            continue
                            
                except Exception as e:
                    logger.debug(f"   Erro com keyword '{keyword}': {e}")
                    continue

            # Summary
            if found_contracts:
                logger.info(f"   📊 Total de contratos encontrados: {len(found_contracts)}")
            else:
                logger.warning("   ⚠️ Nenhum documento de contrato encontrado")
                
                # Debug: List all PDF links
                logger.info("   📋 Debug - Todos os links PDF:")
                for i, link in enumerate(pdf_links[:10]):
                    try:
                        href = (link.get_attribute('href') or '')[:60]
                        parent = link.find_element(By.XPATH, "./..").text[:40]
                        logger.info(f"      [{i}] {parent}... → {href}")
                    except:
                        pass

            return found_contracts

        except Exception as e:
            logger.error(f"   ❌ Erro ao procurar links: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return []

    def extract_doc_id_near_element(self, element) -> str:
        """Extract document ID from nearby span."""
        try:
            # Look for span with document ID pattern (XXX-CAP-YYYY/NNNNN)
            spans = element.find_elements(By.TAG_NAME, "span")
            for span in spans:
                text = span.text.strip()
                match = re.search(r'([A-Z]{2,4}-[A-Z]{2,4}-\d{4}/\d+)', text)
                if match:
                    return match.group(1)
            
            # Also check parent
            parent = element.find_element(By.XPATH, "./..")
            parent_text = parent.text
            match = re.search(r'([A-Z]{2,4}-[A-Z]{2,4}-\d{4}/\d+)', parent_text)
            if match:
                return match.group(1)
                
        except Exception:
            pass
        
        return f"doc_{int(time.time())}"


    def extract_doc_id_from_url(self, url: str) -> str:
        """Extract document ID from URL."""
        match = re.search(r'([A-Z]{2,4}-[A-Z]{2,4}-\d{4}/\d+)', url)
        if match:
            return match.group(1)
        
        # Try to get from query params
        match = re.search(r'id=(\d+)', url)
        if match:
            return f"doc_{match.group(1)}"
        
        return f"doc_{int(time.time())}"

    def download_contract(self, link_info: Dict[str, Any], processo_id: str) -> Optional[Path]:
        """Download the contract document."""
        logger.info(f"   ⬇️ Baixando documento: {link_info['doc_id']}")

        try:
            link_element = link_info['element']
            href = link_info['href']

            # Store current window
            main_window = self.driver.current_window_handle
            initial_handles = set(self.driver.window_handles)

            # Scroll to link and click
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", link_element)
            time.sleep(0.5)

            try:
                link_element.click()
            except (ElementClickInterceptedException, ElementNotInteractableException):
                self.driver.execute_script("arguments[0].click();", link_element)

            logger.info("   🖱️ Link clicado, aguardando...")
            time.sleep(3)

            # Check for new window/tab
            new_handles = set(self.driver.window_handles) - initial_handles

            if new_handles:
                new_window = list(new_handles)[0]
                self.driver.switch_to.window(new_window)

                new_url = self.driver.current_url
                logger.info(f"   📄 Nova janela: {new_url[:60]}...")

                # Try to download from new window
                downloaded = self.download_from_current_page(link_info['doc_id'], processo_id)

                # Close and switch back
                self.driver.close()
                self.driver.switch_to.window(main_window)

                return downloaded
            else:
                # Check if download started
                return self.wait_for_download_complete(link_info['doc_id'], processo_id)

        except Exception as e:
            logger.error(f"   ❌ Erro no download: {e}")
            try:
                self.driver.switch_to.window(self.driver.window_handles[0])
            except:
                pass
            return None

    def download_from_current_page(self, doc_id: str, processo_id: str) -> Optional[Path]:
        """Download document from the current page."""
        current_url = self.driver.current_url

        # If it's a direct PDF link
        if '.pdf' in current_url.lower():
            return self.download_via_requests(current_url, doc_id, processo_id)

        # Look for download button or PDF iframe
        download_selectors = [
            "//a[contains(@href, '.pdf')]",
            "//a[contains(@href, 'download')]",
            "//button[contains(., 'Download')]",
            "//button[contains(., 'Baixar')]",
            "//iframe[contains(@src, '.pdf')]",
        ]

        for selector in download_selectors:
            try:
                elements = self.driver.find_elements(By.XPATH, selector)
                if elements:
                    elem = elements[0]

                    if elem.tag_name == 'iframe':
                        src = elem.get_attribute('src')
                        if src:
                            return self.download_via_requests(src, doc_id, processo_id)
                    else:
                        href = elem.get_attribute('href')
                        if href and '.pdf' in href.lower():
                            return self.download_via_requests(href, doc_id, processo_id)

            except Exception:
                continue

        # Try to find PDF in page source
        try:
            page_source = self.driver.page_source
            pdf_urls = re.findall(r'https?://[^\s<>"\']+\.pdf[^\s<>"\']*', page_source)
            if pdf_urls:
                return self.download_via_requests(pdf_urls[0], doc_id, processo_id)
        except Exception:
            pass

        return None

    def download_via_requests(self, url: str, doc_id: str, processo_id: str) -> Optional[Path]:
        """Download file using requests with browser cookies."""
        logger.info(f"   ⬇️ Baixando via requests: {url[:60]}...")

        try:
            # Get cookies from Selenium
            cookies = {c['name']: c['value'] for c in self.driver.get_cookies()}

            # Download
            response = requests.get(url, cookies=cookies, stream=True, timeout=60)
            response.raise_for_status()

            # Determine filename
            content_disp = response.headers.get('Content-Disposition', '')
            if 'filename=' in content_disp:
                filename = re.findall(r'filename[^;=\n]*=([\"\']?)(.+?)\1(;|$)', content_disp)
                if filename:
                    filename = filename[0][1]
                else:
                    filename = f"{self.sanitize_filename(processo_id)}_{doc_id}.pdf"
            else:
                filename = f"{self.sanitize_filename(processo_id)}_{self.sanitize_filename(doc_id)}.pdf"

            # Save file
            filepath = DOWNLOADS_DIR / filename
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            file_size = filepath.stat().st_size
            logger.info(f"   ✅ Salvo: {filename} ({file_size:,} bytes)")
            return filepath

        except Exception as e:
            logger.error(f"   ❌ Erro no download: {e}")
            return None

    def wait_for_download_complete(self, doc_id: str, processo_id: str, timeout: int = 30) -> Optional[Path]:
        """Wait for download to complete."""
        logger.info("   ⏳ Aguardando download...")

        start_time = time.time()

        while time.time() - start_time < timeout:
            # Check for new PDF files
            pdf_files = list(DOWNLOADS_DIR.glob("*.pdf"))
            crdownloads = list(DOWNLOADS_DIR.glob("*.crdownload"))

            # Get recently modified files
            recent_pdfs = [
                f for f in pdf_files
                if time.time() - f.stat().st_mtime < 60
            ]

            if recent_pdfs and not crdownloads:
                newest = max(recent_pdfs, key=lambda f: f.stat().st_mtime)
                logger.info(f"   ✅ Download concluído: {newest.name}")
                return newest

            time.sleep(1)

        logger.warning("   ⚠️ Timeout no download")
        return None

    def process_url(self, row: pd.Series, index: int, total: int) -> ExtractedProcesso:
        """Process a single processo URL."""
        processo_id = str(row['Processo'])
        url = str(row['Link Documento'])
        empresa = str(row['Empresa'])
        cnpj = str(row['ID'])

        logger.info(f"\n{'='*60}")
        logger.info(f"[{index}/{total}] 🔍 Processando: {processo_id}")
        logger.info(f"   Empresa: {empresa}")
        logger.info(f"   URL: {url[:60]}...")

        documents = []
        status = "pending"
        error_msg = ""

        try:
            # Navigate
            self.driver.get(url)
            time.sleep(DELAY_BETWEEN_REQUESTS)

            WebDriverWait(self.driver, TIMEOUT).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )

            # Handle CAPTCHA
            if not self.captcha_handler.handle():
                status = "captcha_failed"
                error_msg = "Falha ao resolver CAPTCHA"
                return ExtractedProcesso(
                    processo_id=processo_id,
                    empresa=empresa,
                    empresa_cnpj=cnpj,
                    url=url,
                    documents=[],
                    total_documents=0,
                    extraction_status=status,
                    error_message=error_msg
                )

            self.session_valid = True
            time.sleep(2)

            # Verify we're on documents page
            if not self.captcha_handler.is_on_documents_page():
                logger.warning("   ⚠️ Não está na página de documentos")
                page_text = self.driver.find_element(By.TAG_NAME, "body").text[:500]
                status = "wrong_page"
                error_msg = f"Página: {page_text[:200]}"
            else:
                # Find ALL contract links
                contract_links = self.find_contract_links()

                if contract_links:
                    logger.info(f"   📥 Baixando {len(contract_links)} documento(s)...")
                    
                    downloaded_count = 0
                    
                    for i, link_info in enumerate(contract_links, 1):
                        logger.info(f"\n   📄 [{i}/{len(contract_links)}] Baixando: {link_info['doc_id']}")
                        
                        downloaded_path = self.download_contract(link_info, processo_id)

                        doc_entry = {
                            'doc_id': link_info['doc_id'],
                            'description': link_info.get('full_text', link_info['text']),
                            'href': link_info['href'],
                            'file_path': str(downloaded_path) if downloaded_path else None,
                            'downloaded': downloaded_path is not None
                        }
                        
                        documents.append(doc_entry)
                        
                        if downloaded_path:
                            downloaded_count += 1
                        
                        # Small delay between downloads
                        time.sleep(1)

                    # Set status based on results
                    if downloaded_count == len(contract_links):
                        status = "all_downloaded"
                    elif downloaded_count > 0:
                        status = "partial_download"
                    else:
                        status = "download_failed"
                        
                    logger.info(f"   📊 Resultado: {downloaded_count}/{len(contract_links)} baixados")
                    
                else:
                    status = "no_contract_link"
                    
                    # Get page content for debugging
                    page_text = self.driver.find_element(By.TAG_NAME, "body").text
                    documents.append({
                        'doc_id': 'page_content',
                        'description': 'Conteúdo da página (sem links de contrato)',
                        'content': page_text[:5000],
                        'downloaded': False
                    })

        except TimeoutException:
            status = "timeout"
            error_msg = "Timeout ao carregar página"
            logger.warning(f"   ⏱️ Timeout")

        except Exception as e:
            status = "error"
            error_msg = str(e)
            logger.error(f"   ❌ Erro: {e}")

        result = ExtractedProcesso(
            processo_id=processo_id,
            empresa=empresa,
            empresa_cnpj=cnpj,
            url=url,
            documents=documents,
            total_documents=len(documents),
            extraction_status=status,
            error_message=error_msg
        )

        logger.info(f"   📊 Status final: {status} ({len(documents)} documento(s))")
        return result

    def run(self, max_rows: Optional[int] = None, start_from: int = 0):
        """Run the extraction pipeline."""
        print("\n" + "=" * 70)
        print("📄 EXTRATOR DE DOCUMENTOS DE PROCESSOS")
        print("=" * 70)

        df = self.load_input_data()

        if start_from > 0:
            df = df.iloc[start_from:]
            logger.info(f"⏭️ Iniciando do registro {start_from}")

        if max_rows:
            df = df.head(max_rows)
            logger.info(f"🔢 Limitado a {max_rows} registros")

        total = len(df)
        print(f"\n📊 Total a processar: {total} processos")
        print("=" * 70)

        self.setup_driver()

        try:
            for idx, (_, row) in enumerate(df.iterrows(), 1):
                result = self.process_url(row, idx, total)
                self.results.append(result)

                if idx % 5 == 0:
                    self.save_results(partial=True)

                time.sleep(1)

            self.save_results()

        except KeyboardInterrupt:
            logger.info("\n⚠️ Interrompido pelo usuário")
            self.save_results(partial=True)

        finally:
            self.close_driver()

        self.print_summary()

    def save_results(self, partial: bool = False):
        """Save extraction results to JSON and CSV."""
        if not self.results:
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        suffix = "_partial" if partial else "_final"

        # Save detailed JSON
        json_file = EXTRACTIONS_DIR / f"processos{suffix}_{timestamp}.json"
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump([asdict(r) for r in self.results], f, indent=2, ensure_ascii=False)

        # Save summary CSV
        csv_data = []
        for r in self.results:
            downloaded_files = [
                d.get('file_path', '') for d in r.documents 
                if d.get('downloaded', False)
            ]
            csv_data.append({
                'Processo': r.processo_id,
                'Empresa': r.empresa,
                'CNPJ': r.empresa_cnpj,
                'URL': r.url,
                'Status': r.extraction_status,
                'Documentos': r.total_documents,
                'Arquivos Baixados': len(downloaded_files),
                'Caminhos': '; '.join(downloaded_files),
                'Erro': r.error_message,
                'Data': r.extracted_at
            })

        csv_file = EXTRACTIONS_DIR / f"processos_resumo{suffix}_{timestamp}.csv"
        pd.DataFrame(csv_data).to_csv(csv_file, index=False, encoding='utf-8-sig')

        if not partial:
            logger.info(f"💾 Resultados salvos:")
            logger.info(f"   JSON: {json_file}")
            logger.info(f"   CSV:  {csv_file}")

    def print_summary(self):
        """Print extraction summary."""
        print("\n" + "=" * 70)
        print("📊 RESUMO DA EXTRAÇÃO")
        print("=" * 70)

        total = len(self.results)

        # Count by status
        by_status = {}
        total_downloaded = 0
        total_docs = 0

        for r in self.results:
            by_status[r.extraction_status] = by_status.get(r.extraction_status, 0) + 1
            total_docs += r.total_documents
            for doc in r.documents:
                if doc.get('downloaded', False):
                    total_downloaded += 1

        print(f"\n📁 Processos analisados: {total}")
        print(f"📄 Documentos encontrados: {total_docs}")
        print(f"⬇️  Arquivos baixados: {total_downloaded}")

        print(f"\n📈 Por status:")
        status_info = {
            'all_downloaded': ('✅', 'Todos baixados'),
            'partial_download': ('⚠️', 'Download parcial'),
            'download_failed': ('❌', 'Falha no download'),
            'no_contract_link': ('📄', 'Sem link de contrato'),
            'wrong_page': ('🔄', 'Página incorreta'),
            'captcha_failed': ('🔐', 'CAPTCHA falhou'),
            'timeout': ('⏱️', 'Timeout'),
            'error': ('❌', 'Erro'),
        }

        for status, count in sorted(by_status.items(), key=lambda x: -x[1]):
            icon, label = status_info.get(status, ('•', status))
            pct = (count / total * 100) if total > 0 else 0
            print(f"   {icon} {label}: {count} ({pct:.1f}%)")

        # List downloaded files
        print(f"\n📥 Arquivos baixados:")
        file_count = 0
        for r in self.results:
            for doc in r.documents:
                if doc.get('downloaded', False) and doc.get('file_path'):
                    file_count += 1
                    if file_count <= 15:  # Show first 15
                        filename = Path(doc['file_path']).name
                        print(f"   • {r.processo_id}: {filename}")
        
        if file_count > 15:
            print(f"   ... e mais {file_count - 15} arquivo(s)")
        elif file_count == 0:
            print("   (nenhum arquivo baixado)")

        print(f"\n📂 Arquivos salvos em:")
        print(f"   Downloads: {DOWNLOADS_DIR.absolute()}")
        print(f"   Resultados: {EXTRACTIONS_DIR.absolute()}")
        print("=" * 70)

def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Extrai e baixa documentos de contratos do processo.rio",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  python extract_processo_documents.py                  # Processa todos
  python extract_processo_documents.py --max 5          # Apenas 5 primeiros
  python extract_processo_documents.py --start 10       # Começa do 10º
  python extract_processo_documents.py --start 5 --max 10  # Do 5º ao 15º
        """
    )
    parser.add_argument(
        "--max", "-m",
        type=int,
        default=None,
        help="Número máximo de processos para processar"
    )
    parser.add_argument(
        "--start", "-s",
        type=int,
        default=0,
        help="Índice inicial (para continuar de onde parou)"
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Executar sem janela (não recomendado - CAPTCHA requer navegador visível)"
    )

    args = parser.parse_args()

    if args.headless:
        print("⚠️ Aviso: Modo headless pode falhar com CAPTCHA!")

    extractor = ProcessoDocumentExtractor(headless=args.headless)
    extractor.run(max_rows=args.max, start_from=args.start)


if __name__ == "__main__":
    main()