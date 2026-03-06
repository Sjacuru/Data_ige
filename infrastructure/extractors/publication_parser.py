"""
infrastructure/extractors/publication_parser.py

Shared parser: raw gazette text → structured publication dict.

Responsibility
──────────────
One public function:

    parse_publication_text(raw_text, processo_id) -> dict

Takes any raw gazette text — a full D.O.RIO page (masthead + extrato),
a bare EXTRATO block, or a DoWeb numbered structured block — and returns
the same schema every time.

This function is called from two places:

    1. infrastructure/extractors/contract_preprocessor.py
       When _detect_embedded_publication finds a gazette EXTRATO appended
       to the contract PDF, it passes the extrato block here to extract
       structured fields.

    2. infrastructure/extractors/publication_preprocessor.py
       When Stage 3 raw DoWeb publications are post-processed, each
       raw_text entry is passed here to produce the structured JSON
       consumed by the compliance engine (Epic 4).

Both callers receive an identical output schema regardless of source.
The caller is responsible for adding source metadata (e.g. "embedded"
vs "doweb") and saving the result.

Gazette text formats handled
─────────────────────────────
Format A — labelled EXTRATO block (most common):

    DISTRIBUIDORA DE FILMES S/A - RIOFILME
    EXTRATO DE INSTRUMENTO CONTRATUAL
    Processo Instrutivo: FIL-PRO-2023/00482.- CO 01/2024.
    Contrato nº: 2403453/2024.
    Data da Assinatura: 16/09/2024.
    Partes: Distribuidora de Filmes S.A - RIOFILME e Arte Vital ...
    Objeto: Contratação de empresa especializada ...
    Valor Total: R$ 1.216.829,52
    Vigência: 24 meses.

Format B — DoWeb numbered structured block:

    Processo TUR-PRO-2025/01221 1-Objeto: operação do ... 2-Partes:
    RIOTUR e EMPRESA X 3-Instrumento: Contrato nº 059/2023
    4-Data: 03/02/2026 5-Valor: R$ 287.000,00

Format C — D.O.RIO masthead date (appears before the extrato):

    Segunda-feira, 30 de Setembro de 2024
    ...
    EXTRATO DE INSTRUMENTO CONTRATUAL
    ...

Output schema
─────────────
{
  "processo_id":        str | None,   # normalised core ID
  "publication_date":   str | None,   # DD/MM/YYYY — from masthead (Format C)
  "signing_date_in_pub":str | None,   # DD/MM/YYYY — from Data da Assinatura label
  "contract_number":    str | None,   # NNNNNN/YYYY
  "contratante":        str | None,
  "contratada":         str | None,
  "object_summary":     str | None,   # first 400 chars of Objeto field
  "value":              str | None,   # normalised number string e.g. "1.216.829,52"
  "edition":            str | None,   # gazette edition number
  "document_type":      str,          # "contract" | "addendum" | "unknown"
  "warnings":           list[str],    # missing field tags
  "parsed_at":          str,          # ISO timestamp
}

No file I/O. No external dependencies. Testable in isolation.
"""

import re
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# REGEX PATTERNS
# ══════════════════════════════════════════════════════════════════════════════

# ── Publication date from D.O.RIO masthead ────────────────────────────────────
_MASTHEAD_DATE_RE = re.compile(
    r'(?:Segunda|Ter\u00e7a|Quarta|Quinta|Sexta|S\u00e1bado|Domingo)'
    r'(?:-feira)?,?\s+'
    r'(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})',
    re.IGNORECASE,
)

# ── Gazette edition number (Nº 136, No 218, etc.) ────────────────────────────
_EDITION_RE = re.compile(
    r'[Nn][o\u00ba\u00b0°]\s*(\d{3,})'
)

# ── Processo identifier ───────────────────────────────────────────────────────
_PROC_RE = re.compile(
    r'(?:Processo\s+(?:Instrutivo|Administrativo|n[o\u00ba\u00b0°]?)?'
    r'|PROCESSO\s+(?:INSTRUTIVO|ADMINISTRATIVO|N[O\u00ba\u00b0°]?)?)'
    r'\s*[:\-]?\s*([\w\-.]+/\d{4,}(?:/\d+)?(?:\s*[-\u2013.]\s*(?:CO|TP|TA)\s*\d+/\d+)?)',
    re.IGNORECASE,
)

# ── Contract number ───────────────────────────────────────────────────────────
_CNUM_RE = re.compile(
    r'(?:Contrato\s+n[o\u00ba\u00b0°]*'
    r'|Instrumento[:\s]+(?:Termo\s+Aditivo\s+\S+\s+ao\s+)?[Cc]ontrato\s+n[o\u00ba\u00b0°]*'
    r'|CONTRATO\s+N[O\u00ba\u00b0°]*)'
    r'\s*[:\-]?\s*(\d{3,}[/\\]\d{4})',
    re.IGNORECASE,
)

# ── Signing date label ────────────────────────────────────────────────────────
_SIGN_DATE_RE = re.compile(
    r'(?:Data\s+da\s+[Aa]ssinatura|DATA\s+DA\s+ASSINATURA'
    r'|Data[:\s]+\d)'   # Format B shorthand "4-Data: DD/MM/YYYY"
    r'\s*[:\-]?\s*(\d{1,2}/\d{1,2}/\d{4})',
)
# Format B date field specifically: "4-Data: DD/MM/YYYY"
_FORMAT_B_DATE_RE = re.compile(
    r'4\s*[-–]\s*Data\s*[:\-]?\s*(\d{1,2}/\d{1,2}/\d{4})',
    re.IGNORECASE,
)

# ── Parties (Format A labelled block) ────────────────────────────────────────
_PARTIES_RE = re.compile(
    r'(?:Partes|PARTES)\s*[:\-]\s*(.+?)(?=\n|Objeto|OBJETO|$)',
    re.IGNORECASE,
)

# ── Format B numbered fields ──────────────────────────────────────────────────
# "Processo {ID} 1-Objeto: ... 2-Partes: ... 3-Instrumento: ... 4-Data: ... 5-Valor: ..."
_FORMAT_B_TRIGGER_RE = re.compile(
    r'1\s*[-–]\s*Objeto\s*[:\-]',
    re.IGNORECASE,
)
_FORMAT_B_OBJETO_RE = re.compile(
    r'1\s*[-–]\s*Objeto\s*[:\-]\s*(.+?)(?=2\s*[-–]\s*Partes|$)',
    re.IGNORECASE | re.DOTALL,
)
_FORMAT_B_PARTES_RE = re.compile(
    r'2\s*[-–]\s*Partes\s*[:\-]\s*(.+?)(?=3\s*[-–]|$)',
    re.IGNORECASE | re.DOTALL,
)
_FORMAT_B_VALOR_RE = re.compile(
    r'5\s*[-–]\s*Valor\s*[:\-]?\s*R\$\s*([\d.,]+)',
    re.IGNORECASE,
)

# ── Object / Objeto field (Format A) ─────────────────────────────────────────
_OBJETO_RE = re.compile(
    r'(?:Objeto|OBJETO)\s*[:\-]\s*(.+?)(?=\n(?:Valor|VALOR|Vig[eê]ncia|Nota|Fundamento|$)|\Z)',
    re.IGNORECASE | re.DOTALL,
)

# ── Value (Valor Total / Valor) ───────────────────────────────────────────────
_VALOR_RE = re.compile(
    r'(?:Valor\s+Total|VALOR\s+TOTAL|Valor|VALOR)\s*[:\-]?\s*R\$\s*([\d.,]+)',
    re.IGNORECASE,
)

# ── Document type markers ─────────────────────────────────────────────────────
_TYPE_ADDENDUM_RE = re.compile(
    r'EXTRATO\s+DE\s+TERMO\s+ADITIVO'
    r'|EXTRATO\s+ADITIVO'
    r'|Termo\s+Aditivo'
    r'|ADITAMENTO',
    re.IGNORECASE,
)
_TYPE_CONTRACT_RE = re.compile(
    r'EXTRATO\s+DE\s+(?:INSTRUMENTO\s+)?CONTRATUAL?'
    r'|EXTRATO\s+D[OE]\s+CONTRATO'
    r'|EXTRATO\s+DE\s+INSTRUMENTO\s+CONTRATO'
    r'|EXTRATO\s+DE\s+TERMO\s+DE\s+EXECU',
    re.IGNORECASE,
)

_MONTHS_PT = {
    "janeiro": "01", "fevereiro": "02", "março": "03",   "abril": "04",
    "maio":    "05", "junho":     "06", "julho": "07",   "agosto": "08",
    "setembro":"09", "outubro":   "10", "novembro": "11","dezembro": "12",
}


# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ══════════════════════════════════════════════════════════════════════════════

def parse_publication_text(
    raw_text:    str,
    processo_id: str,
) -> dict:
    """
    Parse gazette text and return a structured publication dict.

    The function is source-agnostic: it accepts the full text of a gazette
    page (D.O.RIO masthead + extrato), a bare labelled extrato block, or a
    DoWeb numbered structured block. All return the same schema.

    Args:
        raw_text:    Raw OCR or scraped text containing the publication.
        processo_id: The processo ID being searched for. Used to locate
                     the relevant extrato block when the text contains
                     multiple entries on the same page.

    Returns:
        Structured dict — see module docstring for full schema.
        Never raises; missing fields are None, flagged in "warnings".
    """
    warnings: list = []

    # ── Step 1: Locate the relevant extrato block ─────────────────────────────
    block = _locate_extrato_block(raw_text, processo_id)

    # ── Step 2: Extract gazette-level fields (masthead, edition) ─────────────
    # Always search the full text — masthead can be far from the extrato block
    publication_date = _extract_masthead_date(raw_text)
    edition          = _extract_edition(raw_text)

    # ── Step 3: Extract extrato-level fields ──────────────────────────────────
    if _FORMAT_B_TRIGGER_RE.search(block):
        fields = _parse_format_b(block)
    else:
        fields = _parse_format_a(block)

    # ── Step 4: Normalise processo_id (strip suffix like ".- CO 01/2024") ─────
    pid_in_pub = _normalise_pid(fields.get("processo_id_raw") or processo_id)

    # ── Step 5: Detect document type ─────────────────────────────────────────
    document_type = _detect_document_type(block)

    # ── Step 6: Collect warnings for missing compliance fields ────────────────
    required = {
        "publication_date":    publication_date,
        "signing_date_in_pub": fields.get("signing_date_in_pub"),
        "contratante":         fields.get("contratante"),
        "contratada":          fields.get("contratada"),
    }
    for field_name, value in required.items():
        if not value:
            warnings.append(f"missing:{field_name}")

    return {
        "processo_id":         pid_in_pub,
        "publication_date":    publication_date,
        "signing_date_in_pub": fields.get("signing_date_in_pub"),
        "contract_number":     fields.get("contract_number"),
        "contratante":         fields.get("contratante"),
        "contratada":          fields.get("contratada"),
        "object_summary":      fields.get("object_summary"),
        "value":               fields.get("value"),
        "edition":             edition,
        "document_type":       document_type,
        "warnings":            warnings,
        "parsed_at":           datetime.now().isoformat(),
    }


# ══════════════════════════════════════════════════════════════════════════════
# BLOCK LOCATION
# ══════════════════════════════════════════════════════════════════════════════

def _locate_extrato_block(text: str, processo_id: str) -> str:
    """
    Find the extrato block in the text that belongs to this processo_id.

    Strategy:
    1. Search for the processo_id in the text.
    2. For each occurrence, check whether the surrounding 600 chars back
       and 800 chars forward contain an EXTRATO trigger word. The first
       such occurrence is the relevant block.
    3. If no occurrence is found inside an extrato block, fall back to
       the first EXTRATO trigger in the text — the text may contain only
       one contract and the processo_id format may differ slightly.
    4. If no trigger at all, return the full text (caller may still extract
       partial data from a bare labelled block).
    """
    _EXTRATO_TRIGGER_RE = re.compile(
        r'EXTRATO\s+DE\s+INSTRUMENTO\s+CONTRATUAL'
        r'|EXTRATO\s+INSTRUMENTO\s+CONTRATUAL'
        r'|EXTRATO\s+DE\s+INSTRUMENTO\s+CONTRATO'
        r'|EXTRATO\s+DE\s+CONTRATO'
        r'|EXTRATO\s+DO\s+CONTRATO'
        r'|EXTRATO\s+DE\s+TERMO\s+ADITIVO'
        r'|EXTRATO\s+DE\s+TERMO\s+DE\s+EXECU'
        r'|1\s*[-–]\s*Objeto\s*[:\-]',  # Format B trigger
        re.IGNORECASE,
    )

    # Normalise processo_id for search (strip suffix)
    pid_core = _normalise_pid(processo_id)
    pid_re   = re.compile(re.escape(pid_core), re.IGNORECASE)

    for m in pid_re.finditer(text):
        look_back = max(0, m.start() - 600)
        context   = text[look_back: m.start() + 800]
        if _EXTRATO_TRIGGER_RE.search(context):
            return context

    # Fallback: return text from first extrato trigger to next ~1500 chars
    trig = _EXTRATO_TRIGGER_RE.search(text)
    if trig:
        return text[max(0, trig.start() - 100): trig.start() + 1500]

    return text   # last resort: full text


# ══════════════════════════════════════════════════════════════════════════════
# GAZETTE-LEVEL EXTRACTION
# ══════════════════════════════════════════════════════════════════════════════

def _extract_masthead_date(text: str) -> Optional[str]:
    """Extract publication date from D.O.RIO weekday masthead."""
    m = _MASTHEAD_DATE_RE.search(text)
    if not m:
        return None
    day   = m.group(1).zfill(2)
    month = _MONTHS_PT.get(m.group(2).lower())
    year  = m.group(3)
    if not month:
        return None
    return f"{day}/{month}/{year}"


def _extract_edition(text: str) -> Optional[str]:
    """Extract gazette edition number from masthead area."""
    # Restrict to first 500 chars after any masthead match to avoid
    # edition numbers that appear inside article text
    mh = _MASTHEAD_DATE_RE.search(text)
    search_zone = text[mh.start(): mh.start() + 500] if mh else text[:500]
    m = _EDITION_RE.search(search_zone)
    return m.group(1) if m else None


# ══════════════════════════════════════════════════════════════════════════════
# FORMAT A — LABELLED EXTRATO BLOCK
# ══════════════════════════════════════════════════════════════════════════════

def _parse_format_a(block: str) -> dict:
    """
    Parse a labelled EXTRATO block with named fields:
        Processo Instrutivo: ...
        Contrato nº: ...
        Data da Assinatura: ...
        Partes: ... e ...
        Objeto: ...
        Valor Total: R$ ...
    """
    result: dict = {}

    m = _PROC_RE.search(block)
    result["processo_id_raw"] = m.group(1).strip() if m else None

    m = _CNUM_RE.search(block)
    result["contract_number"] = m.group(1).strip() if m else None

    # Signing date — try label first, then Format B date field
    m = _SIGN_DATE_RE.search(block) or _FORMAT_B_DATE_RE.search(block)
    result["signing_date_in_pub"] = m.group(1).strip() if m else None

    # Parties: split on " e " — first is contratante, second is contratada
    m = _PARTIES_RE.search(block)
    if m:
        raw_parties = m.group(1).strip()
        result["contratante"], result["contratada"] = _split_parties(raw_parties)
    else:
        result["contratante"] = result["contratada"] = None

    # Object summary
    m = _OBJETO_RE.search(block)
    if m:
        raw_obj = re.sub(r'\s+', ' ', m.group(1)).strip()
        result["object_summary"] = raw_obj[:400]
    else:
        result["object_summary"] = None

    # Value — normalise to number string without "R$ "
    m = _VALOR_RE.search(block)
    result["value"] = m.group(1).strip() if m else None

    return result


# ══════════════════════════════════════════════════════════════════════════════
# FORMAT B — DOWEB NUMBERED STRUCTURED BLOCK
# ══════════════════════════════════════════════════════════════════════════════

def _parse_format_b(block: str) -> dict:
    """
    Parse a DoWeb numbered structured block:
        Processo {ID} 1-Objeto: ... 2-Partes: ... 3-Instrumento: ...
        4-Data: DD/MM/YYYY 5-Valor: R$ ...
    """
    result: dict = {}

    m = _PROC_RE.search(block)
    result["processo_id_raw"] = m.group(1).strip() if m else None

    m = _CNUM_RE.search(block)
    result["contract_number"] = m.group(1).strip() if m else None

    # Date is field 4
    m = _FORMAT_B_DATE_RE.search(block) or _SIGN_DATE_RE.search(block)
    result["signing_date_in_pub"] = m.group(1).strip() if m else None

    # Parties from field 2
    m = _FORMAT_B_PARTES_RE.search(block)
    if m:
        raw_parties = re.sub(r'\s+', ' ', m.group(1)).strip()
        result["contratante"], result["contratada"] = _split_parties(raw_parties)
    else:
        result["contratante"] = result["contratada"] = None

    # Object from field 1
    m = _FORMAT_B_OBJETO_RE.search(block)
    if m:
        raw_obj = re.sub(r'\s+', ' ', m.group(1)).strip()
        result["object_summary"] = raw_obj[:400]
    else:
        result["object_summary"] = None

    # Value from field 5
    m = _FORMAT_B_VALOR_RE.search(block)
    result["value"] = m.group(1).strip() if m else None

    return result


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _split_parties(raw: str) -> tuple:
    """
    Split a 'Partes:' string into (contratante, contratada).

    The gazette always lists parties as "A e B". Split on the first " e "
    that appears after a reasonable name length to avoid splitting inside
    a name that contains the word "e" (e.g. "ARTE E CULTURA LTDA").
    """
    # Try splitting on " e " that follows at least 10 non-newline chars
    m = re.search(r'(.{10,}?)\s+e\s+(.+)', raw, re.IGNORECASE | re.DOTALL)
    if m:
        return (
            re.sub(r'\s+', ' ', m.group(1)).strip().rstrip('.,;'),
            re.sub(r'\s+', ' ', m.group(2)).strip().rstrip('.,;'),
        )
    # Fallback: return full string as contratante, None as contratada
    return raw.strip(), None


def _normalise_pid(processo_id: str) -> str:
    """
    Strip known suffix patterns that follow the core processo ID.
    e.g. "FIL-PRO-2023/00482.- CO 01/2024" → "FIL-PRO-2023/00482"
    """
    pid = re.sub(
        r'\s*\.\s*[-–]?\s*(?:CO|TP|TA)\s*\d.*$',
        '',
        processo_id.strip(),
        flags=re.IGNORECASE,
    ).strip().rstrip('.-')
    return pid if pid else processo_id.strip()


def _detect_document_type(block: str) -> str:
    """Classify the extrato as contract, addendum, or unknown."""
    if _TYPE_ADDENDUM_RE.search(block):
        return "addendum"
    if _TYPE_CONTRACT_RE.search(block):
        return "contract"
    return "unknown"