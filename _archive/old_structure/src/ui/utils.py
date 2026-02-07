
import os
import re
import pandas as pd
from pathlib import Path

import streamlit as st
from datetime import datetime

def add_audit_log(message: str, level: str = "info"):
    """Add a message to the audit logs in session state."""
    if "audit_logs" not in st.session_state:
        st.session_state.audit_logs = []
    
    timestamp = datetime.now().strftime("%H:%M:%S")
    st.session_state.audit_logs.append({
        "timestamp": timestamp,
        "message": message,
        "level": level
    })

def load_analysis_summary(filepath: str) -> pd.DataFrame:
    """Load the analysis summary CSV."""
    if not os.path.exists(filepath):
        return pd.DataFrame()
    try:
        return pd.read_csv(filepath)
    except Exception:
        return pd.DataFrame()

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

def get_conformity_badge(conformity_data: dict) -> str:
    """Get conformity status badge."""
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

def normalize_id(value):
    """
    Normalize ID/CNPJ for comparison.
    Removes dots, dashes, slashes, spaces. Keeps only alphanumeric.
    """
    if not value:
        return ""
    # Convert to string, lowercase, remove common separators
    normalized = str(value).lower().strip()
    normalized = re.sub(r'[.\-/\s]', '', normalized)
    return normalized


def find_id_column(df, candidates=None):
    """
    Find the ID/CNPJ column in a DataFrame.
    """
    if candidates is None:
        candidates = [
            'ID', 'id', 'Id',
            'CNPJ', 'cnpj', 'Cnpj',
            'CPF/CNPJ', 'cpf/cnpj',
            'Favorecido', 'favorecido',
            'Código', 'codigo', 'Codigo',
            'Identificador', 'identificador'
        ]
    
    for col in candidates:
        if col in df.columns:
            return col
    
    # Fallback: first column that looks like an ID
    for col in df.columns:
        col_lower = col.lower()
        if any(term in col_lower for term in ['id', 'cnpj', 'cpf', 'codigo', 'favorecido']):
            return col
    
    return None

def find_company_column(df, candidates=None):
    """
    Find the company name column in a DataFrame.
    """
    if candidates is None:
        candidates = [
            'Company', 'company',
            'Nome', 'nome',
            'Razão Social', 'razao_social', 'Razao Social',
            'Empresa', 'empresa',
            'Favorecido', 'favorecido',
            'Nome Favorecido', 'nome_favorecido'
        ]
    
    for col in candidates:
        if col in df.columns:
            return col
    
    # Fallback
    for col in df.columns:
        col_lower = col.lower()
        if any(term in col_lower for term in ['nome', 'company', 'empresa', 'razao']):
            return col
    
    return None

def get_processos_files():
    """Get list of processos CSV files available for download."""
    processos_dir = Path("scripts/outputs")
    if not processos_dir.exists():
        return []
    
    files = list(processos_dir.glob("processos_*.csv"))
    # Sort by modification time, newest first
    files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    return files


def read_processos_csv(filepath):
    """Read processos CSV and return list of URLs."""
    try:
        df = pd.read_csv(filepath, dtype=str)
        
        # Find URL column
        url_col = None
        for col in ['URL', 'url', 'Url', 'href', 'Link']:
            if col in df.columns:
                url_col = col
                break
        
        if not url_col:
            return [], "Coluna URL não encontrada"
        
        # Filter valid URLs
        processos = []
        for _, row in df.iterrows():
            url = row.get(url_col, "")
            if url and url.startswith("http"):
                processos.append({
                    "url": url,
                    "id": row.get("ID", ""),
                    "company": row.get("Company", ""),
                    "processo": row.get("Processo", "")
                })
        
        return processos, None
        
    except Exception as e:
        return [], str(e)
