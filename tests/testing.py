from selenium import webdriver
from selenium.webdriver.chrome.options import Options

options = Options()
options.add_argument("--headless")  # try old headless
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")

driver = webdriver.Chrome(options=options)
driver.get("https://www.google.com")
print("Google loaded")

driver.get("https://contasrio.rio.rj.gov.br/ContasRio/")
print("ContasRio base loaded")

driver.quit()