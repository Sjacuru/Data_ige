# 🤖 Automações Diversas para o TCMRio/SGCE/1IGE

Este repositório contém projetos de automação e scripts utilitários prioritariamente em Python.

---

## 🎯 Projetos Principais

| Nome do Projeto             | Localização                     | Descrição                                                                                  |
| :---                        | :---                            | :---                                                                                       |
| **Automação com Selenium**  | `./Data_ige/`                   | Scripts Python para interação e raspagem de dados via navegador web (Selenium WebDriver).  |
| **Extração de Documentos**  | `./doc_extractor/`              | Pipeline para extração de texto e metadados de PDFs, Word, Excel, HTML e outros formatos.  |
| **Análise de Contratos**    | `./Data_ige/Contract_analisys/` | Sistema de extração e análise de contratos com IA (Groq/LLaMA). |

---

## 📁 Estrutura do Projeto Data_ige
Data_ige/ 
├── config.py # Configurações globais (URLs, timeouts, etc.) 
├── .env # Variáveis de ambiente (FILTER_YEAR) 
├── main.py # Script principal - raspagem completa 
├── download_csv.py # Download do CSV do portal 
├── process_from_csv.py # Processa empresas a partir do CSV 
├── downloads/ # Arquivos CSV baixados 
├── outputs/ # Resultados do processamento 
├── data/   │ 
            └── outputs/ # Relatórios Excel gerados pelo main.py  
            └── src/ 
├── scraper.py # Funções de navegação e raspagem 
├── downloader.py # Download de documentos 
├── parser.py # Extração de texto de documentos 
├── analyzer.py # Análise de contratos com IA 
└── reporter.py # Geração de relatórios

--- ## 📁 Estrutura do Projeto doc_extractor
doc_extractor/ 
├── extract_documents.py # Script principal de extração 
├── requirements.txt # Dependências do projeto 
├── output/ # Resultados das extrações (JSON/TXT) 
└── README.md # Documentação específica

--- ## 🔧 Scripts Disponíveis ### 1️⃣ `main.py` - Raspagem Completa **O que faz:** 
- Acessa o portal ContasRio 
- Faz scroll e coleta todas as empresas da tabela 
- Para cada empresa, navega pelos níveis (Órgão → UG → Objeto) 
- Coleta todos os links de processos 
- Extrai e analisa o conteúdo dos documentos 
- Gera relatórios em Excel **Fluxo de execução:**

Navega para página de contratos
Aplica filtro de ano (FILTER_YEAR)
Scroll e coleta todas as linhas (2 passagens)
Para cada empresa: 
a. Reseta para página inicial 
b. Filtra por ID da empresa 
c. Clica na empresa 
d. Descobre todos os caminhos (Órgão → UG) 
e. Segue cada caminho e coleta processos 
f. Gera relatório

Salva resultados em Excel
**Como executar:** ```bash python main.py
Saída:

data/outputs/analysis_summary.xlsx - Relatório completo
data/outputs/analysis_summary.csv - Backup em CSV

2️⃣ download_csv.py - Download do CSV

O que faz:

Acessa o portal ContasRio
Clica no botão de download (ícone ⬇️)
Seleciona opção "CSV"
Aguarda o download completar
Renomeia o arquivo com timestamp
Fluxo de execução:

1. Navega para página de contratos 2. Aplica filtro de ano 3. Clica no ícone de download 4. Seleciona opção CSV 5. Aguarda download (máx 60s) 6. Renomeia arquivo: contasrio_export_YYYYMMDD_HHMMSS.csv
Como executar:

python download_csv.py
Saída:

downloads/contasrio_export_YYYYMMDD_HHMMSS.csv

3️⃣ process_from_csv.py - Processamento a partir do CSV

O que faz:

Lê o arquivo CSV baixado
Extrai os IDs das empresas
Para cada empresa, navega e coleta processos
Salva resultados em CSV
Fluxo de execução:

1. Lê o CSV mais recente da pasta downloads/ 
2. Extrai IDs únicos das empresas 
3. Para cada empresa: 
   a. Reseta para página de contratos 
   b. Filtra por ID 
   c. Navega pelos níveis 
   d. Coleta processos 
4. Salva progresso a cada 10 empresas 
5. Gera arquivo final com todos os processos

Como executar:

# Processar todas as empresas
python process_from_csv.py

# Processar apenas as primeiras 10 (teste)
python process_from_csv.py --max 10

# Modo headless (sem janela do navegador)
python process_from_csv.py --headless

# Usar CSV específico
python process_from_csv.py --csv downloads/arquivo.csv
Saída:

outputs/processos_YYYYMMDD_HHMMSS.csv

4️⃣ extract_documents.py - Extração de Documentos

O que faz:

Extrai texto e metadados de múltiplos formatos de documento
Suporta: PDF, DOCX, XLSX, CSV, HTML, TXT, MD, JSON
Processamento paralelo para alta performance
Exporta resultados em JSON ou TXT
Formatos suportados:

Formato	  Extensões	                Extração
PDF	        .pdf	          Texto + metadados (autor, título, datas)
Word	      .docx, .doc	      Parágrafos + tabelas + propriedades
Excel	      .xlsx, .xls	      Todas as planilhas em formato texto
CSV	        .csv	          Detecção automática de delimitador
HTML	      .html, .htm	      Texto limpo (sem scripts/styles)
Texto	      .txt, .md	        Conteúdo com detecção de encoding
JSON	      .json	                Formatação pretty-print

Como executar:

# Extrair um único PDF
python extract_documents.py report.pdf

# Processar diretório inteiro recursivamente
python extract_documents.py ./documents/ --recursive

# Saída customizada com 8 workers paralelos
python extract_documents.py ./docs/ -o ./extracted -f json -w 8

# Modo verbose para debugging
python extract_documents.py ./files/ -v --recursive
Opções disponíveis:

Opção	Descrição	Padrão
-o, --output	Diretório de saída	./output
-f, --format	Formato de saída (json ou txt)	json
-r, --recursive	Processar subdiretórios	False
-w, --workers	Número de workers paralelos	4
-v, --verbose	Logging detalhado	False

Saída JSON:

[
  {
    "filename": "relatorio.pdf",
    "filepath": "/caminho/completo/relatorio.pdf",
    "file_type": "pdf",
    "content": "Texto extraído do documento...",
    "metadata": {
      "title": "Relatório Anual",
      "author": "João Silva",
      "creation_date": "2025-01-15"
    },
    "page_count": 24,
    "word_count": 5842,
    "extracted_at": "2025-12-31T10:30:00"
  }
]
Saída:

output/extraction_YYYYMMDD_HHMMSS.json ou .txt
🔄 Fluxo de Trabalho Recomendado

┌──────────────────────────────────────────────────────────────┐ 
│ OPÇÃO 1: Raspagem Completa                                   │ 
│                                                              │ 
│ python main.py                                               │ 
│                                                              
└── Coleta tudo: empresas + processos + análise                │      
│└── Mais lento, mais completo │ 
└──────────────────────────────────────────────────────────────┘ 
┌──────────────────────────────────────────────────────────────┐ 
│ OPÇÃO 2: Duas Etapas                                         │ 
│                                                              │ 
│ 1. python download_csv.py                                    │ 
│ └── Baixa lista de empresas (rápido)                         │ 
│                                                              │ 
│ 2. python process_from_csv.py                                │ 
│ └── Processa cada empresa do CSV                             │ 
│ └── Pode ser interrompido e retomado                         │
└──────────────────────────────────────────────────────────────┘ 
┌──────────────────────────────────────────────────────────────┐ 
│ OPÇÃO 3: Extração de Documentos Locais                       │ 
│                                                              │ 
│ python extract_documents.py ./pasta/ -r -f json              │ 
│ └── Extrai texto de todos os documentos                      │ 
│ └── Ideal para análise posterior com IA                      │ 
└──────────────────────────────────────────────────────────────┘
┌──────────────────────────────────────────────────────────────┐ 
│ OPÇÃO 4: Análise de Contratos com Dashboard 🆕               │ 
│                                                               │ 
│ 1. python extract_processo_documents.py                       │ 
│ └── Baixa PDFs do processo.rio                                │   
│                                                               │ 
│ 2. streamlit run app.py                                       │   
│ └── Abre dashboard para análise                               │ 
│ └── Processa PDFs individuais ou em lote                      │ 
│ └── Exporta resultados em Excel/JSON                          │ 
└──────────────────────────────────────────────────────────────┘


Arquivo .env
Arquivo config.py
BASE_URL: URL da página inicial
CONTRACTS_URL: URL da página de contratos
TIMEOUT_SECONDS: Tempo máximo de espera (padrão: 30)
FILTER_YEAR: Ano para filtrar contratos
PROCESSOS_DIR: Diretório de PDFs baixados
EXTRACTIONS_DIR: Diretório de resultados
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
Para Data_ige (Selenium + Análise de Contratos):

pip install selenium webdriver-manager pandas openpyxl python-dotenv
pip install streamlit pymupdf langchain-groq tenacity pdf2image pytesseract
Para doc_extractor:

cd doc_extractor
pip install -r requirements.txt
Ou instalar manualmente:

pip install PyMuPDF python-docx openpyxl beautifulsoup4 pandas
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



📊 Comparação dos Scripts
Característica	      main.py	      download_csv.py	      process_from_csv.py	      extract_documents.py          app.py
Propósito	      Raspagem completa	   Baixar CSV	         Processar do CSV	         Extrair documentos         Dashboard análise
Entrada	           Portal web	      Portal web	            Arquivo CSV	               Arquivos locais          PDFs locais
Saída	Excel          + CSV	             CSV	                   CSV	                     JSON / TXT           Excel / JSON
Velocidade	          Lento    	        Rápido	                Médio	                       Rápido               Médio
Coleta empresas	      Scroll	      Download direto	        Lê do arquivo	                     N/A                  N/A
Coleta processos	      ✅	               ❌	                  ✅	                           N/A                 N/A
Extrai texto	          ✅	               ❌	                  ❌	                           ✅                  ✅
Análise IA	            ✅	               ❌    	              ❌	                           ❌                  ✅
OCR	                    ❌	               ❌	                  ❌	                           ❌	                ✅
Pré-processamento	      ❌	               ❌	                  ❌	                           ❌	                ✅
Processamento paralelo  ❌	               ❌	                  ❌	                           ✅                  ❌
Interface gráfica	      ❌	               ❌	                  ❌	                           ❌	                ✅
Interrompível	          ✅	               ❌	                  ✅	                           ✅                  ✅

🚨 Problemas Conhecidos
Path discovery pode misturar branches: Em empresas com múltiplos Órgãos, os caminhos podem ser construídos incorretamente. Solução em desenvolvimento.

Timeout em conexões lentas: Aumentar TIMEOUT_SECONDS no config.py se necessário.

Vaadin não reseta estado: O script navega para HOME antes de CONTRACTS_URL para garantir reset completo.

PDFs escaneados: O extract_documents.py não realiza OCR. Use app.py com contract_extractor.py para PDFs escaneados.

Rate limit da API Groq: O sistema possui retry automático (até 5 tentativas). Aguarde alguns segundos entre processamentos em lote.

Tesseract não encontrado: Verifique se o Tesseract está instalado e o caminho configurado em contract_extractor.py.

📅 Atualizações mais Recentes

✅ Adicionado módulo Contract_analisys para análise de contratos
✅ Adicionado dashboard Streamlit (app.py)
✅ Adicionado pré-processamento de texto OCR
✅ Adicionada extração com IA (Groq/LLaMA)
✅ Adicionado suporte a OCR para PDFs escaneados
✅ Corrigidos bugs de extração de PDF
✅ Melhorado tratamento de erros
🔄 Em desenvolvimento: Análise de conformidade legal

📝 Licença
MIT License

Copyright (c) 2025 Salim Jacuru

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated 
documentation files (the "Software"), to deal in the Software without restriction, including without limitation 
the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and 
to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions 
of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED 
TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL 
THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF 
CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS 
IN THE SOFTWARE.

👥 Contribuidores

Salim, Algumas IAs (Principalmente Claude), digo, IAs e depois Salim

📋 Resumo

Seção	Conteúdo
Estrutura	Organização de pastas e arquivos
Scripts	O que cada script faz
Workflow	Como usá-los em conjunto
Configuração	Configurações .env e config.py
Instalação	Setup passo a passo
Comparação	Tabela comparando todos os 4 scripts
Problemas Conhecidos	Limitações atuais