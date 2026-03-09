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
import time
from typing import Optional

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
DEFAULT_MODEL      = "llama-3.3-70b-versatile"
DEFAULT_MAX_TOKENS = 1000
DEFAULT_TEMPERATURE = 0.0
MAX_ATTEMPTS       = 3
BASE_DELAY_SECONDS = 2
RATE_LIMIT_WAIT    = 60   # seconds to wait when Groq returns HTTP 429


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
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                t_start = time.monotonic()

                kwargs: dict = {
                    "model":       model,
                    "max_tokens":  max_tokens,
                    "temperature": temperature,
                    "messages": [
                        {"role": "user", "content": prompt}
                    ],
                }
                if json_mode:
                    kwargs["response_format"] = {"type": "json_object"}

                completion = self._client.chat.completions.create(**kwargs)

                latency   = time.monotonic() - t_start
                content   = completion.choices[0].message.content or ""

                logger.info(
                    "Groq call OK | model=%s | prompt_chars=%d | "
                    "response_chars=%d | latency=%.2fs | attempt=%d/%d",
                    model, len(prompt), len(content),
                    latency, attempt, MAX_ATTEMPTS,
                )
                return content

            except Exception as exc:
                wait = self._classify_and_wait(exc, attempt)
                logger.warning(
                    "Groq call failed (attempt %d/%d): %s — waiting %.0fs",
                    attempt, MAX_ATTEMPTS, exc, wait,
                )
                if attempt < MAX_ATTEMPTS:
                    time.sleep(wait)
                else:
                    logger.error(
                        "Groq call exhausted all %d attempts. Returning None.",
                        MAX_ATTEMPTS,
                    )
                    return None

        return None  # unreachable but satisfies type checker

    # ── Internal helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _classify_and_wait(exc: Exception, attempt: int) -> float:
        """
        Return the number of seconds to sleep before the next attempt.

        HTTP 429 (rate limit) → fixed RATE_LIMIT_WAIT seconds.
        Any other error       → exponential backoff (2^attempt * BASE_DELAY).
        """
        exc_str = str(exc).lower()
        if "429" in exc_str or "rate limit" in exc_str or "rate_limit" in exc_str:
            logger.warning(
                "Rate limit hit (HTTP 429). Waiting %ds before retry.",
                RATE_LIMIT_WAIT,
            )
            return float(RATE_LIMIT_WAIT)

        delay = BASE_DELAY_SECONDS * (2 ** (attempt - 1))  # 2s, 4s, 8s
        return float(delay)