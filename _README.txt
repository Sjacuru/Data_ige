# 🤖 DATA_IGE — Sistema de Análise de Contratos Municipais

**Automação de auditoria de contratos inspirada nos procedimentos do TCMRio**

Este sistema automatizado verifica se contratos públicos estão em conformidade com 
as leis brasileiras de transparência, através de:

1. **Extração** de dados contratuais do portal oficial de licitações
2. **Verificação** de publicação no Diário Oficial (D.O. Rio)
3. **Comparação** dos dados do contrato com os dados publicados
4. **Geração** de relatórios de conformidade

---

## 📜 Contexto Legal

| Requisito                                                        |              Fundamentação |
|-----------                                                       |             ---------------|
| Contratos devem ser publicados em até **20 dias** após assinatura|            RGCAF, Art. 441 |
| Publicação deve ocorrer no D.O. Rio (Diário Oficial)             |     Decreto nº 22.319/2002 |
| Campos obrigatórios: partes, objeto, valor, dotação, prazo, data |   Lei nº 12.527/2011 (LAI) |
| Especificações de formato da publicação                          |Resolução SEGOVI nº 84/2022 |

---

## 🔄 Fluxo do Sistema (4 Fases)
┌─────────────────────────────────────────────────────────────────────────────┐ 
│ FLUXO DATA_IGE voltado para Ferramentas utilizadas                          │ 
└─────────────────────────────────────────────────────────────────────────────┘

FASE 1: Aquisição de Contratos ────────────────────────────── processo.rio 
                                                             (site Vaadin) 
                                                                  │ 
                                                                  ▼ 
                                                         ┌─────────────────┐ 
                                                         │ main.py         │ Navegação Selenium com tempos de espera estendidos 
                                                         │ + src/.py       │ Técnica de scroll duplo para grid Vaadin 
                                                         └────────┬────────┘ 
                                                                  │ 
                                                                  ▼ 
                                              Coleta IDs de empresas (CNPJ) da lista com scroll 
                                                                  │ 
                                                                  ▼ 
                                        Navega pelos níveis da página Vaadin → Acessa link do contrato 
                                                                  │ 
                                                                  ▼ 
                                         Download do PDF → Extração de texto (PyMuPDF + Tesseract OCR) 
                                                                  │ 
                                                                  ▼ 
                                                    ┌─────────────────────────────┐ 
                                                    │ Contract_analisys/          │ 
                                                    │ contract_extractor.py       │ Análise com IA (Groq LLaMA 3.3 70B) 
                                                    │ text_preprocessor.py        │ Limpeza de artefatos OCR 
                                                    └────────────┬────────────────┘ 
                                                                 │ 
                                                                 ▼ 
                                                 Dados Estruturados do Contrato (JSON)

FASE 2: Verificação de Publicação ──────────────── Dados do Contrato (da Fase 1) 
                                                            │ 
                                                            ▼ 
                                               ┌─────────────────────────────┐ 
                                               │ conformity/scraper/         │ 
                                               │ doweb_scraper.py            │ Selenium → doweb.rio.rj.gov.br 
                                               │ doweb_extractor.py          │ PyMuPDF → Extração de texto do PDF 
                                               └────────────┬────────────────┘ 
                                                            │ 
                                                            ▼ 
                          Busca no D.O. Rio pelo número do processo Download de PDFs um por vez → 
                                Verifica EXTRATO correspondente Extrai dados da publicação → 
                                                Deleta PDF temporário 
                                                            │ 
                                                            ▼ 
                                                  Dados da Publicação (JSON)

FASE 3: Análise de Conformidade ──────────── Dados do Contrato + Dados da Publicação 
                                                        │ 
                                                        ▼ 
                                         ┌─────────────────────────────────┐ 
                                         │ conformity/analyzer/            │ 
                                         │ publication_conformity.py       │ 
                                         │                                 │ 
                                         │ • Comparação campo a campo      │ 
                                         │ • Fuzzy matching (similaridade) │ 
                                         │ • Verificação de prazo (20 dias)│ 
                                         │ • Cálc de score de conformidade │ 
                                         └────────────┬────────────────────┘ 
                                                      │ 
                                                      ▼ 
                                          Resultado de Conformidade (JSON)

FASE 4: Visualização ──────────────────── Todos os Resultados 
                                                  │ 
                                                  ▼ 
                                    ┌──────────────────────────┐ 
                                    │ app.py                   │ Dashboard Streamlit 
                                    │                          │ 
                                    │ Abas:                    │ 
                                    │ • 📄 Arquivo Individual  │ 
                                    │ • 📦 Processamento Lote  │ 
                                    │ • 📊 Resultados          │ 
                                    │ • 🔍 Conformidade        │ 
                                    │ • ❓ Ajuda               │ 
                                    └──────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────┐
│                    ARQUITETURA COMPLETA                                         │
└─────────────────────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────────────────┐
│                              3 WEBSITES SCRAPED                               │
├─────────────────────┬─────────────────────┬───────────────────────────────────┤
│     ContasRio       │    processo.rio     │           DOWEB                   │
│  (company list)     │  (contract docs)    │    (D.O. publications)            │
└──────────┬──────────┴──────────┬──────────┴─────────────────┬─────────────────┘
           │                     │                            │
           ▼                     ▼                            ▼
┌──────────────────┐  ┌──────────────────┐       ┌──────────────────────────────┐
│ PHASE 1          │  │ PHASE 2          │       │ PHASE 4                      │
│ Collect Companies│  │ Download Docs    │       │ Verify Publication           │
├──────────────────┤  ├──────────────────┤       ├──────────────────────────────┤
│ main.py          │  │ extract_processo_│       │ conformity/                  │
│ scraper.py       │  │ documents.py     │       │ ├── scraper/                 │
│ reporter.py      │  │      or          │       │ │   ├── doweb_scraper.py     │
│      or          │  │ document_        │       │ │   └── doweb_extractor.py   │
│ download_csv.py  │  │ extractor.py     │       │ ├── analyzer/                │
│ process_from_    │  │                  │       │ │   └── publication_         │
│ csv.py           │  │                  │       │ │       conformity.py        │
└────────┬─────────┘  └────────┬─────────┘       │ └── models/                  │
         │                     │                 │     ├── publication.py       │
         │                     │                 │     └── conformity_result.py │
         ▼                     ▼                 └──────────────┬───────────────┘
┌──────────────────────────────────────────┐                   │
│           data/outputs/                  │                   │
│  • analysis_summary.csv/xlsx             │                   │
│  • companies_with_links.json             │                   │
└──────────────────┬───────────────────────┘                   │
                   │                                           │
                   ▼                                           │
         ┌──────────────────┐                                  │
         │ PHASE 3          │                                  │
         │ Extract Text     │                                  │
         ├──────────────────┤                                  │
         │extract_documents │                                  │
         │.py               │                                  │
         │    or            │                                  │
         │ parser.py        │                                  │
         │ analyzer.py      │                                  │
         └────────┬─────────┘                                  │
                  │                                            │
                  ▼                                            ▼
         ┌──────────────────────────────────────────────────────────────┐
         │                    Contract Data                             │
         │  • processo_administrativo                                   │
         │  • numero_contrato                                           │
         │  • valor_contrato                                            │
         │  • data_assinatura                                           │
         │  • objeto                                                    │
         │  • partes (contratante + contratada)                         │
         │  • prazo (data_inicio + data_fim)                            │
         └──────────────────────────┬───────────────────────────────────┘
                                    │
                                    ▼
         ┌──────────────────────────────────────────────────────────────┐
         │              CONFORMITY ANALYSIS                             │
         │                                                              │
         │  Contract Data ←──compare──→ Publication Data                │
         │                                                              │
         │  Output: ConformityResult                                    │
         │  • overall_status: CONFORME / NÃO CONFORME / PARCIAL        │
         │  • conformity_score: 0-100%                                  │
         │  • publication timing check (20-day deadline)                │
         │  • field-by-field comparison with match percentages          │
         └──────────────────────────────────────────────────────────────┘

--- ## 🛠️ Stack Tecnológica | Componente | Tecnologia | Propósito | 
                            |------------|------------|-----------| 
                            | Linguagem | Python 3.10+ | Desenvolvimento principal | 
                            | Web Scraping | Selenium + Chrome WebDriver | Navegação em sites Vaadin, D.O. Rio | 
                            | Extração PDF | PyMuPDF (fitz) | Extração nativa de texto | 
                            | OCR Fallback | Tesseract | Documentos escaneados | 
                            | Análise IA | LangChain + Groq API (LLaMA 3.3 70B) | Extração de dados contratuais | 
                            | Interface Web | Streamlit | Dashboard e visualização | 
                            | Exportação | pandas, openpyxl | Geração CSV/XLSX | 
                            | Configuração | python-dotenv | Variáveis de ambiente | 

--- ## 📁 Estrutura do Projeto
DATA_IGE/ # Pasta principal do projeto 
      │ 
      ├── .env # Chaves de API (GROQ_API_KEY) 
      ├── .gitignore # Python, env, dados temporários 
      ├── config.py # Configuração central do projeto 
      ├── requirements.txt # Dependências Python 
      │ 
      ├── app.py # Interface Streamlit para análise de contratos 
      ├── main.py # Ponto de entrada principal - orquestra fluxo completo 
      │ 
      ├── scripts/ # Scripts utilitários standalone (execução manual) 
                 │ 
                 ├── download_csv.py # Download de CSV do portal ContasRio 
                 │ 
                 ├── extract_documents.py # Versão offline - extrai texto de documentos locais 
                 │ 
                 ├── extract_processo_documents.py # Download de documentos do processo.rio 
                 │ 
                 ├── process_from_csv.py # Lê IDs de empresas do CSV e recupera dados 
                 │ 
                 └── process_saved_links.py # Processa links salvos (executar após main.py) 
      │ 
      ├── tests/ # Arquivos de teste e saídas 
               │ 
               ├── test_debug_doweb.py # Testes de debug do scraper DOWEB 
               │ 
               ├── test_extractor.py # Testes de extração de documentos 
               │ 
               ├── test_ocr_utils.py # Testes de utilitários OCR 
               │ 
               ├── test_preprocessor.py # Testes do pré-processador de texto 
               │ 
               ├── test_scraper.py # Testes do web scraper 
               │ 
               ├── test_verify_ocr_env.py # Verificação do ambiente OCR 
               │ 
               └── test_preprocessed_output.txt # Artefato de saída de teste 
      │ 
      ├── docs/ # Documentação e diagramas 
              │ 
              ├── CodeStructure_Mermaid.png # Diagrama visual da arquitetura 
              │ 
              └── CodeStructure_Mermaid.txt # Código-fonte Mermaid do diagrama 
      │ 
      ├── src/ # Módulos principais de scraping 
             │ 
             ├── init.py # Inicializador do pacote 
             │ 
             ├── scraper.py # Scraper do processo.rio (ponto de entrada) 
             │ 
             ├── analyzer.py # Análise de conteúdo, gera flags/recomendações 
             │ 
             ├── document_extractor.py # Extração de PDFs, trata CAPTCHA, downloads temp 
             │ 
             ├── downloader.py # Download de PDFs e documentos de URLs 
             │ 
             ├── parser.py # Extração de texto/dados de PDFs, Word, HTML 
             │ 
             └── reporter.py # Criação de relatórios, exportação, dashboard 
      │ 
      ├── Contract_analisys/ # Módulo de extração e análise com IA 
                           │ 
                           ├── init.py # Inicializador do pacote 
                           │ 
                           ├── contract_extractor.py # Integração com Groq LLaMA 
                           │ 
                           └── text_preprocessor.py # Limpeza de texto OCR (standalone) 
      │ 
      ├── conformity/ # Módulo de verificação de conformidade (D.O. Rio) 
                    │ 
                    ├── init.py # Inicializador do pacote 
                    │ 
                    ├── integration.py # Orquestra o fluxo completo de conformidade 
                    │ 
                    │ 
                    │ 
                    ├── models/ # Modelos de dados para análise 
                              │ 
                              │ 
                              ├── init.py 
                              │ 
                              │ 
                              ├── conformity_result.py # ConformityResult, FieldCheck, CheckStatus, MatchLevel 
                              │ 
                              │ 
                              └── publication.py # PublicationResult, SearchResultItem dataclasses 
                    │ 
                    │ 
                    │ 
                    ├── analyzer/ # Lógica de comparação de conformidade 
                                │ 
                                │ 
                                ├── init.py 
                                │ 
                                │ 
                                └── publication_conformity.py # Compara contrato vs publicação, fuzzy matching 
                    │ 
                    │ 
                    │ 
                    ├── scraper/ # Web scraping do D.O. Rio 
                              │ 
                              │ 
                              ├── init.py 
                              │ 
                              │ 
                              ├── doweb_scraper.py # Scraper Selenium para doweb.rio.rj.gov.br 
                              │ 
                              │ 
                              └── doweb_extractor.py # Extração e parsing de PDFs do D.O. 
                    │ 
                    │ 
                    │ 
                    └── criteria/ # Definições de critérios legais 
                                 │ 
                                 ├── init.py 
                                 │ 
                                 └── laws/ 
                                          │ 
                                          └── custom_tcmrio.yaml # Critérios de auditoria TCMRio (a criar) 
      │ 
      └── data/ # Armazenamento de dados 
              ├── downloads/ 
                           │ 
                           └── processos/ # PDFs de contratos do processo.rio 
                                        ├── extractions # JSONs com dados raspados e links 
              ├── outputs/ # Exportações CSV/XLSX 
              ├── conformity/ # Resultados de conformidade 
              └── temp_doweb/ # PDFs temporários do D.O. (auto-deletados)


--- ## 🔧 Scripts Disponíveis ### 
1️⃣ `main.py` — Raspagem Completa **O que faz:** 
- Acessa o portal ContasRio - Faz scroll e coleta todas as empresas da tabela 
- Para cada empresa, navega pelos níveis (Órgão → UG → Objeto) - Coleta todos os links de processos 
- Extrai e analisa o conteúdo dos documentos - Gera relatórios em Excel **Como executar:** ```bash python main.py

Saída:

data/outputs/analysis_summary.xlsx — Relatório completo
data/outputs/analysis_summary.csv — Backup em CSV

2️⃣ scripts/download_csv.py — Download do CSV
O que faz:
Acessa o portal ContasRio
Clica no botão de download (ícone ⬇️)
Seleciona opção "CSV"
Aguarda o download completar
Renomeia o arquivo com timestamp
Como executar:

python scripts/download_csv.py
Saída:

data/downloads/contasrio_export_YYYYMMDD_HHMMSS.csv

3️⃣ scripts/process_from_csv.py — Processamento a partir do CSV
O que faz:

Lê o arquivo CSV baixado
Extrai os IDs das empresas
Para cada empresa, navega e coleta processos
Salva resultados em CSV
Como executar:

# Processar todas as empresas
python scripts/process_from_csv.py

# Processar apenas as primeiras 10 (teste)
python scripts/process_from_csv.py --max 10

# Modo headless (sem janela do navegador)
python scripts/process_from_csv.py --headless

# Usar CSV específico
python scripts/process_from_csv.py --csv data/downloads/arquivo.csv
Saída:

data/outputs/processos_YYYYMMDD_HHMMSS.csv
4️⃣ scripts/extract_documents.py — Extração de Documentos
O que faz:

Extrai texto e metadados de múltiplos formatos de documento
Suporta: PDF, DOCX, XLSX, CSV, HTML, TXT, MD, JSON
Processamento paralelo para alta performance
Exporta resultados em JSON ou TXT
Formatos suportados:

Formato	Extensões	Extração
PDF	.pdf	Texto + metadados (autor, título, datas)
Word	.docx, .doc	Parágrafos + tabelas + propriedades
Excel	.xlsx, .xls	Todas as planilhas em formato texto
CSV	.csv	Detecção automática de delimitador
HTML	.html, .htm	Texto limpo (sem scripts/styles)
Texto	.txt, .md	Conteúdo com detecção de encoding
JSON	.json	Formatação pretty-print
Como executar:

# Extrair um único PDF
python scripts/extract_documents.py report.pdf

# Processar diretório inteiro recursivamente
python scripts/extract_documents.py ./documents/ --recursive

# Saída customizada com 8 workers paralelos
python scripts/extract_documents.py ./docs/ -o ./extracted -f json -w 8

# Modo verbose para debugging
python scripts/extract_documents.py ./files/ -v --recursive
Opções disponíveis:

Opção	Descrição	Padrão
-o, --output	Diretório de saída	./output
-f, --format	Formato de saída (json ou txt)	json
-r, --recursive	Processar subdiretórios	False
-w, --workers	Número de workers paralelos	4
-v, --verbose	Logging detalhado	False

5️⃣ app.py — Dashboard Streamlit
O que faz:

Interface gráfica para análise de contratos
Processamento individual ou em lote
Visualização de resultados de conformidade
Exportação em Excel/JSON
Como executar:

streamlit run app.py
Abas disponíveis:

📄 Arquivo Individual — Processa um PDF por vez
📦 Processamento em Lote — Processa múltiplos PDFs
📊 Resultados — Visualiza dados extraídos
🔍 Conformidade — Verifica publicação no D.O. Rio
❓ Ajuda — Documentação e instruções
                        🔄 Fluxo de Trabalho Recomendado
              ┌──────────────────────────────────────────────────────────────┐ 
              │ OPÇÃO 1: Raspagem Completa                                   │ 
              │                                                              │ 
              │ python main.py                                               │ 
              │          └── Coleta tudo: empresas + processos + análise     │ 
              │          └── Mais lento, mais completo                       │ 
              └──────────────────────────────────────────────────────────────┘ 
              ┌──────────────────────────────────────────────────────────────┐ 
              │ OPÇÃO 2: Duas Etapas                                         │ 
              │                                                              │ 
              │ 1. python scripts/download_csv.py                            │ 
              │                       └── Baixa lista de empresas (rápido)   │ 
              │                                                              │ 
              │ 2. python scripts/process_from_csv.py                        │ 
              │                       └── Processa cada empresa do CSV       │ 
              │                       └── Pode ser interrompido e retomado   │ 
              └──────────────────────────────────────────────────────────────┘ 
              ┌──────────────────────────────────────────────────────────────┐ 
              │ OPÇÃO 3: Extração de Documentos Locais                       │ 
              │                                                              │ 
              │ python scripts/extract_documents.py ./pasta/ -r -f json      │ 
              │                      └── Extrai texto de todos os documentos │ 
              │                      └── Ideal para análise posterior com IA │ 
              └──────────────────────────────────────────────────────────────┘ 
              ┌──────────────────────────────────────────────────────────────┐ 
              │ OPÇÃO 4: Análise com Dashboard + Conformidade 🆕            │ 
              │                                                              │ 
              │ 1. python scripts/extract_processo_documents.py              │ 
              │                               └── Baixa PDFs do processo.rio │ 
              │                                                              │ 
              │ 2. streamlit run app.py                                      │ 
              │                   └── Abre dashboard para análise            │ 
              │                   └── Processa PDFs individuais ou em lote   │ 
              │                   └── Verifica conformidade no D.O. Rio      │ 
              │                   └── Exporta resultados em Excel/JSON       │ 
              └──────────────────────────────────────────────────────────────┘

📊 Lógica de Conformidade
Determinação de Status
Status	                           Condição
✅ DADOS PUBLICADOS	                     Publicado + no prazo (≤20 dias) + todos os campos conferem
⚠️ PARCIAL	                      Publicado mas atrasado OU campos parcialmente conferem
❌ NÃO CONFORME	                 Não publicado OU divergências graves nos campos

Níveis de Match                   (Fuzzy Matching)
Nível	                        Porcentagem	Resultado
EXATO	100%	                          APROVADO
ALTO	80-99%	                        APROVADO
MÉDIO	50-79%	                        PARCIAL
BAIXO	20-49%	                        REPROVADO
NENHUM	<20%	                        REPROVADO

⚠️ Nota Importante
"Não encontrado na busca" ≠ "Não publicado"

O sistema só pode confirmar o que encontra. Nunca afirma definitivamente que algo não foi publicado — apenas que não foi localizado na busca.

🔑 Desafios Técnicos Resolvidos
Desafio                                     Solução
Grid Vaadin não carregando	                Tempos de espera estendidos (8+ segundos)
Scroll Vaadin não captura todas as linhas	  Técnica de scroll duplo
Renderização JavaScript do D.O. Rio	        Espera de 8 segundos antes do parsing
Parsing de resultados do D.O. Rio	          Regex no texto do body (não XPath)
Confiabilidade do download de PDF	          Biblioteca requests ao invés de click Selenium
Artefatos de texto OCR	                    Limpeza via text_preprocessor.py
Correspondência fuzzy de campos	            SequenceMatcher com níveis de match
Formatos de número de processo	            Padrões regex para formatos antigo/novo

📊 Comparação dos Scripts
Característica	      main.py	  download_csv.py	  process_from_csv.py	  extract_documents.py	  app.py
Propósito	      Raspagem completa	Baixar CSV	      Processar do CSV	   Extrair documentos	 Dashboard análise
Entrada	             Portal web	  Portal web	         Arquivo CSV	       Arquivos locais	  PDFs locais
Saída	              Excel + CSV	    CSV	                    CSV	             JSON / TXT	      Excel / JSON
Velocidade	           Lento	     Rápido	                 Médio	              Rápido	         Médio
Coleta emp Scroll	    Download     direto	            Lê do arquivo	              N/A	            N/A
Coleta processos	       ✅         ❌	                   ✅	                  N/A	            N/A
Extrai texto	           ✅	       ❌	                   ❌	                  ✅	             ✅
Análise IA	             ✅	       ❌	                   ❌	                  ❌	             ✅
OCR	                     ❌	       ❌	                   ❌	                  ❌	             ✅
Pré-processamento	       ❌	       ❌  	                 ❌	                  ❌	             ✅
Processamento paralelo	 ❌	       ❌	                   ❌	                  ✅	             ❌
Interface gráfica	       ❌	       ❌	                   ❌	                  ❌	             ✅
Conformidade D.O.	       ❌	       ❌	                   ❌	                  ❌	             ✅
Interrompível	           ✅	       ❌	                   ✅	                  ✅	             ✅

💻 Instalação
Pré-requisitos
Windows 10/11
Google Chrome browser
Anaconda ou Miniconda
Tesseract OCR (para análise de contratos)
Poppler (para pdf2image)

1. Criar ambiente Conda
conda create --name ige python=3.11
conda activate ige

2. Clonar repositório
git clone https://github.com/sjacuru/Data_ige.git
cd Data_ige

3. Instalar dependências
# Dependências principais
pip install selenium webdriver-manager pandas openpyxl python-dotenv
pip install streamlit pymupdf langchain-groq tenacity pdf2image pytesseract

# Ou usar requirements.txt
pip install -r requirements.txt

4. Instalar Tesseract OCR (Windows)
Baixar instalador: https://github.com/UB-Mannheim/tesseract/wiki
Instalar em C:\Program Files\Tesseract-OCR\
Adicionar ao PATH ou configurar em contract_extractor.py
5. Instalar Poppler (Windows)
Baixar: https://github.com/oschwartz10612/poppler-windows/releases
Extrair para C:\poppler-XX.XX.X\
Configurar caminho em contract_extractor.py
6. Configurar variáveis de ambiente
Criar arquivo .env na raiz do projeto:

⚙️ Configuração
Arquivo                              config.py
Variável          	              Descrição	Padrão
BASE_URL	                URL da página inicial	processo.rio
CONTRACTS_URL	                 URL da página de contratos	—
TIMEOUT_SECONDS	              Tempo máximo de espera	30
FILTER_YEAR	               Ano para filtrar contratos	2025
PROCESSOS_DIR 	     Diretório de PDFs baixados	data/downloads/processos
EXTRACTIONS_DIR	         Diretório de resultados	data/extractions
DOWEB_BASE_URL	        URL do Diário Oficial	doweb.rio.rj.gov.br

🚨 Problemas Conhecidos
Problema	                                                      Solução

Path discovery                mistura branches	Em empresas com múltiplos Órgãos, os caminhos 
                              podem ser construídos incorretamente. Solução em desenvolvimento.

Timeout em conexões lentas	                Aumentar TIMEOUT_SECONDS no config.py

Vaadin não reseta estado	            O script navega para HOME antes de CONTRACTS_URL 
                                                para garantir reset completo

PDFs escaneados	              Use app.py com contract_extractor.py para PDFs escaneados (inclui OCR)

Rate limit da API Groq	                Sistema possui retry automático (até 5 tentativas). 
                                      Aguarde alguns segundos entre processamentos em lote

Tesseract não encontrado	        Verifique se o Tesseract está instalado e o caminho configurado em 
                                                      contract_extractor.py


🚀 Próximos Passos (Planejado)
 Orquestração YAML — Definir passos do workflow, critérios e configurações em custom_tcmrio.yaml
 Deploy Docker — Containerizar para acesso remoto
 Critérios Adicionais — Adicionar mais verificações legais além da publicação
 Armazenamento em Banco — SQLite/PostgreSQL para resultados persistentes
 API REST — Expor verificação de conformidade como endpoints

📅 Atualizações Recentes
✅ Adicionado módulo Contract_analisys para análise de contratos
✅ Adicionado dashboard Streamlit (app.py)
✅ Adicionado pré-processamento de texto OCR
✅ Adicionada extração com IA (Groq/LLaMA)
✅ Adicionado suporte a OCR para PDFs escaneados
✅ Adicionado módulo conformity/ para verificação no D.O. Rio
✅ Reorganização da estrutura de pastas (scripts/, tests/, docs/)
✅ Corrigidos bugs de extração de PDF
✅ Melhorado tratamento de erros
🔄 Em desenvolvimento: Orquestração YAML e deploy Docker


📝 Licença
MIT License

Copyright (c) 2025 Salim Jacuru

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

👥 Contribuidores
Salim — Desenvolvimento principal
Claude & outras IAs — Pair programming e documentação
📋 Resumo das Seções
Seção	Conteúdo
Contexto Legal	Fundamentação jurídica
Fluxo do Sistema	4 fases do workflow
Stack Tecnológica	Ferramentas utilizadas
Estrutura	Organização de pastas e arquivos
Scripts	O que cada script faz e como usar
Workflow	Como usar os scripts em conjunto
Conformidade	Lógica de análise e níveis de match
Configuração	Variáveis .env e config.py
Instalação	Setup passo a passo
Comparação	Tabela comparando todos os scripts
Problemas Conhecidos	Limitações atuais e soluções

--- ## ✅ Changes Made 
| Section                              | Change                                                     | 
|---------                             |--------                                                    | 
| **Header**                           | Added project purpose and 4-step overview                  | 
| **Legal Context**                    | New section with law references                            | 
| **Workflow Diagram**                 | Updated 4-phase ASCII diagram                              | 
| **Tech Stack**                       | New table with all technologies                            |       
| **Project Structure**                | Updated with `scripts/`, `tests/`, `docs/`, `conformity/`  | 
| **Scripts Section**                  | Updated paths to `scripts/` folder                         | 
| **Conformity Logic**                 | New section explaining status and match levels             | 
| **Technical Challenges**             | New section documenting solutions                          | 
| **Comparison Table**                 | Added Conformity D.O. row                                  | 
| **Next Steps**                       | Updated with YAML, Docker, API plans                       | 
| **Recent Updates**                   | Added conformity module and folder reorganization 

| Ready to copy! 📋