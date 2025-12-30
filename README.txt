# 🤖 Automações Diversas para o TCMRio/SGCE/1IGE

Este repositório contém projetos de automação e scripts utilitários prioritariamente em Python.

---

## 🎯 Projetos Principais

| Nome do Projeto | Localização | Descrição |
| :--- | :--- | :--- |
| **Automação com Selenium** | `./Data_ige/` | Scripts Python para interação e raspagem de dados via navegador web (Selenium WebDriver). |
| [próximo Projeto] | `./nome_nova_pasta/` | [Descrição breve] |

---

## 📁 Estrutura do Projeto Data_ige

Data_ige/ ├── config.py # Configurações globais (URLs, timeouts, etc.) ├── .env # Variáveis de ambiente (FILTER_YEAR) ├── main.py # Script principal - raspagem completa ├── download_csv.py # Download do CSV do portal ├── process_from_csv.py # Processa empresas a partir do CSV ├── downloads/ # Arquivos CSV baixados ├── outputs/ # Resultados do processamento ├── data/ │ └── outputs/ # Relatórios Excel gerados pelo main.py └── src/ ├── scraper.py # Funções de navegação e raspagem ├── downloader.py # Download de documentos ├── parser.py # Extração de texto de documentos ├── analyzer.py # Análise de contratos com IA └── reporter.py # Geração de relatórios

--- ## 🔧 Scripts Disponíveis ### 1️⃣ `main.py` - Raspagem Completa **O que faz:** - Acessa o portal ContasRio - Faz scroll e coleta todas as empresas da tabela - Para cada empresa, navega pelos níveis (Órgão → UG → Objeto) - Coleta todos os links de processos - Extrai e analisa o conteúdo dos documentos - Gera relatórios em Excel **Fluxo de execução:**
Navega para página de contratos
Aplica filtro de ano (FILTER_YEAR)
Scroll e coleta todas as linhas (2 passagens)
Para cada empresa: a. Reseta para página inicial b. Filtra por ID da empresa c. Clica na empresa d. Descobre todos os caminhos (Órgão → UG) e. Segue cada caminho e coleta processos f. Gera relatório
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

1. Lê o CSV mais recente da pasta downloads/ 2. Extrai IDs únicos das empresas 3. Para cada empresa: a. Reseta para página de contratos b. Filtra por ID c. Navega pelos níveis d. Coleta processos 4. Salva progresso a cada 10 empresas 5. Gera arquivo final com todos os processos
Como executar:

# Processar todas as empresas
python process_from_csv.py

# Processar apenas as primeiras 10 (teste)
python process_from_csv.py --max 10

# Modo headless (sem janela)
python process_from_csv.py --headless

# Usar CSV específico
python process_from_csv.py --csv downloads/arquivo.csv
Saída:

outputs/processos_YYYYMMDD_HHMMSS.csv
🔄 Fluxo de Trabalho Recomendado
┌─────────────────────────────────────────────────────────────┐ │ OPÇÃO 1: Raspagem Completa │ │ │ │ python main.py │ │ └── Coleta tudo: empresas + processos + análise │ │ └── Mais lento, mais completo │ └─────────────────────────────────────────────────────────────┘ ┌─────────────────────────────────────────────────────────────┐ │ OPÇÃO 2: Duas Etapas │ │ │ │ 1. python download_csv.py │ │ └── Baixa lista de empresas (rápido) │ │ │ │ 2. python process_from_csv.py │ │ └── Processa cada empresa do CSV │ │ └── Pode ser interrompido e retomado │ └─────────────────────────────────────────────────────────────┘
⚙️ Configuração
Arquivo .env
Arquivo config.py
BASE_URL: URL da página inicial
CONTRACTS_URL: URL da página de contratos
TIMEOUT_SECONDS: Tempo máximo de espera (padrão: 30)
FILTER_YEAR: Ano para filtrar contratos
💻 Instalação
Pré-requisitos
Windows 10/11
Google Chrome browser
Anaconda ou Miniconda
1. Criar ambiente Conda
conda create --name ige python=3.11
conda activate ige
2. Clonar repositório
git clone https://github.com/sjacuru/Data_ige.git
cd Data_ige
3. Instalar dependências
pip install selenium webdriver-manager pandas openpyxl python-dotenv
4. Configurar variáveis de ambiente
Criar arquivo .env:

📊 Comparação dos Scripts
Característica	main.py	download_csv.py	process_from_csv.py
Propósito	Raspagem completa	Baixar CSV	Processar do CSV
Entrada	Portal web	Portal web	Arquivo CSV
Saída	Excel + CSV	CSV	CSV
Velocidade	Lento	Rápido	Médio
Coleta empresas	Scroll	Download direto	Lê do arquivo
Coleta processos	✅	❌	✅
Análise IA	✅	❌	❌
Interrompível	✅	❌	✅
🚨 Problemas Conhecidos
Path discovery pode misturar branches: Em empresas com múltiplos Órgãos, os caminhos podem ser construídos incorretamente. Solução em desenvolvimento.

Timeout em conexões lentas: Aumentar TIMEOUT_SECONDS no config.py se necessário.

Vaadin não reseta estado: O script navega para HOME antes de CONTRACTS_URL para garantir reset completo.

📝 Licença
[Sua licença aqui]

👥 Contribuidores
[Lista de contribuidores]

--- ## Summary This README explains: | Section | Content | |---------|---------| | Structure | Folder and file organization | | Scripts | What each script does | | Workflow | How to use them together | | Configuration | .env and config.py settings | | Installation | Step-by-step setup | | Comparison | Table comparing all 3 scripts | | Known Issues | Current limitations |