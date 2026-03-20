from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is on sys.path regardless of how Streamlit launches this file
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ── Import-safe module: NO module-level Streamlit calls. ──────────────────────
# st.set_page_config() lives inside render_app() to allow test imports.

import logging
import importlib

logger = logging.getLogger(__name__)

PAGES: dict = {}  # populated inside render_app() to avoid circular at import


def render_app() -> None:
	"""Entry point for all UI logic. Called from __main__ only."""
	try:
		import streamlit as st
		from infrastructure.dashboard.pipeline_runner import get_stage_status, is_any_running
		control = importlib.import_module("application.pages.control")
		explorer = importlib.import_module("application.pages.explorer")
		analytics = importlib.import_module("application.pages.analytics")
		errors_page = importlib.import_module("application.pages.errors")

		st.set_page_config(
			page_title="TCM-Rio | Análise de Contratos",
			page_icon="⚖️",
			layout="wide",
			initial_sidebar_state="expanded",
		)

		pages = {
			"🎛️ Controle do Pipeline": control,
			"🔍 Explorador de Dados": explorer,
			"📊 Análise e Filtros": analytics,
			"⚠️ Erros e Reprocessamento": errors_page,
		}

		status_icons = {
			"NOT_STARTED": "—",
			"IN_PROGRESS": "🔄",
			"COMPLETE": "✅",
			"FAILED": "❌",
		}

		with st.sidebar:
			st.title("⚖️ TCM-Rio Auditoria")
			st.caption("Análise de Contratos")
			st.divider()

			selection = st.radio("NAVEGAÇÃO", list(pages.keys()), label_visibility="collapsed")
			st.divider()

			st.markdown("**STATUS DO PIPELINE**")
			stage_labels = {
				"stage1": "Descoberta",
				"stage2": "Extração Contrato",
				"stage3": "Extração Publicação",
				"stage4": "Análise Compliance",
				"stage5": "Conformidade",
				"stage6_alerts": "Alertas",
			}
			for key, label in stage_labels.items():
				s = get_stage_status(key)
				icon = status_icons.get(s.get("status", ""), "—")
				st.write(f"{icon} {label}")

			if st.button("🔄 Atualizar status"):
				st.cache_data.clear()
				st.rerun()

			st.divider()
			running = is_any_running()
			if running:
				st.info("⏳ Executando...")

		pages[selection].render()
	except Exception as exc:
		logger.warning("Failed to render app: %s", exc)


if __name__ == "__main__":
	render_app()
