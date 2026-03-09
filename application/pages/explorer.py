from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

logger = logging.getLogger(__name__)


def render() -> None:
    try:
        import streamlit as st

        from infrastructure.dashboard.chart_builder import render_status_badge
        from infrastructure.dashboard.state_reader import read_processo_detail, read_state_index

        st.header("🔍 Explorador de Dados")

        index = read_state_index()
        contracts = index.get("contracts", {}) if isinstance(index, dict) else {}
        all_pids_safe = sorted(contracts.keys()) if isinstance(contracts, dict) else []

        col1, col2 = st.columns([2, 3])
        with col1:
            search_text = st.text_input("🔍 Buscar por Processo ID")
            selected_pid = st.selectbox("Ou selecionar da lista", options=[""] + all_pids_safe, index=0)

        with col2:
            st.empty()

        pid_to_load = search_text.strip() or selected_pid

        if not pid_to_load:
            st.info("Digite ou selecione um Processo ID para visualizar.")
            return

        detail = read_processo_detail(pid_to_load)
        contract_meta = contracts.get(pid_to_load, {}) if isinstance(contracts, dict) else {}

        if not any(value is not None for value in detail.values()):
            st.warning(f"Processo '{pid_to_load}' não encontrado. Execute as etapas do pipeline primeiro.")
            return

        status = str(contract_meta.get("pipeline_stage", "DISCOVERED")) if isinstance(contract_meta, dict) else "DISCOVERED"
        conformity_data = detail.get("conformity") if isinstance(detail, dict) else None
        score = f"{float(conformity_data.get('conformity_score', 0) or 0):.1f}" if isinstance(conformity_data, dict) else "—"
        overall = str(conformity_data.get("overall_status", "—")) if isinstance(conformity_data, dict) else "—"

        st.markdown(
            f"**{pid_to_load}** &nbsp;|&nbsp; Etapa: `{status}` &nbsp;|&nbsp; "
            f"Status: {render_status_badge(overall)} &nbsp;|&nbsp; Score: `{score}`",
            unsafe_allow_html=True,
        )
        st.divider()

        tab_map = [
            ("📄 Contrato Bruto", "raw"),
            ("📰 Publicação Bruta", "pub_raw"),
            ("🔧 Pré-processado", "preprocessed"),
            ("📋 Publicação Estruturada", "pub_structured"),
            ("⚖️ Compliance", "compliance"),
            ("📊 Conformidade", "conformity"),
            ("🚨 Alerta", "alert"),
        ]

        tabs = st.tabs([item[0] for item in tab_map])
        for tab, (_label, key) in zip(tabs, tab_map):
            with tab:
                data = detail.get(key) if isinstance(detail, dict) else None
                if data is None:
                    stage_num = {
                        "raw": 2,
                        "pub_raw": 3,
                        "preprocessed": 3,
                        "pub_structured": 3,
                        "compliance": 4,
                        "conformity": 5,
                        "alert": 6,
                    }.get(key, "?")
                    st.info(f"Dados não disponíveis — execute o Stage {stage_num} primeiro.")
                else:
                    if isinstance(data, dict) and "raw_text" in data and isinstance(data["raw_text"], str):
                        full_text = data["raw_text"]
                        display_data = {
                            **data,
                            "raw_text": full_text[:2000] + ("..." if len(full_text) > 2000 else ""),
                        }
                        with st.expander("Ver texto completo (raw_text)"):
                            st.text(full_text)
                    else:
                        display_data = data
                    st.json(display_data)
    except Exception as exc:
        logger.warning("Failed to render explorer page: %s", exc)
