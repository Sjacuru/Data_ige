"""
infrastructure/extractors/publication_preprocessor.py

Stage 3 post-processor: raw DoWeb publications → structured publication JSON.

Responsibility
──────────────
Reads the multi-document raw JSON produced by Stage 3 (downloader.py):
    data/extractions/{pid}_publications_raw.json

For each publication record that passed OCR quality checks, calls
publication_parser.parse_publication_text() to extract structured fields.

Saves the result to:
    data/preprocessed/{pid}_publication_structured.json

This file handles all I/O, source metadata, and multi-document merging.
The text parsing logic lives entirely in publication_parser.py.

Output schema
─────────────
{
  "processo_id":         "FIL-PRO-2023/00482",
  "source":              "doweb",
  "publication_date":    "30/09/2024",      // gazette masthead date (preferred)
                                            // or publication_metadata.publication_date
                                            // from searcher (fallback)
  "signing_date_in_pub": "16/09/2024",      // Data da Assinatura inside extrato
  "contract_number":     "2403453/2024",
  "contratante":         "Distribuidora de Filmes S.A - RIOFILME",
  "contratada":          "Arte Vital Exibições Cinematográficas LTDA",
  "object_summary":      "Contratação de empresa especializada...",
  "value":               "1.216.829,52",
  "edition":             "136",
  "document_type":       "contract",
  "documents_found":     2,                 // total in raw JSON
  "documents_parsed":    1,                 // quality_passes=True
  "warnings":            [],
  "parsed_at":           "..."
}

Multi-document note
───────────────────
A single processo may have more than one DoWeb result (e.g. original contract
publication + addendum). This module consolidates them: it picks the record
with content_hint="structured_contract" as the primary source for party and
date fields, and preserves all parsed records in "all_publications" for
Epic 4's compliance engine to inspect.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from infrastructure.extractors.publication_parser import parse_publication_text

logger = logging.getLogger(__name__)

EXTRACTIONS_DIR  = Path("data/extractions")
PREPROCESSED_DIR = Path("data/preprocessed")


# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ══════════════════════════════════════════════════════════════════════════════

def preprocess_publication(processo_id: str) -> Optional[dict]:
    """
    Load raw publications JSON, parse each record, save structured JSON.

    Returns the structured dict on success, None if the raw file does not
    exist or contains no usable records.
    """
    safe     = _sanitize(processo_id)
    raw_path = EXTRACTIONS_DIR / f"{safe}_publications_raw.json"

    if not raw_path.exists():
        logger.error(f"Raw publications file not found: {raw_path}")
        return None

    with open(raw_path, encoding="utf-8") as f:
        raw = json.load(f)

    return preprocess_publications_data(processo_id, raw)


def preprocess_publications_data(processo_id: str, raw: dict) -> Optional[dict]:
    """
    Parse publications from a raw dict (useful for testing without file I/O).

    Args:
        processo_id: The processo ID string.
        raw:         Dict as written by downloader._save_publications_json().

    Returns:
        Structured dict or None if no usable records.
    """
    publications = raw.get("publications", [])
    if not publications:
        logger.warning(f"{processo_id}: no publication records in raw file")
        return None

    total      = len(publications)
    parsed     = []
    skipped    = 0
    warnings   = []

    for record in publications:
        validation = record.get("validation", {})

        # Skip records that failed OCR quality entirely — no usable text
        if not validation.get("quality_passes", False):
            skip_reason = validation.get("extraction_error") or "quality_failed"
            logger.info(
                f"   ⏭  [{record.get('document_index')}/{total}] "
                f"skipped — {skip_reason}"
            )
            skipped += 1
            warnings.append(
                f"document_{record.get('document_index')}_skipped:{skip_reason}"
            )
            continue

        raw_text = record.get("raw_text", "")
        if not raw_text:
            skipped += 1
            warnings.append(
                f"document_{record.get('document_index')}_skipped:empty_raw_text"
            )
            continue

        # Parse text fields via shared parser
        parsed_fields = parse_publication_text(raw_text, processo_id)

        # Supplement publication_date from searcher metadata if parser
        # found no masthead (e.g. searcher already extracted date from
        # the gazette index page — more reliable than OCR in this case)
        pub_meta = record.get("publication_metadata", {})
        if not parsed_fields["publication_date"]:
            searcher_date = pub_meta.get("publication_date")
            if searcher_date:
                parsed_fields["publication_date"] = searcher_date
                parsed_fields["warnings"].append(
                    "publication_date:from_searcher_metadata"
                )

        # Carry forward any parser warnings into the top-level list
        warnings.extend(parsed_fields.get("warnings", []))

        parsed.append({
            "document_index":    record.get("document_index"),
            "content_hint":      pub_meta.get("content_hint", "unknown"),
            "edition_number":    pub_meta.get("edition_number"),
            "page_number":       pub_meta.get("page_number"),
            "source_url":        pub_meta.get("source_url"),
            "parsed_fields":     parsed_fields,
        })

        logger.info(
            f"   ✓ [{record.get('document_index')}/{total}] "
            f"parsed — type={parsed_fields['document_type']} "
            f"pub_date={parsed_fields['publication_date']} "
            f"signing_date={parsed_fields['signing_date_in_pub']}"
        )

    if not parsed:
        logger.warning(f"{processo_id}: no publication records passed quality check")
        return None

    # ── Select primary record ─────────────────────────────────────────────────
    # Prefer structured_contract; fall back to first passing record.
    primary = next(
        (p for p in parsed if p["content_hint"] == "structured_contract"),
        parsed[0],
    )
    primary_fields = primary["parsed_fields"]

    result = {
        "processo_id":         processo_id,
        "source":              "doweb",
        # Top-level fields from primary record — what Epic 4 reads directly
        "publication_date":    primary_fields["publication_date"],
        "signing_date_in_pub": primary_fields["signing_date_in_pub"],
        "contract_number":     primary_fields["contract_number"],
        "contratante":         primary_fields["contratante"],
        "contratada":          primary_fields["contratada"],
        "object_summary":      primary_fields["object_summary"],
        "value":               primary_fields["value"],
        "edition":             primary_fields["edition"],
        "document_type":       primary_fields["document_type"],
        # Provenance
        "documents_found":     total,
        "documents_parsed":    len(parsed),
        "all_publications":    parsed,   # all records for Epic 4 multi-doc analysis
        "warnings":            list(dict.fromkeys(warnings)),  # deduplicate
        "preprocessed_at":     datetime.now().isoformat(),
    }

    _save(processo_id, result)
    return result


# ══════════════════════════════════════════════════════════════════════════════
# SAVE
# ══════════════════════════════════════════════════════════════════════════════

def _save(processo_id: str, result: dict) -> None:
    PREPROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out = PREPROCESSED_DIR / f"{_sanitize(processo_id)}_publication_structured.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    logger.info(f"   💾 Saved: {out.name}")


def _sanitize(pid: str) -> str:
    import re
    return re.sub(r'[^\w\-]', '_', pid)


# ══════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if len(sys.argv) < 2:
        print("Usage: python publication_preprocessor.py <processo_id>")
        sys.exit(1)

    pid    = sys.argv[1]
    result = preprocess_publication(pid)

    if result:
        print(f"\n{'='*60}")
        print(f"Processo ID   : {result['processo_id']}")
        print(f"Source        : {result['source']}")
        print(f"Pub date      : {result['publication_date']}")
        print(f"Signing date  : {result['signing_date_in_pub']}")
        print(f"Contract num  : {result['contract_number']}")
        print(f"Contratante   : {result['contratante']}")
        print(f"Contratada    : {result['contratada']}")
        print(f"Value         : {result['value']}")
        print(f"Edition       : {result['edition']}")
        print(f"Doc type      : {result['document_type']}")
        print(f"Docs found    : {result['documents_found']}")
        print(f"Docs parsed   : {result['documents_parsed']}")
        print(f"Warnings      : {result['warnings']}")
        print(f"{'='*60}")
    else:
        print(f"No usable publications found for: {pid}")
        sys.exit(1)