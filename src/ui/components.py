
import streamlit as st
import pandas as pd
from pathlib import Path
from datetime import datetime
import time

from src.ui.utils import (
    format_file_size, get_status_emoji, format_currency, 
    get_conformity_badge, get_conformity_color, get_processos_files,
    add_audit_log
)
from src.ui.logic import compare_data_sources, run_conformity_check_logic, run_single_extraction_logic
from Contract_analisys.contract_extractor import (
    process_single_contract, export_to_excel, export_to_json, get_folder_stats, TYPES_KEYWORDS
)

# Constants from config
from config import PROCESSOS_DIR, ANALYSIS_SUMMARY_CSV, EXTRACTIONS_DIR, FILTER_YEAR

def render_header():
    """Render the page header."""
    st.title("📄 TCMRio - Análise de Contratos")
    st.markdown("Sistema de extração e análise de contratos públicos")

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
    
    if status == "CONFORME":
        st.success(f"✅ **CONFORME** — Score: {score:.0f}%")
    elif status == "PARCIAL":
        st.warning(f"⚠️ **PARCIAL** — Score: {score:.0f}%")
    else:
        st.error(f"❌ **NÃO CONFORME** — Score: {score:.0f}%")
    
    pub_check = conformity_data.get("publication_check", {})
    if pub_check and pub_check.get("was_published"):
        st.caption(f"📰 Publicado em: {pub_check.get('publication_date', 'N/A')}")
        if pub_check.get("download_link"):
            st.link_button("🔗 Ver D.O.", pub_check.get("download_link"))

def render_scraping_section(scraper_loaded, scraper_error, driver_available):
    """Render the data collection section in sidebar."""
    st.subheader("🔄 Coleta de Dados")
    if not scraper_loaded:
        st.error("Módulo scraper não disponível")
        return
    if not driver_available:
        st.warning("Chrome não detectado")
        return
    
    year = st.number_input("Ano para filtrar", 2020, 2030, FILTER_YEAR or 2025, key="sidebar_scraping_year")
    headless = st.checkbox("Modo invisível", False, key="sidebar_scraping_headless")
    
    if st.button("🚀 Iniciar Scraping", type="primary", use_container_width=True, key="sidebar_start_scraping"):
        st.session_state.scraping_in_progress = True
        st.session_state.scraping_trigger = True
        st.session_state.scraping_year = year
        st.session_state.scraping_headless = headless
        st.rerun()

def render_download_csv_section(download_csv_loaded, driver_available):
    """Render the CSV download section in sidebar."""
    st.subheader("📥 Download CSV (Portal)")
    if not download_csv_loaded:
        st.error("Módulo download_csv não disponível")
        return
    if not driver_available:
        st.warning("Chrome não detectado")
        return
    
    year = st.number_input("Ano para download", 2020, 2030, FILTER_YEAR or 2025, key="sidebar_csv_year")
    headless = st.checkbox("Modo invisível", False, key="sidebar_csv_headless")
    
    if st.button("📥 Baixar CSV", type="secondary", use_container_width=True, key="sidebar_start_csv"):
        st.session_state.csv_download_in_progress = True
        st.session_state.csv_download_trigger = True
        st.session_state.csv_download_year = year
        st.session_state.csv_download_headless = headless
        st.rerun()

def render_compare_section():
    """Render the comparison section in sidebar."""
    st.subheader("🔄 Comparar Quantidades")
    scraped_file = Path("data/outputs/favorecidos_latest.csv")
    portal_file = Path("data/outputs/contasrio_latest.csv")
    
    if st.button("🔄 Comparar", type="secondary", use_container_width=True):
        if scraped_file.exists() and portal_file.exists():
            st.session_state.comparison_result = compare_data_sources(scraped_file, portal_file)
        else:
            st.warning("Arquivos necessários não encontrados")
        st.rerun()
    
    if st.session_state.comparison_result:
        res = st.session_state.comparison_result
        if res.get("success"):
            st.metric("Scraped", res["scraped_count"])
            st.metric("Portal", res["portal_count"])
            st.metric("Match", res["matched_count"])
        else:
            st.error(res.get("error"))

def render_download_contracts_section(driver_available):
    """Render the download contracts section in sidebar."""
    st.subheader("📥 Download Contratos")
    if not driver_available:
        st.warning("Chrome não detectado")
        return
    
    files = get_processos_files()
    if not files:
        st.warning("Nenhum arquivo de processos")
        return
    
    selected_file = st.selectbox("Arquivo de processos", files, format_func=lambda x: x.name)
    max_d = st.number_input("Limite (0=todos)", 0, 1000, 0)
    headless = st.checkbox("Modo invisível", False, key="sidebar_contracts_headless")
    
    if st.button("📥 Baixar PDFs", use_container_width=True):
        st.session_state.contracts_download_in_progress = True
        st.session_state.contracts_download_trigger = True
        st.session_state.contracts_selected_file = selected_file
        st.session_state.contracts_max = max_d if max_d > 0 else None
        st.session_state.contracts_headless = headless
        st.rerun()

def render_sidebar(extractor_loaded, scraper_loaded, scraper_error, download_csv_loaded, driver_available, summary_df):
    """Render the sidebar."""
    with st.sidebar:
        st.header("📂 Configuração")
        stats = get_folder_stats(str(PROCESSOS_DIR))
        if stats["exists"]:
            st.metric("PDFs", stats["total_files"])
            st.metric("Tamanho", format_file_size(stats["total_size_mb"]))
        
        st.divider()
        render_scraping_section(scraper_loaded, scraper_error, driver_available)
        st.divider()
        render_download_csv_section(download_csv_loaded, driver_available)
        st.divider()
        render_compare_section()
        st.divider()
        render_download_contracts_section(driver_available)
        st.divider()
        
        if st.session_state.results:
            if st.button("🗑️ Limpar Resultados", use_container_width=True):
                st.session_state.results = []
                st.rerun()
    return stats

def render_conformity_details(conf):
    """Visualizes the rich conformity data from the D.O. Rio."""
    if not conf:
        st.warning("Dados de conformidade não encontrados.")
        return
        
    st.subheader("🛡️ Resultado da Verificação de Conformidade")
    
    # Summary Metrics
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Status Geral", conf.get("overall_status", "N/A"))
    with col2:
        st.metric("Score de Batimento", f"{conf.get('conformity_score', 0)}%")
    with col3:
        pub = conf.get("publication_check", {})
        status = pub.get("status", "PENDENTE")
        color = "green" if status == "APROVADO" else "red"
        st.markdown(f"**Prazo Legal:** :{color}[{status}]")

    # Comparison Table
    st.markdown("### 🔍 Batimento de Campos")
    fields = conf.get("field_checks", [])
    if fields:
        df_fields = pd.DataFrame(fields)
        # Select and rename columns for a better UI experience
        ui_df = df_fields[["field_label", "contract_value", "publication_value", "status"]]
        ui_df.columns = ["Campo", "No Contrato", "No Diário Oficial", "Status"]
        st.table(ui_df)
    
    if pub.get("observation"):
        st.info(f"📝 **Observação:** {pub.get('observation')}")

def render_audit_logs():
    """Render the audit logs expander."""
    with st.expander("🕒 Logs de Auditoria", expanded=False):
        if not st.session_state.get("audit_logs"):
            st.caption("Nenhum log disponível.")
            return
            
        for log in reversed(st.session_state.audit_logs):
            color = "blue" if log["level"] == "info" else "red" if log["level"] == "error" else "green"
            st.markdown(f"**{log['timestamp']}** — :{color}[{log['message']}]")

def render_single_file_tab(stats):
    st.header("🎯 Processamento de Contrato")
    
    # Render logs at the top
    render_audit_logs()
    
    if not stats["files"]:
        st.warning("Nenhum PDF encontrado em data/downloads/processos.")
        return

    selected = st.selectbox("Selecione o PDF para análise:", stats["files"], key="proc_select")
    
    st.divider()
    
    # Mode Selection
    mode = st.radio("Escolha o modo de análise:", 
                    ["🚶 Passo a Passo (Auditor)", "⚡ Automático (One-Click)"], 
                    horizontal=True)

    if mode == "🚶 Passo a Passo (Auditor)":
        st.info("Siga os passos abaixo para verificar a inteligência do sistema.")
        c1, c2, c3 = st.columns(3)
        
        # STEP 1
        if c1.button("1. Extração AI", use_container_width=True):
            add_audit_log(f"Iniciando extração AI para {selected}")
            with st.status("IA Analisando PDF...") as s:
                res = run_single_extraction_logic(PROCESSOS_DIR / selected)
                st.session_state.current_extraction = res
                s.update(label="Extração Completa!", state="complete")
            add_audit_log(f"Extração concluída para {selected}")

        # STEP 2
        if c2.button("2. Checar D.O.", use_container_width=True):
            if "current_extraction" in st.session_state:
                add_audit_log(f"Iniciando busca no Diário Oficial para {selected}")
                with st.status("Buscando no Diário Oficial...") as s:
                    # Get the extracted data
                    contract_data = st.session_state.current_extraction.get("extracted_data", {})
                    # Run real conformity check
                    result = run_conformity_check_logic(contract_data, headless=True)
                    st.session_state.last_conformity_sample = result
                    st.session_state.show_conformity = True
                    s.update(label="Busca Concluída!", state="complete")
                
                status_val = result.get('overall_status', 'DESCONHECIDO')
                add_audit_log(f"Busca no D.O. concluída: {status_val}")
                st.toast("Verificação no Diário Oficial concluída!")
            else:
                st.error("Primeiro execute o Passo 1.")

        # STEP 3
        if c3.button("3. Veredito Final", use_container_width=True):
            if st.session_state.get("show_conformity"):
                add_audit_log(f"Veredito final gerado para {selected}")
                st.success("Relatório de Auditoria Gerado!")
            else:
                st.error("Execute os passos anteriores.")

        # Rendering Results based on clicks
        if st.session_state.get("current_extraction"):
            with st.expander("📄 Dados Extraídos do PDF (Passo 1)", expanded=True):
                st.json(st.session_state.current_extraction)
        
        if st.session_state.get("show_conformity"):
            # Using the JSON sample you provided as the visual output
            render_conformity_details(st.session_state.get("last_conformity_sample"))

    else: # AUTOMÁTICO
        if st.button("🚀 Iniciar Auditoria Completa", type="primary", use_container_width=True):
            add_audit_log(f"Iniciando auditoria automática para {selected}")
            with st.status("Executando Auditoria Ponta-a-Ponta...") as status:
                st.write("Lendo Contrato...")
                res = process_single_contract(str(PROCESSOS_DIR / selected))
                st.session_state.current_extraction = res
                
                st.write("Verificando Publicação no D.O. Rio...")
                contract_data = res.get("extracted_data", {})
                result = run_conformity_check_logic(contract_data, headless=True)
                st.session_state.last_conformity_sample = result
                st.session_state.show_conformity = True
                
                status.update(label="Auditoria Concluída!", state="complete")
            
            add_audit_log(f"Auditoria automática concluída para {selected}")
            render_conformity_details(st.session_state.get("last_conformity_sample"))

def render_batch_tab(stats):
    """Render batch processing tab."""
    st.header("📦 Processamento em Lote")
    
    render_audit_logs()
    
    limit = st.number_input("Limite", 0, stats["total_files"], 0)
    if st.button("🚀 Iniciar", type="primary"):
        st.session_state.processing = True
        files = stats["files"][:limit] if limit > 0 else stats["files"]
        add_audit_log(f"Iniciando processamento em lote de {len(files)} arquivos")
        results = []
        bar = st.progress(0)
        for i, f in enumerate(files):
            add_audit_log(f"Processando [{i+1}/{len(files)}]: {f}")
            results.append(process_single_contract(str(PROCESSOS_DIR / f)))
            bar.progress((i+1)/len(files))
        st.session_state.results = results
        st.session_state.processing = False
        add_audit_log(f"Processamento em lote concluído")
        st.success("Fim!")

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
            "Status": "✅" if r.get("success", False) else "❌",
            "Arquivo": r.get("file_name", ""),
            "Processo": r.get("processo_id", "") or data.get("processo_administrativo", "") or data.get("numero_processo", "") or "N/A",
            "Valor": data.get("valor_contrato", "N/A"),
            "Contratada": data.get("contratada", "N/A") or "N/A",
            "Tipo": data.get("tipo_contrato", "N/A") or "N/A",
            "Tipos Identificados": types_info.get("primary_type", "N/A"),
            "Conformidade": conformity.get("overall_status", "⏳ Pendente") if conformity else "⏳ Pendente",
            "Score Conf.": f"{conformity.get('conformity_score', 0):.0f}%" if conformity else "N/A",
            "Páginas": r.get("total_pages", 0),
            "CSV Match": "✅" if csv_match.get("matched") else "❌",
            "Erro": r.get("error", "") or "",
        })
    
    return pd.DataFrame(rows)

def render_results_tab():
    """Render the results viewer tab."""
    st.header("📊 Visualizar Resultados")
    
    if not st.session_state.results:
        st.info("Nenhum resultado disponível.")
        return
    
    df = create_results_dataframe(st.session_state.results)
    
    # Filters
    st.subheader("🔍 Filtros")
    col1, col2, col3 = st.columns(3)
    with col1:
        status_filter = st.selectbox("Status", options=["Todos", "✅ Sucesso", "❌ Erro"])
    with col2:
        type_options = ["Todos"] + df["Tipo"].dropna().unique().tolist()
        type_filter = st.selectbox("Tipo de Contrato", options=type_options)
    with col3:
        search_text = st.text_input("🔎 Buscar", placeholder="Nome do arquivo ou empresa...")
    
    # Apply filters
    filtered_df = df.copy()
    if status_filter == "✅ Sucesso": filtered_df = filtered_df[filtered_df["Status"] == "✅"]
    elif status_filter == "❌ Erro": filtered_df = filtered_df[filtered_df["Status"] == "❌"]
    if type_filter != "Todos": filtered_df = filtered_df[filtered_df["Tipo"] == type_filter]
    if search_text:
        mask = (filtered_df["Arquivo"].str.contains(search_text, case=False, na=False) |
                filtered_df["Contratada"].str.contains(search_text, case=False, na=False))
        filtered_df = filtered_df[mask]
    
    st.subheader(f"📋 Resultados ({len(filtered_df)} de {len(df)})")
    st.dataframe(filtered_df, use_container_width=True, hide_index=True)

    # Export Section
    st.divider()
    col_ex1, col_ex2, _ = st.columns([1, 1, 2])
    
    with col_ex1:
        if st.button("📊 Exportar para Excel", use_container_width=True):
            output_file = "extractions/resultados_export.xlsx"
            Path("extractions").mkdir(exist_ok=True)
            path = export_to_excel(st.session_state.results, output_file)
            st.success(f"Salvo em {path}")
            with open(path, "rb") as f:
                st.download_button("📥 Baixar Excel", f, file_name="resultados.xlsx")
                
    with col_ex2:
        if st.button("📝 Exportar para JSON", use_container_width=True):
            output_file = "extractions/resultados_export.json"
            Path("extractions").mkdir(exist_ok=True)
            path = export_to_json(st.session_state.results, output_file)
            st.success(f"Salvo em {path}")
            with open(path, "rb") as f:
                st.download_button("📥 Baixar JSON", f, file_name="resultados.json")

    # Details Section
    st.divider()
    st.subheader("🔍 Detalhes do Contrato")
    if not filtered_df.empty:
        selected_file = st.selectbox("Selecione um arquivo para ver detalhes:", filtered_df["Arquivo"].tolist())
        result_item = next((r for r in st.session_state.results if r.get("file_name") == selected_file), None)
        
        if result_item:
            col_d1, col_d2 = st.columns(2)
            data = result_item.get("extracted_data", {})
            
            with col_d1:
                st.markdown("### 📝 Dados Extraídos")
                # Filter out heavy data for display
                display_data = {k: v for k, v in data.items() if k not in ["clausulas_principais"]}
                for k, v in display_data.items():
                    st.text_input(k.replace("_", " ").title(), value=str(v), disabled=True)
                
                if data.get("clausulas_principais"):
                    with st.expander("Ver Cláusulas Principais"):
                        for c in data.get("clausulas_principais", []):
                            st.markdown(f"- {c}")
            
            with col_d2:
                st.markdown("### 🛡️ Conformidade")
                render_conformity_badge(result_item.get("conformity"))
                
                st.markdown("### 📂 Metadados")
                st.write(f"**Páginas:** {result_item.get('total_pages')}")
                st.write(f"**Tempo:** {result_item.get('processing_time', 0):.2f}s")
                
                if result_item.get("error"):
                    st.error(f"Erro: {result_item.get('error')}")

def render_conformity_tab():
    """Render the conformity analysis tab."""
    st.header("🔍 Análise de Conformidade")
    
    if not st.session_state.results:
        st.info("Nenhum resultado disponível. Processe alguns arquivos na aba 'Arquivo Individual' ou 'Processamento em Lote'.")
        return
    
    results_with_conformity = [r for r in st.session_state.results if r.get("conformity") and not r.get("conformity", {}).get("error")]
    
    # 1. Summary Metrics
    st.subheader("📊 Panorama Geral")
    col1, col2, col3, col4 = st.columns(4)
    
    total = len(st.session_state.results)
    conforme = sum(1 for r in results_with_conformity if r.get("conformity", {}).get("overall_status") == "CONFORME")
    parcial = sum(1 for r in results_with_conformity if r.get("conformity", {}).get("overall_status") == "PARCIAL")
    nao_conforme = sum(1 for r in results_with_conformity if r.get("conformity", {}).get("overall_status") == "NÃO CONFORME")
    pendente = total - len(results_with_conformity)
    
    col1.metric("Total", total)
    col2.metric("✅ Conforme", conforme)
    col3.metric("⚠️ Parcial", parcial)
    col4.metric("❌ Não Conforme", nao_conforme)
    
    # 2. Visual Heatmap (Health Chart)
    if results_with_conformity:
        st.subheader("🏥 Mapa de Saúde dos Contratos")
        
        # Prepare data for Altair
        chart_data = pd.DataFrame([
            {"Status": "Conforme", "Quantidade": conforme, "Cor": "#28a745"},
            {"Status": "Parcial", "Quantidade": parcial, "Cor": "#ffc107"},
            {"Status": "Não Conforme", "Quantidade": nao_conforme, "Cor": "#dc3545"},
            {"Status": "Pendente", "Quantidade": pendente, "Cor": "#6c757d"}
        ])
        
        import altair as alt
        
        chart = alt.Chart(chart_data).mark_bar().encode(
            x=alt.X('Status', sort=['Conforme', 'Parcial', 'Não Conforme', 'Pendente']),
            y='Quantidade',
            color=alt.Color('Status', scale=alt.Scale(
                domain=['Conforme', 'Parcial', 'Não Conforme', 'Pendente'],
                range=['#28a745', '#ffc107', '#dc3545', '#6c757d']
            )),
            tooltip=['Status', 'Quantidade']
        ).properties(height=300)
        
        st.altair_chart(chart, use_container_width=True)
        
    st.divider()
    
    # 3. Detailed List
    st.subheader("📋 Detalhamento por Processo")
    for r in st.session_state.results:
        conformity = r.get("conformity")
        file_name = r.get("file_name", "Desconhecido")
        
        if conformity:
            status = conformity.get("overall_status", "DESCONHECIDO")
            with st.expander(f"{file_name} — {status}"):
                render_conformity_details(conformity)
        else:
            with st.expander(f"{file_name} — ⏳ PENDENTE"):
                st.info("Este contrato ainda não passou pela verificação de conformidade.")
                if st.button(f"🔍 Verificar agora: {file_name}", key=f"verify_{file_name}"):
                    # Trigger verification
                    contract_data = r.get("extracted_data", {})
                    if contract_data:
                        with st.spinner("Buscando no D.O. Rio..."):
                            result = run_conformity_check_logic(contract_data)
                            r["conformity"] = result
                            st.rerun()
                    else:
                        st.error("Dados extraídos não encontrados para este arquivo.")


def render_help_tab():
    """Render help tab."""
    st.header("❓ Ajuda & Documentação")
    
    st.markdown("""
    ### 🚀 Como usar o Sistema
    
    1. **Coleta de Dados**: Use a barra lateral para coletar dados do portal de favorecidos (Scraping).
    2. **Download de CSV**: Baixe a lista oficial de contratos do portal ContasRio.
    3. **Processamento**: 
       - Vá na aba **Arquivo Individual** para testar um PDF específico.
       - Use a aba **Processamento em Lote** para analisar múltiplos arquivos de uma vez.
    4. **Análise de Resultados**: Confira na aba **Resultados** os dados extraídos pela IA.
    5. **Verificação de Conformidade**: A aba **Conformidade** mostra se o contrato foi publicado oficialmente e se os dados batem.
    
    ### 🛠️ Tecnologias Utilizadas
    - **Streamlit**: Interface do usuário.
    - **Selenium**: Automação de coleta de dados.
    - **LangChain & Groq (LLaMA 3.3)**: Extração de dados com IA.
    - **PyMuPDF & Tesseract**: Processamento de PDFs e OCR.
    
    ### 📂 Estrutura de Pastas
    - `data/downloads/processos`: PDFs baixados.
    - `data/outputs`: CSVs e JSONs coletados.
    - `extractions`: Resultados das análises de IA.
    """)
