"""
infrastructure/extractors/contract_preprocessor.py

Transforms raw contract text into a structured, clean representation.

Pipeline
--------
1. Noise removal   - strips per-page signatures, letterheads, barcodes, page markers
2. Type detection  - contract / addendum / unknown
3. Header extraction - contract number, processo, date, parties, object
4. Clause segmentation - CLAUSULA blocks with internal paragraph structure
5. Appendix detection  - tables, charts, staff lists, technical specs
6. Embedded publication detection - gazette extracts attached to contract
7. Validation + save  - warns on missing fields, never hard-fails

Input:  raw_text from {processo_id}_raw.json  (data/extractions/)
Output: data/preprocessed/{processo_id}_preprocessed.json
        data/preprocessed/{processo_id}_pub_embedded.flag  (only when pub found)

Usage:
    from infrastructure.extractors.contract_preprocessor import preprocess_contract
    result = preprocess_contract("FIL-PRO-2023/00482")

    # Or process raw text directly (useful in tests):
    from infrastructure.extractors.contract_preprocessor import preprocess_text
    result = preprocess_text(processo_id, raw_text)
"""

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

EXTRACTIONS_DIR  = Path("data/extractions")
PREPROCESSED_DIR = Path("data/preprocessed")

# ── Noise patterns ─────────────────────────────────────────────────────────────

_SIG_RE = re.compile(
    r'Assinado com senha por .{5,120}?\d{2}/\d{2}/\d{4} '
    r'\u00e0s \d{2}:\d{2}:\d{2}\.?',
    re.DOTALL
)
_AUTH_DOC_RE = re.compile(
    r'Documento N[o\u00ba\u00b0][:.]\s*\d{5,}-\d{4}\s*[-\u2013]\s*consulta .{0,120}',
    re.IGNORECASE
)
_AUTH_URL_RE = re.compile(
    r'https?://acesso\.processo\.rio/sigaex/public/app/autenticar\S*',
    re.IGNORECASE
)
_BARCODE_RE  = re.compile(r'\b[A-Z]{2,6}[A-Z]{2,4}\d{6,12}\b')
_PAGENUM_RE  = re.compile(r'P[a\u00e1]gina\s+\d+\s+de\s+\d+', re.IGNORECASE)
_PAGENUM2_RE = re.compile(r'^\s*\d+\s+de\s+\d+\s*$', re.MULTILINE)
_LTRHEAD_RE  = re.compile(
    r'(?:^.{5,80}$\n){1,5}(?:Tel\..{0,60}|CEP.{0,40})\n?',
    re.MULTILINE
)

_NOISE_PATTERNS = [
    (_SIG_RE,       "per_page_signatures"),
    (_AUTH_DOC_RE,  "per_page_signatures"),
    (_AUTH_URL_RE,  "per_page_signatures"),
    (_BARCODE_RE,   "barcodes"),
    (_PAGENUM_RE,   "page_markers"),
    (_PAGENUM2_RE,  "page_markers"),
    (_LTRHEAD_RE,   "per_page_letterhead"),
]

# ── Document type ──────────────────────────────────────────────────────────────

_ADDENDUM_RE = re.compile(
    r'TERMO\s+ADITIVO|ADITAMENTO|APOSTILAMENTO', re.IGNORECASE
)
_CONTRACT_RE = re.compile(
    r'CONTRATO\s+N[o\u00ba\u00b0]|TERMO\s+DE\s+CONTRATO'
    r'|TERMO\s+DE\s+COLABORA|TERMO\s+DE\s+EXECU|CONTRATO\s+DE\s+PATROC',
    re.IGNORECASE
)

# ── Header patterns ────────────────────────────────────────────────────────────

_CNUM_RE = re.compile(
    r'(?:Contrato|CONTRATO)\s*[Nn\u00ba\u00b0oO.]*\s*[:\-]?\s*(\d{4,}[/\\]\d{4})'
)
_PROC_RE = re.compile(
    r'(?:Processo\s+(?:Instrutivo|Administrativo|n[o\u00ba\u00b0]?)?'
    r'|PROCESSO\s+(?:INSTRUTIVO|ADMINISTRATIVO|N[O\u00ba\u00b0]?)?)'
    r'\s*[:\-]?\s*([\w\-.]+/\d{4}(?:/\d+)?(?:\s*[-\u2013.]\s*(?:CO|TP|TA)\s*\d+/\d+)?)',
    re.IGNORECASE
)
_DATE_LBL_RE = re.compile(
    r'(?:Data\s+da\s+[Aa]ssinatura|DATA\s+DA\s+ASSINATURA)\s*[:\-]?\s*'
    r'(\d{1,2}/\d{1,2}/\d{4})'
)
_DATE_PROSE_RE = re.compile(
    r'Aos\s+(\d{1,2})\s+dias\s+do\s+m[e\u00ea]s\s+de\s+(\w+)\s+do\s+ano\s+de\s+(\d{4})',
    re.IGNORECASE
)
_CTANTE_RE = re.compile(
    r'(?:CONTRATANTE|contratante)[,:]?\s*([A-Z\u00c1\u00c9\u00cd\u00d3\u00da][^\n,;]{5,120})'
)
_CTADA_RE = re.compile(
    r'(?:CONTRATADA|contratada)[,:]?\s*([A-Z\u00c1\u00c9\u00cd\u00d3\u00da][^\n,;]{5,120})'
)
_MONTHS_PT = {
    "janeiro":"01","fevereiro":"02","mar\u00e7o":"03","abril":"04",
    "maio":"05","junho":"06","julho":"07","agosto":"08",
    "setembro":"09","outubro":"10","novembro":"11","dezembro":"12",
}

# ── Clause patterns ────────────────────────────────────────────────────────────

_CLAUSE_HDR_RE = re.compile(
    r'^(CL[A\u00c1]USULA\s+([A-Z\u00c1\u00c9\u00cd\u00d3\u00da\u00c0\u00c2\u00ca'
    r'\u00d4\u00c3\u00d5\u00dc\u00c7\s]+?)\s*[–\-]\s*(.+?))$',
    re.MULTILINE | re.IGNORECASE
)
_PARA_HDR_RE = re.compile(
    r'^(Par[a\u00e1]grafo\s+(?:[A-Z\u00c1\u00c9\u00cd\u00d3\u00da][a-z\u00e1\u00e9'
    r'\u00ed\u00f3\u00fa\u00e0\u00e2\u00ea\u00f4\u00e3\u00f5\u00fc\u00e7]+'
    r'|\d+[o\u00ba\u00b0]?|\bU\u00fanico\b|\b\u00fanico\b))',
    re.MULTILINE
)

# ── Appendix patterns ──────────────────────────────────────────────────────────

_APPENDIX_KEYS = [
    "LISTAGEM","QUADRO","ANEXO","TABELA","CRONOGRAMA",
    "TERMO DE REFER","MODELO","PLANILHA","ESPECIFICA","PROPOSTA","DECLARA",
]
_APPENDIX_RE = re.compile(
    r'^(' + '|'.join(re.escape(k) for k in _APPENDIX_KEYS) + r')',
    re.MULTILINE | re.IGNORECASE
)

# ── Embedded publication patterns ──────────────────────────────────────────────
# Intentionally excludes bare "Diario Oficial" — too common inside clause bodies.
# Requires an actual EXTRATO block or D.O.RIO masthead.

_PUB_TRIGGER_RE = re.compile(
    r'EXTRATO\s+DE\s+INSTRUMENTO\s+CONTRATUAL'
    r'|EXTRATO\s+DE\s+INSTRUMENTO\s+CONTRATO'
    r'|EXTRATO\s+DE\s+CONTRATO'
    r'|EXTRATO\s+DO\s+CONTRATO'
    r'|EXTRATO\s+DE\s+TERMO\s+DE\s+EXECU'
    r'|D\.O\.RIO\b',
    re.IGNORECASE
)
_PUB_DATE_RE    = _DATE_LBL_RE   # same pattern as contract signing date label
_PUB_EDITION_RE = re.compile(r'[Nn][o\u00ba\u00b0]\s*(\d{3,})')
_PUB_PARTIES_RE = re.compile(
    r'(?:Partes|PARTES)\s*[:\-]\s*(.+?)(?=\n|Objeto|OBJETO)', re.IGNORECASE
)
_PUB_END_RE = re.compile(
    r'^(?:SECRETARIA\s+MUNICIPAL|PREFEITURA|DISTRIBUIDORA\s+DE)',
    re.MULTILINE
)


# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ══════════════════════════════════════════════════════════════════════════════

def preprocess_contract(processo_id: str) -> Optional[dict]:
    """Load raw JSON, run pipeline, save preprocessed JSON. Returns dict or None."""
    safe     = _sanitize(processo_id)
    raw_path = EXTRACTIONS_DIR / f"{safe}_raw.json"
    if not raw_path.exists():
        logger.error(f"Raw file not found: {raw_path}")
        return None
    with open(raw_path, encoding="utf-8") as f:
        record = json.load(f)
    raw_text = record.get("raw_text", "")
    if not raw_text:
        logger.warning(f"{processo_id}: raw_text is empty")
        return None
    return preprocess_text(processo_id, raw_text)


def preprocess_text(processo_id: str, raw_text: str) -> dict:
    """Run full pipeline on raw text string. Never raises — errors go to warnings."""
    warnings = []
    clean_text, noise_removed = _remove_noise(raw_text)
    document_type  = _detect_type(clean_text)
    header         = _extract_header(clean_text, warnings)
    clauses        = _segment_clauses(clean_text)
    appendices     = _detect_appendices(clean_text)
    embedded_pub   = _detect_embedded_publication(clean_text, processo_id)

    for field in ("signing_date", "contratante", "contratada"):
        if not header.get(field):
            warnings.append(f"missing_header_field:{field}")
    if not clauses:
        warnings.append("no_clauses_detected")

    result = {
        "processo_id":          processo_id,
        "preprocessed_at":      datetime.now().isoformat(),
        "document_type":        document_type,
        "header":               header,
        "clauses":              clauses,
        "appendices":           appendices,
        "embedded_publication": embedded_pub,
        "noise_removed":        noise_removed,
        "warnings":             warnings,
    }
    _save(processo_id, result, embedded_pub)
    return result


# ══════════════════════════════════════════════════════════════════════════════
# STEP 1 — NOISE REMOVAL
# ══════════════════════════════════════════════════════════════════════════════

def _remove_noise(text: str):
    removed = set()
    clean   = text
    for pattern, category in _NOISE_PATTERNS:
        new = pattern.sub("", clean)
        if new != clean:
            removed.add(category)
        clean = new
    clean = re.sub(r'\n{3,}', '\n\n', clean).strip()
    return clean, sorted(removed)


# ══════════════════════════════════════════════════════════════════════════════
# STEP 2 — DOCUMENT TYPE DETECTION
# ══════════════════════════════════════════════════════════════════════════════

def _detect_type(text: str) -> str:
    probe = text[:800]
    if _ADDENDUM_RE.search(probe):
        return "addendum"
    if _CONTRACT_RE.search(probe):
        return "contract"
    return "unknown"


# ══════════════════════════════════════════════════════════════════════════════
# STEP 3 — HEADER EXTRACTION
# ══════════════════════════════════════════════════════════════════════════════

def _extract_header(text: str, warnings: list) -> dict[str, str | None]:
# def _extract_header(text: str, warnings: list) -> dict:

    header: dict[str, str | None] = {
        "contract_number": None,
        "processo_id_in_document": None,
        "signing_date": None,
        "contratante": None,
        "contratada": None,
        "object_summary": None,
    }

    m = _CNUM_RE.search(text)
    if m: header["contract_number"] = m.group(1).strip()

    m = _PROC_RE.search(text)
    if m: header["processo_id_in_document"] = m.group(1).strip()

    m = _DATE_LBL_RE.search(text)
    if m:
        header["signing_date"] = m.group(1).strip()
    else:
        m = _DATE_PROSE_RE.search(text)
        if m:
            day   = m.group(1).zfill(2)
            month = _MONTHS_PT.get(m.group(2).lower(), "??")
            header["signing_date"] = f"{day}/{month}/{m.group(3)}"

    m = _CTANTE_RE.search(text)
    if m: header["contratante"] = _clean_party(m.group(1))

    m = _CTADA_RE.search(text)
    if m: header["contratada"] = _clean_party(m.group(1))

    if not header["contratante"] or not header["contratada"]:
        _parties_from_prose(text, header)

    m = re.search(
        r'(?:objeto\s*(?:do\s+presente)?|OBJETO)[:\-]?\s*\n?\s*([^\n]{20,400})',
        text, re.IGNORECASE
    )
    if m: header["object_summary"] = m.group(1).strip()[:400]

    return header


def _clean_party(raw: str) -> str:
    c = raw.strip().rstrip(".,;:-")
    c = re.sub(r'\s*,?\s*inscrit[ao].{0,200}$', '', c, flags=re.IGNORECASE)
    c = re.sub(r'\s*,?\s*CNPJ.{0,100}$',        '', c, flags=re.IGNORECASE)
    return c.strip()


def _parties_from_prose(text: str, header: dict) -> None:
    m = re.search(
        r'entre\s+(?:si\s+)?(?:celebram\s+)?[ao]\s+'
        r'([A-Z\u00c1\u00c9\u00cd\u00d3\u00da][^,\n]{5,120})'
        r'(?:,|\s+e\s+[ao]\s+empresa\s+)'
        r'([A-Z\u00c1\u00c9\u00cd\u00d3\u00da][^,\n]{5,120})',
        text, re.IGNORECASE
    )
    if m:
        if not header["contratante"]: header["contratante"] = _clean_party(m.group(1))
        if not header["contratada"]:  header["contratada"]  = _clean_party(m.group(2))


# ══════════════════════════════════════════════════════════════════════════════
# STEP 4 — CLAUSE SEGMENTATION
# ══════════════════════════════════════════════════════════════════════════════

def _segment_clauses(text: str) -> list:
    clauses  = []
    matches  = list(_CLAUSE_HDR_RE.finditer(text))
    for i, match in enumerate(matches):
        full_title = match.group(1).strip()
        ordinal    = match.group(2).strip()
        title      = match.group(3).strip()
        start      = match.end()
        end        = matches[i+1].start() if i+1 < len(matches) else len(text)
        raw        = text[start:end].strip()
        # Clip at first appendix marker inside this block
        app_m = _APPENDIX_RE.search(raw)
        if app_m:
            raw = raw[:app_m.start()].strip()
        content, paragraphs = _parse_content(raw)
        clauses.append({
            "number":     ordinal,
            "title":      title,
            "full_title": full_title,
            "content":    content,
            "paragraphs": paragraphs,
        })
    return clauses


def _parse_content(raw: str):
    para_ms = list(_PARA_HDR_RE.finditer(raw))
    if not para_ms:
        return raw.strip(), []
    paragraphs = []
    for j, pm in enumerate(para_ms):
        p_end  = para_ms[j+1].start() if j+1 < len(para_ms) else len(raw)
        p_text = raw[pm.start():p_end].strip()
        p_hdr  = pm.group(1).strip()
        p_body = p_text[len(p_hdr):].strip().lstrip("\u2013-: \n")
        paragraphs.append({"header": p_hdr, "content": p_body})
    return raw.strip(), paragraphs


# ══════════════════════════════════════════════════════════════════════════════
# STEP 5 — APPENDIX DETECTION
# ══════════════════════════════════════════════════════════════════════════════

def _detect_appendices(text: str) -> list:
    appendices = []
    clause_ms  = list(_CLAUSE_HDR_RE.finditer(text))
    scan_from  = clause_ms[-1].start() if clause_ms else 0
    post       = text[scan_from:]
    app_ms     = list(_APPENDIX_RE.finditer(post))
    for k, am in enumerate(app_ms):
        h_end  = post.find('\n', am.start())
        header = post[am.start():h_end].strip() if h_end != -1 \
                 else post[am.start():am.start()+80].strip()
        c_s    = (h_end+1) if h_end != -1 else am.start()+len(header)
        c_e    = app_ms[k+1].start() if k+1 < len(app_ms) else len(post)
        sample = post[c_s:c_s+200]
        appendices.append({
            "index":  k+1,
            "header": header,
            "type":   "table" if (sum(1 for c in sample if c.isdigit()) / max(len(sample),1)) > 0.15
                      else "text",
        })
    return appendices


# ══════════════════════════════════════════════════════════════════════════════
# STEP 6 — EMBEDDED PUBLICATION DETECTION
# ══════════════════════════════════════════════════════════════════════════════

def _detect_embedded_publication(text: str, processo_id: str) -> dict:
    base = {
        "found": False, "processo_id_in_pub": None,
        "publication_date": None, "edition": None,
        "contratante_pub": None, "contratada_pub": None, "raw_block": None,
    }
    match = _PUB_TRIGGER_RE.search(text)
    if not match:
        return base

    block_start = match.start()
    suffix      = text[block_start+50:]
    end_ms      = list(_PUB_END_RE.finditer(suffix))
    block_end   = (block_start+50+end_ms[0].start()) if end_ms else len(text)
    raw_block   = text[block_start:block_end].strip()

    date_m    = _PUB_DATE_RE.search(raw_block)
    edition_m = _PUB_EDITION_RE.search(raw_block)
    parties_m = _PUB_PARTIES_RE.search(raw_block)
    proc_m    = _PROC_RE.search(raw_block)

    # Require a publication date — without it we cannot do compliance checks
    # and the block is likely just a clause reference, not a real publication
    if not date_m:
        return base

    pub_contratante = pub_contratada = None
    if parties_m:
        pts = parties_m.group(1).strip()
        if " e " in pts:
            p1, p2 = pts.split(" e ", 1)
            pub_contratante, pub_contratada = p1.strip(), p2.strip()

    return {
        "found":              True,
        "processo_id_in_pub": proc_m.group(1).strip() if proc_m else None,
        "publication_date":   date_m.group(1),
        "edition":            edition_m.group(1) if edition_m else None,
        "contratante_pub":    pub_contratante,
        "contratada_pub":     pub_contratada,
        "raw_block":          raw_block[:1000],
    }


# ══════════════════════════════════════════════════════════════════════════════
# SAVE + HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _save(processo_id: str, result: dict, embedded_pub: dict) -> None:
    PREPROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out = PREPROCESSED_DIR / f"{_sanitize(processo_id)}_preprocessed.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    logger.info(f"   \u2713 Saved: {out.name}")
    if embedded_pub.get("found"):
        flag = PREPROCESSED_DIR / f"{_sanitize(processo_id)}_pub_embedded.flag"
        flag.write_text(processo_id, encoding="utf-8")
        logger.info(f"   \U0001f4cc Embedded publication flag: {flag.name}")


def _sanitize(pid: str) -> str:
    return re.sub(r'[^\w\-]', '_', pid)


# ══════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if len(sys.argv) < 2:
        print("Usage: python contract_preprocessor.py <processo_id>")
        sys.exit(1)
    pid    = sys.argv[1]
    result = preprocess_contract(pid)
    if result:
        print(f"\n{'='*60}")
        print(f"Type         : {result['document_type']}")
        print(f"Signing date : {result['header'].get('signing_date')}")
        print(f"Contratante  : {result['header'].get('contratante')}")
        print(f"Contratada   : {result['header'].get('contratada')}")
        print(f"Clauses      : {len(result['clauses'])}")
        print(f"Appendices   : {len(result['appendices'])}")
        print(f"Embedded pub : {result['embedded_publication']['found']}")
        print(f"Warnings     : {result['warnings']}")
        print(f"Noise removed: {result['noise_removed']}")
        print(f"{'='*60}")
    else:
        print(f"No raw file found for: {pid}")
        sys.exit(1)