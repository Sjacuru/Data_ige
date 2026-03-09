from __future__ import annotations

import io
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

logger = logging.getLogger(__name__)


def render() -> None:
    try:
        import streamlit as st
        import csv
        import pandas as pd

        from infrastructure.dashboard.pipeline_runner import is_any_running, launch_stage
        from infrastructure.dashboard.state_reader import read_errors, read_state_index

        st.header("⚠️ Erros e Reprocessamento")

        errors = read_errors()
        total_errors = sum(len(value) for value in errors.values()) if isinstance(errors, dict) else 0

        if total_errors == 0:
            st.success("✅ Nenhum erro encontrado em nenhuma etapa.")
        else:
            st.warning(f"{total_errors} erro(s) encontrado(s) no pipeline.")

        stage_labels = {
            "stage2": "Stage 2 — Extração",
            "stage3": "Stage 3 — Publicação",
            "stage4": "Stage 4 — Compliance",
        }
        tabs = st.tabs([f"{label} ({len(errors.get(key, []))})" for key, label in stage_labels.items()])

        for tab, (stage_key, label) in zip(tabs, stage_labels.items()):
            with tab:
                errs = errors.get(stage_key, []) if isinstance(errors, dict) else []
                if not errs:
                    st.success("Nenhum erro nesta etapa.")
                    continue

                df = pd.DataFrame(errs)
                col_order = [col for col in ["processo_id", "error", "at"] if col in df.columns]
                st.dataframe(df[col_order], use_container_width=True, hide_index=True)

                for index, err in enumerate(errs[:20]):
                    pid = str((err or {}).get("processo_id", "")) if isinstance(err, dict) else ""
                    btn_label = f"↺ Reprocessar {pid}"
                    if st.button(btn_label, key=f"retry_{stage_key}_{pid}_{index}", disabled=is_any_running()):
                        launch_stage(stage_key, pid_filter=pid, rerun_failed=False)
                        st.info(f"Reprocessando {pid}...")

                if st.button(
                    f"↺ Reprocessar todos — {label}",
                    key=f"retry_all_{stage_key}",
                    disabled=is_any_running(),
                ):
                    launch_stage(stage_key, rerun_failed=True)
                    st.info(f"{label} reiniciada com modo reprocessar falhas.")

        st.divider()
        st.subheader("Contratos Incompletos")
        index = read_state_index()
        contracts = index.get("contracts", {}) if isinstance(index, dict) else {}
        incomplete = [
            {
                "processo_id": str(meta.get("processo_id", pid_safe)),
                "pipeline_stage": str(meta.get("pipeline_stage", "")),
                "fase_faltante": {
                    "DISCOVERED": "Extração de Contrato",
                    "EXTRACTED": "Extração de Publicação",
                    "PUB_FOUND": "Pré-processamento",
                    "PREPROCESSED": "Análise de Conformidade",
                }.get(str(meta.get("pipeline_stage", "")), ""),
            }
            for pid_safe, meta in contracts.items()
            if isinstance(meta, dict) and meta.get("pipeline_stage") not in ("SCORED", "COMPLIANCE")
        ]

        if incomplete:
            st.dataframe(pd.DataFrame(incomplete), use_container_width=True, hide_index=True)
        else:
            st.success("Todos os contratos chegaram à etapa de análise.")

        if total_errors > 0:
            buf = io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=["stage", "processo_id", "error", "at"])
            writer.writeheader()
            for stage_key in stage_labels:
                for err in errors.get(stage_key, []) if isinstance(errors, dict) else []:
                    row = {
                        "stage": stage_key,
                        "processo_id": str((err or {}).get("processo_id", "")) if isinstance(err, dict) else "",
                        "error": str((err or {}).get("error", "")) if isinstance(err, dict) else "",
                        "at": str((err or {}).get("at", "")) if isinstance(err, dict) else "",
                    }
                    writer.writerow(row)
            st.download_button(
                "⬇ Exportar lista de erros (CSV)",
                data=buf.getvalue().encode("utf-8-sig"),
                file_name="erros_pipeline.csv",
                mime="text/csv",
            )
    except Exception as exc:
        logger.warning("Failed to render errors page: %s", exc)
