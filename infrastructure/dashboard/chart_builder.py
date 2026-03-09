from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import streamlit as st

logger = logging.getLogger(__name__)

STATUS_COLORS: dict[str, str] = {
    "CONFORME": "#C6EFCE",
    "PARCIAL": "#FFEB9C",
    "NÃO CONFORME": "#FFC7CE",
    "INCOMPLETE": "#FFCC99",
    "OK": "#C6EFCE",
    "REVIEW": "#FFEB9C",
    "FAILED": "#FFC7CE",
}


def render_conformity_donut(summary: dict) -> None:
    try:
        import streamlit as st
        import pandas as pd
        import altair as alt

        labels = ["CONFORME", "PARCIAL", "NÃO CONFORME", "INCOMPLETE"]
        values = [summary.get(k, 0) if isinstance(summary, dict) else 0 for k in labels]
        colors = [STATUS_COLORS[k] for k in labels]

        if sum(values) == 0:
            st.info("Sem dados de conformidade.")
            return

        df = pd.DataFrame({"Status": labels, "Contratos": values, "Color": colors})
        chart = alt.Chart(df).mark_arc(innerRadius=60).encode(
            theta=alt.Theta("Contratos:Q"),
            color=alt.Color("Status:N", scale=alt.Scale(domain=labels, range=colors)),
            tooltip=["Status", "Contratos"],
        ).properties(title="Distribuição de Conformidade", width=280, height=280)
        st.altair_chart(chart, use_container_width=False)
    except Exception as exc:
        logger.warning("Failed to render conformity donut: %s", exc)


def render_pipeline_progress_bars(state_index: dict) -> None:
    try:
        import streamlit as st
        from infrastructure.dashboard.pipeline_runner import get_stage_status

        stage_labels = {
            "stage1": "Stage 1 — Descoberta",
            "stage2": "Stage 2 — Extração Contrato",
            "stage3": "Stage 3 — Extração Publicação",
            "stage4": "Stage 4 — Análise Conformidade",
            "stage5": "Stage 5 — Conformidade",
            "stage6_alerts": "Stage 6 — Alertas",
        }
        for key, label in stage_labels.items():
            s = get_stage_status(key)
            pct = float((s.get("progress_pct", 0.0) if isinstance(s, dict) else 0.0) or 0.0) / 100
            st.write(
                f"**{label}** — {str(s.get('status', '') if isinstance(s, dict) else '')} "
                f"({int(s.get('completed', 0) if isinstance(s, dict) else 0)}/"
                f"{int(s.get('total', 0) if isinstance(s, dict) else 0)})"
            )
            st.progress(pct)
    except Exception as exc:
        logger.warning("Failed to render pipeline progress bars: %s", exc)


def render_rule_averages_bar(rule_averages: dict) -> None:
    try:
        import streamlit as st
        import pandas as pd
        import altair as alt

        if not rule_averages:
            st.info("Sem médias de regras disponíveis.")
            return

        df = pd.DataFrame([
            {"Regra": k, "Média": v} for k, v in (rule_averages.items() if isinstance(rule_averages, dict) else [])
        ])
        chart = alt.Chart(df).mark_bar().encode(
            x=alt.X("Média:Q", scale=alt.Scale(domain=[0, 100])),
            y=alt.Y("Regra:N", sort="-x"),
            color=alt.value("#1F3864"),
            tooltip=["Regra", "Média"],
        ).properties(title="Médias por Regra", height=180)
        st.altair_chart(chart, use_container_width=True)
    except Exception as exc:
        logger.warning("Failed to render rule averages bar: %s", exc)


def render_coverage_metrics(coverage: dict) -> None:
    try:
        import streamlit as st

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Descobertos", coverage.get("total_discovered", 0) if isinstance(coverage, dict) else 0)
        c2.metric("Extraídos", coverage.get("total_extracted", 0) if isinstance(coverage, dict) else 0)
        c3.metric("Publicações", coverage.get("total_pub_found", 0) if isinstance(coverage, dict) else 0)
        c4.metric("Analisados", coverage.get("total_analyzed", 0) if isinstance(coverage, dict) else 0)
    except Exception as exc:
        logger.warning("Failed to render coverage metrics: %s", exc)


def render_alert_distribution(summary: dict) -> None:
    try:
        import streamlit as st
        import pandas as pd
        import altair as alt

        data = [
            {"Nível": "OK", "Contratos": summary.get("ok", 0) if isinstance(summary, dict) else 0, "Cor": STATUS_COLORS["OK"]},
            {
                "Nível": "REVIEW",
                "Contratos": summary.get("review", 0) if isinstance(summary, dict) else 0,
                "Cor": STATUS_COLORS["REVIEW"],
            },
            {
                "Nível": "FAILED",
                "Contratos": summary.get("failed", 0) if isinstance(summary, dict) else 0,
                "Cor": STATUS_COLORS["FAILED"],
            },
        ]
        df = pd.DataFrame(data)
        chart = alt.Chart(df).mark_bar().encode(
            x="Nível:N",
            y="Contratos:Q",
            color=alt.Color(
                "Nível:N",
                scale=alt.Scale(
                    domain=["OK", "REVIEW", "FAILED"],
                    range=[STATUS_COLORS["OK"], STATUS_COLORS["REVIEW"], STATUS_COLORS["FAILED"]],
                ),
            ),
            tooltip=["Nível", "Contratos"],
        ).properties(title="Distribuição de Alertas", height=200)
        st.altair_chart(chart, use_container_width=True)
    except Exception as exc:
        logger.warning("Failed to render alert distribution: %s", exc)


def render_status_badge(status: str) -> str:
    try:
        color = STATUS_COLORS.get(status, "#E0E0E0")
        return f'<span style="background-color:{color};padding:2px 8px;border-radius:4px;font-weight:bold;">{status}</span>'
    except Exception as exc:
        logger.warning("Failed to render status badge: %s", exc)
        return '<span style="background-color:#E0E0E0;padding:2px 8px;border-radius:4px;font-weight:bold;"></span>'
