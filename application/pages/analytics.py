from __future__ import annotations

import io
import logging
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

logger = logging.getLogger(__name__)


def render() -> None:
    try:
        import streamlit as st
        import pandas as pd

        from infrastructure.dashboard.chart_builder import (
            render_conformity_donut,
            render_coverage_metrics,
            render_rule_averages_bar,
        )
        from infrastructure.dashboard.state_reader import read_aggregate_report
        from infrastructure.io.excel_writer import write_excel_filtered
        from infrastructure.io.report_csv_writer import build_report_csv_bytes

        _ = io

        st.header("📊 Análise e Filtros")

        agg = read_aggregate_report()
        if not (agg.get("contracts") if isinstance(agg, dict) else []):
            st.info("Sem contratos analisados. Execute as etapas do pipeline primeiro.")
            return

        render_coverage_metrics(agg.get("coverage", {}) if isinstance(agg, dict) else {})
        st.divider()

        chart_col, rule_col = st.columns(2)
        with chart_col:
            render_conformity_donut(agg.get("conformity_summary", {}) if isinstance(agg, dict) else {})
        with rule_col:
            render_rule_averages_bar(agg.get("rule_averages", {}) if isinstance(agg, dict) else {})
        st.divider()

        st.subheader("🔎 Filtros")
        contracts = agg.get("contracts", []) if isinstance(agg, dict) and isinstance(agg.get("contracts", []), list) else []

        filter_col1, filter_col2, filter_col3 = st.columns(3)
        with filter_col1:
            status_opts = ["CONFORME", "PARCIAL", "NÃO CONFORME", "INCOMPLETE"]
            sel_status = st.multiselect("Status", status_opts, default=status_opts)
        with filter_col2:
            company_search = st.text_input("Empresa (contém)")
        with filter_col3:
            score_range = st.slider("Score", 0, 100, (0, 100))

        filtered = [
            contract
            for contract in contracts
            if str(contract.get("overall_status", "INCOMPLETE")) in sel_status
            and (
                company_search.lower() in str(contract.get("company_name", "")).lower()
                if company_search
                else True
            )
            and score_range[0] <= float(contract.get("conformity_score", 0) or 0) <= score_range[1]
        ]

        btn_col1, btn_col2, btn_col3 = st.columns([1, 1, 4])
        with btn_col1:
            if st.button("🔄 Limpar Filtros"):
                st.rerun()

        datestamp = datetime.now().strftime("%Y%m%d")

        with btn_col2:
            if filtered:
                csv_bytes = build_report_csv_bytes(filtered, datetime.now().isoformat())
                st.download_button(
                    "⬇ CSV",
                    data=csv_bytes,
                    file_name=f"contratos_filtrados_{datestamp}.csv",
                    mime="text/csv",
                )

        with btn_col3:
            if filtered:
                with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
                    tmp_path = Path(tmp.name)
                write_excel_filtered(filtered, tmp_path)
                excel_bytes = tmp_path.read_bytes()
                tmp_path.unlink(missing_ok=True)
                st.download_button(
                    "⬇ Excel",
                    data=excel_bytes,
                    file_name=f"contratos_filtrados_{datestamp}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )

        st.subheader(f"Contratos Analisados — {len(contracts)} total / {len(filtered)} filtrados")
        if filtered:
            df = pd.DataFrame(filtered)
            display_cols = [
                "processo_id",
                "company_name",
                "contract_value",
                "overall_status",
                "conformity_score",
                "pipeline_stage",
            ]
            show_df = df[[col for col in display_cols if col in df.columns]]
            st.dataframe(
                show_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "overall_status": st.column_config.TextColumn("Status"),
                    "conformity_score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100),
                },
            )
        else:
            st.info("Nenhum contrato corresponde aos filtros selecionados.")
    except Exception as exc:
        logger.warning("Failed to render analytics page: %s", exc)
