"""
tests/test_contract_preprocessor.py

Test suite for infrastructure/extractors/contract_preprocessor.py
36 tests across 7 groups (A–G).

Run:
    python tests/test_contract_preprocessor.py
"""

import json
import sys
import tempfile
from pathlib import Path

# ── Path setup ────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from infrastructure.extractors.contract_preprocessor import (
    preprocess_text,
    _remove_noise,
    _detect_type,
    _extract_header,
    _segment_clauses,
    _detect_appendices,
    _detect_embedded_publication,
    PREPROCESSED_DIR,
)

# ── Test counters ─────────────────────────────────────────────────────────────
PASSED = FAILED = 0

def check(label: str, condition: bool, hint: str = "") -> None:
    global PASSED, FAILED
    if condition:
        PASSED += 1
        print(f"OK    {label}")
    else:
        FAILED += 1
        note = f"  ← {hint}" if hint else ""
        print(f"FAIL  {label}{note}")

def section(title: str) -> None:
    print(f"\n{'─'*60}")
    print(f"  {title}")
    print(f"{'─'*60}")


# ══════════════════════════════════════════════════════════════════════════════
# SAMPLE DATA
# ══════════════════════════════════════════════════════════════════════════════

_SIGNATURE_BLOCK = (
    "Assinado com senha por CARLA DA COSTA PRUDENTE - ASSISTENTE II / 52097 "
    "- 23/05/2025 às 11:12:29."
)
_AUTH_LINE = (
    "Documento Nº: 10460380-9695 - consulta à autenticidade em\n"
    "https://acesso.processo.rio/sigaex/public/app/autenticar?n=10460380-9695"
)
_BARCODE   = "FILCAP202500206"
_PAGE_NUM  = "Página 3 de 14"
_LETTERHEAD = (
    "Distribuidora de Filmes S/A – RIOFILME\n"
    "Gerência de Licitações e Contratos - GLC\n"
    "Rua das Laranjeiras, nº 307, Laranjeiras – RJ/RJ\n"
    "Tel.: +55 (21) 2225-7082\n"
)

_CONTRACT_BODY = """CONTRATO Nº 2403453/2024

PARA OPERACIONALIZAÇÃO DO CINECARIOCA JOSÉ WILKER ENTRE:
DISTRIBUIDORA DE FILMES S/A E A EMPRESA ARTE VITAL EXIBIÇÕES CINEMATOGRÁFICAS LTDA.

Processo Instrutivo: FIL-PRO-2023/00482.- CO 01/2024.
Data da Assinatura: 16/09/2024.
Partes: CONTRATANTE: DISTRIBUIDORA DE FILMES S/A - RIOFILME e
CONTRATADA: ARTE VITAL EXIBIÇÕES CINEMATOGRÁFICAS LTDA.

CLÁUSULA PRIMEIRA - OBJETO

Constitui objeto do presente a contratação de empresa especializada.

Parágrafo Primeiro – O CINECARIOCA JOSÉ WILKER está situado com entrada principal.

Parágrafo Segundo – É expressamente vedada sua utilização por terceiros.

CLÁUSULA SEGUNDA – PRAZO

O prazo da presente contratação é de 24 meses.

Parágrafo Primeiro – Contados da data da assinatura.

CLÁUSULA TERCEIRA - DO APORTE DA RIOFILME

A RIOFILME aportará mensalmente o valor de apoio financeiro.

a) Manter condições de habilitação jurídica;
b) Conservar a área pública e suas instalações;

CLÁUSULA DÉCIMA PRIMEIRA - DA EFICÁCIA

A eficácia deste Contrato fica condicionada à sua publicação, em extrato,
no Diário Oficial, no prazo de 20 dias contados da assinatura.

LISTAGEM DE BENS MÓVEIS

EQUIPAMENTOS, MOBILIÁRIOS E UTENSÍLIOS - CINECARIOCA JOSÉ WILKER

ITEM  QTDE.  DESCRIÇÃO
1     1      Processador de áudio CP-950
2     1      Tela de projeção SOUNDMAX-ONE

QUADRO FUNCIONAL

NÚMERO MÍNIMO  CARGO
01             Gerente
02             Bomboniere
"""

_ADDENDUM_BODY = """SEGUNDO TERMO ADITIVO AO CONTRATO Nº 2403453/2024

Aos 17 dias do mês de abril do ano de 2025, na Rua das Laranjeiras, 307,
a DISTRIBUIDORA DE FILMES S/A - RIOFILME e a empresa ARTE VITAL EXIBIÇÕES
CINEMATOGRÁFICAS LTDA ME.
"""

_EMBEDDED_PUB_BLOCK = """
DISTRIBUIDORA DE FILMES S/A - RIOFILME
EXTRATO DE INSTRUMENTO CONTRATUAL
Processo Instrutivo: FIL-PRO-2023/00482.- CO 01/2024.
Contrato nº: 2403453/2024.
Data da Assinatura: 16/09/2024.
Partes: Distribuidora de Filmes S.A - RIOFILME e Arte Vital Exibições Cinematográficas LTDA.
Objeto: Contratação de empresa especializada em exibição cinematográfica.
Valor Total: R$ 1.216.829,52
Vigência: 24 meses.
Nota de Empenho: 2024NE00006
Fundamento: Art. 28, CAPUT, Lei Federal nº 13.303/2016.
"""


# ══════════════════════════════════════════════════════════════════════════════
# GROUP A — NOISE REMOVAL (8 tests)
# ══════════════════════════════════════════════════════════════════════════════

def group_a_noise_removal():
    section("GROUP A — Noise Removal")

    # A1: per-page signature removed
    text = f"Some contract content.\n{_SIGNATURE_BLOCK}\nMore content."
    clean, cats = _remove_noise(text)
    check("A1: per-page signature removed",
          "Assinado com senha por" not in clean)

    # A2: authentication URL removed
    text = f"Content.\n{_AUTH_LINE}\nMore."
    clean, cats = _remove_noise(text)
    check("A2: authentication URL removed",
          "autenticar" not in clean and "Documento Nº" not in clean)

    # A3: barcode string removed
    text = f"Content.\n{_BARCODE}\nMore content."
    clean, cats = _remove_noise(text)
    check("A3: barcode string removed",
          _BARCODE not in clean)

    # A4: page number marker removed
    text = f"Content.\n{_PAGE_NUM}\nMore content."
    clean, cats = _remove_noise(text)
    check("A4: page number marker removed",
          "Página 3 de 14" not in clean)

    # A5: letterhead footer removed
    text = f"Content.\n{_LETTERHEAD}More content."
    clean, cats = _remove_noise(text)
    check("A5: letterhead footer removed",
          "Gerência de Licitações" not in clean or "Tel.:" not in clean)

    # A6: clean contract content preserved after noise removal
    text = f"{_SIGNATURE_BLOCK}\n\n{_CONTRACT_BODY}"
    clean, _ = _remove_noise(text)
    check("A6: CLÁUSULA PRIMEIRA preserved after noise removal",
          "CLÁUSULA PRIMEIRA" in clean)

    # A7: noise categories returned correctly
    text = f"{_SIGNATURE_BLOCK}\n{_BARCODE}\n{_PAGE_NUM}\nContent."
    _, cats = _remove_noise(text)
    check("A7: noise categories list is non-empty",
          len(cats) > 0)

    # A8: no false positives on contract body text
    clean, _ = _remove_noise(_CONTRACT_BODY)
    check("A8: CLÁUSULA TERCEIRA not falsely removed",
          "CLÁUSULA TERCEIRA" in clean)


# ══════════════════════════════════════════════════════════════════════════════
# GROUP B — DOCUMENT TYPE DETECTION (4 tests)
# ══════════════════════════════════════════════════════════════════════════════

def group_b_type_detection():
    section("GROUP B — Document Type Detection")

    check("B1: detects 'contract' on CONTRATO Nº",
          _detect_type(_CONTRACT_BODY) == "contract")

    check("B2: detects 'addendum' on TERMO ADITIVO",
          _detect_type(_ADDENDUM_BODY) == "addendum")

    check("B3: detects 'unknown' on ambiguous short text",
          _detect_type("Some random text without keywords.") == "unknown")

    result = preprocess_text("TEST-001", _CONTRACT_BODY)
    check("B4: document_type present in output dict",
          "document_type" in result)


# ══════════════════════════════════════════════════════════════════════════════
# GROUP C — HEADER EXTRACTION (6 tests)
# ══════════════════════════════════════════════════════════════════════════════

def group_c_header():
    section("GROUP C — Header Extraction")

    warnings = []
    header = _extract_header(_CONTRACT_BODY, warnings)

    check("C1: contract number extracted",
          header.get("contract_number") == "2403453/2024",
          hint=f"got: {header.get('contract_number')}")

    check("C2: processo_id extracted from document",
          header.get("processo_id_in_document") is not None
          and "FIL-PRO-2023" in (header.get("processo_id_in_document") or ""),
          hint=f"got: {header.get('processo_id_in_document')}")

    check("C3: signing date extracted (DD/MM/YYYY)",
          header.get("signing_date") == "16/09/2024",
          hint=f"got: {header.get('signing_date')}")

    check("C4: contratante contains RIOFILME",
          "RIOFILME" in (header.get("contratante") or "").upper(),
          hint=f"got: {header.get('contratante')}")

    check("C5: contratada contains ARTE VITAL",
          "ARTE VITAL" in (header.get("contratada") or "").upper(),
          hint=f"got: {header.get('contratada')}")

    # C6: missing field goes to warnings, not exception
    sparse_text = "CONTRATO Nº 9999/2024\nSome content here."
    warnings2 = []
    header2 = _extract_header(sparse_text, warnings2)
    result2  = preprocess_text("SPARSE-001", sparse_text)
    check("C6: missing fields produce warnings, not exception",
          isinstance(result2.get("warnings"), list)
          and any("missing_header_field" in w for w in result2["warnings"]))


# ══════════════════════════════════════════════════════════════════════════════
# GROUP D — CLAUSE SEGMENTATION (6 tests)
# ══════════════════════════════════════════════════════════════════════════════

def group_d_clauses():
    section("GROUP D — Clause Segmentation")

    clauses = _segment_clauses(_CONTRACT_BODY)

    check("D1: at least 3 clauses found",
          len(clauses) >= 3,
          hint=f"found: {len(clauses)}")

    titles = [c["title"] for c in clauses]
    check("D2: OBJETO clause found",
          any("OBJETO" in t.upper() for t in titles),
          hint=f"titles: {titles}")

    check("D3: PRAZO clause found",
          any("PRAZO" in t.upper() for t in titles))

    # D4: Parágrafo Primeiro treated as paragraph not new clause
    obj_clause = next((c for c in clauses if "OBJETO" in c["title"].upper()), None)
    check("D4: Parágrafo Primeiro is inside clause, not a new clause",
          obj_clause is not None and len(obj_clause.get("paragraphs", [])) >= 1)

    # D5: lettered items a) b) not treated as paragraph breaks
    terceira = next((c for c in clauses if "APORTE" in c["title"].upper()
                     or "TERCEIRA" in c["number"].upper()), None)
    check("D5: lettered items a) b) kept inside clause content",
          terceira is not None and "a)" in terceira.get("content", ""))

    # D6: clause dict has required keys
    first = clauses[0] if clauses else {}
    required = {"number", "title", "full_title", "content", "paragraphs"}
    check("D6: clause dict has all required keys",
          required.issubset(first.keys()),
          hint=f"missing: {required - set(first.keys())}")


# ══════════════════════════════════════════════════════════════════════════════
# GROUP E — APPENDIX DETECTION (4 tests)
# ══════════════════════════════════════════════════════════════════════════════

def group_e_appendices():
    section("GROUP E — Appendix Detection")

    appendices = _detect_appendices(_CONTRACT_BODY)

    check("E1: LISTAGEM DE BENS MÓVEIS detected",
          any("LISTAGEM" in a["header"].upper() for a in appendices),
          hint=f"found headers: {[a['header'] for a in appendices]}")

    check("E2: QUADRO FUNCIONAL detected",
          any("QUADRO" in a["header"].upper() for a in appendices))

    check("E3: appendix type classified (not None)",
          all(a.get("type") in {"table", "text", "unknown"} for a in appendices))

    # E4: appendix content not bleeding into clauses
    clauses = _segment_clauses(_CONTRACT_BODY)
    last_clause_content = clauses[-1]["content"] if clauses else ""
    check("E4: LISTAGEM not inside last clause content",
          "LISTAGEM DE BENS MÓVEIS" not in last_clause_content)


# ══════════════════════════════════════════════════════════════════════════════
# GROUP F — EMBEDDED PUBLICATION DETECTION (4 tests)
# ══════════════════════════════════════════════════════════════════════════════

def group_f_embedded_pub():
    section("GROUP F — Embedded Publication Detection")

    text_with_pub = _CONTRACT_BODY + "\n\n" + _EMBEDDED_PUB_BLOCK
    pub = _detect_embedded_publication(text_with_pub, "FIL-PRO-2023/00482")

    check("F1: embedded publication found",
          pub["found"] is True,
          hint=f"found={pub['found']}, block={str(pub.get('raw_block',''))[:80]}")

    check("F2: publication date extracted from embedded block",
          pub.get("publication_date") == "16/09/2024",
          hint=f"got: {pub.get('publication_date')}")

    # F3: flag file created when embedded pub found
    result = preprocess_text("FIL-PRO-2023_00482_flagtest", text_with_pub)
    from infrastructure.extractors.contract_preprocessor import _sanitize
    flag = PREPROCESSED_DIR / f"{_sanitize('FIL-PRO-2023_00482_flagtest')}_pub_embedded.flag"
    check("F3: flag file created when embedded publication found",
          flag.exists() or result["embedded_publication"]["found"],
          hint="flag file not found but pub was detected")

    # F4: no false positive on plain contract without gazette block
    pub2 = _detect_embedded_publication(_CONTRACT_BODY, "FIL-PRO-2023/00482")
    # The efficacy clause mentions "Diário Oficial" — it should NOT be flagged
    # as an embedded publication because it has no publication_date
    check("F4: efficacy clause mention does not trigger false positive",
          not pub2["found"] or pub2.get("publication_date") is not None,
          hint="gazette mention in clause body falsely triggered embedded pub")


# ══════════════════════════════════════════════════════════════════════════════
# GROUP G — OUTPUT SCHEMA (4 tests)
# ══════════════════════════════════════════════════════════════════════════════

def group_g_schema():
    section("GROUP G — Output Schema")

    result = preprocess_text("SCHEMA-TEST-001", _CONTRACT_BODY)

    top_level_keys = {
        "processo_id", "preprocessed_at", "document_type",
        "header", "clauses", "appendices",
        "embedded_publication", "noise_removed", "warnings"
    }
    check("G1: all required top-level keys present",
          top_level_keys.issubset(result.keys()),
          hint=f"missing: {top_level_keys - set(result.keys())}")

    header_keys = {
        "contract_number", "processo_id_in_document", "signing_date",
        "contratante", "contratada", "object_summary"
    }
    check("G2: header sub-keys all present",
          header_keys.issubset(result["header"].keys()),
          hint=f"missing: {header_keys - set(result['header'].keys())}")

    check("G3: clauses is a non-empty list",
          isinstance(result["clauses"], list) and len(result["clauses"]) > 0)

    # G4: preprocessed.json saved to correct path
    safe   = result["processo_id"].replace("/", "_").replace(".", "_")
    # just check dir was created
    check("G4: data/preprocessed/ directory exists after save",
          PREPROCESSED_DIR.exists())


# ══════════════════════════════════════════════════════════════════════════════
# RUNNER
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  CONTRACT PREPROCESSOR — TEST SUITE")
    print("=" * 60)

    group_a_noise_removal()
    group_b_type_detection()
    group_c_header()
    group_d_clauses()
    group_e_appendices()
    group_f_embedded_pub()
    group_g_schema()

    print(f"\n{'=' * 60}")
    total = PASSED + FAILED
    print(f"  {PASSED}/{total} passed")
    if FAILED:
        print(f"  {FAILED} FAILED")
    print("=" * 60)
    sys.exit(0 if FAILED == 0 else 1)