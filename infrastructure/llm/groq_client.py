"""
infrastructure/llm/groq_client.py

Thin, reusable Groq API transport wrapper.
No prompt logic here — only connection, retry, and logging.

Dependency
──────────
Requires the official Groq SDK:
    pip install groq

This is separate from the legacy langchain-groq used in earlier scripts.
Add to requirements.txt:  groq>=0.9.0

Usage
─────
    from infrastructure.llm.groq_client import GroqClient

    client = GroqClient()                       # reads GROQ_API_KEY from env
    response = client.call(prompt)              # returns str or None
    response = client.call(prompt,
                           max_tokens=500,
                           json_mode=False)

Contract
────────
    call() NEVER raises. On exhausted retries it returns None.
    Callers must handle None → treat rule as INCONCLUSIVE.

Retry strategy
──────────────
    Attempt 1 → wait 2s  → Attempt 2 → wait 4s  → Attempt 3 → None
    HTTP 429 (rate limit) → wait 60s then retry (counts as one attempt)
    Any other exception   → wait base_delay * 2^attempt then retry
"""

import logging
import os
from typing import Optional

from domain.errors import CriticalError, RateLimitError, TransientError
from infrastructure.resilience.retry_policy import RetryPolicy

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
DEFAULT_MODEL      = "llama-3.3-70b-versatile"
DEFAULT_MAX_TOKENS = 1000
DEFAULT_TEMPERATURE = 0.0
MAX_ATTEMPTS       = 3
BASE_DELAY_SECONDS = 2
RATE_LIMIT_WAIT    = 60   # seconds to wait when Groq returns HTTP 429

MAX_ATTEMPTS       = 5

_RETRY_POLICY = RetryPolicy(
    max_attempts=5,
    base_delay=BASE_DELAY_SECONDS,
    max_delay=32.0,
    rate_limit_wait=RATE_LIMIT_WAIT,
)


class GroqClient:
    """
    Thin Groq API wrapper.

    Reads GROQ_API_KEY from the environment (loaded via config/settings.py
    which calls load_dotenv() at import time).

    Thread-safety: a single Groq client instance is reused across calls.
    The Groq SDK is stateless between calls, so sharing is safe.
    """

    def __init__(self) -> None:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "GROQ_API_KEY not found in environment. "
                "Add it to your .env file or set it as an environment variable."
            )
        try:
            from groq import Groq
            self._client = Groq(api_key=api_key)
        except ImportError:
            raise ImportError(
                "The 'groq' package is not installed. "
                "Run: pip install groq>=0.9.0"
            )
        logger.info("GroqClient initialised — model default: %s", DEFAULT_MODEL)

    # ── Public API ─────────────────────────────────────────────────────────────

    def call(
        self,
        prompt: str,
        model: str = DEFAULT_MODEL,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
        json_mode: bool = True,
    ) -> Optional[str]:
        """
        Send a prompt to the Groq API and return the response text.

        Args:
            prompt:      The user prompt. Include system-level instructions
                         inside the prompt itself (single-turn pattern).
            model:       Groq model identifier.
            max_tokens:  Maximum tokens in the response.
            temperature: Sampling temperature (0.0 = deterministic).
            json_mode:   When True, sets response_format={"type":"json_object"}.
                         The prompt MUST instruct the model to return JSON only.

        Returns:
            The response content string, or None if all retries are exhausted.
        """
        def _attempt_call(
            prompt: str,
            model: str,
            max_tokens: int,
            temperature: float,
            json_mode: bool,
        ) -> Optional[str]:
            """Inner function passed to RetryPolicy.execute()."""
            response_format = {"type": "json_object"} if json_mode else None
            kwargs: dict = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
            if response_format:
                kwargs["response_format"] = response_format

            try:
                response = self._client.chat.completions.create(**kwargs)
                text = response.choices[0].message.content
                logger.debug("GroqClient: received %d chars", len(text or ""))
                return text
            except Exception as exc:
                exc_str = str(exc).lower()
                if "429" in exc_str or "rate limit" in exc_str:
                    raise RateLimitError(str(exc)) from exc
                raise TransientError(str(exc)) from exc

        try:
            result = _RETRY_POLICY.execute(_attempt_call, prompt, model, max_tokens, temperature, json_mode)
            return result
        except CriticalError as exc:
            logger.error("GroqClient: CriticalError — returning None: %s", exc)
            return None
        except Exception as exc:
            logger.warning("GroqClient: unexpected error — returning None: %s", exc)
            return None