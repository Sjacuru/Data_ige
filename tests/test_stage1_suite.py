"""
tests/test_stage1_suite.py

Stage 1 — Three-track test suite.

Run this BEFORE the live integration test to catch wiring/logic bugs
without opening a browser.

Usage
-----
    # From project root:
    python tests/test_stage1_suite.py

    # Verbose mode:
    python tests/test_stage1_suite.py --verbose

Tracks
------
    TRACK A  Pre-flight    All imports resolve, files exist, env is sane
    TRACK B  Unit tests    Models + JSONStorage offline logic
    TRACK C  Instructions  How to run the live integration test
"""
import sys
import time
import json
import shutil
import tempfile
import argparse
import traceback
from pathlib import Path
from datetime import datetime

# ── Colour helpers ────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def ok(msg):  print(f"  {GREEN}✅ {msg}{RESET}")
def fail(msg): print(f"  {RED}❌ {msg}{RESET}")
def warn(msg): print(f"  {YELLOW}⚠  {msg}{RESET}")
def info(msg): print(f"  {CYAN}ℹ  {msg}{RESET}")

PASSED = 0
FAILED = 0
WARNINGS = 0

def check(label: str, condition: bool, hint: str = "") -> bool:
    global PASSED, FAILED, WARNINGS
    if condition:
        ok(label)
        PASSED += 1
        return True
    else:
        fail(f"{label}")
        if hint:
            print(f"       {YELLOW}→ {hint}{RESET}")
        FAILED += 1
        return False

def section(title: str):
    print(f"\n{BOLD}{CYAN}{'─' * 60}{RESET}")
    print(f"{BOLD}{CYAN}  {title}{RESET}")
    print(f"{BOLD}{CYAN}{'─' * 60}{RESET}")


# ═══════════════════════════════════════════════════════════════════════════════
# TRACK A — PRE-FLIGHT CHECKS
# ═══════════════════════════════════════════════════════════════════════════════

def track_a_preflight():
    section("TRACK A — PRE-FLIGHT: Imports & Structure")

    # ── A1: Python version ────────────────────────────────────────────────────
    major, minor = sys.version_info[:2]
    check(
        f"Python version {major}.{minor} (need 3.9+)",
        major == 3 and minor >= 9,
        hint=f"Current: {sys.version}. Upgrade to Python 3.9+."
    )

    # ── A2: Critical third-party packages ─────────────────────────────────────
    packages = {
        "selenium":     "pip install selenium",
        "fitz":         "pip install pymupdf",
        "requests":     "pip install requests",
    }
    for pkg, install_cmd in packages.items():
        try:
            __import__(pkg)
            ok(f"Package '{pkg}' importable")
            PASSED
        except ImportError:
            fail(f"Package '{pkg}' missing")
            print(f"       {YELLOW}→ {install_cmd}{RESET}")
            global FAILED
            FAILED += 1

    # ── A3: Project root on sys.path ──────────────────────────────────────────
    project_root = Path(__file__).resolve().parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    roots_on_path = any(
        Path(p).resolve() == project_root
        for p in sys.path
    )
    check(
        "Project root is on sys.path",
        roots_on_path,
        hint=f"Add this to your runner: sys.path.insert(0, '{project_root}')"
    )

    # ── A4: Domain model imports ───────────────────────────────────────────────
    try:
        from domain.models.processo_link import ProcessoLink, CompanyData, DiscoveryResult
        ok("domain.models.processo_link imports OK")
        PASSED
    except ImportError as e:
        fail(f"domain.models.processo_link import failed: {e}")
        FAILED += 1

    # ── A5: JSONStorage import ────────────────────────────────────────────────
    try:
        from infrastructure.persistence.json_storage import JSONStorage
        ok("infrastructure.persistence.json_storage imports OK")
        PASSED
    except ImportError as e:
        fail(f"json_storage import failed: {e}")
        FAILED += 1

    # ── A6: Config imports ────────────────────────────────────────────────────
    try:
        from config.settings import (
            CONTASRIO_CONTRACTS_URL, FILTER_YEAR,
            DISCOVERY_DIR, EXTRACTIONS_DIR
        )
        ok("config.settings imports OK")
        PASSED
    except ImportError as e:
        fail(f"config.settings import failed: {e}")
        FAILED += 1

    # ── A7: Scraper + navigation imports ──────────────────────────────────────
    modules_to_check = [
        ("infrastructure.scrapers.contasrio.scraper",     "ContasRioScraper"),
        ("infrastructure.scrapers.contasrio.navigation",  "PathNavigator"),
        ("infrastructure.scrapers.contasrio.parsers",     "CompanyRowParser"),
        ("infrastructure.web.navigation",                 "wait_for_element"),
        ("infrastructure.web.captcha_handler",            "CaptchaHandler"),
        ("infrastructure.extractors.pdf_text_extractor",  "extract_text"),
        ("infrastructure.scrapers.transparencia.downloader", "ProcessoDownloader"),
        ("application.workflows.stage1_discovery",        "run_stage1_discovery"),
        ("application.workflows.stage2_extraction",       "run_stage2_extraction"),
    ]
    for module_path, symbol in modules_to_check:
        try:
            mod = __import__(module_path, fromlist=[symbol])
            getattr(mod, symbol)
            ok(f"{module_path}.{symbol}")
            PASSED
        except (ImportError, AttributeError) as e:
            fail(f"{module_path}.{symbol}  →  {e}")
            FAILED += 1

    # ── A8: data/discovery output files exist from a previous run ─────────────
    discovery_files = {
        "data/discovery/processo_links.json":  "Run Stage 1 first",
        "data/discovery/companies.json":        "Run Stage 1 first",
        "data/discovery/discovery_summary.json":"Run Stage 1 first",
    }
    any_discovery_data = False
    for fpath, hint in discovery_files.items():
        p = Path(fpath)
        exists = p.exists()
        if exists:
            any_discovery_data = True
        check(f"File exists: {fpath}", exists, hint=hint)

    if not any_discovery_data:
        global WARNINGS
        WARNINGS += 1
        warn("No discovery output files found — Track B structure tests will be skipped")

    return any_discovery_data


# ═══════════════════════════════════════════════════════════════════════════════
# TRACK B — UNIT TESTS
# ═══════════════════════════════════════════════════════════════════════════════

def track_b_unit_models():
    section("TRACK B.1 — UNIT: Domain Models")

    try:
        from domain.models.processo_link import ProcessoLink, CompanyData, DiscoveryResult
    except ImportError:
        fail("Cannot import models — skipping model unit tests")
        return

    # ── B1.1: ProcessoLink round-trip ─────────────────────────────────────────
    try:
        pl = ProcessoLink(
            processo_id="TUR-PRO-2025/01221",
            url="https://acesso.processo.rio/test",
            company_name="GREMIO RECREATIVO TESTADOR",
            company_cnpj="01282704000167",
            contract_value="2.150.000,00",
            discovery_path=["GREMIO RECREATIVO TESTADOR", "SECRETARIA", "UG-TESTE"],
        )
        d = pl.to_dict()
        pl2 = ProcessoLink.from_dict(d)
        check(
            "ProcessoLink to_dict() → from_dict() round-trip",
            pl2.processo_id == "TUR-PRO-2025/01221"
            and pl2.company_name == "GREMIO RECREATIVO TESTADOR"
            and pl2.discovery_path == ["GREMIO RECREATIVO TESTADOR", "SECRETARIA", "UG-TESTE"]
        )
    except Exception as e:
        fail(f"ProcessoLink round-trip: {e}")

    # ── B1.2: ProcessoLink rejects unknown keys (from_dict safety) ────────────
    try:
        safe = ProcessoLink.from_dict({
            "processo_id": "X-001", "url": "https://x.com",
            "unknown_future_field": "ignored"
        })
        check(
            "ProcessoLink.from_dict() ignores unknown keys safely",
            safe.processo_id == "X-001"
        )
    except Exception as e:
        fail(f"ProcessoLink.from_dict() with unknown keys: {e}")

    # ── B1.3: CompanyData round-trip ─────────────────────────────────────────
    try:
        cd = CompanyData(
            company_id="01282704000167",
            company_name="GREMIO RECREATIVO TESTADOR",
            company_cnpj="01282704000167",
            total_contracts=5,
            total_value="10.000.000,00"
        )
        cd2 = CompanyData.from_dict(cd.to_dict())
        check(
            "CompanyData to_dict() → from_dict() round-trip",
            cd2.company_name == "GREMIO RECREATIVO TESTADOR"
            and cd2.total_contracts == 5
        )
    except Exception as e:
        fail(f"CompanyData round-trip: {e}")

    # ── B1.4: DiscoveryResult aggregation ────────────────────────────────────
    d = None  # ← initialize before the try block
    try:
        dr = DiscoveryResult()
        link1 = ProcessoLink(processo_id="A-001", url="https://a.com", company_name="ACME")
        link2 = ProcessoLink(processo_id="B-002", url="https://b.com", company_name="BRAVO")
        dr.processos = [link1, link2]
        dr.total_processos = 2
        dr.add_error("test error")

        d = dr.to_dict()
        check(
            "DiscoveryResult.to_dict() has all required keys",
            all(k in d for k in ["discovery_date", "total_companies", "total_processos",
                                   "companies", "processos", "errors"])
        )
        check(
            "DiscoveryResult.add_error() appended correctly",
            "test error" in d["errors"]
        )
        check(
            "DiscoveryResult.processos serialised correctly",
            d["processos"][0]["processo_id"] == "A-001"
        )
    except Exception as e:
        fail(f"DiscoveryResult: {e}")

    # ── B1.5: DiscoveryResult from_dict round-trip ────────────────────────────
    if d is not None:
        try:
            dr_restored = DiscoveryResult.from_dict(d)
            check(
                "DiscoveryResult from_dict() round-trip",
                len(dr_restored.processos) == 2
                and dr_restored.processos[0].processo_id == "A-001"
            )
        except Exception as e:
            fail(f"DiscoveryResult.from_dict(): {e}")


def track_b_unit_json_storage():
    section("TRACK B.2 — UNIT: JSONStorage")

    try:
        from infrastructure.persistence.json_storage import JSONStorage
    except ImportError:
        fail("Cannot import JSONStorage — skipping storage unit tests")
        return

    tmp = Path(tempfile.mkdtemp())

    try:
        # B2.1: save + load round-trip
        data = {
            "discovery_date": "2026-02-20T10:00:00",
            "total_companies": 3,
            "total_processos": 12,
            "companies": [],
            "processos": [],
            "errors": []
        }
        ok_save = JSONStorage.save(data, tmp / "test.json")
        loaded = JSONStorage.load(tmp / "test.json")
        check(
            "save() returns True, load() returns correct data",
            ok_save is True and loaded["total_processos"] == 12
        )

        # B2.2: accepts str path
        loaded2 = JSONStorage.load(str(tmp / "test.json"))
        check("load() accepts str filepath", loaded2["total_companies"] == 3)

        # B2.3: missing file returns {}
        check(
            "load() returns {} for missing file",
            JSONStorage.load(tmp / "ghost.json") == {}
        )

        # B2.4: creates nested dirs
        nested = tmp / "data" / "discovery" / "companies.json"
        ok_nested = JSONStorage.save({"total": 0, "companies": []}, nested)
        check(
            "save() auto-creates nested parent directories",
            ok_nested and nested.exists()
        )

        # B2.5: Portuguese chars as real unicode
        pt = {"name": "AÇÃO COMUNITÁRIA", "note": "ç ã é"}
        JSONStorage.save(pt, tmp / "pt.json")
        raw = (tmp / "pt.json").read_text(encoding="utf-8")
        check(
            "Portuguese characters stored as real unicode (not \\\\u escapes)",
            "AÇÃO" in raw and "\\u00" not in raw
        )

        # B2.6: exists()
        check(
            "exists() returns True for present file, False for missing",
            JSONStorage.exists(tmp / "test.json") is True
            and JSONStorage.exists(tmp / "nope.json") is False
        )

        # B2.7: no .tmp left behind
        JSONStorage.save({"x": 1}, tmp / "atomic.json")
        check(
            "Atomic write leaves no .tmp files behind",
            list(tmp.glob("*.tmp")) == []
        )

        # B2.8: append_to_list
        JSONStorage.save({"errors": ["err1"]}, tmp / "err.json")
        JSONStorage.append_to_list(tmp / "err.json", "errors", ["err2", "err3"])
        errs = JSONStorage.load(tmp / "err.json")["errors"]
        check(
            "append_to_list() extends list correctly",
            errs == ["err1", "err2", "err3"]
        )

        # B2.9: exact signatures from stage1_discovery.py
        #   JSONStorage.save(result.to_dict(), processos_file)   Path arg
        #   JSONStorage.load("data/discovery/processo_links.json") str arg
        pf = tmp / "stage1" / "processo_links.json"
        rd = {
            "discovery_date": "2026-02-20",
            "total_companies": 0, "total_processos": 0,
            "companies": [], "processos": [], "errors": []
        }
        check(
            "Matches stage1_discovery.py call signatures (Path + str)",
            JSONStorage.save(rd, pf) and JSONStorage.load(str(pf)) == rd
        )

    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def track_b_unit_output_structure(has_discovery_data: bool):
    section("TRACK B.3 — UNIT: Validate Existing Discovery Output Files")

    if not has_discovery_data:
        warn("Skipped — no discovery output files found yet")
        warn("Run Stage 1 once, then re-run this suite to validate the output")
        return

    try:
        from infrastructure.persistence.json_storage import JSONStorage
    except ImportError:
        fail("Cannot import JSONStorage")
        return

    # ── B3.1: processo_links.json structure ───────────────────────────────────
    pl = JSONStorage.load("data/discovery/processo_links.json")
    required_keys = ["discovery_date", "total_companies", "total_processos",
                     "companies", "processos", "errors"]
    check(
        "processo_links.json has all required top-level keys",
        all(k in pl for k in required_keys),
        hint=f"Missing: {[k for k in required_keys if k not in pl]}"
    )
    check(
        "total_processos matches actual processos list length",
        pl.get("total_processos", -1) == len(pl.get("processos", [])),
        hint="total_processos counter is out of sync with the list"
    )

    if pl.get("processos"):
        p0 = pl["processos"][0]
        required_p = ["processo_id", "url", "company_name", "discovery_path", "discovered_at"]
        check(
            "First ProcessoLink entry has all required fields",
            all(k in p0 for k in required_p),
            hint=f"Missing fields: {[k for k in required_p if k not in p0]}"
        )
        check(
            "processo_id is non-empty string",
            isinstance(p0.get("processo_id"), str) and len(p0["processo_id"]) > 0
        )
        check(
            "url starts with https://",
            str(p0.get("url", "")).startswith("https://")
        )
        check(
            "discovery_path is a list with at least 1 element",
            isinstance(p0.get("discovery_path"), list) and len(p0["discovery_path"]) >= 1
        )
        info(f"Sample processo: {p0['processo_id']} | {p0.get('company_name', '?')[:50]}")

    # ── B3.2: companies.json structure ───────────────────────────────────────
    co = JSONStorage.load("data/discovery/companies.json")
    check(
        "companies.json has all required top-level keys",
        all(k in co for k in ["total", "discovery_date", "companies"])
    )
    check(
        "companies.total matches companies list length",
        co.get("total", -1) == len(co.get("companies", []))
    )

    if co.get("companies"):
        c0 = co["companies"][0]
        check(
            "First CompanyData entry has required fields",
            all(k in c0 for k in ["company_id", "company_name", "total_contracts"])
        )
        info(f"Top company: {c0.get('company_name', '?')[:60]} ({c0.get('total_contracts', 0)} contracts)")

    # ── B3.3: discovery_summary.json structure ────────────────────────────────
    sm = JSONStorage.load("data/discovery/discovery_summary.json")
    check(
        "discovery_summary.json has all required top-level keys",
        all(k in sm for k in ["discovery_date", "total_companies",
                               "total_processos", "errors_count"])
    )

    # ── B3.4: cross-file consistency ─────────────────────────────────────────
    check(
        "total_processos consistent across processo_links and summary",
        pl.get("total_processos") == sm.get("total_processos"),
        hint="Stage 1 save logic may have a bug — counts differ between files"
    )
    check(
        "total_companies consistent across processo_links and companies",
        pl.get("total_companies") == co.get("total"),
        hint="Stage 1 save logic may have a bug — counts differ between files"
    )

    # ── B3.5: zero-record warning (files exist but are empty) ─────────────────
    if pl.get("total_processos", 0) == 0:
        global WARNINGS
        WARNINGS += 1
        warn("total_processos = 0 — Stage 1 ran but found nothing")
        warn("Check scraper logs or run Stage 1 again with headless=False")
    else:
        info(f"Discovery output: {pl['total_processos']} processos across {pl['total_companies']} companies")




# ═══════════════════════════════════════════════════════════════════════════════
# TRACK C — INSTRUCTIONS FOR LIVE INTEGRATION TEST
# ═══════════════════════════════════════════════════════════════════════════════



def track_c_instructions():
    section("TRACK C — LIVE INTEGRATION TEST (run on your machine)")

    # ── Import config BEFORE using it in the f-string ─────────────────────
    try:
        from config.settings import FILTER_YEAR, CONTASRIO_CONTRACTS_URL
    except ImportError:
        FILTER_YEAR = "<unknown — check config/settings.py>"
        CONTASRIO_CONTRACTS_URL = "<unknown>"

    print(f"""
  {BOLD}This track requires a real browser + ContasRio portal access.{RESET}
  Only run after Track A + B pass cleanly.

  {BOLD}{CYAN}Option 1 — Quick single-company smoke test (recommended first){RESET}
  ─────────────────────────────────────────────────────────────
  Opens browser, navigates to ContasRio, processes 1 company only.
  Takes ~3 minutes. Good for verifying selectors are still working.

    {GREEN}python tests/scraper_test.py{RESET}

  {BOLD}{CYAN}Option 2 — Full integration test (all 5 assertions){RESET}
  ────────────────────────────────────────────────────────────
  Runs the complete TestStage1Discovery suite against a live run.
  Takes 20-30 minutes for 400+ processos.

    {GREEN}python -m pytest tests/integration/test_stage1_discovery.py -v -s{RESET}

  {BOLD}{CYAN}Option 3 — Manual runner (no pytest needed){RESET}
  ────────────────────────────────────────────
    {GREEN}python tests/integration/test_stage1_discovery.py{RESET}

  {BOLD}{CYAN}What to check during the live run:{RESET}
  ─────────────────────────────────────
  {YELLOW}1.{RESET} Browser opens ContasRio portal and contracts page loads
  {YELLOW}2.{RESET} Year filter {FILTER_YEAR} is applied (check the dropdown)
  {YELLOW}3.{RESET} Company rows appear in the grid (scroll should happen)
  {YELLOW}4.{RESET} data/discovery/progress.json grows after each company
  {YELLOW}5.{RESET} Final: data/discovery/processo_links.json has > 0 processos

  {BOLD}{CYAN}If the run crashes mid-way:{RESET}
  ──────────────────────────────
  Progress is saved after every company. Just re-run the same command —
  it will resume from where it stopped. To force a fresh start:

    {GREEN}python -c "from infrastructure.scrapers.contasrio.scraper import clear_progress; clear_progress()"{RESET}
""")

    info(f"Configured year filter: {FILTER_YEAR}")
    info(f"Target URL: {CONTASRIO_CONTRACTS_URL}")

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Stage 1 test suite")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    # Ensure project root is importable
    project_root = Path(__file__).resolve().parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    print(f"\n{BOLD}{'=' * 60}")
    print(f"  STAGE 1 — TEST SUITE")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'=' * 60}{RESET}")

    t0 = time.time()

    # Run tracks
    has_discovery = track_a_preflight()
    track_b_unit_models()
    track_b_unit_json_storage()
    track_b_unit_output_structure(has_discovery)
    track_c_instructions()

    # Final summary
    elapsed = time.time() - t0
    section("SUMMARY")
    print(f"  {GREEN}Passed  : {PASSED}{RESET}")
    print(f"  {RED}Failed  : {FAILED}{RESET}")
    if WARNINGS:
        print(f"  {YELLOW}Warnings: {WARNINGS}{RESET}")
    print(f"  Time    : {elapsed:.1f}s")

    if FAILED == 0:
        print(f"\n  {GREEN}{BOLD}✅  All offline checks passed — safe to run Track C{RESET}\n")
    else:
        print(f"\n  {RED}{BOLD}❌  Fix {FAILED} failure(s) before running the live test{RESET}\n")

    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())