"""Shared retry decorator for provider rate limits.

Groq's free tier throttles output tokens per minute, and running several
agents back-to-back trips it routinely. Neither framework retries usefully
on its own: CrewAI/instructor gives up after one attempt in practice, and
ADK surfaces the failure as a bare `DynamicNodeFailError: Dynamic node
<name> failed`.

Two things this gets right that the obvious implementation doesn't:

1. Detection walks the whole exception chain, not just the outer message.
   Each layer wraps the error differently -- litellm raises RateLimitError,
   instructor wraps it in InstructorRetryException, and ADK replaces it
   entirely with DynamicNodeFailError whose own message says nothing about
   rate limits; only __cause__/__context__ still carries the 429. Matching
   on the outer message or on exception class silently misses the ADK case.

2. Wait length comes from the error itself where possible. Groq's transient
   error carries "Please try again in 4.26s", so we sleep that long instead
   of guessing. The other flavour -- "Request too large ... expected output
   tokens exceed the enforced limit" -- looks permanent but is NOT: it means
   the per-minute output budget is throttled down right now, and the same
   request succeeds once the window resets (verified directly: a 2000-token
   completion that this error rejected went through fine minutes later). It
   carries no hint, so it gets a full window wait.
"""

import re
import time
from functools import wraps

_RATE_LIMIT_MARKERS = (
    "rate_limit",
    "rate limit",
    "resource_exhausted",
    "429",
    "too many requests",
    "request too large",
)

# Transient network/server faults. These show up once the execution agents
# run concurrently -- four simultaneous connections to the same provider
# gets one reset often enough to fail a run, and a reset is exactly the
# thing worth retrying. Kept separate from the rate-limit markers because
# these need no cooldown: retry promptly rather than waiting out a window.
_TRANSIENT_MARKERS = (
    "connection forcibly closed",
    "winerror 10054",
    "connectionreset",
    "connection reset",
    "connecterror",
    "remote end closed",
    "server disconnected",
    "internalservererror",
    "502",
    "503",
    "504",
)
_TRANSIENT_WAIT_SECONDS = 2.0

# "Please try again in 4.26s" / "in 21.06s"
_RETRY_HINT = re.compile(r"try again in ([\d.]+)s", re.IGNORECASE)

# No hint accompanies this one, and it only clears on a window reset.
_NEEDS_FULL_WINDOW = "request too large"

FULL_WINDOW_SECONDS = 62.0
MAX_SLEEP_SECONDS = 90.0


def _chain(exc: BaseException):
    seen = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


def _describe(exc: BaseException) -> str:
    return " | ".join(f"{type(e).__name__}: {e}" for e in _chain(exc)).lower()


def _is_rate_limit(exc: BaseException) -> bool:
    text = _describe(exc)
    return any(marker in text for marker in _RATE_LIMIT_MARKERS)


def _is_transient(exc: BaseException) -> bool:
    text = _describe(exc)
    return any(marker in text for marker in _TRANSIENT_MARKERS)


def _is_retryable(exc: BaseException) -> bool:
    return _is_rate_limit(exc) or _is_transient(exc)


def _wait_for(exc: BaseException, default: float) -> float:
    """How long to sleep before retrying, preferring the provider's own hint."""
    text = _describe(exc)
    match = _RETRY_HINT.search(text)
    if match:
        # Small buffer: the hint is the exact boundary, and landing on it
        # re-trips the limit.
        return min(float(match.group(1)) + 1.0, MAX_SLEEP_SECONDS)
    if _NEEDS_FULL_WINDOW in text:
        return FULL_WINDOW_SECONDS
    # A dropped connection isn't a quota problem -- nothing is refilling, so
    # waiting a full window just wastes time. Retry promptly.
    if _is_transient(exc) and not _is_rate_limit(exc):
        return _TRANSIENT_WAIT_SECONDS
    return default


def retry_on_rate_limit(max_attempts: int = 4, wait_seconds: float = 15.0):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(max_attempts):
                try:
                    return fn(*args, **kwargs)
                except Exception as e:
                    if not _is_retryable(e):
                        raise
                    last_exc = e
                    if attempt < max_attempts - 1:
                        time.sleep(_wait_for(e, wait_seconds))
            raise last_exc

        return wrapper

    return decorator
