from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from config.settings import (
    DATA_DIR,
    DISCOVERY_DIR,
    EXTRACTIONS_DIR,
    LOGS_DIR,
    OUTPUTS_DIR,
    PREPROCESSED_DIR,
    COMPLIANCE_DIR,
    CONFORMITY_DIR,
    ALERTS_DIR,
    TEMP_DIR,
)

logger = logging.getLogger(__name__)

MIN_FREE_DISK_MB: int = 500
INTERNET_CHECK_URL: str = "https://www.google.com"
INTERNET_TIMEOUT_S: int = 5
REQUIRED_DIRS: list[Path] = [
    DATA_DIR, DISCOVERY_DIR, EXTRACTIONS_DIR, PREPROCESSED_DIR,
    COMPLIANCE_DIR, CONFORMITY_DIR, ALERTS_DIR, TEMP_DIR,
    OUTPUTS_DIR, LOGS_DIR,
]


@dataclass
class PreflightResult:
    """
    Output of run_preflight().

    passed:   True if no ERROR-grade checks failed.
              WARNING-grade failures do NOT set passed=False.
    warnings: Human-readable warning messages (non-blocking).
    errors:   Human-readable error messages (blocking — stage should not run).
    """
    passed: bool = True
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)
        logger.warning("[preflight] WARNING: %s", msg)

    def add_error(self, msg: str) -> None:
        self.errors.append(msg)
        self.passed = False
        logger.error("[preflight] ERROR: %s", msg)


def _check_directories(result: PreflightResult) -> None:
    """Auto-create missing required directories. Log warning if creation fails."""
    for d in REQUIRED_DIRS:
        try:
            d.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            result.add_warning(f"Could not create directory {d}: {exc}")


def _check_disk_space(result: PreflightResult) -> None:
    """ERROR if less than MIN_FREE_DISK_MB MB free on the DATA_DIR filesystem."""
    try:
        usage = shutil.disk_usage(DATA_DIR)
        free_mb = usage.free / (1024 * 1024)
        if free_mb < MIN_FREE_DISK_MB:
            result.add_error(
                f"Insufficient disk space: {free_mb:.0f} MB free, "
                f"minimum {MIN_FREE_DISK_MB} MB required."
            )
        else:
            logger.debug("[preflight] Disk space OK: %.0f MB free", free_mb)
    except Exception as exc:
        result.add_warning(f"Could not check disk space: {exc}")


def _check_api_key(result: PreflightResult) -> None:
    """ERROR if GROQ_API_KEY is absent from environment."""
    key = os.getenv("GROQ_API_KEY", "")
    if not key:
        result.add_error(
            "GROQ_API_KEY is not set. "
            "Add it to your .env file or environment before running."
        )
    else:
        logger.debug("[preflight] GROQ_API_KEY present (length %d)", len(key))


def _check_groq_reachable(result: PreflightResult) -> None:
    """
    WARNING (not ERROR) if the Groq API is unreachable.
    Online check — must never block offline/CI environments.
    """
    try:
        import urllib.request
        req = urllib.request.Request(
            "https://api.groq.com",
            headers={"User-Agent": "tcm-rj-preflight/1.0"},
        )
        urllib.request.urlopen(req, timeout=INTERNET_TIMEOUT_S)
        logger.debug("[preflight] Groq API reachable")
    except Exception as exc:
        result.add_warning(
            f"Groq API may be unreachable ({type(exc).__name__}). "
            "LLM-based steps will fail if connectivity does not recover."
        )


def _check_internet(result: PreflightResult) -> None:
    """
    WARNING (not ERROR) if the internet is unreachable.
    Online check — must never block offline/CI environments.
    """
    try:
        import urllib.request
        urllib.request.urlopen(INTERNET_CHECK_URL, timeout=INTERNET_TIMEOUT_S)
        logger.debug("[preflight] Internet reachable")
    except Exception as exc:
        result.add_warning(
            f"Internet appears unreachable ({type(exc).__name__}). "
            "Portal scraping steps will fail."
        )


def _check_discovery_file(
    result: PreflightResult,
    stage_name: str,
    require_discovery: bool,
) -> None:
    """
    ERROR for Stages 2–6 if processo_links.json is absent.
    WARNING for Stage 1 (it is about to create this file).
    """
    discovery_file = DISCOVERY_DIR / "processo_links.json"
    if discovery_file.exists():
        logger.debug("[preflight] processo_links.json found")
        return

    if require_discovery:
        result.add_error(
            f"data/discovery/processo_links.json not found. "
            f"Run Stage 1 (discovery) before running {stage_name}."
        )
    else:
        result.add_warning(
            "data/discovery/processo_links.json not found. "
            "Stage 1 will create it."
        )


def _check_chromedriver(result: PreflightResult) -> None:
    """WARNING if chromedriver is not on PATH (only matters for Stages 1–3)."""
    if shutil.which("chromedriver") is None:
        result.add_warning(
            "chromedriver not found on PATH. "
            "Browser-based stages (1–3) will fail. "
            "Install ChromeDriver matching your Chrome version."
        )
    else:
        logger.debug("[preflight] chromedriver found on PATH")


def run_preflight(
    stage_name: str,
    require_discovery: bool = True,
    require_browser: bool = False,
) -> PreflightResult:
    """
    Run environment checks before a stage starts.

    Args:
        stage_name:        Name of the calling stage, e.g. "stage4_compliance".
                           Used in error messages and logging.
        require_discovery: If True (default), ERROR when processo_links.json
                           is absent. Set False only for Stage 1.
        require_browser:   If True, check chromedriver availability.
                           Set True for Stages 1, 2, 3.

    Returns:
        PreflightResult with passed=True if no ERROR-grade checks failed.
        Never raises.

    Usage in stage workflow functions:
        result = run_preflight("stage4_compliance", require_discovery=True)
        if not result.passed:
            logger.error("Pre-flight failed — aborting stage.")
            return {"total": 0, "completed": 0, "failed": 0,
                    "preflight_failed": True, "preflight_errors": result.errors}
    """
    result = PreflightResult()
    logger.info("[preflight] Running checks for %s ...", stage_name)

    _check_directories(result)
    _check_disk_space(result)
    _check_api_key(result)
    _check_internet(result)
    _check_groq_reachable(result)
    _check_discovery_file(result, stage_name, require_discovery)

    if require_browser:
        _check_chromedriver(result)

    if result.passed:
        logger.info(
            "[preflight] %s: all checks passed (%d warning(s))",
            stage_name, len(result.warnings),
        )
    else:
        logger.error(
            "[preflight] %s: FAILED — %d error(s), %d warning(s)",
            stage_name, len(result.errors), len(result.warnings),
        )

    return result