import time, requests
from infrastructure.web.driver import create_driver, close_driver
from infrastructure.web.captcha_handler import CaptchaHandler
from selenium.webdriver.common.by import By

URL = "https://acesso.processo.rio/sigaex/public/app/transparencia/processo?n=FIL-PRO-2023/00482"

driver = create_driver(headless=False, anti_detection=True)
assert driver is not None
driver.get(URL)
input("Solve CAPTCHA then press ENTER...")
time.sleep(3)

captcha = CaptchaHandler(driver)
print("On documents page:", captcha.is_on_documents_page())

items = driver.find_elements(
    By.XPATH, "//li[.//img[contains(@src,'page_white_acrobat.png')]]"
)

CONTRACT_BODY_LABEL = "Íntegra do contrato/demais instrumentos jurídicos celebrados"

for i, li in enumerate(items, 1):
    text = li.text.strip()
    matched = CONTRACT_BODY_LABEL in text
    try:
        a = li.find_element(By.XPATH, ".//a[img[contains(@src,'page_white_acrobat.png')]]")
        href = a.get_attribute("href") or "no href"
    except:
        href = "no anchor"
    
    print(f"\n[{i}] MATCHED={matched}")
    print(f"     TEXT: {text[:100]}")
    print(f"     HREF: {href[:120]}")
    
    # If this is the one we want, follow the URL and check what it is
    if matched:
        print(f"     >> Following download URL...")
        cookies = {c["name"]: c["value"] for c in driver.get_cookies()}
        headers = {"User-Agent": driver.execute_script("return navigator.userAgent;")}
        resp = requests.head(href, cookies=cookies, headers=headers, 
                            timeout=30, allow_redirects=True)
        print(f"     >> Final URL: {resp.url[:120]}")
        print(f"     >> Content-Type: {resp.headers.get('Content-Type','?')}")
        print(f"     >> Content-Length: {resp.headers.get('Content-Length','?')}")

close_driver(driver)