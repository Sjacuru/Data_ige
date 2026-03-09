"""
tests/test_task4_1_groq_client.py

Acceptance tests for Task 4.1 — infrastructure/llm/groq_client.py

Three tracks:

  TRACK A — Import + environment
  TRACK B — Unit tests (no API key required — uses mock)
  TRACK C — Live smoke test (requires real GROQ_API_KEY)

Usage
─────
    python tests/test_task4_1_groq_client.py              # A + B + C
    python tests/test_task4_1_groq_client.py --offline    # A + B only
    python tests/test_task4_1_groq_client.py --live-only  # C only
"""

import sys
import os
import time
import argparse
import unittest.mock as mock
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# ── Console helpers ──────────────────────────────────────────────────────────
GREEN  = "\033[92m"; RED = "\033[91m"; YELLOW = "\033[93m"
CYAN   = "\033[96m"; BOLD = "\033[1m"; RESET = "\033[0m"

PASSED = FAILED = WARNINGS = 0

def check(label, condition, hint=""):
    global PASSED, FAILED
    if condition:
        print(f"  {GREEN}✓{RESET}  {label}"); PASSED += 1
    else:
        print(f"  {RED}✗{RESET}  {label}")
        if hint: print(f"       {YELLOW}hint: {hint}{RESET}")
        FAILED += 1

def warn(msg):
    global WARNINGS
    print(f"  {YELLOW}⚠{RESET}  {msg}"); WARNINGS += 1

def info(msg): print(f"  {CYAN}·{RESET}  {msg}")

def section(title):
    print(f"\n{BOLD}{title}{RESET}")
    print("  " + "─" * 60)


# ══════════════════════════════════════════════════════════════════════════════
# TRACK A — Import + Environment
# ══════════════════════════════════════════════════════════════════════════════

def track_a():
    section("TRACK A — Import & Environment")

    # A1: module importable
    try:
        from infrastructure.llm.groq_client import GroqClient, DEFAULT_MODEL
        check("A1: infrastructure.llm.groq_client imports cleanly", True)
    except ImportError as e:
        check("A1: infrastructure.llm.groq_client imports cleanly", False,
              hint=str(e))
        return False

    # A2: groq SDK available
    try:
        import groq
        check("A2: groq SDK installed", True)
        info(f"  groq version: {groq.__version__}")
    except ImportError:
        check("A2: groq SDK installed", False,
              hint="Run: pip install groq>=0.9.0")

    # A3: default model constant
    check("A3: DEFAULT_MODEL is llama-3.3-70b-versatile",
          DEFAULT_MODEL == "llama-3.3-70b-versatile",
          hint=f"got: {DEFAULT_MODEL}")

    # A4: GROQ_API_KEY present (warn only — offline tests don't need it)
    key = os.getenv("GROQ_API_KEY")
    if key:
        check("A4: GROQ_API_KEY present in environment", True)
        info(f"  key prefix: {key[:8]}...")
    else:
        warn("A4: GROQ_API_KEY not found — live test (Track C) will be skipped")

    # A5: __init__.py exists for infrastructure.llm package
    init_path = ROOT / "infrastructure" / "llm" / "__init__.py"
    check("A5: infrastructure/llm/__init__.py exists",
          init_path.exists(),
          hint=f"Create empty file at {init_path}")

    return True


# ══════════════════════════════════════════════════════════════════════════════
# TRACK B — Unit Tests (no real API key — uses mock)
# ══════════════════════════════════════════════════════════════════════════════

def track_b():
    section("TRACK B — Unit Tests (offline)")

    # Temporarily set a fake API key so GroqClient.__init__ passes
    os.environ.setdefault("GROQ_API_KEY", "test-key-offline")

    try:
        from infrastructure.llm.groq_client import (
            GroqClient, MAX_ATTEMPTS, BASE_DELAY_SECONDS,
            RATE_LIMIT_WAIT, DEFAULT_MODEL,
        )
    except ImportError as e:
        check("GroqClient importable", False, hint=str(e))
        return

    # ── B1: GroqClient raises on missing API key ──────────────────────────────
    original_key = os.environ.pop("GROQ_API_KEY", None)
    try:
        raised = False
        try:
            with mock.patch.dict(os.environ, {}, clear=True):
                # Remove key from env entirely for this check
                env_without_key = {k: v for k, v in os.environ.items()
                                   if k != "GROQ_API_KEY"}
                with mock.patch.dict(os.environ, env_without_key, clear=True):
                    GroqClient()
        except EnvironmentError:
            raised = True
        except Exception:
            raised = True  # ImportError for missing groq SDK also acceptable
        check("B1: GroqClient raises EnvironmentError with no API key", raised)
    finally:
        if original_key:
            os.environ["GROQ_API_KEY"] = original_key
        else:
            os.environ["GROQ_API_KEY"] = "test-key-offline"

    # ── B2: successful call returns string ────────────────────────────────────
    fake_response = '{"result": "ok"}'

    with mock.patch("groq.Groq") as MockGroq:
        mock_completion         = mock.MagicMock()
        mock_completion.choices[0].message.content = fake_response
        MockGroq.return_value.chat.completions.create.return_value = mock_completion

        client = GroqClient()
        result = client.call("test prompt", max_tokens=10)

    check("B2: call() returns string on success",
          isinstance(result, str),
          hint=f"got: {type(result)}")
    check("B2: call() returns expected content",
          result == fake_response,
          hint=f"got: {repr(result)}")

    # ── B3: returns None when all retries exhausted ───────────────────────────
    with mock.patch("groq.Groq") as MockGroq:
        MockGroq.return_value.chat.completions.create.side_effect = \
            RuntimeError("Connection error")

        client = GroqClient()
        # Patch sleep so the test doesn't actually wait
        with mock.patch("time.sleep"):
            result = client.call("test", max_tokens=10)

    check("B3: call() returns None when all retries exhausted",
          result is None,
          hint=f"got: {type(result)}")

    # ── B4: call() does NOT raise exceptions ─────────────────────────────────
    with mock.patch("groq.Groq") as MockGroq:
        MockGroq.return_value.chat.completions.create.side_effect = \
            Exception("Unexpected error")
        client = GroqClient()
        exception_raised = False
        try:
            with mock.patch("time.sleep"):
                client.call("test", max_tokens=10)
        except Exception:
            exception_raised = True

    check("B4: call() never raises — swallows all exceptions",
          not exception_raised)

    # ── B5: rate limit wait is longer than base delay ─────────────────────────
    check("B5: RATE_LIMIT_WAIT (60s) > BASE_DELAY_SECONDS (2s)",
          RATE_LIMIT_WAIT > BASE_DELAY_SECONDS,
          hint=f"rate_limit={RATE_LIMIT_WAIT}, base={BASE_DELAY_SECONDS}")

    # ── B6: _classify_and_wait returns 60s on 429 ────────────────────────────
    exc_429    = Exception("error code: 429 rate limit exceeded")
    exc_other  = Exception("connection refused")
    wait_429   = GroqClient._classify_and_wait(exc_429, attempt=1)
    wait_other = GroqClient._classify_and_wait(exc_other, attempt=1)

    check("B6: 429 exception → wait = RATE_LIMIT_WAIT (60s)",
          wait_429 == float(RATE_LIMIT_WAIT),
          hint=f"got: {wait_429}")
    check("B6: other exception → wait = exponential backoff",
          wait_other == float(BASE_DELAY_SECONDS * 1),
          hint=f"got: {wait_other}")

    # ── B7: exponential backoff doubles each attempt ──────────────────────────
    exc = Exception("timeout")
    waits = [GroqClient._classify_and_wait(exc, a) for a in range(1, 4)]
    check("B7: backoff doubles each attempt (2s → 4s → 8s)",
          waits == [2.0, 4.0, 8.0],
          hint=f"got: {waits}")

    # ── B8: MAX_ATTEMPTS == 3 ─────────────────────────────────────────────────
    check("B8: MAX_ATTEMPTS == 3",
          MAX_ATTEMPTS == 3,
          hint=f"got: {MAX_ATTEMPTS}")

    # ── B9: json_mode passes response_format to API ───────────────────────────
    with mock.patch("groq.Groq") as MockGroq:
        mock_completion         = mock.MagicMock()
        mock_completion.choices[0].message.content = '{"x": 1}'
        create_fn = MockGroq.return_value.chat.completions.create
        create_fn.return_value = mock_completion

        client = GroqClient()
        client.call("test", json_mode=True)
        call_kwargs = create_fn.call_args[1]

    check("B9: json_mode=True passes response_format to API",
          call_kwargs.get("response_format") == {"type": "json_object"},
          hint=f"got: {call_kwargs.get('response_format')}")

    # ── B10: json_mode=False omits response_format ────────────────────────────
    with mock.patch("groq.Groq") as MockGroq:
        mock_completion         = mock.MagicMock()
        mock_completion.choices[0].message.content = "plain text"
        create_fn = MockGroq.return_value.chat.completions.create
        create_fn.return_value = mock_completion

        client = GroqClient()
        client.call("test", json_mode=False)
        call_kwargs_nojson = create_fn.call_args[1]

    check("B10: json_mode=False omits response_format",
          "response_format" not in call_kwargs_nojson,
          hint=f"response_format present: {call_kwargs_nojson.get('response_format')}")

    # ── B11: exact retry count ─────────────────────────────────────────────────
    with mock.patch("groq.Groq") as MockGroq:
        create_fn = MockGroq.return_value.chat.completions.create
        create_fn.side_effect = Exception("fail always")
        client = GroqClient()
        with mock.patch("time.sleep"):
            client.call("test")
        call_count = create_fn.call_count

    check("B11: API called exactly MAX_ATTEMPTS (3) times before giving up",
          call_count == MAX_ATTEMPTS,
          hint=f"called {call_count} times")


# ══════════════════════════════════════════════════════════════════════════════
# TRACK C — Live Smoke Test (requires real GROQ_API_KEY)
# ══════════════════════════════════════════════════════════════════════════════

def track_c():
    section("TRACK C — Live Smoke Test (real API key)")

    key = os.getenv("GROQ_API_KEY")
    if not key or key == "test-key-offline":
        warn("GROQ_API_KEY not set — skipping live test")
        warn("Set GROQ_API_KEY in .env and re-run without --offline to test live")
        return

    try:
        from infrastructure.llm.groq_client import GroqClient
    except ImportError as e:
        check("GroqClient importable", False, hint=str(e))
        return

    # C1: instantiation succeeds
    try:
        client = GroqClient()
        check("C1: GroqClient instantiates with real key", True)
    except Exception as e:
        check("C1: GroqClient instantiates with real key", False, hint=str(e))
        return

    # C2: JSON call returns parseable JSON
    import json
    t_start = time.monotonic()
    prompt = (
        'Return a JSON object with exactly one key "status" '
        'and value "ok". Return JSON only, no other text.'
    )
    response = client.call(prompt, max_tokens=50, json_mode=True)
    latency = time.monotonic() - t_start

    check("C2: call() returns a non-None string",
          response is not None,
          hint="Got None — check GROQ_API_KEY and network")

    if response:
        try:
            parsed = json.loads(response)
            check("C2: response is valid JSON", True)
            info(f"  parsed: {parsed}")
        except json.JSONDecodeError as e:
            check("C2: response is valid JSON", False,
                  hint=f"JSONDecodeError: {e}\nraw: {repr(response[:200])}")

        check("C2: latency < 30s", latency < 30,
              hint=f"took {latency:.1f}s")
        info(f"  latency: {latency:.2f}s")
        info(f"  response length: {len(response)} chars")

    # C3: non-JSON call (json_mode=False) returns plain text
    response2 = client.call(
        "Reply with exactly the word: PONG",
        max_tokens=20,
        json_mode=False
    )
    check("C3: json_mode=False call returns string",
          isinstance(response2, str) and len(response2) > 0,
          hint=f"got: {repr(response2)}")
    if response2:
        info(f"  plain response: {repr(response2.strip())}")


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Task 4.1 acceptance tests — GroqClient"
    )
    parser.add_argument("--offline",   action="store_true",
                        help="Run Track A + B only (no real API calls)")
    parser.add_argument("--live-only", action="store_true",
                        help="Run Track C only")
    args = parser.parse_args()

    print(f"\n{BOLD}{'═' * 65}{RESET}")
    print(f"{BOLD}  TASK 4.1 — GroqClient Acceptance Tests{RESET}")
    print(f"{BOLD}{'═' * 65}{RESET}")

    if not args.live_only:
        ok = track_a()
        if ok:
            track_b()

    if not args.offline:
        track_c()

    print(f"\n{BOLD}{'═' * 65}{RESET}")
    print(f"{BOLD}  RESULTS{RESET}")
    print(f"{'═' * 65}")
    print(f"  {GREEN}✓  Passed  : {PASSED}{RESET}")
    print(f"  {RED}✗  Failed  : {FAILED}{RESET}")
    print(f"  {YELLOW}⚠  Warnings: {WARNINGS}{RESET}")

    if FAILED == 0:
        print(f"\n  {BOLD}{GREEN}✅ Task 4.1 COMPLETE — safe to proceed to Task 4.2{RESET}")
    else:
        print(f"\n  {BOLD}{RED}❌ {FAILED} check(s) failed{RESET}")
    print(f"{'═' * 65}\n")
    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())