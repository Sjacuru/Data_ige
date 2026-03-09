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

        from infrastructure.dashboard.pipeline_runner import (
            get_running_stage,
            get_stage_status,
            is_any_running,
            launch_stage,
            stop_running_stage,
        )
        from infrastructure.dashboard.state_reader import read_log_tail

        st.header("🎛️ Controle do Pipeline")
        col_left, col_right = st.columns([1, 1.5])

        with col_left:
            st.info("⚠️ Etapas 1, 2 e 3 abrem o Chrome. Resolva o CAPTCHA quando solicitado.")

            headless = st.toggle("Modo Headless (Stages 1–3)", value=True)

            pid_filter = st.text_input("PID específico (opcional)", value="")
            pid_filter = pid_filter.strip() or None

            rerun_failed = st.checkbox("Reprocessar apenas falhas")

            any_running = is_any_running()
            stage1_path = ROOT / "application" / "main.py"
            stage1_exists = stage1_path.exists()

            stage1_clicked = st.button(
                "🌐 Executar Descoberta",
                disabled=any_running or (not stage1_exists),
            )
            if stage1_clicked:
                if not stage1_exists:
                    st.error("application/main.py não encontrado.")
                else:
                    launched = launch_stage(
                        "stage1",
                        headless=headless,
                        pid_filter=pid_filter,
                        rerun_failed=rerun_failed,
                    )
                    if launched:
                        st.success("Stage iniciada — veja progresso ao lado.")

            if st.button("📄 Extrair Contratos", disabled=is_any_running()):
                launched = launch_stage(
                    "stage2",
                    headless=headless,
                    pid_filter=pid_filter,
                    rerun_failed=rerun_failed,
                )
                if launched:
                    st.success("Stage iniciada — veja progresso ao lado.")

            if st.button("📰 Extrair Publicações", disabled=is_any_running()):
                launched = launch_stage(
                    "stage3",
                    headless=headless,
                    pid_filter=pid_filter,
                    rerun_failed=rerun_failed,
                )
                if launched:
                    st.success("Stage iniciada — veja progresso ao lado.")

            if st.button("⚖️ Análise de Conformidade", disabled=is_any_running()):
                launched = launch_stage(
                    "stage4",
                    headless=headless,
                    pid_filter=pid_filter,
                    rerun_failed=rerun_failed,
                )
                if launched:
                    st.success("Stage iniciada — veja progresso ao lado.")

            if st.button("📊 Calcular Conformidade", disabled=is_any_running()):
                launched = launch_stage(
                    "stage5",
                    headless=headless,
                    pid_filter=pid_filter,
                    rerun_failed=rerun_failed,
                )
                if launched:
                    st.success("Stage iniciada — veja progresso ao lado.")

            if st.button("🚨 Gerar Alertas", disabled=is_any_running()):
                launched = launch_stage(
                    "stage6_alerts",
                    headless=headless,
                    pid_filter=pid_filter,
                    rerun_failed=rerun_failed,
                )
                if launched:
                    st.success("Stage iniciada — veja progresso ao lado.")

            if st.button("📋 Gerar Relatório", disabled=is_any_running()):
                launched = launch_stage(
                    "stage6_report",
                    headless=headless,
                    pid_filter=pid_filter,
                    rerun_failed=rerun_failed,
                )
                if launched:
                    st.success("Stage iniciada — veja progresso ao lado.")

            if st.button("▶ Executar Pipeline Completo (4→5→6)", disabled=is_any_running()):
                launched = launch_stage(
                    "full",
                    headless=headless,
                    pid_filter=pid_filter,
                    rerun_failed=rerun_failed,
                )
                if launched:
                    st.success("Stage iniciada — veja progresso ao lado.")

            if is_any_running():
                if st.button("⏹ Parar Execução", type="secondary"):
                    stop_running_stage()
                    st.warning("Solicitação de parada enviada.")

        with col_right:
            stage_map = {
                "stage1": "Descoberta",
                "stage2": "Contrato",
                "stage3": "Publicação",
                "stage4": "Compliance",
                "stage5": "Conformidade",
                "stage6_alerts": "Alertas",
            }
            for key, label in stage_map.items():
                s = get_stage_status(key)
                pct = float(s.get("progress_pct", 0.0) or 0.0) / 100
                st.write(
                    f"**{label}** — {str(s.get('status', 'NOT_STARTED'))} "
                    f"({int(s.get('completed', 0) or 0)}/{int(s.get('total', 0) or 0)})"
                )
                st.progress(pct)

            st.subheader("📋 Log")
            running = get_running_stage()
            log_stage = running or "stage4"
            log_lines = read_log_tail(log_stage, lines=30)
            st.text_area("Log output", value="\n".join(log_lines), height=300, disabled=True, label_visibility="collapsed")

            if is_any_running():
                import time

                time.sleep(1.5)
                st.rerun()
    except Exception as exc:
        logger.warning("Failed to render control page: %s", exc)
