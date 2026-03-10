from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Tuple, Type

from domain.errors import (
    AuditToolError,
    CriticalError,
    PermanentError,
    RateLimitError,
    TransientError,
)

logger = logging.getLogger(__name__)

_DEFAULT_RETRYABLE: Tuple[Type[Exception], ...] = (TransientError, Exception)


@dataclass
class RetryPolicy:
    """
    Configurable retry engine with exponential backoff.

    PUBLIC FUNCTION SAFETY WARNING
    ──────────────────────────────
    execute() re-raises CriticalError immediately. This is intentional —
    a critical error (auth failure, disk full) means no retry can succeed
    and the stage must stop.

    However, execute() is NOT a public stage entrypoint. Every public
    run_stageN_*() function and every client method (e.g. GroqClient.call())
    that calls execute() MUST wrap it in try/except CriticalError and
    convert it to a safe fallback return value (None, error dict, etc.).

    This preserves the project rule: "public functions never raise."

    Backoff schedule (base_delay=2.0, max_delay=32.0):
        Attempt 1 fails → wait  2 s
        Attempt 2 fails → wait  4 s
        Attempt 3 fails → wait  8 s
        Attempt 4 fails → wait 16 s
        Attempt 5 fails → wait 32 s → exhausted → return None

    Rate limit override:
        RateLimitError always waits rate_limit_wait seconds (fixed, not exponential).
    """

    max_attempts: int = 5
    base_delay: float = 2.0
    max_delay: float = 32.0
    rate_limit_wait: float = 60.0

    _retryable_types: Tuple[Type[Exception], ...] = field(default=_DEFAULT_RETRYABLE, init=False, repr=False)

    def _delay_for(self, attempt: int, exc: Exception) -> float:
        """
        Return how many seconds to wait before the next attempt.
        attempt is 1-based (first failure = attempt 1).
        """
        if isinstance(exc, RateLimitError):
            return self.rate_limit_wait
        delay = self.base_delay * (2 ** (attempt - 1))
        return min(delay, self.max_delay)

    def execute(self, fn: Callable, *args: Any, **kwargs: Any) -> Optional[Any]:
        """
        Call fn(*args, **kwargs) up to max_attempts times.

        Returns:
            fn's return value on success.
            None after all attempts are exhausted.

        Raises:
            CriticalError — immediately, without retry, without wrapping.
                            Callers MUST catch this (see class docstring).

        Never raises any other exception.
        """
        last_exc: Optional[Exception] = None

        for attempt in range(1, self.max_attempts + 1):
            try:
                result = fn(*args, **kwargs)
                if attempt > 1:
                    logger.info(
                        "RetryPolicy: succeeded on attempt %d/%d",
                        attempt,
                        self.max_attempts,
                    )
                return result

            except CriticalError:
                logger.error(
                    "RetryPolicy: CriticalError on attempt %d — aborting",
                    attempt,
                )
                raise

            except PermanentError as exc:
                logger.warning(
                    "RetryPolicy: PermanentError on attempt %d — skipping: %s",
                    attempt,
                    exc,
                )
                return None

            except Exception as exc:
                last_exc = exc
                delay = self._delay_for(attempt, exc)

                if attempt < self.max_attempts:
                    logger.warning(
                        "RetryPolicy: attempt %d/%d failed (%s: %s) — retrying in %.1fs",
                        attempt,
                        self.max_attempts,
                        type(exc).__name__,
                        exc,
                        delay,
                    )
                    time.sleep(delay)
                else:
                    logger.error(
                        "RetryPolicy: all %d attempts exhausted. Last error (%s): %s",
                        self.max_attempts,
                        type(exc).__name__,
                        last_exc,
                    )

        return None
