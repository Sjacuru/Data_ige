
"""
TCMRio Contract Analysis Dashboard v2.0
=======================================
Streamlit interface for contract extraction and analysis.

Features:
- Folder statistics and overview
- Single file or batch extraction
- Real-time progress tracking
- Results viewer with filtering
- Export to Excel/JSON
- Contract type identification
"""

import pytesseract
import streamlit as st
import pandas as pd
import json
from pathlib import Path
from datetime import datetime
import subprocess
import time

try:
    from Contract_analisys.contract_extractor import (
        process_single_contract,
        process_all_contracts,
        export_to_excel,
        export_to_json,
        get_folder_stats,
        load_analysis_summary,
        identify_contract_types,
        TYPES_KEYWORDS,
    )
    EXTRACTOR_LOADED = True
except ImportError as e:
    EXTRACTOR_LOADED = False
    IMPORT_ERROR = str(e)

# Conformity module (NEW)
try:
    from conformity.models.conformity_result import ConformityStatus
    CONFORMITY_LOADED = True
except ImportError:
    CONFORMITY_LOADED = False
    ConformityStatus = None

# ============================================================
# CONFIGURATION
# ============================================================

from config import (
    PROCESSOS_DIR,
    ANALYSIS_SUMMARY_CSV,
    EXTRACTIONS_DIR
)

PDF_FOLDER = PROCESSOS_DIR
CSV_PATH = ANALYSIS_SUMMARY_CSV
OUTPUT_FOLDER = EXTRACTIONS_DIR
OUTPUT_DIR = Path("data/extractions")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

st.set_page_config(
    page_title="Análise de Contratos - Processo.rio",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================================
# SESSION STATE INITIALIZATION
# ============================================================

try:
    result = subprocess.run(
        [pytesseract.pytesseract.tesseract_cmd, "--version"],
        capture_output=True,
        text=True
    )
    st.success("Tesseract detected")
    st.text(result.stdout.splitlines()[0])
except Exception as e:
    st.error("Tesseract NOT available")
    st.exception(e)

if "results" not in st.session_state:
    st.session_state.results = []
if "processing" not in st.session_state:
    st.session_state.processing = False
if "last_export" not in st.session_state:
    st.session_state.last_export = None

st.sidebar.markdown("### Debug paths")
st.sidebar.code(f"""
PDF_FOLDER = {PDF_FOLDER}
CSV_PATH = {CSV_PATH }
OUTPUT_FOLDER = {OUTPUT_FOLDER}
""")

# ============================================================
# HELPER FUNCTIONS
# ============================================================

def format_file_size(size_mb: float) -> str:
    """Format file size for display."""
    if size_mb < 1:
        return f"{size_mb * 1024:.0f} KB"
    return f"{size_mb:.2f} MB"


def get_status_emoji(success: bool) -> str:
    """Get status emoji based on success."""
    return "✅" if success else "❌"


def format_currency(value: str) -> str:
    """Format currency value for display."""
    if not value:
        return "N/A"
    return value


def create_results_dataframe(results: list) -> pd.DataFrame:
    """Convert results list to a DataFrame for display."""
    if not results:
        return pd.DataFrame()
    
    rows = []
    for r in results:
        data = r.get("extracted_data", {})
        types_info = r.get("type_analysis", {})
        csv_match = r.get("csv_match", {})
        conformity = r.get("conformity", {})
        
        rows.append({
            "Status": get_status_emoji(r.get("success", False)),
            "Arquivo": r.get("file_name", ""),
            "Processo": r.get("processo_id", "") or data.get("processo_administrativo", "") or "N/A",
            "Valor": format_currency(data.get("valor_contrato")),
            "Contratada": data.get("contratada", "N/A") or "N/A",
            "Tipo": data.get("tipo_contrato", "N/A") or "N/A",
            "Tipos Identificados": types_info.get("primary_type", "N/A"),
            "Conformidade": get_conformity_badge(conformity) if conformity else "⏳ Pendente",  # NEW
            "Páginas": r.get("total_pages", 0),
            "CSV Match": "✅" if csv_match.get("matched") else "❌",
            "Erro": r.get("error", "") or "",
        })
    
    return pd.DataFrame(rows)

def get_conformity_badge(conformity_data: dict) -> str:
    """
    Get conformity status badge.
    
    Returns emoji + status text.
    """
    if not conformity_data:
        return "⏳ Pendente"
    
    if conformity_data.get("error"):
        return "⚠️ Erro"
    
    status = conformity_data.get("overall_status", "")
    
    if status == "CONFORME":
        return "✅ Conforme"
    elif status == "PARCIAL":
        return "⚠️ Parcial"
    elif status == "NÃO CONFORME":
        return "❌ Não Conforme"
    else:
        return "❓ Desconhecido"


def get_conformity_color(status: str) -> str:
    """Get color for conformity status."""
    if "CONFORME" in status and "NÃO" not in status:
        return "green"
    elif "PARCIAL" in status:
        return "orange"
    elif "NÃO CONFORME" in status:
        return "red"
    else:
        return "gray"

def render_conformity_badge(conformity_data: dict):
    """Render a conformity status badge."""
    if not conformity_data:
        st.info("⏳ Verificação de conformidade pendente")
        return
    
    if conformity_data.get("error"):
        st.warning(f"⚠️ Erro na verificação: {conformity_data.get('error')}")
        return
    
    status = conformity_data.get("overall_status", "DESCONHECIDO")
    score = conformity_data.get("conformity_score", 0)
    
    # Status badge
    if status == "CONFORME":
        st.success(f"✅ **CONFORME** — Score: {score:.0f}%")
    elif status == "PARCIAL":
        st.warning(f"⚠️ **PARCIAL** — Score: {score:.0f}%")
    else:
        st.error(f"❌ **NÃO CONFORME** — Score: {score:.0f}%")
    
    # Publication info
    pub_check = conformity_data.get("publication_check", {})
    if pub_check:
        if pub_check.get("was_published"):
            pub_date = pub_check.get("publication_date", "N/A")
            link = pub_check.get("download_link", "")
            
            col1, col2 = st.columns([3, 1])
            with col1:
                st.caption(f"📰 Publicado em: {pub_date}")
                if pub_check.get("published_on_time"):
                    st.caption(f"✓ Dentro do prazo ({pub_check.get('days_to_publish')} dias)")
                else:
                    st.caption(f"✗ Fora do prazo ({pub_check.get('days_to_publish')} dias)")
            with col2:
                if link:
                    st.link_button("🔗 Ver D.O.", link)
        else:
            st.caption("📰 Publicação não encontrada no D.O. Rio")


# ============================================================
# UI COMPONENTS
# ============================================================

def render_header():
    """Render the page header."""
    st.title("📄 TCMRio - Análise de Contratos")
    st.markdown("Sistema de extração e análise de contratos públicos")
    
    if not EXTRACTOR_LOADED:
        st.error(f"""
        ❌ **Erro ao carregar o módulo contract_extractor**
        
        ```
        {IMPORT_ERROR}
        ```
        
        Verifique se o arquivo `Contract_analisys/contract_extractor.py` existe e está correto.
        """)
        st.stop()


def render_sidebar():
    """Render the sidebar with folder stats and settings."""
    with st.sidebar:
        st.header("📂 Configuração")
        
        # Folder stats
        st.subheader("Status das Pastas")
        
        stats = get_folder_stats(str(PDF_FOLDER))
        
        if stats["exists"]:
            col1, col2 = st.columns(2)
            with col1:
                st.metric("PDFs", stats["total_files"])
            with col2:
                st.metric("Tamanho", format_file_size(stats["total_size_mb"]))
            
            if stats["total_files"] == 0:
                st.warning("Nenhum PDF encontrado na pasta")
        else:
            st.error(f"Pasta não encontrada: {PDF_FOLDER}")
        
        st.divider()
        
        # CSV stats
        st.subheader("Dados de Referência")
        summary_df = load_analysis_summary(str(CSV_PATH))
        
        if not summary_df.empty:
            st.success(f"✅ {len(summary_df)} registros carregados")
            
            with st.expander("Ver colunas"):
                st.write(list(summary_df.columns))
        else:
            st.warning("CSV não carregado ou vazio")
        
        st.divider()
        
        # Types keywords info
        st.subheader("Tipos de Contrato")
        with st.expander("Ver palavras-chave"):
            for category, keywords in TYPES_KEYWORDS.items():
                st.markdown(f"**{category.title()}:**")
                st.caption(", ".join(keywords[:5]) + "...")
        
        st.divider()
        
        # Session info
        if st.session_state.results:
            st.subheader("📊 Sessão Atual")
            total = len(st.session_state.results)
            success = sum(1 for r in st.session_state.results if r.get("success"))
            st.write(f"Processados: {total}")
            st.write(f"Sucesso: {success}")
            st.write(f"Erros: {total - success}")
            
            if st.button("🗑️ Limpar Resultados", use_container_width=True):
                st.session_state.results = []
                st.rerun()
        
        return stats, summary_df


def render_single_file_tab(stats: dict):
    """Render the single file processing tab."""
    st.header("📄 Processar Arquivo Individual")
    
    if not stats["exists"] or stats["total_files"] == 0:
        st.warning("Nenhum arquivo PDF disponível para processamento.")
        return
    
    # File selector
    selected_file = st.selectbox(
        "Selecione um arquivo PDF:",
        options=stats["files"],
        format_func=lambda x: f"📄 {x}"
    )
    
    col1, col2 = st.columns([1, 3])
    
    with col1:
        process_button = st.button(
            "🔍 Processar",
            type="primary",
            use_container_width=True,
            disabled=st.session_state.processing
        )
    
    if process_button and selected_file:
        st.session_state.processing = True
        
        with st.spinner(f"Processando {selected_file}..."):
            pdf_path = PDF_FOLDER / selected_file
            
            # Progress steps
            progress = st.progress(0)
            status = st.empty()
            
            # Step 1: Extract text
            status.text("📖 Extraindo texto do PDF...")
            progress.progress(25)
            time.sleep(0.3)
            
            # Step 2: Process contract
            status.text("🤖 Analisando com IA...")
            progress.progress(50)
            
            result = process_single_contract(str(pdf_path))
            
            progress.progress(100)
            status.text("✅ Concluído!")
            time.sleep(0.5)
            status.empty()
            progress.empty()
        
        st.session_state.processing = False
        
        # Display results
        with st.expander("📄 Texto extraído (debug)"):
            st.text(result.get("full_text", "")[:5000])  # Limit to 5000 chars
        
        if result["success"]:
            st.success(f"✅ Arquivo processado com sucesso!")
            
            # Add to session results
            st.session_state.results.append(result)
            
            # Display extracted data
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("📋 Dados Extraídos")
                data = result.get("extracted_data", {})
                
                st.markdown(f"""
                | Campo | Valor |
                |-------|-------|
                | **Valor** | {data.get('valor_contrato', 'N/A')} |
                | **Contratante** | {data.get('contratante', 'N/A')} |
                | **Contratada** | {data.get('contratada', 'N/A')} |
                | **Objeto** | {(str(data.get('objeto')) if data.get('objeto') is not None else 'N/A')[:100] + ('...' if len(str(data.get('objeto')) if data.get('objeto') is not None else 'N/A') > 100 else '')} |
                | **Tipo** | {data.get('tipo_contrato', 'N/A')} |
                | **Modalidade** | {data.get('modalidade_licitacao', 'N/A')} |
                | **Vigência** | {data.get('vigencia_meses', 'N/A')} meses |
                """)
            
            with col2:
                st.subheader("📊 Metadados")
                st.markdown(f"""
                - **Páginas:** {result.get('total_pages', 0)}
                - **Parágrafos:** {result.get('paragraph_count', 0)}
                - **Processo ID:** {result.get('processo_id', 'N/A') or 'N/A'}
                """)
                
                st.divider()
                st.subheader("🔍 Verificação de Conformidade")
                
                conformity = result.get("conformity")
                if conformity:
                    render_conformity_badge(conformity)
                    
                    # Detailed checks expander
                    with st.expander("Ver detalhes da verificação"):
                        field_checks = conformity.get("field_checks", [])
                        if field_checks:
                            for check in field_checks:
                                status_icon = "✓" if check.get("status") == "APROVADO" else "✗" if check.get("status") == "REPROVADO" else "◐"
                                match_pct = check.get("match_percentage", 0)
                                st.markdown(f"{status_icon} **{check.get('field_label')}**: {check.get('match_level')} ({match_pct:.0f}%)")
                                
                                col1, col2 = st.columns(2)
                                with col1:
                                    st.caption(f"Contrato: {check.get('contract_value', 'N/A')}")
                                with col2:
                                    st.caption(f"Publicação: {check.get('publication_value', 'N/A')}")
                        else:
                            st.caption("Nenhuma verificação de campo disponível")
                else:
                    st.info("Verificação de conformidade não realizada ou não disponível")

                # Types analysis
                types_info = result.get("type_analysis", {})
                if types_info:
                    st.markdown(f"- **Tipo Principal:** {types_info.get('primary_type', 'N/A')}")
                    if types_info.get("types_found"):
                        st.markdown(f"- **Tipos encontrados:** {', '.join(types_info.get('types_found', []))}")
            
            # Full JSON expander
            with st.expander("🔍 Ver JSON completo"):
                display_data = {k: v for k, v in result.items() if k != "full_text"}
                display_data["text_preview"] = result.get("full_text", "")[:500] + "..."
                st.json(display_data)
        
        else:
            st.error(f"❌ Erro ao processar: {result.get('error', 'Erro desconhecido')}")
            
            with st.expander("Ver detalhes do erro"):
                st.json({
                    "error": result.get("error"),
                    "error_stage": result.get("error_stage"),
                    "file_name": result.get("file_name")
                })


def render_batch_tab(stats: dict):
    """Render the batch processing tab."""
    st.header("📦 Processamento em Lote")
    
    if not stats["exists"] or stats["total_files"] == 0:
        st.warning("Nenhum arquivo PDF disponível para processamento.")
        return
    
    st.info(f"📂 **{stats['total_files']}** arquivos PDF disponíveis ({format_file_size(stats['total_size_mb'])})")
    
    # Options
    col1, col2, col3 = st.columns(3)
    
    with col1:
        limit = st.number_input(
            "Limite de arquivos (0 = todos)",
            min_value=0,
            max_value=stats["total_files"],
            value=0
        )
    
    with col2:
        export_excel = st.checkbox("Exportar Excel", value=True)
    
    with col3:
        export_json = st.checkbox("Exportar JSON", value=True)
    
    # Start button
    if st.button(
        "🚀 Iniciar Processamento",
        type="primary",
        disabled=st.session_state.processing,
        use_container_width=True
    ):
        st.session_state.processing = True
        
        # Progress elements
        progress_bar = st.progress(0)
        status_text = st.empty()
        results_container = st.empty()
        
        # Files to process
        files_to_process = stats["files"][:limit] if limit > 0 else stats["files"]
        total = len(files_to_process)
        
        results = []
        
        for i, file_name in enumerate(files_to_process):
            status_text.text(f"🔄 Processando [{i+1}/{total}]: {file_name}")
            
            pdf_path = PDF_FOLDER / file_name
            result = process_single_contract(str(pdf_path))
            results.append(result)
            
            # Update progress
            progress_bar.progress((i + 1) / total)
            
            # Show live results
            with results_container.container():
                df = create_results_dataframe(results)
                st.dataframe(df, use_container_width=True, hide_index=True)
        
        progress_bar.progress(1.0)
        status_text.text("✅ Processamento concluído!")
        
        # Store results
        st.session_state.results = results
        
        # Export
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        exports = []
        
        if export_excel:
            excel_path = OUTPUT_DIR / f"contracts_{timestamp}.xlsx"
            export_to_excel(results, str(excel_path))
            exports.append(f"📊 Excel: `{excel_path}`")
        
        if export_json:
            json_path = OUTPUT_DIR / f"contracts_{timestamp}.json"
            export_to_json(results, str(json_path))
            exports.append(f"📄 JSON: `{json_path}`")
        
        if exports:
            st.success("Arquivos exportados:\n" + "\n".join(exports))
            st.session_state.last_export = timestamp
        
        st.session_state.processing = False
        
        # Summary
        success_count = sum(1 for r in results if r.get("success"))
        st.markdown(f"""
        ### 📊 Resumo
        - **Total processados:** {len(results)}
        - **Sucesso:** {success_count} ✅
        - **Erros:** {len(results) - success_count} ❌
        """)


def render_results_tab():
    """Render the results viewer tab."""
    st.header("📊 Visualizar Resultados")
    
    if not st.session_state.results:
        st.info("Nenhum resultado disponível. Processe alguns contratos primeiro.")
        
        # Option to load from file
        st.subheader("📂 Carregar resultados salvos")
        
        json_files = list(OUTPUT_DIR.glob("contracts_*.json"))
        
        if json_files:
            selected_json = st.selectbox(
                "Selecione um arquivo de resultados:",
                options=sorted(json_files, reverse=True),
                format_func=lambda x: x.name
            )
            
            if st.button("📥 Carregar"):
                with open(selected_json, 'r', encoding='utf-8') as f:
                    st.session_state.results = json.load(f)
                st.success(f"Carregados {len(st.session_state.results)} resultados")
                st.rerun()
        else:
            st.caption("Nenhum arquivo de resultados encontrado.")
        
        return
    
    # Results DataFrame
    df = create_results_dataframe(st.session_state.results)
    
    # Filters
    st.subheader("🔍 Filtros")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        status_filter = st.selectbox(
            "Status",
            options=["Todos", "✅ Sucesso", "❌ Erro"]
        )
    
    with col2:
        type_options = ["Todos"] + df["Tipo"].dropna().unique().tolist()
        type_filter = st.selectbox("Tipo de Contrato", options=type_options)
    
    with col3:
        search_text = st.text_input("🔎 Buscar", placeholder="Nome do arquivo ou empresa...")
    
    # Apply filters
    filtered_df = df.copy()
    
    if status_filter == "✅ Sucesso":
        filtered_df = filtered_df[filtered_df["Status"] == "✅"]
    elif status_filter == "❌ Erro":
        filtered_df = filtered_df[filtered_df["Status"] == "❌"]
    
    if type_filter != "Todos":
        filtered_df = filtered_df[filtered_df["Tipo"] == type_filter]
    
    if search_text:
        mask = (
            filtered_df["Arquivo"].str.contains(search_text, case=False, na=False) |
            filtered_df["Contratada"].str.contains(search_text, case=False, na=False)
        )
        filtered_df = filtered_df[mask]
    
    # Display
    st.subheader(f"📋 Resultados ({len(filtered_df)} de {len(df)})")
    
    st.dataframe(
        filtered_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Status": st.column_config.TextColumn(width="small"),
            "Valor": st.column_config.TextColumn(width="medium"),
            "Objeto": st.column_config.TextColumn(width="large"),
        }
    )
    
    # Export buttons
    st.subheader("📤 Exportar")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("📊 Exportar Excel", use_container_width=True):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            excel_path = OUTPUT_DIR / f"contracts_{timestamp}.xlsx"
            export_to_excel(st.session_state.results, str(excel_path))
            st.success(f"Exportado: {excel_path}")
    
    with col2:
        if st.button("📄 Exportar JSON", use_container_width=True):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            json_path = OUTPUT_DIR / f"contracts_{timestamp}.json"
            export_to_json(st.session_state.results, str(json_path))
            st.success(f"Exportado: {json_path}")
    
    with col3:
        # Download filtered as CSV
        csv_data = filtered_df.to_csv(index=False).encode('utf-8')
        st.download_button(
            "⬇️ Download CSV",
            data=csv_data,
            file_name=f"contracts_filtered_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
            use_container_width=True
        )
    
    # Detailed view
    st.subheader("🔍 Visualização Detalhada")
    
    file_options = [r.get("file_name", "") for r in st.session_state.results]
    selected_detail = st.selectbox("Selecione um contrato para ver detalhes:", file_options)
    
    if selected_detail:
        result = next((r for r in st.session_state.results if r.get("file_name") == selected_detail), None)
        
        if result:
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("**Dados Extraídos**")
                data = result.get("extracted_data", {})
                st.json(data)
            
            with col2:
                st.markdown("**Análise de Tipos**")
                types_info = result.get("type_analysis", {})
                if types_info:
                    st.json(types_info)
                else:
                    st.caption("Não disponível")
                
                st.markdown("**Match CSV**")
                csv_match = result.get("csv_match", {})
                st.json(csv_match)


def render_help_tab():
    """Render the help/documentation tab."""
    st.header("❓ Ajuda e Documentação")
    
    st.markdown("""
    ## 📖 Como usar o sistema
    
    ### 1. Preparar os dados
    
    1. Coloque os PDFs de contratos na pasta `data/downloads/processos/`
    2. (Opcional) Tenha o arquivo `data/outputs/analysis_summary.csv` com dados de referência
    
    ### 2. Processar contratos
    
    **Arquivo Individual:**
    - Vá para a aba "📄 Arquivo Individual"
    - Selecione um PDF e clique em "Processar"
    
    **Lote:**
    - Vá para a aba "📦 Processamento em Lote"
    - Configure as opções e clique em "Iniciar"
    
    ### 3. Visualizar resultados
    
    - Vá para a aba "📊 Resultados"
    - Use os filtros para encontrar contratos específicos
    - Exporte para Excel, JSON ou CSV
    
    ---
    
    ## 🔧 Configuração
    
    ### Variáveis de Ambiente
    
    Crie um arquivo `.env` na raiz do projeto:
    
    ```
    GROQ_API_KEY=sua_chave_api_aqui
    ```
    
    ### Estrutura de Pastas
    
    ```
    Data_ige/
    ├── data/
    │   ├── downloads/processos/    ← PDFs aqui
    │   ├── outputs/                ← CSV de referência
    │   └── extractions/            ← Resultados exportados
    ├── Contract_analisys/
    │   └── contract_extractor.py
    └── app.py
    ```
    
    ---
    
    ## 📊 Dados Extraídos
    
    O sistema extrai automaticamente:
    
    | Campo | Descrição |
    |-------|-----------|
    | `valor_contrato` | Valor total do contrato |
    | `contratante` | Órgão contratante |
    | `contratada` | Empresa contratada |
    | `objeto` | Descrição do objeto |
    | `tipo_contrato` | Tipo (Serviços, Fornecimento, etc) |
    | `vigencia_meses` | Período de vigência |
    | `modalidade_licitacao` | Modalidade usada |
    
    ---
    
    ## ⚠️ Solução de Problemas
    
    **Erro de API Key:**
    - Verifique se o arquivo `.env` existe
    - Confirme que a chave GROQ_API_KEY está correta
    
    **Erro de Rate Limit:**
    - O sistema tenta novamente automaticamente
    - Aguarde alguns segundos entre processamentos
    
    **PDF não processado:**
    - Verifique se o PDF não está corrompido
    - Alguns PDFs escaneados podem não ter texto extraível
    """)


# ============================================================
# MAIN APP
# ============================================================

def main():
    """Main application entry point."""
    render_header()
    stats, summary_df = render_sidebar()
    
    # Main tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📄 Arquivo Individual",
        "📦 Processamento em Lote",
        "📊 Resultados",
        "🔍 Conformidade", 
        "❓ Ajuda"
    ])
    
    with tab1:
        render_single_file_tab(stats)
    
    with tab2:
        render_batch_tab(stats)
    
    with tab3:
        render_results_tab()
    
    with tab4:
        render_conformity_tab() 
    
    with tab5:
        render_help_tab()

def render_conformity_tab():
    """Render the conformity analysis tab."""
    st.header("🔍 Análise de Conformidade")
    
    st.markdown("""
    Esta aba mostra o resultado da verificação de conformidade dos contratos.
    
    A verificação é executada **automaticamente** após a extração de cada contrato e inclui:
    - ✅ Verificação de publicação no D.O. Rio
    - ✅ Verificação do prazo de publicação (20 dias)
    - ✅ Comparação dos dados do contrato com a publicação
    """)
    
    st.divider()
    
    # Check if we have results
    if not st.session_state.results:
        st.info("Nenhum resultado disponível. Processe alguns contratos primeiro.")
        return
    
    # Filter results with conformity data
    results_with_conformity = [
        r for r in st.session_state.results 
        if r.get("conformity") and not r.get("conformity", {}).get("error")
    ]
    
    results_without_conformity = [
        r for r in st.session_state.results 
        if not r.get("conformity") or r.get("conformity", {}).get("error")
    ]
    
    # Summary metrics
    st.subheader("📊 Resumo")
    
    col1, col2, col3, col4 = st.columns(4)
    
    total = len(st.session_state.results)
    verified = len(results_with_conformity)
    
    conforme = sum(1 for r in results_with_conformity 
                   if r.get("conformity", {}).get("overall_status") == "CONFORME")
    parcial = sum(1 for r in results_with_conformity 
                  if r.get("conformity", {}).get("overall_status") == "PARCIAL")
    nao_conforme = sum(1 for r in results_with_conformity 
                       if r.get("conformity", {}).get("overall_status") == "NÃO CONFORME")
    
    with col1:
        st.metric("Total Contratos", total)
    with col2:
        st.metric("✅ Conforme", conforme)
    with col3:
        st.metric("⚠️ Parcial", parcial)
    with col4:
        st.metric("❌ Não Conforme", nao_conforme)
    
    # Pending verification info
    if results_without_conformity:
        st.warning(f"⏳ {len(results_without_conformity)} contrato(s) aguardando verificação ou com erro")
    
    st.divider()
    
    # Detailed results
    st.subheader("📋 Resultados Detalhados")
    
    # Status filter
    status_filter = st.selectbox(
        "Filtrar por status",
        ["Todos", "✅ Conforme", "⚠️ Parcial", "❌ Não Conforme", "⏳ Pendente"]
    )
    
    # Build filtered list
    filtered_results = []
    
    for r in st.session_state.results:
        conformity = r.get("conformity", {})
        status = conformity.get("overall_status", "") if conformity else ""
        
        if status_filter == "Todos":
            filtered_results.append(r)
        elif status_filter == "✅ Conforme" and status == "CONFORME":
            filtered_results.append(r)
        elif status_filter == "⚠️ Parcial" and status == "PARCIAL":
            filtered_results.append(r)
        elif status_filter == "❌ Não Conforme" and status == "NÃO CONFORME":
            filtered_results.append(r)
        elif status_filter == "⏳ Pendente" and not status:
            filtered_results.append(r)
    
    st.caption(f"Mostrando {len(filtered_results)} de {total} contratos")
    
    # Display each result
    for r in filtered_results:
        file_name = r.get("file_name", "Arquivo desconhecido")
        processo = r.get("processo_id", "") or r.get("extracted_data", {}).get("processo_administrativo", "N/A")
        conformity = r.get("conformity", {})
        
        # Get status for header
        if conformity and not conformity.get("error"):
            status = conformity.get("overall_status", "DESCONHECIDO")
            score = conformity.get("conformity_score", 0)
            
            if status == "CONFORME":
                icon = "✅"
            elif status == "PARCIAL":
                icon = "⚠️"
            else:
                icon = "❌"
            
            header = f"{icon} {file_name} — {status} ({score:.0f}%)"
        else:
            header = f"⏳ {file_name} — Pendente"
        
        with st.expander(header):
            col1, col2 = st.columns([2, 1])
            
            with col1:
                st.markdown(f"**Processo:** {processo}")
                
                # Contract data
                data = r.get("extracted_data", {})
                st.markdown(f"**Valor:** {data.get('valor_contrato', 'N/A')}")
                st.markdown(f"**Contratada:** {data.get('contratada', 'N/A')}")
            
            with col2:
                if conformity and not conformity.get("error"):
                    pub = conformity.get("publication_check", {})
                    if pub and pub.get("was_published"):
                        st.markdown(f"**Publicado em:** {pub.get('publication_date', 'N/A')}")
                        st.markdown(f"**Edição:** {pub.get('edition_number', 'N/A')}")
                        if pub.get("download_link"):
                            st.link_button("🔗 Ver no D.O.", pub.get("download_link"))
                    else:
                        st.warning("Publicação não encontrada")
            
            # Field checks
            if conformity and conformity.get("field_checks"):
                st.markdown("---")
                st.markdown("**Verificações:**")
                
                checks_df = []
                for check in conformity.get("field_checks", []):
                    checks_df.append({
                        "Campo": check.get("field_label", ""),
                        "Status": "✓" if check.get("status") == "APROVADO" else "✗",
                        "Match": f"{check.get('match_percentage', 0):.0f}%",
                        "Nível": check.get("match_level", ""),
                    })
                
                if checks_df:
                    st.dataframe(
                        pd.DataFrame(checks_df),
                        use_container_width=True,
                        hide_index=True
                    )
    
    st.divider()
    
    # Export conformity report
    st.subheader("📤 Exportar Relatório")
    
    if st.button("📊 Exportar Relatório de Conformidade", use_container_width=True):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Build report data
        report_rows = []
        for r in st.session_state.results:
            conformity = r.get("conformity", {})
            data = r.get("extracted_data", {})
            pub = conformity.get("publication_check", {}) if conformity else {}
            
            report_rows.append({
                "Arquivo": r.get("file_name", ""),
                "Processo": r.get("processo_id", "") or data.get("processo_administrativo", ""),
                "Status_Extração": "OK" if r.get("success") else "ERRO",
                "Status_Conformidade": conformity.get("overall_status", "PENDENTE") if conformity else "PENDENTE",
                "Score": conformity.get("conformity_score", 0) if conformity else 0,
                "Publicado": "SIM" if pub.get("was_published") else "NÃO",
                "Data_Publicação": pub.get("publication_date", ""),
                "Prazo_OK": "SIM" if pub.get("published_on_time") else "NÃO",
                "Dias_Para_Publicar": pub.get("days_to_publish", ""),
                "Link_DO": pub.get("download_link", ""),
                "Valor_Contrato": data.get("valor_contrato", ""),
                "Contratada": data.get("contratada", ""),
            })
        
        report_df = pd.DataFrame(report_rows)
        
        # Save Excel
        excel_path = OUTPUT_DIR / f"conformity_report_{timestamp}.xlsx"
        report_df.to_excel(excel_path, index=False)
        
        st.success(f"✅ Relatório exportado: {excel_path}")
        
        # Download button
        csv_data = report_df.to_csv(index=False).encode('utf-8')
        st.download_button(
            "⬇️ Download CSV",
            data=csv_data,
            file_name=f"conformity_report_{timestamp}.csv",
            mime="text/csv"
        )

if __name__ == "__main__":
    main()