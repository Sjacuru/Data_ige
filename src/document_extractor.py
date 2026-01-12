"""
document_extractor.py - Extract text from PDF documents in processo pages.
Handles CAPTCHA, downloads PDFs temporarily, extracts text, then deletes PDFs.

UNIQUE VALUE:
- CAPTCHA detection and handling (auto + manual)
- Security page navigation ("Consultar" button)
- Smart PDF download with progress monitoring
- Tab management for downloads
- Cleanup after extraction

DELEGATES TEXT EXTRACTION TO:
- src/parser.py (fast, simple OCR) - default
- Contract_analisys/contract_extractor.py (quality, AI + preprocessing)

INTEGRATION:
    from src.document_extractor import extract_processo_documents
    
    results = extract_processo_documents(
        driver=driver,
        processo_url="https://processo.rio/...",
        empresa_info={"id": "12345678000199", "name": "Empresa XYZ"}
    )
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

# Import from core modules
from core.captcha import CaptchaHandler

# Import from existing modules
from config import (
    TIMEOUT_SECONDS, 
    PROCESSO_BASE_URL,
    TARGET_DOCUMENTS,
    TEMP_DOWNLOAD_PATH
)


# ═══════════════════════════════════════════════════════════════════════
# TEXT EXTRACTION DELEGATION
# ═══════════════════════════════════════════════════════════════════════

def get_parser_extractor():
    """
    Get the simple OCR-based extractor from parser.py.
    Fast but less accurate.
    """
    try:
        from src.parser import extract_text_from_pdf
        return extract_text_from_pdf
    except ImportError as e:
        print(f"⚠️ parser.py not available: {e}")
        return None


def get_ai_extractor():
    """
    Get the AI-powered extractor from contract_extractor.py.
    Better quality with preprocessing, but slower.
    """
    try:
        from Contract_analisys.contract_extractor import extract_text_from_pdf
        return extract_text_from_pdf
    except ImportError as e:
        print(f"⚠️ contract_extractor.py not available: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════
# MAIN CLASS
# ═══════════════════════════════════════════════════════════════════════

class DocumentExtractor:
    """
    Extracts text from specific PDF documents on processo pages.
    
    Unique Features:
    - CAPTCHA detection and handling
    - Security page navigation
    - Smart PDF download management
    - Delegates text extraction to specialized modules
    """
    
    def __init__(self, driver, download_dir=None, use_ai_extractor=False):
        """
        Initialize extractor with existing driver.
        
        Args:
            driver: Selenium WebDriver instance (already initialized)
            download_dir: Directory for temporary PDF downloads
            use_ai_extractor: If True, use AI extractor (better quality)
                             If False, use simple OCR (faster)
        """
        self.driver = driver
        self.download_dir = download_dir or TEMP_DOWNLOAD_PATH
        self.use_ai_extractor = use_ai_extractor
        self.captcha_handler = CaptchaHandler(driver)
        os.makedirs(self.download_dir, exist_ok=True)
        
    # ═══════════════════════════════════════════════════════════════════════
    # CAPTCHA HANDLING is DELEGATED TO core/captcha.py for refactoring under the functions:
    # - detect_captcha(self)
    # - handle_captcha(self)
    # - _play_alert_sound(self)
    # ═══════════════════════════════════════════════════════════════════════
    
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
            if self.captcha_handler.detect_captcha():            # 🆕 NEW
                if not self.captcha_handler.handle():            # 🆕 NEW
                    return False

            # Click Consultar button
            print("   → Clicando em 'Consultar'...")
            self.driver.execute_script("arguments[0].click();", consultar_btn)
            time.sleep(3)
            
            # May need to handle CAPTCHA again after clicking
            if self.captcha_handler.detect_captcha():            # 🆕 NEW
                if not self.captcha_handler.handle():            # 🆕 NEW
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
            if self.captcha_handler.detect_captcha():            # 🆕 NEW
                if not self.captcha_handler.handle():            # 🆕 NEW
                    return None
            
            # Wait for download
            pdf_path = self.wait_for_download()
            
            return pdf_path
            
        finally:
            # Close download tab and return to original
            self.driver.close()
            self.driver.switch_to.window(original_window)
    
    # ═══════════════════════════════════════════════════════════════════════
    # TEXT EXTRACTION (DELEGATES TO SPECIALIZED MODULES)
    # ═══════════════════════════════════════════════════════════════════════
    
    def extract_text_from_pdf(self, pdf_path):
        """
        Extract text from PDF file using existing extractors.
        
        Delegates to:
        - Contract_analisys/contract_extractor.py (if use_ai_extractor=True)
        - src/parser.py (if use_ai_extractor=False) - default
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            Dict with extracted text and metadata
        """
        print(f"\n   📝 Extraindo texto...")
        
        try:
            if self.use_ai_extractor:
                # Use AI extractor (better quality, slower)
                return self._extract_with_ai(pdf_path)
            else:
                # Use simple OCR extractor (faster)
                return self._extract_with_parser(pdf_path)
                
        except Exception as e:
            print(f"   ✗ Erro na extração: {e}")
            return {
                "texto": "",
                "paginas": 0,
                "tamanho_bytes": 0,
                "caracteres": 0,
                "erro": str(e)
            }
    
    def _extract_with_parser(self, pdf_path):
        """
        Extract text using src/parser.py (simple OCR).
        Fast but less accurate.
        """
        print("      → Usando parser.py (OCR simples)")
        
        extractor = get_parser_extractor()
        if not extractor:
            raise ImportError("parser.py not available")
        
        text = extractor(pdf_path)
        file_size = os.path.getsize(pdf_path)
        
        if text:
            print(f"   ✓ Extraído: {len(text):,} caracteres")
            return {
                "texto": text,
                "paginas": 0,  # parser doesn't return page count
                "tamanho_bytes": file_size,
                "caracteres": len(text),
                "extraction_source": "parser_ocr"
            }
        else:
            return {
                "texto": "",
                "paginas": 0,
                "tamanho_bytes": file_size,
                "caracteres": 0,
                "erro": "Parser returned empty text"
            }
    
    def _extract_with_ai(self, pdf_path):
        """
        Extract text using Contract_analisys/contract_extractor.py.
        Better quality with preprocessing, but slower.
        """
        print("      → Usando contract_extractor.py (IA + pré-processamento)")
        
        extractor = get_ai_extractor()
        if not extractor:
            # Fallback to parser if AI extractor not available
            print("      ⚠ AI extractor não disponível, usando parser...")
            return self._extract_with_parser(pdf_path)
        
        result = extractor(pdf_path)
        file_size = os.path.getsize(pdf_path)
        
        if result.get("success"):
            text = result.get("full_text", "")
            print(f"   ✓ Extraído: {len(text):,} caracteres ({result.get('extraction_source', 'unknown')})")
            return {
                "texto": text,
                "paginas": result.get("total_pages", 0),
                "tamanho_bytes": file_size,
                "caracteres": result.get("total_chars", 0),
                "extraction_source": result.get("extraction_source", "ai_extractor"),
                "preprocessing": result.get("preprocessing", {})
            }
        else:
            return {
                "texto": "",
                "paginas": 0,
                "tamanho_bytes": file_size,
                "caracteres": 0,
                "erro": result.get("error", "AI extraction failed")
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
                
                # Extract text (delegates to specialized modules)
                extraction = self.extract_text_from_pdf(pdf_path)
                
                # Build result
                result = {
                    "processo_url": processo_url,
                    "empresa_id": empresa_id,
                    "empresa_name": empresa_name,
                    "documento_tipo": doc['tipo'],
                    "documento_pattern": doc['pattern'],
                    "processo_id": doc['processo_id'],
                    "texto_extraido": extraction.get('texto', ''),
                    "paginas": extraction.get('paginas', 0),
                    "tamanho_bytes": extraction.get('tamanho_bytes', 0),
                    "caracteres": extraction.get('caracteres', 0),
                    "extraction_source": extraction.get('extraction_source', 'unknown'),
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


# ═══════════════════════════════════════════════════════════════════════
# INTEGRATION FUNCTIONS (for main.py)
# ═══════════════════════════════════════════════════════════════════════

def extract_processo_documents(
    driver, 
    processo_url, 
    empresa_info=None, 
    use_ai=False,
    download_dir=None
):
    """
    High-level function to extract all documents from a processo page.
    Handles CAPTCHA, downloads, and text extraction.
    
    This is the main integration point for main.py.
    
    Args:
        driver: Selenium WebDriver instance
        processo_url: URL to the processo page
        empresa_info: Optional dict with 'id' and 'name' keys
        use_ai: If True, use AI extractor (better quality, slower)
               If False, use simple OCR parser (faster) - default
        download_dir: Optional custom download directory
    
    Returns:
        List of extracted document data
    
    Example:
        from src.document_extractor import extract_processo_documents
        
        results = extract_processo_documents(
            driver=driver,
            processo_url="https://processo.rio/...",
            empresa_info={"id": "12.345.678/0001-99", "name": "Empresa XYZ"},
            use_ai=False  # Use simple OCR for speed
        )
        
        for doc in results:
            print(f"Documento: {doc['documento_tipo']}")
            print(f"Texto: {doc['texto_extraido'][:200]}...")
    """
    extractor = DocumentExtractor(
        driver=driver,
        download_dir=download_dir,
        use_ai_extractor=use_ai
    )
    
    return extractor.process_processo(
        processo_url,
        empresa_id=empresa_info.get('id') if empresa_info else None,
        empresa_name=empresa_info.get('name') if empresa_info else None
    )


def create_extractor(driver, use_ai=False, download_dir=None):
    """
    Factory function to create a DocumentExtractor instance.
    
    Useful when you need to process multiple processos with the same settings.
    
    Args:
        driver: Selenium WebDriver instance
        use_ai: If True, use AI extractor
        download_dir: Optional custom download directory
    
    Returns:
        DocumentExtractor instance
    
    Example:
        from src.document_extractor import create_extractor
        
        extractor = create_extractor(driver, use_ai=False)
        
        for url in processo_urls:
            results = extractor.process_processo(url)
            # ... process results
    """
    return DocumentExtractor(
        driver=driver,
        download_dir=download_dir,
        use_ai_extractor=use_ai
    )


# ═══════════════════════════════════════════════════════════════════════
# STANDALONE TESTING
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("📄 Document Extractor - Standalone Test")
    print("=" * 60)
    print("\nThis module is designed to be imported by main.py")
    print("\nUsage:")
    print("  from src.document_extractor import extract_processo_documents")
    print("  ")
    print("  results = extract_processo_documents(")
    print("      driver=driver,")
    print("      processo_url='https://processo.rio/...',")
    print("      empresa_info={'id': '12345678000199', 'name': 'Empresa'},")
    print("      use_ai=False")
    print("  )")
    print("\nFeatures:")
    print("  ✓ CAPTCHA detection and handling")
    print("  ✓ Security page navigation")
    print("  ✓ Smart PDF download management")
    print("  ✓ Delegates text extraction to parser.py or contract_extractor.py")
    print("  ✓ Auto-cleanup of downloaded PDFs")