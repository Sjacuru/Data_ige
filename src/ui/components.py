import streamlit as st  
import pandas as pd  
from pathlib import Path  
from src.ui.utils import format_file_size, get_status_emoji  
from Contract_analisys.contract_extractor import (  
    process_single_contract, get_folder_stats, export_to_excel, export_to_json  
)  
from config import PROCESSOS_DIR, FILTER_YEAR, ANALYSIS_SUMMARY_CSV  
  
def render_header():  
    """Render the page header."""  
    st.title("📄 TCMRio - Análise de Contratos")  
    st.markdown("Sistema de extração e análise de contratos públicos")  
  
def render_conformity_details(conf):  
    """Visualizes the rich conformity data from the D.O. Rio into a Report Card."""  
    if not conf:  
        st.warning("Dados de conformidade não encontrados.")  
        return  
          
    st.subheader("🛡️ Resultado da Verificação de Conformidade")  
      
    # 1. Summary Metrics  
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
        if pub.get("observation"):  
            st.caption(pub.get("observation"))  
  
    # 2. Comparison Table  
    st.markdown("### 🔍 Batimento de Campos (Contrato vs. Diário Oficial)")  
    fields = conf.get("field_checks", [])  
    if fields:  
        df_fields = pd.DataFrame(fields)  
        # Select and rename columns for a better UI experience  
        ui_df = df_fields[["field_label", "contract_value", "publication_value", "status"]]  
        ui_df.columns = ["Campo", "No Contrato", "No Diário Oficial", "Status"]  
        st.table(ui_df)  
  
def render_sidebar(extractor_loaded, scraper_loaded, driver_available, summary_df):  
    """Renders the sidebar with statistics and integrity check."""  
    with st.sidebar:  
        st.header("📂 Configuração")  
        stats = get_folder_stats(str(PROCESSOS_DIR))  
        if stats["exists"]:  
            col1, col2 = st.columns(2)  
            col1.metric("PDFs", stats["total_files"])  
            col2.metric("Tamanho", format_file_size(stats["total_size_mb"]))  
          
        st.divider()  
        st.subheader("⚖️ Integridade de Dados")  
          
        # Check integrity between Scraped vs Portal CSV  
        scraped_path = "data/outputs/favorecidos_2025.csv"  
        portal_path = "data/outputs/contasrio_2025.csv"  
          
        if Path(scraped_path).exists() and Path(portal_path).exists():  
            from src.ui.logic import compare_data_sources  
            comparison = compare_data_sources(scraped_path, portal_path)  
            if comparison["success"]:  
                st.metric("Scraped vs Portal", f"{comparison['scraped_count']} / {comparison['portal_count']}")  
                var = comparison["variance"]  
                st.write(f"Variância: :{'green' if var == 0 else 'red'}[{var}]")  
            else:  
                st.error("Erro na checagem.")  
        else:  
            st.info("Aguardando fontes para checagem.")  
  
        st.divider()  
        st.subheader("🔄 Automação")  
        year = st.number_input("Ano para filtrar", 2020, 2030, FILTER_YEAR or 2025)  
        if st.button("🚀 Iniciar Scraping", use_container_width=True):  
            st.session_state.scraping_trigger = True  
            st.session_state.scraping_year = year  
            st.rerun()  
  
    return stats  
  
def render_single_file_tab(stats):  
    """Handles the Step-by-Step and Automatic analysis workflow."""  
    st.header("🎯 Processamento de Contrato")  
      
    if not stats["files"]:  
        st.warning("Nenhum PDF encontrado em data/downloads/processos.")  
        return  
  
    selected = st.selectbox("Selecione o PDF para análise:", stats["files"], key="proc_select")  
    st.divider()  
      
    mode = st.radio("Escolha o modo de análise:",   
                    ["🚶 Passo a Passo (Auditor)", "⚡ Automático (One-Click)"],   
                    horizontal=True)  
  
    if mode == "🚶 Passo a Passo (Auditor)":  
        st.info("Siga os passos para verificar a inteligência do sistema.")  
        c1, c2, c3 = st.columns(3)  
          
        if c1.button("1. Extração AI", use_container_width=True):  
            with st.status("IA Analisando PDF...") as s:  
                res = process_single_contract(str(PROCESSOS_DIR / selected))  
                st.session_state.current_extraction = res  
                s.update(label="Extração Completa!", state="complete")  
  
        if c2.button("2. Checar D.O.", use_container_width=True):  
            if st.session_state.get("current_extraction"):  
                st.session_state.show_conformity = True  
                st.toast("Busca no Diário Oficial concluída!")  
            else:  
                st.error("Execute o Passo 1 primeiro.")  
  
        if c3.button("3. Veredito Final", use_container_width=True):  
            if not st.session_state.get("show_conformity"):  
                st.error("Execute os passos anteriores.")  
            else:  
                st.success("Checagem realizada!")  
  
        if st.session_state.get("current_extraction"):  
            with st.expander("📄 Dados Extraídos do PDF (Evidência)", expanded=True):  
                st.json(st.session_state.current_extraction)  
          
        if st.session_state.get("show_conformity"):  
            render_conformity_details(st.session_state.get("last_conformity_sample"))  
  
    else: # AUTOMÁTICO  
        if st.button("🚀 Iniciar Auditoria Completa", type="primary", use_container_width=True):  
            with st.status("Executando Auditoria...") as status:  
                res = process_single_contract(str(PROCESSOS_DIR / selected))  
                st.session_state.current_extraction = res  
                status.update(label="Auditoria Concluída!", state="complete")  
            render_conformity_details(st.session_state.get("last_conformity_sample"))  
  
def render_results_tab():  
    """Visualizes the history of results and allows exports."""  
    st.header("📊 Histórico de Resultados")  
    if not st.session_state.results:  
        st.info("Nenhum resultado processado nesta sessão.")  
        return  
  
    df = pd.DataFrame(st.session_state.results)  
    st.dataframe(df, use_container_width=True)  
  
    st.divider()  
    e1, e2, _ = st.columns([1, 1, 2])  
    if e1.button("📊 Exportar Excel"):  
        path = export_to_excel(st.session_state.results, "extractions/results.xlsx")  
        st.success(f"Salvo em {path}")  
    if e2.button("📝 Exportar JSON"):  
        path = export_to_json(st.session_state.results, "extractions/results.json")  
        st.success(f"Salvo em {path}")  
  
def render_help_tab():  
    """Documentation for the Auditor."""  
    st.header("❓ Ajuda")  
    st.markdown("""  
    - **Scraping**: Coleta dados básicos do portal.  
    - **Processamento**: Extrai texto do PDF e compara com o D.O. Rio.  
    - **Conformidade**: Verifica se o contrato segue as regras de publicação.  
    """)  