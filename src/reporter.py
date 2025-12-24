"""
reporter.py - Output generation functionality.
Creates reports, exports data, and handles dashboard.
"""

import os
import pandas as pd
from datetime import datetime
from config import DATA_OUTPUTS_PATH


def save_to_excel(data, filename=None):
    """
    Save data to Excel file.
    
    Args:
        data: List of dictionaries or DataFrame
        filename: Optional filename
        
    Returns:
        Path to saved file
    """
    try:
        # Ensure output directory exists
        os.makedirs(DATA_OUTPUTS_PATH, exist_ok=True)
        
        # Generate filename if not provided
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"report_{timestamp}.xlsx"
        
        filepath = os.path.join(DATA_OUTPUTS_PATH, filename)
        
        # Convert to DataFrame if needed
        if isinstance(data, list):
            df = pd.DataFrame(data)
        else:
            df = data
        
        # Save to Excel
        df.to_excel(filepath, index=False, engine='openpyxl')
        
        print(f"✓ Relatório salvo: {filepath}")
        return filepath
        
    except Exception as e:
        print(f"✗ Erro ao salvar Excel: {e}")
        return None


def save_to_csv(data, filename=None):
    """
    Save data to CSV file.
    
    Args:
        data: List of dictionaries or DataFrame
        filename: Optional filename
        
    Returns:
        Path to saved file
    """
    try:
        os.makedirs(DATA_OUTPUTS_PATH, exist_ok=True)
        
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"report_{timestamp}.csv"
        
        filepath = os.path.join(DATA_OUTPUTS_PATH, filename)
        
        if isinstance(data, list):
            df = pd.DataFrame(data)
        else:
            df = data
        
        df.to_csv(filepath, index=False, encoding='utf-8-sig')
        
        print(f"✓ CSV salvo: {filepath}")
        return filepath
        
    except Exception as e:
        print(f"✗ Erro ao salvar CSV: {e}")
        return None


def generate_analysis_report(company_data, analysis_results):
    """
    Generate a complete analysis report.
    
    Args:
        company_data: Dictionary with company information
        analysis_results: Dictionary with analysis flags and summary
        
    Returns:
        Dictionary with report data
    """
    report = {
        "generated_at": datetime.now().isoformat(),
        "company_id": company_data.get("ID", "N/A"),
        "company_name": company_data.get("Company", "N/A"),
        "total_contratado": company_data.get("Total Contratado", "N/A"),
        "risk_level": analysis_results.get("risk_level", "unknown"),
        "flags_count": len(analysis_results.get("flags", [])),
        "flags": analysis_results.get("flags", []),
        "summary": analysis_results.get("summary", ""),
        "recommendations": analysis_results.get("recommendations", [])
    }
    
    return report


def print_report(report):
    """
    Print a formatted report to console.
    
    Args:
        report: Dictionary with report data
    """
    print("\n" + "=" * 60)
    print("           RELATÓRIO DE ANÁLISE DE CONTRATO")
    print("=" * 60)
    print(f"\n📅 Gerado em: {report.get('generated_at', 'N/A')}")
    print(f"\n🏢 EMPRESA")
    print(f"   ID: {report.get('company_id', 'N/A')}")
    print(f"   Nome: {report.get('company_name', 'N/A')}")
    print(f"   Total Contratado: {report.get('total_contratado', 'N/A')}")
    
    risk_level = report.get('risk_level', 'unknown')
    risk_emoji = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(risk_level, "⚪")
    print(f"\n⚠️  NÍVEL DE RISCO: {risk_emoji} {risk_level.upper()}")
    
    flags = report.get('flags', [])
    if flags:
        print(f"\n🚩 FLAGS ({len(flags)}):")
        for i, flag in enumerate(flags, 1):
            print(f"   {i}. [{flag.get('severity', 'N/A').upper()}] {flag.get('message', 'N/A')}")
    else:
        print("\n🚩 FLAGS: Nenhuma flag identificada")
    
    print("\n" + "-" * 60)
    print(report.get('summary', 'Sem resumo disponível'))
    print("=" * 60 + "\n")


def create_summary_dataframe(all_reports):
    """
    Create a summary DataFrame from multiple reports.
    
    Args:
        all_reports: List of report dictionaries
        
    Returns:
        pandas DataFrame with summary
    """
    summary_data = []
    
    for report in all_reports:
        summary_data.append({
            "ID": report.get("company_id"),
            "Empresa": report.get("company_name"),
            "Total Contratado": report.get("total_contratado"),
            "Nível de Risco": report.get("risk_level"),
            "Qtd Flags": report.get("flags_count"),
            "Data Análise": report.get("generated_at")
        })
    
    return pd.DataFrame(summary_data)