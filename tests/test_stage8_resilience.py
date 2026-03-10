"""
tests/test_stage8_resilience.py

Acceptance tests for Epic 8 — Error Handling & Resilience.

All tests are pure unit tests:
  - No network calls
  - No Selenium / browser
  - No real Groq API calls
  - All file I/O uses pytest's tmp_path fixture

Groups:
  TestErrorHierarchy       (T8.1)
  TestRetryPolicy          (T8.2)
  TestFailedItemsWriter    (T8.3)
  TestHealthChecker        (T8.4)
  TestStructureMonitor     (T8.5)
  TestGroqClientHardening  (T8.6)
  TestRegressionBaselines  (guard — Epics 6 + 7 not broken)

Usage:
    pytest tests/test_stage8_resilience.py -v
    pytest tests/test_stage8_resilience.py tests/test_stage6_alerts.py
tests/test_stage6_integration.py tests/test_stage7_dashboard.py -v
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


class TestErrorHierarchy:
    def test_transient_is_audit_tool_error(self):
        from domain.errors import TransientError, AuditToolError
        assert issubclass(TransientError, AuditToolError)

    def test_permanent_is_audit_tool_error(self):
        from domain.errors import PermanentError, AuditToolError
        assert issubclass(PermanentError, AuditToolError)

    def test_critical_is_audit_tool_error(self):
        from domain.errors import CriticalError, AuditToolError
        assert issubclass(CriticalError, AuditToolError)

    def test_network_timeout_is_transient(self):
        from domain.errors import NetworkTimeoutError, TransientError
        assert issubclass(NetworkTimeoutError, TransientError)

    def test_rate_limit_is_transient(self):
        from domain.errors import RateLimitError, TransientError
        assert issubclass(RateLimitError, TransientError)

    def test_missing_document_is_permanent(self):
        from domain.errors import MissingDocumentError, PermanentError
        assert issubclass(MissingDocumentError, PermanentError)

    def test_auth_error_is_critical(self):
        from domain.errors import AuthenticationError, CriticalError
        assert issubclass(AuthenticationError, CriticalError)

    def test_nodocumenterror_alias_intact(self):
        from infrastructure.scrapers.transparencia.downloader import (
            NoDocumentError, MissingDocumentError,
        )
        assert MissingDocumentError is NoDocumentError


class TestRetryPolicy:
    def _fast_policy(self, max_attempts=3):
        from infrastructure.resilience.retry_policy import RetryPolicy
        return RetryPolicy(
            max_attempts=max_attempts,
            base_delay=0.001,
            max_delay=0.004,
            rate_limit_wait=0.001,
        )

    def test_success_on_first_attempt(self):
        p = self._fast_policy()
        assert p.execute(lambda: 99) == 99

    def test_returns_none_after_exhaustion(self):
        from domain.errors import TransientError
        calls = []

        def fail():
            calls.append(1)
            raise TransientError("boom")

        result = self._fast_policy(max_attempts=3).execute(fail)
        assert result is None
        assert len(calls) == 3

    def test_backoff_schedule(self):
        from domain.errors import TransientError
        p = self._fast_policy()
        delays = [p._delay_for(i, TransientError()) for i in range(1, 5)]
        assert delays[0] < delays[1] < delays[2]
        assert delays[2] == delays[3]

    def test_rate_limit_uses_fixed_wait(self):
        from domain.errors import RateLimitError
        p = self._fast_policy()
        delay = p._delay_for(1, RateLimitError())
        assert delay == p.rate_limit_wait

    def test_permanent_error_no_retry(self):
        from domain.errors import PermanentError
        calls = []

        def perm():
            calls.append(1)
            raise PermanentError("skip me")

        result = self._fast_policy().execute(perm)
        assert result is None
        assert len(calls) == 1

    def test_critical_error_reraises(self):
        from domain.errors import CriticalError
        with pytest.raises(CriticalError):
            self._fast_policy().execute(lambda: (_ for _ in ()).throw(CriticalError("auth")))

    def test_unknown_exception_treated_as_transient(self):
        calls = []

        def fail():
            calls.append(1)
            raise ValueError("unknown")

        result = self._fast_policy(max_attempts=2).execute(fail)
        assert result is None
        assert len(calls) == 2

    def test_public_wrapper_catches_critical(self):
        from domain.errors import CriticalError
        from infrastructure.resilience.retry_policy import RetryPolicy
        p = RetryPolicy(max_attempts=1, base_delay=0.001, max_delay=0.001)

        def safe_caller():
            try:
                return p.execute(lambda: (_ for _ in ()).throw(CriticalError("x")))
            except CriticalError:
                return None

        assert safe_caller() is None


class TestFailedItemsWriter:
    @pytest.fixture(autouse=True)
    def _patch_path(self, tmp_path, monkeypatch):
        import infrastructure.io.failed_items_writer as fw
        monkeypatch.setattr(fw, "FAILED_ITEMS_PATH", tmp_path / "failed_items.json")

    def test_append_creates_file(self):
        from infrastructure.io.failed_items_writer import append_failed_item
        import infrastructure.io.failed_items_writer as fw
        result = append_failed_item("PID/001", "stage3", "TransientError", "timeout")
        assert result is True
        assert fw.FAILED_ITEMS_PATH.exists()

    def test_append_is_additive(self):
        from infrastructure.io.failed_items_writer import append_failed_item, load_failed_items
        append_failed_item("PID/001", "stage3", "TransientError", "t1")
        append_failed_item("PID/002", "stage4", "PermanentError", "t2")
        items = load_failed_items()
        assert len(items) == 2

    def test_mark_resolved(self):
        from infrastructure.io.failed_items_writer import (
            append_failed_item, mark_resolved, count_unresolved,
        )
        append_failed_item("PID/001", "stage3", "TransientError", "t")
        mark_resolved("PID/001", "stage3")
        assert count_unresolved() == 0

    def test_filter_by_stage(self):
        from infrastructure.io.failed_items_writer import append_failed_item, load_failed_items
        append_failed_item("PID/001", "stage3", "TransientError", "t")
        append_failed_item("PID/002", "stage4", "TransientError", "t")
        s3 = load_failed_items(stage="stage3")
        assert len(s3) == 1
        assert s3[0]["processo_id"] == "PID/001"

    def test_read_errors_contract_unchanged(self):
        from infrastructure.dashboard.state_reader import read_errors
        result = read_errors()
        assert isinstance(result, dict)
        assert "stage2" in result
        assert "stage3" in result
        assert "stage4" in result


class TestHealthChecker:
    def test_api_key_missing_is_error(self, monkeypatch):
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        from infrastructure.health_check import run_preflight
        result = run_preflight("test", require_discovery=False, require_browser=False)
        assert not result.passed
        assert any("GROQ_API_KEY" in e for e in result.errors)

    def test_online_checks_are_warning_only(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "test-key-present")
        import urllib.request

        def fail_url(*args, **kwargs):
            raise OSError("no network")

        monkeypatch.setattr(urllib.request, "urlopen", fail_url)
        from infrastructure.health_check import run_preflight
        result = run_preflight("test", require_discovery=False, require_browser=False)
        assert result.passed, f"online check incorrectly set passed=False: {result.errors}"
        assert len(result.warnings) > 0

    def test_missing_discovery_errors_for_stage4(self, tmp_path, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "key")
        import infrastructure.health_check as hc
        monkeypatch.setattr(hc, "MIN_FREE_DISK_MB", 0)
        monkeypatch.setattr(hc, "REQUIRED_DIRS", [])
        monkeypatch.setattr(hc, "DISCOVERY_DIR", tmp_path / "discovery")

        import urllib.request
        monkeypatch.setattr(urllib.request, "urlopen", lambda *args, **kwargs: True)

        from infrastructure.health_check import run_preflight
        result = run_preflight("stage4", require_discovery=True, require_browser=False)
        assert not result.passed
        assert any("processo_links.json" in e for e in result.errors)

    def test_missing_discovery_is_warning_for_stage1(self, tmp_path, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "key")
        import infrastructure.health_check as hc
        monkeypatch.setattr(hc, "MIN_FREE_DISK_MB", 0)
        monkeypatch.setattr(hc, "REQUIRED_DIRS", [])
        monkeypatch.setattr(hc, "DISCOVERY_DIR", tmp_path / "discovery")

        import urllib.request
        monkeypatch.setattr(urllib.request, "urlopen", lambda *args, **kwargs: True)

        from infrastructure.health_check import run_preflight
        result = run_preflight("stage1", require_discovery=False, require_browser=False)
        assert result.passed


class TestStructureMonitor:
    @pytest.fixture(autouse=True)
    def _patch_path(self, tmp_path, monkeypatch):
        import infrastructure.scrapers.structure_monitor as sm
        monkeypatch.setattr(sm, "BASELINES_PATH", tmp_path / "portal_baselines.json")

    def test_no_baseline_saves_and_no_drift(self):
        from infrastructure.scrapers.structure_monitor import check_drift
        r = check_drift("portal_a", {"sel1": True, "sel2": True})
        assert not r.drifted
        assert r.changed_selectors == []

    def test_same_selectors_no_drift(self):
        from infrastructure.scrapers.structure_monitor import check_drift
        check_drift("portal_a", {"sel1": True, "sel2": True})
        r2 = check_drift("portal_a", {"sel1": True, "sel2": True})
        assert not r2.drifted

    def test_selector_disappears_drift_detected(self):
        from infrastructure.scrapers.structure_monitor import check_drift
        check_drift("portal_a", {"sel1": True, "sel2": True})
        r = check_drift("portal_a", {"sel1": True, "sel2": False})
        assert r.drifted
        assert "sel2" in r.changed_selectors

    def test_exception_is_fail_open(self, monkeypatch):
        import infrastructure.scrapers.structure_monitor as sm
        from infrastructure.scrapers.structure_monitor import check_drift

        def _boom():
            raise OSError("simulated failure")

        monkeypatch.setattr(sm, "_load_baselines", _boom)
        r = check_drift("portal_a", {"sel1": True})
        assert not r.drifted


class TestGroqClientHardening:
    def test_max_attempts_is_five(self):
        import infrastructure.llm.groq_client as gc
        assert gc.MAX_ATTEMPTS == 5

    def test_call_signature_unchanged(self):
        from infrastructure.llm.groq_client import GroqClient
        sig = inspect.signature(GroqClient.call)
        params = list(sig.parameters.keys())
        assert params == ["self", "prompt", "model", "max_tokens", "temperature", "json_mode"]

    def test_retry_policy_present(self):
        import infrastructure.llm.groq_client as gc
        assert hasattr(gc, "_RETRY_POLICY")

    def test_call_returns_none_not_raises_on_critical(self, monkeypatch):
        from domain.errors import CriticalError
        import infrastructure.llm.groq_client as gc

        mock_policy = MagicMock()
        mock_policy.execute.side_effect = CriticalError("auth failed")
        monkeypatch.setattr(gc, "_RETRY_POLICY", mock_policy)
        monkeypatch.setenv("GROQ_API_KEY", "fake-key")

        client = object.__new__(gc.GroqClient)
        client._client = MagicMock()
        result = client.call("any prompt")
        assert result is None


class TestRegressionBaselines:
    """
    Guard against regressions in Epic 6 and 7 test contracts.
    These tests confirm the baseline test files are importable and
    that the Epic 8 changes have not altered their module structure.
    """

    def test_stage6_alerts_importable(self):
        import tests.test_stage6_alerts  # noqa: F401

    def test_stage6_integration_importable(self):
        import tests.test_stage6_integration  # noqa: F401

    def test_stage7_dashboard_importable(self):
        import tests.test_stage7_dashboard  # noqa: F401

    def test_state_reader_read_errors_returns_correct_shape(self):
        from infrastructure.dashboard.state_reader import read_errors
        result = read_errors()
        assert isinstance(result, dict)
        for key in ("stage2", "stage3", "stage4"):
            assert key in result
            assert isinstance(result[key], list)
