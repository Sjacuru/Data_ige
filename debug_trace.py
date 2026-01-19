"""
debug_trace.py - Trace processo number through the entire pipeline

Add this to your code to see exactly where the wrong number comes from.
"""

import json
from datetime import datetime

class ProcessoTracer:
    """Traces processo number through the pipeline."""
    
    def __init__(self):
        self.events = []
    
    def log(self, stage: str, processo: str, source: str, extra: dict = None):
        """Log a processo observation."""
        event = {
            "timestamp": datetime.now().isoformat(),
            "stage": stage,
            "processo": processo,
            "source": source,
            "extra": extra or {}
        }
        self.events.append(event)
        
        print(f"\n🔍 [{stage}] Processo: {processo}")
        print(f"   Source: {source}")
        if extra:
            print(f"   Extra: {extra}")
    
    def report(self):
        """Print full trace report."""
        print("\n" + "=" * 70)
        print("📊 PROCESSO TRACE REPORT")
        print("=" * 70)
        
        if not self.events:
            print("   No events recorded")
            return
        
        # Show timeline
        for i, event in enumerate(self.events, 1):
            print(f"\n{i}. [{event['stage']}] at {event['timestamp']}")
            print(f"   Processo: {event['processo']}")
            print(f"   Source: {event['source']}")
            if event['extra']:
                print(f"   Details: {json.dumps(event['extra'], indent=6)}")
        
        # Check for changes
        unique_processos = set(e['processo'] for e in self.events if e['processo'])
        if len(unique_processos) > 1:
            print("\n" + "⚠️ " * 10)
            print("WARNING: Processo changed during pipeline!")
            print(f"Different values found: {unique_processos}")
            print("⚠️ " * 10)
        else:
            print(f"\n✅ Processo remained consistent: {unique_processos.pop() if unique_processos else 'NONE'}")
        
        print("\n" + "=" * 70)
    
    def save_to_file(self, filename: str = "processo_trace.json"):
        """Save trace to JSON file."""
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(self.events, f, indent=2, ensure_ascii=False)
        print(f"💾 Trace saved to {filename}")


# Global tracer instance
tracer = ProcessoTracer()


# ============================================================
# INSTRUMENTATION PATCHES
# ============================================================

def patch_contract_extractor():
    """
    Patch contract_extractor.py to trace processo extraction.
    
    Add this at the end of analyze_contract_with_ai():
    """
    code = """
    # ADD THIS at the end of analyze_contract_with_ai() function
    from debug_trace import tracer
    
    tracer.log(
        stage="AI_EXTRACTION",
        processo=extracted.get("processo_administrativo") or extracted.get("numero_processo") or "NONE",
        source="AI model",
        extra={
            "processo_administrativo": extracted.get("processo_administrativo"),
            "numero_processo": extracted.get("numero_processo"),
            "numero_contrato": extracted.get("numero_contrato"),
        }
    )
    """
    print("Add this code to contract_extractor.py::analyze_contract_with_ai():")
    print(code)


def patch_integration():
    """
    Patch integration.py to trace processo selection.
    
    Add this in extract_processo_from_contract():
    """
    code = """
    # ADD THIS at the end of extract_processo_from_contract() function
    from debug_trace import tracer
    
    tracer.log(
        stage="CONFORMITY_INTEGRATION",
        processo=best['value'] if found_processos else "NONE",
        source=f"contract_data['{best['field']}']" if found_processos else "NOT_FOUND",
        extra={
            "available_fields": list(contract_data.keys()),
            "all_processos_found": [p['value'] for p in found_processos]
        }
    )
    """
    print("Add this code to integration.py::extract_processo_from_contract():")
    print(code)


def patch_doweb_scraper():
    """
    Patch doweb_scraper.py to trace what's being searched.
    
    Add this at the start of search_and_extract_publication():
    """
    code = """
    # ADD THIS at the start of search_and_extract_publication() function
    from debug_trace import tracer
    
    tracer.log(
        stage="DOWEB_SEARCH",
        processo=processo,
        source="Function parameter",
        extra={
            "headless": headless
        }
    )
    """
    print("Add this code to doweb_scraper.py::search_and_extract_publication():")
    print(code)


# ============================================================
# STANDALONE USAGE
# ============================================================

def trace_full_pipeline(pdf_path: str, expected_processo: str = None):
    """
    Run a full pipeline trace for debugging.
    
    Args:
        pdf_path: Path to the contract PDF
        expected_processo: What you expect the processo to be
    """
    print("\n" + "=" * 70)
    print("🔬 FULL PIPELINE TRACE")
    print("=" * 70)
    
    if expected_processo:
        print(f"Expected processo: {expected_processo}")
        tracer.log("EXPECTED", expected_processo, "User input")
    
    # Step 1: Extract from PDF
    print("\n📄 Step 1: Extracting from PDF...")
    from Contract_analisys.contract_extractor import extract_text_from_pdf, analyze_contract_with_ai
    
    extraction = extract_text_from_pdf(pdf_path)
    if extraction["success"]:
        tracer.log("PDF_EXTRACTION", "N/A", "PDF text extracted", {"chars": extraction["total_chars"]})
        
        # Step 2: AI Analysis
        print("\n🤖 Step 2: AI Analysis...")
        ai_result = analyze_contract_with_ai(extraction["full_text"])
        
        tracer.log(
            "AI_EXTRACTION",
            ai_result.get("processo_administrativo") or ai_result.get("numero_processo") or "NONE",
            "AI model",
            {
                "processo_administrativo": ai_result.get("processo_administrativo"),
                "numero_processo": ai_result.get("numero_processo"),
                "numero_contrato": ai_result.get("numero_contrato"),
            }
        )
        
        # Step 3: Conformity Check
        print("\n✅ Step 3: Conformity Check...")
        from conformity.integration import check_publication_conformity
        
        result = check_publication_conformity(
            contract_data=ai_result,
            headless=True
        )
        
        tracer.log(
            "CONFORMITY_RESULT",
            result.processo,
            "Conformity check",
            {
                "overall_status": result.overall_status.value,
                "found_publication": result.publication_check.was_published if result.publication_check else False
            }
        )
    else:
        print(f"❌ PDF extraction failed: {extraction.get('error')}")
    
    # Generate report
    tracer.report()
    tracer.save_to_file()


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python debug_trace.py <path_to_pdf> [expected_processo]")
        print("\nExample:")
        print("  python debug_trace.py data/downloads/processos/contract.pdf SME-PRO-2025/19222")
        print("\nOr to see instrumentation code:")
        print("  python debug_trace.py --patches")
        sys.exit(1)
    
    if sys.argv[1] == "--patches":
        print("\n🔧 INSTRUMENTATION PATCHES\n")
        patch_contract_extractor()
        print("\n" + "─" * 70 + "\n")
        patch_integration()
        print("\n" + "─" * 70 + "\n")
        patch_doweb_scraper()
    else:
        pdf_path = sys.argv[1]
        expected = sys.argv[2] if len(sys.argv) > 2 else None
        trace_full_pipeline(pdf_path, expected)