"""
Quick diagnostic — run this from the project root to find why object_summary is None.

    python diagnose_fix3.py
"""
import re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

# ── Reproduce the exact text preprocess_text sees ────────────────────────────
TEXT = """\
CONTRATO Nº 2403453/2024

Processo Instrutivo: FIL-PRO-2023/00482.

Aos 16 dias do mês de Setembro de 2024, a DISTRIBUIDORA DE FILMES S/A - RIOFILME e
a empresa ARTE VITAL EXIBIÇÕES CINEMATOGRÁFICAS LTDA, inscrita no CNPJ 00.000.000/0001-00.

CLÁUSULA PRIMEIRA - OBJETO
Constitui objeto do presente a contratação de empresa especializada.

Parágrafo Primeiro – O CINECARIOCA JOSÉ WILKER está situado com entrada principal.

Parágrafo Segundo – É expressamente vedada sua utilização por terceiros.

CLÁUSULA SEGUNDA – PRAZO
O prazo da presente contratação é de 24 meses.

Valor Total: R$ 1.216.829,52
Vigência: 24 meses.
"""

print("=" * 60)
print("STEP 1 — Does 'OBJETO' appear in text?")
print("  Found:", bool(re.search(r'OBJETO', TEXT, re.IGNORECASE)))

print()
print("STEP 2 — What does the CURRENT source code do?")
try:
    from infrastructure.extractors.contract_preprocessor import _extract_header
    import inspect
    src = inspect.getsource(_extract_header)
    # Find the object_summary block
    if 'object_summary' in src:
        lines = src.split('\n')
        for i, line in enumerate(lines):
            if 'object_summary' in line or 'OBJETO' in line.upper():
                print(f"  line {i:3d}: {line}")
    else:
        print("  WARNING: object_summary not found in _extract_header source!")
except Exception as e:
    print(f"  ERROR importing: {e}")

print()
print("STEP 3 — Test the CORRECT Fix 3 regex directly:")
m = re.search(
    r'(?:objeto\s*(?:do\s+presente)?|OBJETO)\s*[:\-]?\s*'
    r'(.+?)'
    r'(?=\n\s*(?:'
    r'Valor|VALOR'
    r'|Vig[eê]n'
    r'|Prazo|PRAZO'
    r'|Data\s+da'
    r'|Par[aá]grafo\s+[Pp]rimeiro'
    r'|CL[AÁ]USULA|\u0043L\u00c1USULA'
    r'))',
    TEXT, re.IGNORECASE | re.DOTALL
)
if m:
    result = re.sub(r'\s+', ' ', m.group(1)).strip()
    print(f"  MATCH → '{result[:100]}'")
else:
    print("  NO MATCH — checking boundaries:")
    # Check which boundaries exist in the text
    for kw in ['Valor', 'Vigência', 'Prazo', 'Data da', 'Parágrafo Primeiro', 'CLÁUSULA']:
        found = bool(re.search(r'\n\s*' + re.escape(kw), TEXT, re.IGNORECASE))
        print(f"    '{kw}' boundary present: {found}")

print()
print("STEP 4 — Run full preprocess_text and show object_summary:")
try:
    from infrastructure.extractors.contract_preprocessor import preprocess_text
    r = preprocess_text("DIAG-001", TEXT)
    obj = r["header"].get("object_summary")
    print(f"  object_summary = {repr(obj)}")
    if obj is None:
        print()
        print("  CONCLUSION: Fix 3 regex was NOT applied correctly.")
        print("  Check the exact content of _extract_header in the source file.")
except Exception as e:
    print(f"  ERROR: {e}")

print("=" * 60)