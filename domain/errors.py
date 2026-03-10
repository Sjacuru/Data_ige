from __future__ import annotations

"""
domain/errors.py

Typed exception hierarchy for the TCM-RJ auditing tool.

Design rules
────────────
- All custom exceptions inherit from AuditToolError.
- TransientError  → safe to retry automatically (network glitches, rate limits).
- PermanentError  → log and skip; retrying will not help.
- CriticalError   → stop the current stage; public entrypoints MUST catch this
                    and convert it to a safe fallback return value.

Migration note
──────────────
NoDocumentError currently lives in infrastructure/scrapers/transparencia/downloader.py.
MissingDocumentError is its canonical replacement here.
Full migration is deferred; the alias in downloader.py maintains backward compat.
"""


class AuditToolError(Exception):
    """Base class for all TCM-RJ auditing tool exceptions."""


class TransientError(AuditToolError):
    """Operation failed but may succeed on retry."""


class NetworkTimeoutError(TransientError):
    """HTTP or Selenium request timed out."""


class RateLimitError(TransientError):
    """API rate limit hit (e.g. HTTP 429 from Groq)."""


class PortalUnavailableError(TransientError):
    """Target portal is unreachable or returned 5xx."""


class PermanentError(AuditToolError):
    """Operation failed and will not succeed on retry."""


class MissingDocumentError(PermanentError):
    """Document does not exist on the portal for this processo_id."""


class InvalidURLError(PermanentError):
    """URL is malformed or points to a non-existent resource."""


class ExtractionFailedError(PermanentError):
    """Data could not be extracted from the document (OCR/parse failure)."""


class CriticalError(AuditToolError):
    """
    Environment failure that makes further processing impossible.
    RetryPolicy.execute() re-raises this immediately.
    All public stage functions MUST catch CriticalError and return a safe fallback.
    """


class AuthenticationError(CriticalError):
    """API key missing, invalid, or rejected."""


class DiskSpaceError(CriticalError):
    """Insufficient disk space to continue."""


class ConfigurationError(CriticalError):
    """Required configuration is absent or malformed."""
