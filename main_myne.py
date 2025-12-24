#%% Livrarias 
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException
import time # Usado para pausas 
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import StaleElementReferenceException, ElementClickInterceptedException, NoSuchElementException
import re
import os

#%% Inicializa o Driver no Chrome

try:
    driver = webdriver.Chrome()
except Exception as e:
    print(f"Erro ao inicializar o driver (verifique se o Chrome está instalado): {e}")
    exit()

#%% Define os localizadores e constantes
TEMPO_MAXIMO = 20  # Tempo máximo de espera em segundos
wait = WebDriverWait(driver, TEMPO_MAXIMO)
MAX_RETRIES = 3
LOCALIZADOR_HOME_CARREGADA_1 = (By.XPATH, "//*[@id='menu-do-portal-container']/div[1]/ul/li[5]/a") # ID comum em frameworks
LOCALIZADOR_HOME_CARREGADA_2 = (By.XPATH, "//table//tbody//tr") # ID comum em frameworks

#%% Navega para um site e aguarda o carregamento da página inicial
driver.get("https://contasrio.rio.rj.gov.br/ContasRio/#!Home")
print("Aguardando carregamento da tela Home...")
wait.until(EC.presence_of_element_located(LOCALIZADOR_HOME_CARREGADA_1))
print("Home carregada. Prosseguindo...")


#%% Navega para um site específico e aguarda o carregamento do painel com refreshs se necessário
driver.get("https://contasrio.rio.rj.gov.br/ContasRio/#!Contratos/Contrato%20por%20Favorecido")

for attempt in range(1, MAX_RETRIES + 1):
    try:
        print(f"Tentativa {attempt}: Aguardando carregamento do painel...")

        # Wait for table rows to load (your stable condition)
        wait.until(EC.presence_of_element_located((LOCALIZADOR_HOME_CARREGADA_2)))

        print("Painel carregado com sucesso!")
        break  # exit the retry loop

    except TimeoutException:
        print(f"Timeout na tentativa {attempt}.")

        if attempt == MAX_RETRIES:
            print(f"O painel não carregou após {attempt} tentativas.")
            raise  # rethrow the exception for debugging

        print("Atualizando a página e tentando novamente...")
        driver.refresh()
        time.sleep(2)  # small wait to allow refresh complete


#%% Scroll para carregar todas as linhas da tabela dinâmica
print("Iniciando o scroll para carregar todas as linhas...")

scroller = driver.find_element(By.CSS_SELECTOR, ".v-grid-scroller")

all_rows = set()
last_scroll = -1
stopped = 0

while True:
    # Collect visible rows
    visible_rows = driver.find_elements(By.CSS_SELECTOR, ".v-grid-row")
    for row in visible_rows:
        all_rows.add(row.text)

    # Scroll
    driver.execute_script(
        "arguments[0].scrollTop += arguments[0].clientHeight;", scroller
    )

    time.sleep(0.8)  # Wait for loading

    # Check if we reached the bottom
    current_scroll = scroller.get_property("scrollTop")
    if current_scroll == last_scroll:
        stopped += 1
    else:
        stopped = 0
    if stopped >= 5:
        break
    last_scroll = current_scroll

print("Scroll finalizado!")
print(f"Total de linhas coletadas: {len(all_rows)}")

#%% Trantando e guardando os dados recuperados
 
print("Carregar todas as linhas...")

all_data = []

value_names = ["Total Contratado", "Empenhado", "Saldo a Executar", "Liquidado", "Pago"]

for row_text in all_rows:

    # Skip summary or totalizer rows
    if "total" in row_text.lower():
        continue

    # Regex to capture CNPJ, company name, and the 5 numeric values
    match = re.match(r"(.+?)\s*-\s*(.*?)\s((?:[\d\.,]+\s?){5})$", row_text)
    if match:
        identifier = match.group(1).strip()
        company_name = match.group(2)
        numbers = match.group(3).split()  # split into 5 numbers
        # Map numbers to their respective column names
        data_dict = {"ID": identifier, "Company": company_name}
        data_dict.update({name: num for name, num in zip(value_names, numbers)})
        all_data.append(data_dict)
    else:
        print("No match:", row_text)

# Print results
for item in all_data:
    print(item)


#%% PART 1 — FILTER COMPANY (original code — unchanged)

print("\n============================================================")
print("FILTRANDO E CLICANDO NA EMPRESA")
print("============================================================\n")

company = all_data[0]   # you can change for iteration later
empresa_id = company["ID"]

print(f"Empresa: {empresa_id} - {company['Company']}")

print("\n→ Encontrando o filtro...")
filter_box = wait.until(EC.presence_of_element_located((By.XPATH, "//input[@placeholder='Digite para filtrar']")))
print("✓ Filtro encontrado")

print(f"\n→ Filtrando por ID: {empresa_id}")
filter_box.clear()
filter_box.send_keys(empresa_id)
time.sleep(3)
filter_box.send_keys(Keys.ENTER)
time.sleep(3)

print("Searching for company caption attempt 1...")
time.sleep(3)

captions = driver.find_elements(By.XPATH, f"//span[contains(@class,'v-button-caption') and contains(text(), '{empresa_id}')]")


#%%
print("\n→ Clicando na empresa...")

# Find the actual clickable button (v-button-link)
company_button = driver.find_element(
    By.XPATH,
    f"//div[contains(@class,'v-button-link') and @role='button']"
    f"[.//span[contains(@class,'v-button-caption') and contains(text(), '{empresa_id}')]]"
)

# Extract the caption BEFORE clicking — used to exclude later
company_button_caption = company_button.find_element(
    By.XPATH, ".//span[contains(@class,'v-button-caption')]"
)

original_caption = company_button_caption.text.strip()

# Scroll and click
for attempt in range(3):
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", company_button)
        time.sleep(0.3)
        driver.execute_script("arguments[0].click();", company_button)
        print("✓ Empresa clicada.")
        break
    except Exception as e:
        print("   Tentativa de clique falhou:", e)
        time.sleep(0.5)


#%% AFTER CLICK — select next-level button (org/secretaria)
print("\n→ Aguardando botões do próximo nível carregarem...")
time.sleep(0.7)

found_next = False

for attempt in range(6):
    try:
        captions = driver.find_elements(
            By.XPATH,
            "//div[@role='button' and not(contains(@style,'display: none'))]"
            "//span[contains(@class,'v-button-caption')]"
        )

        print(f"   Attempt {attempt+1}: found {len(captions)} caption(s)")

        candidate_captions = []
        for c in captions:
            txt = c.text.strip()
            if not txt:
                continue
            if txt == original_caption:
                continue  # skip the company we already clicked

            # Prefer pattern "digits - name"
            if " - " in txt:
                left, _ = txt.split(" - ", 1)
                if left.replace(".", "").isdigit():
                    candidate_captions.append((c, txt))
                    continue

            # fallback — any non-empty caption
            candidate_captions.append((c, txt))

        if not candidate_captions:
            time.sleep(0.8)
            continue

        # Select best match
        chosen = None
        for c, txt in candidate_captions:
            if " - " in txt and txt.split(" - ", 1)[0].replace(".", "").isdigit():
                chosen = (c, txt)
                break

        if not chosen:
            chosen = candidate_captions[0]

        chosen_elem, chosen_text = chosen
        print(f"   Selected to click: '{chosen_text}'")

        clickable_next = chosen_elem.find_element(By.XPATH, "./ancestor::div[@role='button']")

        for click_attempt in range(3):
            try:
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", clickable_next)
                time.sleep(0.2)
                driver.execute_script("arguments[0].click();", clickable_next)
                found_next = True
                break
            except Exception as e_click:
                print("   click failed:", e_click)
                time.sleep(0.5)

        if found_next:
            time.sleep(1.0)
            print("✓ Próximo nível clicado:", chosen_text)
            break

    except Exception as e:
        print("   Exception while locating next-level buttons:", e)
        time.sleep(0.8)

if not found_next:
    print("⚠️  Não foi possível identificar/selecionar o próximo botão automaticamente.")

    all_captions = [
        c.text.strip() for c in driver.find_elements(
            By.XPATH,
            "//div[@role='button']//span[contains(@class,'v-button-caption')]"
        )
    ]

    print("   Captions currently on page (first 20):")
    for i, txt in enumerate(all_captions[:20], 1):
        print(f"    {i:02d}: '{txt}'")



#%%
print("\n→ Procurando o link da UG dentro do grid (Vaadin)...")

try:
    # 1 — get ALL hyperlink captions
    all_buttons = driver.find_elements(
        By.XPATH,
        "//span[contains(@class,'v-button-caption')]"
    )

    print("Total de botões encontrados:", len(all_buttons))

    # 2 — extract non-empty captions
    non_empty = [b for b in all_buttons if b.text.strip() != ""]

    print("\nBotões não vazios encontrados:")
    for b in non_empty:
        print("   •", b.text.strip())

    # 3 — The UG is ALWAYS the 3rd non-empty caption
    if len(non_empty) < 3:
        raise Exception("Não há links suficientes para selecionar UG.")

    ug_button = non_empty[2]   # 3rd non-empty caption

    print("\n→ UG encontrada:", ug_button.text.strip())

    # 4 — Go up to the clickable button div
    clickable = ug_button.find_element(By.XPATH, "./ancestor::div[@role='button']")

    for attempt in range(3):
        try:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", clickable)
            time.sleep(0.2)
            driver.execute_script("arguments[0].click();", clickable)
            print("✓ Link da UG clicado com sucesso.")
            break
        except Exception as e:
            print("Tentativa de clique falhou:", e)
            time.sleep(0.3)

except Exception as e:
    print("Erro:", e)

#%% Download do arquivo
import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import StaleElementReferenceException

print("\n→ Procurando link HTTP na coluna 'Processo'...")

try:
    # Step 1 — Wait for the Vaadin grid table
    grid = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((
            By.XPATH,
            "//div[contains(@class,'v-grid-tablewrapper')]/table"
        ))
    )
    print("✓ Grid Vaadin encontrado.")

    # Step 2 — Scroll grid into view to force rendering
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", grid)
    time.sleep(0.5)  # let Vaadin render headers and cells

    # Step 3 — Wait for headers to be fully loaded (with non-empty text)
    end_time = time.time() + 10
    headers = []
    while time.time() < end_time:
        headers = driver.find_elements(By.XPATH, "//div[contains(@class,'v-grid-column-header-content')]")
        if any(h.text.strip() == "Processo" for h in headers):
            break
        time.sleep(0.2)
    else:
        raise Exception("Coluna 'Processo' não encontrada ou não renderizada ainda")
    print("✓ Cabeçalhos da tabela carregados")

    # Step 4 — Find column index for 'Processo'
    column_index = None
    for i, header in enumerate(headers):
        if header.text.strip() == "Processo":
            column_index = i + 1  # XPath is 1-indexed
            break
    if column_index is None:
        raise Exception("Coluna 'Processo' não encontrada no grid.")
    print("Coluna 'Processo' encontrada no índice:", column_index)

    # Step 5 — Retry loop for rows and link (to avoid stale elements)
    target_link = None
    end_time = time.time() + 10
    while time.time() < end_time and target_link is None:
        try:
            rows = grid.find_elements(By.XPATH, ".//tbody/tr")  # re-query rows each iteration
            for row in rows:
                try:
                    cell = row.find_element(By.XPATH, f"./td[{column_index}]//a[starts-with(@href,'http')]")
                    target_link = cell
                    break
                except StaleElementReferenceException:
                    continue
                except:
                    continue
        except StaleElementReferenceException:
            continue
        time.sleep(0.2)

    if target_link is None:
        raise Exception("Nenhum link HTTP encontrado na coluna 'Processo'.")

    print("→ Link encontrado:", target_link.get_attribute("href"))
    print("→ Texto exibido:", target_link.text)

    # Step 6 — Scroll to the link and click
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", target_link)
    time.sleep(0.2)
    driver.execute_script("arguments[0].click();", target_link)

    print("✓ Link HTTP clicado com sucesso!")

except Exception as e:
    print("Erro ao procurar/clicar o link:", e)
