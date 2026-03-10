"""
application/workflows/stage4_compliance.py

Stage 4 Compliance Engine — Workflow Orchestrator.

This is the only file in Stage 4 that reads from or writes to disk.
All rule logic lives in domain/services/. All LLM calls live in infrastructure/llm/.

Pipeline per processo_id
────────────────────────
1. Skip if already in compliance_progress.json → completed
2. Load _preprocessed.json                       → contract fields
3. Load _publication_structured.json             → publication fields
   └─ If missing: write INCONCLUSIVE, mark done
4. Load _raw.json + _publications_raw.json       → raw text for diagnostic
   └─ If missing: skip diagnostic, proceed deterministic-only
5. Run extraction diagnostic (Groq A + B → comparator)
6. Evaluate R001 — timeliness (deterministic, gated)
7. Evaluate R002 — party match  (LLM-assisted, gated)
8. Write data/compliance/{pid_safe}_compliance.json
9. Mark PID complete in progress file

Entry points
────────────
    python application/workflows/stage4_compliance.py
    python application/workflows/stage4_compliance.py --pid FIL-PRO-2023/00482
    python application/workflows/stage4_compliance.py --dry-run
    python application/workflows/stage4_compliance.py --rerun-failed
"""

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

# ── Project root on sys.path ───────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.settings import EXTRACTIONS_DIR, LOGS_DIR
from infrastructure.logging_config import setup_logging, add_error_log_file
from infrastructure.health_check import run_preflight

from domain.services.compliance_engine import evaluate_r001, evaluate_r002
from domain.services.extraction_comparator import (
    compare_extractions,
    build_default_field_map,
    build_publication_field_map,
    DiagnosticResult,
)
from infrastructure.llm.groq_client import GroqClient
from infrastructure.llm.diagnostic_prompt import (
    build_contract_extraction_prompt,
    build_publication_extraction_prompt,
)
from infrastructure.llm.r002_prompt import build_r002_prompt
from infrastructure.io.failed_items_writer import append_failed_item

logger = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────────────
PREPROCESSED_DIR  = Path("data/preprocessed")
EXTRACTIONS_DIR   = Path("data/extractions")
COMPLIANCE_DIR    = Path("data/compliance")
PROGRESS_FILE     = Path("data/compliance_progress.json")
DISCOVERY_FILE    = Path("data/discovery/processo_links.json")


# ══════════════════════════════════════════════════════════════════════════════
# PID UTILITIES
# ══════════════════════════════════════════════════════════════════════════════

def _sanitize(processo_id: str) -> str:
    """'FIL-PRO-2023/00482' → 'FIL-PRO-2023_00482'"""
    return processo_id.replace("/", "_")


def load_all_pids() -> list:
    """
    Load the full list of processo_ids from the discovery file.
    Falls back to scanning data/preprocessed/ for *_preprocessed.json files.
    """
    if DISCOVERY_FILE.exists():
        try:
            data = json.loads(DISCOVERY_FILE.read_text(encoding="utf-8"))
            pids = [p["processo_id"] for p in data.get("processos", [])
                    if p.get("processo_id")]
            if pids:
                logger.info("Loaded %d PIDs from discovery file.", len(pids))
                return pids
        except Exception as e:
            logger.warning("Could not read discovery file: %s — falling back to scan.", e)

    # Fallback: scan preprocessed dir
    files = sorted(PREPROCESSED_DIR.glob("*_preprocessed.json"))
    pids = []
    for f in files:
        stem = f.stem.replace("_preprocessed", "")
        # Restore / from _ only for the year separator (last _NNNNN segment)
        # Pattern: ALPHA_PRO_YYYY_NNNNN → ALPHA-PRO-YYYY/NNNNN
        parts = stem.rsplit("_", 1)
        if len(parts) == 2 and parts[1].isdigit():
            pid = parts[0].replace("_", "-") + "/" + parts[1]
        else:
            pid = stem.replace("_", "-")
        pids.append(pid)
    logger.info("Fallback scan found %d PIDs in preprocessed dir.", len(pids))
    return pids


# ══════════════════════════════════════════════════════════════════════════════
# PROGRESS TRACKING
# ══════════════════════════════════════════════════════════════════════════════

def _load_progress() -> dict:
    if PROGRESS_FILE.exists():
        try:
            return json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("Could not read progress file: %s — starting fresh.", e)
    return {
        "last_run":  None,
        "stats":     {"total": 0, "completed": 0, "failed": 0, "skipped": 0},
        "completed": [],
        "failed":    [],
        "skipped":   [],
    }


def _save_progress(progress: dict) -> None:
    PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    progress["last_run"] = datetime.now().isoformat()
    PROGRESS_FILE.write_text(
        json.dumps(progress, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _mark_completed(progress: dict, pid: str) -> None:
    if pid not in progress["completed"]:
        progress["completed"].append(pid)
    progress["stats"]["completed"] = len(progress["completed"])
    _save_progress(progress)


def _mark_failed(progress: dict, pid: str, error: str) -> None:
    progress["failed"].append({
        "processo_id": pid,
        "error":       error,
        "at":          datetime.now().isoformat(),
    })
    progress["stats"]["failed"] += 1
    _save_progress(progress)


def _mark_skipped(progress: dict, pid: str) -> None:
    if pid not in progress["skipped"]:
        progress["skipped"].append(pid)
    progress["stats"]["skipped"] = len(progress["skipped"])
    _save_progress(progress)


# ══════════════════════════════════════════════════════════════════════════════
# INPUT LOADERS
# ══════════════════════════════════════════════════════════════════════════════

def _load_json(path: Path) -> dict | None:
    """Load a JSON file. Returns None silently if file does not exist."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("Could not parse %s: %s", path.name, e)
        return None


def _load_contract_preprocessed(pid: str) -> dict | None:
    path = PREPROCESSED_DIR / f"{_sanitize(pid)}_preprocessed.json"
    data = _load_json(path)
    if data is None:
        logger.error("Preprocessed contract not found: %s", path)
    return data


def _load_publication_structured(pid: str) -> dict | None:
    path = PREPROCESSED_DIR / f"{_sanitize(pid)}_publication_structured.json"
    return _load_json(path)  # None is expected for ~22 PIDs


def _load_raw_contract(pid: str) -> str | None:
    """Return raw_text string from the contract raw JSON, or None."""
    path = EXTRACTIONS_DIR / f"{_sanitize(pid)}_raw.json"
    data = _load_json(path)
    if data is None:
        return None
    return data.get("raw_text") or None


def _load_raw_publication(pid: str) -> str | None:
    """
    Return the raw_text of the best-quality publication record.
    Prefers records with quality_passes=True and content_hint='structured_contract'.
    """
    path = EXTRACTIONS_DIR / f"{_sanitize(pid)}_publications_raw.json"
    data = _load_json(path)
    if data is None:
        return None

    publications = data.get("publications", [])
    if not publications:
        return None

    # Prefer structured_contract + quality_passes
    for record in publications:
        hint = (record.get("publication_metadata") or {}).get("content_hint", "")
        qp   = (record.get("validation") or {}).get("quality_passes", False)
        if hint == "structured_contract" and qp:
            return record.get("raw_text") or None

    # Fall back to first quality-passing record
    for record in publications:
        qp = (record.get("validation") or {}).get("quality_passes", False)
        if qp:
            return record.get("raw_text") or None

    # Last resort: first record regardless of quality
    return publications[0].get("raw_text") or None


# ══════════════════════════════════════════════════════════════════════════════
# FIELD EXTRACTION (preprocessed → flat dicts for comparator)
# ══════════════════════════════════════════════════════════════════════════════

def _extract_contract_det_fields(preprocessed: dict) -> dict:
    """Flatten preprocessed contract JSON → comparator-ready dict."""
    header = preprocessed.get("header") or {}
    return {
        "processo_id":    preprocessed.get("processo_id"),
        "contract_number": header.get("contract_number"),
        "signing_date":   header.get("signing_date"),
        "contratante":    header.get("contratante"),
        "contratada":     header.get("contratada"),
    }


def _extract_publication_det_fields(pub_structured: dict, preprocessed: dict) -> dict:
    """Flatten publication structured JSON → comparator-ready dict.
    
    For embedded publications, prefer embedded data over potentially incorrect DoWeb data.
    """
    # Start with DoWeb data
    contratada = pub_structured.get("contratada")
    contratante = pub_structured.get("contratante")
    
    # For embedded publications, prefer embedded data
    embedded = preprocessed.get("embedded_publication", {})
    if embedded.get("found"):
        # Always use embedded data for parties, as DoWeb may have found wrong publication
        if embedded.get("contratada_pub"):
            contratada = embedded.get("contratada_pub")
        if embedded.get("contratante_pub"):
            contratante = embedded.get("contratante_pub")
    
    return {
        "processo_id":    pub_structured.get("processo_id"),
        "contract_number": pub_structured.get("contract_number"),
        "publication_date": pub_structured.get("publication_date"),
        "contratante":    contratante,
        "contratada":     contratada,
    }


# ══════════════════════════════════════════════════════════════════════════════
# EXTRACTION DIAGNOSTIC
# ══════════════════════════════════════════════════════════════════════════════

def _run_extraction_diagnostic(
    groq:              GroqClient,
    raw_contract_text: str,
    raw_pub_text:      str,
    det_contract:      dict,
    det_publication:   dict,
    warnings:          list,
) -> tuple[DiagnosticResult | None, DiagnosticResult | None, list]:
    """
    Run dual-path extraction diagnostic.

    Calls Groq Prompt A (contract) and Prompt B (publication) in sequence,
    then compares each against the deterministic extraction.

    Returns (contract_diag, publication_diag, combined_divergent_fields).
    Either result may be None if the Groq call failed.
    """
    contract_diag = None
    pub_diag      = None
    combined_divergent: list = []

    # ── Prompt A: contract extraction ─────────────────────────────────────────
    prompt_a   = build_contract_extraction_prompt(raw_contract_text)
    response_a = groq.call(prompt_a, max_tokens=400, json_mode=True)

    if response_a:
        try:
            llm_contract = json.loads(response_a)
            contract_diag = compare_extractions(
                det_contract, llm_contract, build_default_field_map()
            )
            logger.info("  Contract diagnostic: %s", contract_diag.agreement_level)
        except (json.JSONDecodeError, Exception) as e:
            logger.warning("  Contract diagnostic parse error: %s", e)
            warnings.append(f"diagnostic:contract_llm_parse_error:{e}")
    else:
        logger.warning("  Contract diagnostic: LLM call returned None")
        warnings.append("diagnostic:contract_llm_unavailable")

    # ── Prompt B: publication extraction ──────────────────────────────────────
    prompt_b   = build_publication_extraction_prompt(raw_pub_text)
    response_b = groq.call(prompt_b, max_tokens=400, json_mode=True)

    if response_b:
        try:
            llm_publication = json.loads(response_b)
            pub_diag = compare_extractions(
                det_publication, llm_publication, build_publication_field_map()
            )
            logger.info("  Publication diagnostic: %s", pub_diag.agreement_level)
        except (json.JSONDecodeError, Exception) as e:
            logger.warning("  Publication diagnostic parse error: %s", e)
            warnings.append(f"diagnostic:publication_llm_parse_error:{e}")
    else:
        logger.warning("  Publication diagnostic: LLM call returned None")
        warnings.append("diagnostic:publication_llm_unavailable")

    # ── Combine divergent fields from both diagnostics ─────────────────────────
    if contract_diag:
        combined_divergent.extend(contract_diag.fields_divergent)
    if pub_diag:
        combined_divergent.extend(pub_diag.fields_divergent)

    return contract_diag, pub_diag, combined_divergent


def _merge_diagnostics(
    contract_diag: DiagnosticResult | None,
    pub_diag:      DiagnosticResult | None,
) -> dict:
    """
    Merge two DiagnosticResults into the single extraction_diagnostic block
    written to the compliance output JSON.

    Agreement level logic:
      DIVERGENT  if either is DIVERGENT
      PARTIAL    if either is PARTIAL (and neither is DIVERGENT)
      CONFIRMED  only if both are CONFIRMED
      SKIPPED    if both are None
    """
    if contract_diag is None and pub_diag is None:
        return {
            "agreement_level":        "SKIPPED",
            "fields_confirmed":       [],
            "fields_divergent":       [],
            "divergence_detail":      {},
            "auditor_action_required": False,
        }

    levels = []
    confirmed: list = []
    divergent: list = []
    detail: dict    = {}
    auditor_flag    = False

    for diag in (contract_diag, pub_diag):
        if diag is None:
            continue
        levels.append(diag.agreement_level)
        confirmed.extend(diag.fields_confirmed)
        divergent.extend(diag.fields_divergent)
        detail.update(diag.divergence_detail)
        if diag.auditor_action_required:
            auditor_flag = True

    if "DIVERGENT" in levels:
        level = "DIVERGENT"
    elif "PARTIAL" in levels:
        level = "PARTIAL"
    else:
        level = "CONFIRMED"

    return {
        "agreement_level":        level,
        "fields_confirmed":       sorted(set(confirmed)),
        "fields_divergent":       sorted(set(divergent)),
        "divergence_detail":      detail,
        "auditor_action_required": auditor_flag or level != "CONFIRMED",
    }


# ══════════════════════════════════════════════════════════════════════════════
# OVERALL STATUS
# ══════════════════════════════════════════════════════════════════════════════

def _compute_overall(r001_verdict: str, r002_verdict: str,
                     diagnostic_level: str) -> tuple[str, bool, str | None]:
    """
    Derive overall compliance status.

    Returns (status, requires_review, review_reason).
    """
    if r001_verdict == "FAIL" or r002_verdict == "FAIL":
        return "FAIL", True, "one_or_more_rules_failed"

    if (r001_verdict == "INCONCLUSIVE" or r002_verdict == "INCONCLUSIVE"
            or diagnostic_level == "DIVERGENT"):
        reasons = []
        if r001_verdict == "INCONCLUSIVE":
            reasons.append("r001_inconclusive")
        if r002_verdict == "INCONCLUSIVE":
            reasons.append("r002_inconclusive")
        if diagnostic_level == "DIVERGENT":
            reasons.append("diagnostic_divergent")
        return "INCONCLUSIVE", True, ",".join(reasons)

    # Both PASS; diagnostic CONFIRMED or PARTIAL
    requires = diagnostic_level == "PARTIAL"
    reason   = "diagnostic_partial" if requires else None
    return "PASS", requires, reason


# ══════════════════════════════════════════════════════════════════════════════
# SINGLE PID PROCESSOR
# ══════════════════════════════════════════════════════════════════════════════

def process_pid(pid: str, groq: GroqClient) -> dict:
    """
    Run the full compliance pipeline for one processo_id.

    Returns the compliance result dict (also written to disk).
    Never raises — all exceptions are caught and converted to INCONCLUSIVE.
    """
    t_start      = time.monotonic()
    api_calls    = 0
    warnings:list = []
    safe_pid     = _sanitize(pid)

    logger.info("─" * 60)
    logger.info("Processing: %s", pid)

    # ── Step 2: Load contract preprocessed ────────────────────────────────────
    preprocessed = _load_contract_preprocessed(pid)
    if preprocessed is None:
        raise FileNotFoundError(f"_preprocessed.json not found for {pid}")

    det_contract = _extract_contract_det_fields(preprocessed)

    # ── Step 3: Load publication structured ────────────────────────────────────
    pub_structured = _load_publication_structured(pid)
    pub_source     = pub_structured.get("source") if pub_structured else None

    if pub_structured is None:
        logger.warning("  No publication file — writing INCONCLUSIVE")
        return _write_inconclusive_no_publication(
            pid, preprocessed, t_start, warnings
        )

    det_publication = _extract_publication_det_fields(pub_structured, preprocessed)

    # ── Step 4: Load raw files for diagnostic ─────────────────────────────────
    raw_contract_text = _load_raw_contract(pid)
    raw_pub_text      = _load_raw_publication(pid)
    diagnostic_skipped = False

    contract_diag = None
    pub_diag      = None
    combined_divergent: list = []

    if raw_contract_text and raw_pub_text:
        # ── Step 5: Extraction diagnostic ──────────────────────────────────────
        contract_diag, pub_diag, combined_divergent = _run_extraction_diagnostic(
            groq, raw_contract_text, raw_pub_text,
            det_contract, det_publication, warnings,
        )
        api_calls += 2  # Prompt A + Prompt B
    else:
        diagnostic_skipped = True
        missing = []
        if not raw_contract_text: missing.append("raw_contract")
        if not raw_pub_text:      missing.append("raw_publication")
        logger.warning("  Diagnostic skipped — missing raw files: %s", missing)
        warnings.append(f"diagnostic:skipped:missing_raw_files:{','.join(missing)}")

    diagnostic_block = _merge_diagnostics(contract_diag, pub_diag)
    if diagnostic_skipped:
        diagnostic_block["agreement_level"] = "SKIPPED"

    # ── Step 6: R001 — Timeliness ─────────────────────────────────────────────
    r001 = evaluate_r001(
        signing_date=det_contract.get("signing_date"),
        publication_date=det_publication.get("publication_date"),
        diagnostic_divergent_fields=combined_divergent,
    )
    logger.info("  R001: %s  (delta=%s days)", r001.verdict, r001.days_delta)

    # Handle embedded publication date proxy warning
    if pub_source == "embedded" and not pub_structured.get("publication_date"):
        warnings.append("publication_date:from_signing_date_in_pub")

    # ── Step 7: R002 — Party Match ────────────────────────────────────────────
    r002_llm_response = None
    r002_skipped      = False

    # Gate: only call LLM if we have party fields and diagnostic is not DIVERGENT
    parties_present = all([
        det_contract.get("contratante"),
        det_publication.get("contratante"),
        det_contract.get("contratada"),
        det_publication.get("contratada"),
    ])
    diag_blocks_r002 = diagnostic_block["agreement_level"] == "DIVERGENT"

    if parties_present and not diag_blocks_r002:
        r002_prompt = build_r002_prompt(
            contract_contratante=det_contract.get("contratante"),
            pub_contratante=det_publication.get("contratante"),
            contract_contratada=det_contract.get("contratada"),
            pub_contratada=det_publication.get("contratada"),
        )
        r002_llm_response = groq.call(r002_prompt, max_tokens=500, json_mode=True)
        api_calls += 1
    else:
        r002_skipped = True
        if not parties_present:
            warnings.append("r002:skipped:missing_party_fields")
        if diag_blocks_r002:
            warnings.append("r002:skipped:diagnostic_divergent")

    r002 = evaluate_r002(
        contract_contratante=det_contract.get("contratante"),
        pub_contratante=det_publication.get("contratante"),
        contract_contratada=det_contract.get("contratada"),
        pub_contratada=det_publication.get("contratada"),
        llm_response=r002_llm_response,
        diagnostic_divergent_fields=combined_divergent,
    )
    logger.info("  R002: %s  (confidence=%s)", r002.verdict, r002.confidence)

    # ── Step 8: Overall status ────────────────────────────────────────────────
    overall_status, overall_review, review_reason = _compute_overall(
        r001.verdict, r002.verdict, diagnostic_block["agreement_level"]
    )

    elapsed = time.monotonic() - t_start

    # ── Build compliance result ───────────────────────────────────────────────
    result = {
        "processo_id":   pid,
        "evaluated_at":  datetime.now().isoformat(),
        "inputs": {
            "contract_file":    str(PREPROCESSED_DIR / f"{safe_pid}_preprocessed.json"),
            "publication_file": str(PREPROCESSED_DIR / f"{safe_pid}_publication_structured.json"),
            "publication_source": pub_source,
        },
        "extraction_diagnostic": diagnostic_block,
        "r001_timeliness": {
            "verdict":             r001.verdict,
            "signing_date":        det_contract.get("signing_date"),
            "publication_date":    det_publication.get("publication_date"),
            "days_delta":          r001.days_delta,
            "limit_days":          20,
            "explanation":         r001.explanation,
            "confidence":          r001.confidence,
            "requires_review":     r001.requires_review,
            "inconclusive_reason": r001.inconclusive_reason,
        },
        "r002_party_match": {
            "verdict":               r002.verdict,
            "contract_contratante":  det_contract.get("contratante"),
            "publication_contratante": det_publication.get("contratante"),
            "contract_contratada":   det_contract.get("contratada"),
            "publication_contratada": det_publication.get("contratada"),
            "explanation":           r002.explanation,
            "confidence":            r002.confidence,
            "requires_review":       r002.requires_review,
            "inconclusive_reason":   r002.inconclusive_reason,
            "llm_model":             "llama-3.3-70b-versatile",
        },
        "overall": {
            "status":         overall_status,
            "requires_review": overall_review,
            "review_reason":  review_reason,
        },
        "metadata": {
            "diagnostic_skipped":        diagnostic_skipped,
            "r001_skipped":              False,
            "r002_skipped":              r002_skipped,
            "api_calls_made":            api_calls,
            "processing_time_seconds":   round(elapsed, 2),
            "warnings":                  warnings,
        },
    }

    # ── Step 9: Write output ───────────────────────────────────────────────────
    _write_compliance_json(pid, result)
    logger.info("  Overall: %s  (%.1fs, %d API calls)", overall_status, elapsed, api_calls)
    return result


def _write_inconclusive_no_publication(
    pid: str, preprocessed: dict, t_start: float, warnings: list
) -> dict:
    """Write an INCONCLUSIVE result for a PID with no publication file."""
    det = _extract_contract_det_fields(preprocessed)
    result = {
        "processo_id":   pid,
        "evaluated_at":  datetime.now().isoformat(),
        "inputs": {
            "contract_file":     str(PREPROCESSED_DIR / f"{_sanitize(pid)}_preprocessed.json"),
            "publication_file":  None,
            "publication_source": None,
        },
        "extraction_diagnostic": {
            "agreement_level":        "SKIPPED",
            "fields_confirmed":       [],
            "fields_divergent":       [],
            "divergence_detail":      {},
            "auditor_action_required": False,
        },
        "r001_timeliness": {
            "verdict":             "INCONCLUSIVE",
            "signing_date":        det.get("signing_date"),
            "publication_date":    None,
            "days_delta":          None,
            "limit_days":          20,
            "explanation":         "No publication file found for this processo.",
            "confidence":          "n/a",
            "requires_review":     True,
            "inconclusive_reason": "no_publication_found",
        },
        "r002_party_match": {
            "verdict":               "INCONCLUSIVE",
            "contract_contratante":  det.get("contratante"),
            "publication_contratante": None,
            "contract_contratada":   det.get("contratada"),
            "publication_contratada": None,
            "explanation":           "No publication file found for this processo.",
            "confidence":            "n/a",
            "requires_review":       True,
            "inconclusive_reason":   "no_publication_found",
            "llm_model":             "llama-3.3-70b-versatile",
        },
        "overall": {
            "status":          "INCONCLUSIVE",
            "requires_review": True,
            "review_reason":   "no_publication_found",
        },
        "metadata": {
            "diagnostic_skipped":       True,
            "r001_skipped":             False,
            "r002_skipped":             True,
            "api_calls_made":           0,
            "processing_time_seconds":  round(time.monotonic() - t_start, 2),
            "warnings":                 warnings + ["no_publication_file"],
        },
    }
    _write_compliance_json(pid, result)
    return result


def _write_compliance_json(pid: str, result: dict) -> None:
    COMPLIANCE_DIR.mkdir(parents=True, exist_ok=True)
    path = COMPLIANCE_DIR / f"{_sanitize(pid)}_compliance.json"
    path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("  Written: %s", path.name)


# ══════════════════════════════════════════════════════════════════════════════
# MAIN ORCHESTRATOR
# ══════════════════════════════════════════════════════════════════════════════

def run_stage4_compliance(
    pid_filter: str | None = None,
    dry_run:    bool       = False,
    rerun_failed: bool     = False,
) -> dict:
    """
    Main entry point for Stage 4 compliance evaluation.

    Args:
        pid_filter:   If set, process only this PID.
        dry_run:      Print plan, exit without making any API calls or writes.
        rerun_failed: Also reprocess PIDs that previously failed.

    Returns:
        Summary dict with counts.
    """
    COMPLIANCE_DIR.mkdir(parents=True, exist_ok=True)

    all_pids  = load_all_pids()
    progress  = _load_progress()
    completed = set(progress.get("completed", []))
    previously_failed = {e["processo_id"] for e in progress.get("failed", [])}

    if pid_filter:
        all_pids = [p for p in all_pids if p == pid_filter]
        if not all_pids:
            # PID might not be in discovery — add it directly
            all_pids = [pid_filter]

    progress["stats"]["total"] = len(all_pids)

    # ── Dry run ────────────────────────────────────────────────────────────────
    if dry_run:
        pending = [p for p in all_pids if p not in completed]
        if rerun_failed:
            pending = list(all_pids)
        print(f"\n{'─'*60}")
        print(f"  Stage 4 Compliance Engine — DRY RUN")
        print(f"{'─'*60}")
        print(f"  Total PIDs          : {len(all_pids)}")
        print(f"  Already completed   : {len(completed)}")
        print(f"  Previously failed   : {len(previously_failed)}")
        print(f"  Pending this run    : {len(pending)}")
        print(f"  Output directory    : {COMPLIANCE_DIR}")
        print(f"  Progress file       : {PROGRESS_FILE}")
        print(f"{'─'*60}\n")
        return {"dry_run": True, "total": len(all_pids), "pending": len(pending)}

    # ── Initialise Groq client ─────────────────────────────────────────────────
    try:
        groq = GroqClient()
    except (EnvironmentError, ImportError) as e:
        logger.error("Cannot initialise GroqClient: %s", e)
        print(f"\n❌ GROQ_API_KEY missing or groq package not installed.\n   {e}")
        sys.exit(1)

    # ── Process PIDs ──────────────────────────────────────────────────────────
    results = {"total": len(all_pids), "completed": 0, "failed": 0, "skipped": 0}

    for i, pid in enumerate(all_pids, 1):
        label = f"[{i}/{len(all_pids)}] {pid}"

        # Skip already completed (unless rerun_failed and it failed before)
        if pid in completed:
            if not (rerun_failed and pid in previously_failed):
                logger.info("%s — already completed, skipping", label)
                results["skipped"] += 1
                continue

        logger.info("Processing %s", label)

        try:
            process_pid(pid, groq)
            _mark_completed(progress, pid)
            results["completed"] += 1

        except FileNotFoundError as e:
            logger.error("  Skipped — %s", e)
            _mark_skipped(progress, pid)
            results["skipped"] += 1

        except Exception as e:
            logger.error("  FAILED — %s", e, exc_info=True)
            _mark_failed(progress, pid, str(e))
            append_failed_item(
                processo_id=pid,
                stage="stage4",
                error_type="ExtractionFailedError",
                error_msg=str(e),
            )
            results["failed"] += 1

    # ── Final summary ──────────────────────────────────────────────────────────
    logger.info("═" * 60)
    logger.info("Stage 4 complete.")
    logger.info("  Total   : %d", results["total"])
    logger.info("  Done    : %d", results["completed"])
    logger.info("  Skipped : %d", results["skipped"])
    logger.info("  Failed  : %d", results["failed"])
    logger.info("═" * 60)

    return results


# ══════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Stage 4 — Compliance Engine"
    )
    parser.add_argument(
        "--pid", type=str, default=None,
        help="Process a single processo_id, e.g. FIL-PRO-2023/00482",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print plan without making API calls or writing files",
    )
    parser.add_argument(
        "--rerun-failed", action="store_true",
        help="Reprocess PIDs that previously failed",
    )
    parser.add_argument(
        "--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
    )
    args = parser.parse_args()

    log_file = setup_logging(
        "compliance", log_level=getattr(logging, args.log_level)
    )
    error_log_path = add_error_log_file()

    preflight = run_preflight(
        "stage4_compliance",
        require_discovery=True,
        require_browser=False,
    )
    if not preflight.passed:
        logger.error("Aborting stage4_compliance — pre-flight failed.")
        results = {
            "total": 0,
            "completed": 0,
            "failed": 0,
            "skipped": 0,
            "preflight_failed": True,
            "preflight_errors": preflight.errors,
        }
        if not args.dry_run:
            print(f"\n📝 Logging to:    {log_file}")
            print(f"📝 Error log:     {error_log_path}\n")
        print(f"\n{'═'*60}")
        print(f"  Stage 4 Results")
        print(f"{'─'*60}")
        for k, v in results.items():
            print(f"  {k:<20}: {v}")
        print(f"{'═'*60}\n")
        sys.exit(1)

    if not args.dry_run:
        print(f"\n📝 Logging to:    {log_file}")
        print(f"📝 Error log:     {error_log_path}\n")

    results = run_stage4_compliance(
        pid_filter=args.pid,
        dry_run=args.dry_run,
        rerun_failed=args.rerun_failed,
    )

    if not args.dry_run:
        print(f"\n{'═'*60}")
        print(f"  Stage 4 Results")
        print(f"{'─'*60}")
        for k, v in results.items():
            print(f"  {k:<20}: {v}")
        print(f"{'═'*60}\n")

    sys.exit(0 if results.get("failed", 0) == 0 else 1)


if __name__ == "__main__":
    main()