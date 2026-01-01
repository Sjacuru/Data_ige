"""
document_extractor.py - Extract text from PDF documents in processo pages.
Handles CAPTCHA, downloads PDFs temporarily, extracts text, then deletes PDFs.
"""

import os
import time
import re
from datetime import datetime
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, 
    NoSuchElementException,
    ElementClickInterceptedException
)

# Import from existing modules
from config import (
    TIMEOUT_SECONDS, 
    PROCESSO_BASE_URL,
    TARGET_DOCUMENTS,
    TEMP_DOWNLOAD_PATH
)


class DocumentExtractor:
    """
    Extracts text from specific PDF documents on processo pages.
    """
    
    def __init__(self, driver, download_dir=None):
        """
        Initialize extractor with existing driver.
        
        Args:
            driver: Selenium WebDriver instance (already initialized)
            download_dir: Directory for temporary PDF downloads
        """
        self.driver = driver
        self.download_dir = download_dir or TEMP_DOWNLOAD_PATH
        os.makedirs(self.download_dir, exist_ok=True)
        
    # ═══════════════════════════════════════════════════════════════════════
    # CAPTCHA HANDLING
    # ═══════════════════════════════════════════════════════════════════════
    
    def detect_captcha(self):
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
            "//div[@class='recaptcha-checkbox-border']"
        ]
        
        for xpath in captcha_indicators:
            try:
                element = self.driver.find_element(By.XPATH, xpath)
                if element.is_displayed():
                    return True
            except NoSuchElementException:
                continue
        
        return False
    
    def handle_captcha(self, auto_attempt=True):
        """
        Handle CAPTCHA challenge.
        
        Args:
            auto_attempt: Try to click checkbox automatically first
            
        Returns:
            bool: True if CAPTCHA was resolved
        """
        if not self.detect_captcha():
            return True  # No CAPTCHA present
        
        print("\n⚠️  CAPTCHA DETECTADO!")
        
        if auto_attempt:
            print("   → Tentando resolver automaticamente...")
            try:
                # Try to find and click the reCAPTCHA checkbox
                iframe = WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((
                        By.XPATH, 
                        "//iframe[contains(@src, 'recaptcha')]"
                    ))
                )
                
                # Switch to reCAPTCHA iframe
                self.driver.switch_to.frame(iframe)
                
                # Click the checkbox
                checkbox = WebDriverWait(self.driver, 5).until(
                    EC.element_to_be_clickable((
                        By.CSS_SELECTOR, 
                        ".recaptcha-checkbox-border"
                    ))
                )
                checkbox.click()
                
                # Switch back to main content
                self.driver.switch_to.default_content()
                
                # Wait to see if challenge appears
                time.sleep(3)
                
                # Check if solved (checkbox turns green)
                if not self.detect_captcha():
                    print("   ✓ CAPTCHA resolvido automaticamente!")
                    return True
                    
            except Exception as e:
                print(f"   ⚠ Auto-resolve falhou: {e}")
                self.driver.switch_to.default_content()
        
        # Manual intervention required
        print("\n" + "="*50)
        print("   🔐 INTERVENÇÃO MANUAL NECESSÁRIA")
        print("   Por favor, resolva o CAPTCHA no navegador.")
        print("="*50)
        
        # Play alert sound (Windows)
        try:
            import winsound
            winsound.Beep(1000, 500)
            winsound.Beep(1500, 500)
        except:
            pass
        
        input("\n   Pressione ENTER quando terminar...")
        
        # Verify resolution
        time.sleep(1)
        if self.detect_captcha():
            print("   ⚠ CAPTCHA ainda presente. Tentando continuar...")
            return False
        
        print("   ✓ CAPTCHA resolvido!")
        return True
    
    # ═══════════════════════════════════════════════════════════════════════
    # PAGE NAVIGATION
    # ═══════════════════════════════════════════════════════════════════════
    
    def access_processo_page(self, processo_url):
        """
        Access a processo page and handle initial security check.
        
        Args:
            processo_url: Full URL to the processo page
            
        Returns:
            bool: True if successfully accessed
        """
        print(f"\n📄 Acessando: {processo_url[:70]}...")
        
        self.driver.get(processo_url)
        time.sleep(2)
        
        # Check for security verification page
        try:
            # Look for "Consultar" button (security check page)
            consultar_btn = WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located((
                    By.XPATH,
                    "//button[contains(text(), 'Consultar')] | "
                    "//a[contains(text(), 'Consultar')] | "
                    "//*[contains(@class, 'btn') and contains(text(), 'Consultar')]"
                ))
            )
            
            print("   → Página de verificação detectada")
            
            # Handle CAPTCHA if present
            if self.detect_captcha():
                if not self.handle_captcha():
                    return False
            
            # Click Consultar button
            print("   → Clicando em 'Consultar'...")
            self.driver.execute_script("arguments[0].click();", consultar_btn)
            time.sleep(3)
            
            # May need to handle CAPTCHA again after clicking
            if self.detect_captcha():
                if not self.handle_captcha():
                    return False
                    
        except TimeoutException:
            # No security page, might be directly on document list
            print("   → Acesso direto (sem verificação)")
        
        # Wait for document list to load
        try:
            WebDriverWait(self.driver, TIMEOUT_SECONDS).until(
                EC.presence_of_element_located((
                    By.XPATH,
                    "//li[contains(text(), 'Documento')] | "
                    "//div[contains(@class, 'documento')]"
                ))
            )
            print("   ✓ Lista de documentos carregada")
            return True
            
        except TimeoutException:
            print("   ✗ Timeout aguardando lista de documentos")
            return False
    
    def find_target_documents(self):
        """
        Find all target documents on the current page.
        
        Returns:
            List of dicts with document info
        """
        found_docs = []
        
        for target in TARGET_DOCUMENTS:
            pattern = target["pattern"]
            print(f"\n   🔍 Buscando: '{pattern[:50]}...'")
            
            try:
                # Find <li> elements containing the target text
                li_elements = self.driver.find_elements(
                    By.XPATH,
                    f"//li[contains(., '{pattern}')]"
                )
                
                for li in li_elements:
                    try:
                        # Get the full text
                        li_text = li.text.strip()
                        
                        # Extract processo ID from span
                        try:
                            span = li.find_element(By.TAG_NAME, "span")
                            processo_id = span.text.replace("|", "").strip()
                        except:
                            processo_id = "N/A"
                        
                        # Get download link
                        try:
                            link = li.find_element(By.TAG_NAME, "a")
                            href = link.get_attribute("href")
                        except:
                            href = None
                            continue  # Skip if no link
                        
                        if href:
                            doc_info = {
                                "tipo": target["tipo"],
                                "pattern": pattern,
                                "processo_id": processo_id,
                                "href": href,
                                "priority": target["priority"]
                            }
                            found_docs.append(doc_info)
                            print(f"      ✓ Encontrado: {processo_id}")
                            
                    except Exception as e:
                        print(f"      ⚠ Erro processando elemento: {e}")
                        continue
                        
            except NoSuchElementException:
                print(f"      ✗ Não encontrado")
                continue
        
        # Sort by priority
        found_docs.sort(key=lambda x: x["priority"])
        
        print(f"\n   📋 Total de documentos encontrados: {len(found_docs)}")
        return found_docs
    
    # ═══════════════════════════════════════════════════════════════════════
    # PDF DOWNLOAD
    # ═══════════════════════════════════════════════════════════════════════
    
    def clear_download_folder(self):
        """Remove all PDF files from download folder."""
        for f in os.listdir(self.download_dir):
            if f.endswith('.pdf') or f.endswith('.crdownload'):
                try:
                    os.remove(os.path.join(self.download_dir, f))
                except:
                    pass
    
    def wait_for_download(self, timeout=180):
        """
        Wait for PDF download to complete.
        
        Args:
            timeout: Maximum wait time in seconds (default 3 min for large files)
            
        Returns:
            Path to downloaded file or None
        """
        print(f"   ⏳ Aguardando download (máx {timeout}s)...")
        
        start_time = time.time()
        last_size = 0
        stable_count = 0
        
        while time.time() - start_time < timeout:
            # Check for completed PDFs
            pdf_files = [f for f in os.listdir(self.download_dir) 
                        if f.endswith('.pdf')]
            
            # Check for in-progress downloads
            crdownload_files = [f for f in os.listdir(self.download_dir)
                               if f.endswith('.crdownload')]
            
            if pdf_files and not crdownload_files:
                # Download complete
                pdf_path = os.path.join(self.download_dir, pdf_files[0])
                file_size = os.path.getsize(pdf_path)
                
                # Verify file is stable (not still writing)
                if file_size == last_size and file_size > 0:
                    stable_count += 1
                    if stable_count >= 2:
                        print(f"   ✓ Download completo: {file_size:,} bytes")
                        return pdf_path
                else:
                    stable_count = 0
                    last_size = file_size
            
            time.sleep(2)
        
        print("   ✗ Timeout no download")
        return None
    
    def download_pdf(self, url):
        """
        Download PDF from URL.
        
        Args:
            url: Download URL (JWT-based)
            
        Returns:
            Path to downloaded file or None
        """
        print(f"\n   📥 Baixando PDF...")
        print(f"      URL: {url[:60]}...")
        
        # Clear previous downloads
        self.clear_download_folder()
        
        # Navigate to download URL
        # Open in new tab to avoid losing current page
        original_window = self.driver.current_window_handle
        
        # Create new tab
        self.driver.execute_script("window.open('');")
        self.driver.switch_to.window(self.driver.window_handles[-1])
        
        try:
            self.driver.get(url)
            
            # Handle potential CAPTCHA on download page
            time.sleep(2)
            if self.detect_captcha():
                if not self.handle_captcha():
                    return None
            
            # Wait for download
            pdf_path = self.wait_for_download()
            
            return pdf_path
            
        finally:
            # Close download tab and return to original
            self.driver.close()
            self.driver.switch_to.window(original_window)
    
    # ═══════════════════════════════════════════════════════════════════════
    # TEXT EXTRACTION
    # ═══════════════════════════════════════════════════════════════════════
    
    def extract_text_from_pdf(self, pdf_path):
        """
        Extract text from PDF file.
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            Dict with extracted text and metadata
        """
        print(f"\n   📝 Extraindo texto...")
        
        try:
            # Try pdfplumber first (better for complex layouts)
            try:
                import pdfplumber
                
                text_content = []
                with pdfplumber.open(pdf_path) as pdf:
                    page_count = len(pdf.pages)
                    for i, page in enumerate(pdf.pages):
                        text = page.extract_text()
                        if text:
                            text_content.append(text)
                        if (i + 1) % 10 == 0:
                            print(f"      Processando página {i+1}/{page_count}...")
                
                full_text = "\n\n".join(text_content)
                
            except ImportError:
                # Fallback to PyPDF2
                from PyPDF2 import PdfReader
                
                reader = PdfReader(pdf_path)
                page_count = len(reader.pages)
                text_content = []
                
                for i, page in enumerate(reader.pages):
                    text = page.extract_text()
                    if text:
                        text_content.append(text)
                    if (i + 1) % 10 == 0:
                        print(f"      Processando página {i+1}/{page_count}...")
                
                full_text = "\n\n".join(text_content)
            
            file_size = os.path.getsize(pdf_path)
            
            print(f"   ✓ Extraído: {len(full_text):,} caracteres de {page_count} páginas")
            
            return {
                "texto": full_text,
                "paginas": page_count,
                "tamanho_bytes": file_size,
                "caracteres": len(full_text)
            }
            
        except Exception as e:
            print(f"   ✗ Erro na extração: {e}")
            return {
                "texto": "",
                "paginas": 0,
                "tamanho_bytes": 0,
                "caracteres": 0,
                "erro": str(e)
            }
    
    # ═══════════════════════════════════════════════════════════════════════
    # MAIN PROCESSING
    # ═══════════════════════════════════════════════════════════════════════
    
    def process_processo(self, processo_url, empresa_id=None, empresa_name=None):
        """
        Process a single processo page: access, find docs, download, extract.
        
        Args:
            processo_url: URL to the processo page
            empresa_id: Optional company ID for reference
            empresa_name: Optional company name for reference
            
        Returns:
            List of extracted document data
        """
        results = []
        
        # Access the processo page
        if not self.access_processo_page(processo_url):
            return results
        
        # Find target documents
        documents = self.find_target_documents()
        
        if not documents:
            print("   ⚠ Nenhum documento alvo encontrado")
            return results
        
        # Process each document
        for i, doc in enumerate(documents, 1):
            print(f"\n{'─'*50}")
            print(f"   DOCUMENTO {i}/{len(documents)}: {doc['tipo'].upper()}")
            print(f"   Processo: {doc['processo_id']}")
            print(f"{'─'*50}")
            
            try:
                # Download PDF
                pdf_path = self.download_pdf(doc['href'])
                
                if not pdf_path:
                    print("   ✗ Falha no download")
                    continue
                
                # Extract text
                extraction = self.extract_text_from_pdf(pdf_path)
                
                # Build result
                result = {
                    "processo_url": processo_url,
                    "empresa_id": empresa_id,
                    "empresa_name": empresa_name,
                    "documento_tipo": doc['tipo'],
                    "documento_pattern": doc['pattern'],
                    "processo_id": doc['processo_id'],
                    "texto_extraido": extraction['texto'],
                    "paginas": extraction['paginas'],
                    "tamanho_bytes": extraction['tamanho_bytes'],
                    "caracteres": extraction['caracteres'],
                    "data_extracao": datetime.now().isoformat(),
                    "erro": extraction.get('erro')
                }
                
                results.append(result)
                
                # Delete PDF after extraction
                try:
                    os.remove(pdf_path)
                    print(f"   🗑️ PDF removido (texto salvo)")
                except:
                    pass
                
            except Exception as e:
                print(f"   ✗ Erro processando documento: {e}")
                continue
        
        return results