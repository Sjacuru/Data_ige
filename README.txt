# 🤖 Automações Diversas para o TCMRio/SGCE/1IGE

Este repositório contém projetos de automação e scripts utilitários prioritariamente em Python.

## 🎯 Projetos Principais

This tool automates the process of:
1. **Retrieving** contract information from the ContasRio web portal
2. **Identifying** and downloading relevant documents
3. **Analyzing** document content using AI
4. **Answering** based on pre-set instructions and generating reports

| Nome do Projeto             | Localização           | Descrição                                                                                     |
| :---                        | :---                  | :---                                                                                          |
| **Automação com Selenium**  | `./Data_ige/`         | Scripts Python para interação e raspagem de dados via navegador web (Selenium WebDriver).     |
| [próximo Projeto]           | `./nome_nova_pasta/`  | [Descrição breve] |

---

## 💻 Configuração e Instalação (Selenium para obter contratos)

Para rodar os scripts localizados em `./Data_ige/`, siga os passos abaixo para configurar o ambiente Python.

### 1. Criar o Ambiente Conda
### Prerequisites
- Windows 10/11
- Google Chrome browser
- Anaconda or Miniconda

Conda foi usado para isolar as dependências.

```bash
conda create --name ige python=3.11
conda activate ige

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/sjacuru/Data_ige.git
   cd contrato-analyzer
