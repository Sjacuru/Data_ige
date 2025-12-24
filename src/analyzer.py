"""
analyzer.py - AI-based document analysis.
Analyzes contract content and generates flags/recommendations.
"""


def analyze_contract(contract_data, instructions=None):
    """
    Analyze contract data based on pre-set instructions.
    
    Args:
        contract_data: Dictionary with parsed contract data
        instructions: Dictionary with analysis rules
        
    Returns:
        Dictionary with analysis results and flags
    """
    # Default instructions if none provided
    if instructions is None:
        instructions = get_default_instructions()
    
    results = {
        "flags": [],
        "recommendations": [],
        "summary": "",
        "risk_level": "low"  # low, medium, high
    }
    
    # Example analysis rules - customize these!
    
    # Check for high values
    for value in contract_data.get("values_found", []):
        # Remove formatting and convert to number
        clean_value = value.replace("R$", "").replace(".", "").replace(",", ".")
        try:
            numeric_value = float(clean_value.strip())
            if numeric_value > 1000000:  # More than 1 million
                results["flags"].append({
                    "type": "high_value",
                    "message": f"Valor alto encontrado: {value}",
                    "severity": "medium"
                })
        except ValueError:
            continue
    
    # Check for missing dates
    if not contract_data.get("dates_found"):
        results["flags"].append({
            "type": "missing_dates",
            "message": "Nenhuma data encontrada no documento",
            "severity": "low"
        })
    
    # Determine overall risk level
    high_severity_count = sum(
        1 for f in results["flags"] if f.get("severity") == "high"
    )
    medium_severity_count = sum(
        1 for f in results["flags"] if f.get("severity") == "medium"
    )
    
    if high_severity_count > 0:
        results["risk_level"] = "high"
    elif medium_severity_count > 0:
        results["risk_level"] = "medium"
    
    # Generate summary
    results["summary"] = generate_summary(contract_data, results)
    
    return results


def get_default_instructions():
    """
    Return default analysis instructions.
    
    Returns:
        Dictionary with analysis rules
    """
    return {
        "value_threshold": 1000000,
        "required_fields": ["dates", "cnpj", "values"],
        "flag_expired": True,
        "flag_high_values": True
    }


def generate_summary(contract_data, analysis_results):
    """
    Generate a text summary of the analysis.
    
    Args:
        contract_data: Parsed contract data
        analysis_results: Analysis results with flags
        
    Returns:
        Summary string
    """
    lines = [
        "=== RESUMO DA ANÁLISE ===",
        f"Valores encontrados: {len(contract_data.get('values_found', []))}",
        f"Datas encontradas: {len(contract_data.get('dates_found', []))}",
        f"CNPJs encontrados: {len(contract_data.get('cnpj_found', []))}",
        f"Flags geradas: {len(analysis_results.get('flags', []))}",
        f"Nível de risco: {analysis_results.get('risk_level', 'unknown').upper()}",
    ]
    
    return "\n".join(lines)