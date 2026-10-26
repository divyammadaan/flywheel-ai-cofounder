import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from agents._retry import (
    FULL_WINDOW_SECONDS,
    _is_rate_limit,
    _is_retryable,
    _wait_for,
    retry_on_rate_limit,
)


def test_wait_uses_providers_own_hint():
    exc = RuntimeError("Rate limit reached ... Please try again in 4.26s. Upgrade to Dev Tier")
    # hint + 1s buffer, so we don't land exactly on the boundary and re-trip
    assert _wait_for(exc, default=15.0) == pytest.approx(5.26)


def test_request_too_large_waits_a_full_window():
    exc = RuntimeError(
        "Request too large for model `qwen` ... on output tokens per minute (OTPM): "
        "Limit 1000, Requested 1513. The request's expected output tokens exceed the enforced limit"
    )
    assert _wait_for(exc, default=15.0) == FULL_WINDOW_SECONDS


def test_request_too_large_is_treated_as_retryable():
    """It reads like a permanent error but isn't -- it clears on a window
    reset. Treating it as fatal would abort flows that would have succeeded."""
    exc = RuntimeError("Request too large for model `qwen`: expected output tokens exceed the enforced limit")
    assert _is_rate_limit(exc)


def test_falls_back_to_default_wait_without_a_hint():
    exc = RuntimeError("429 too many requests")
    assert _wait_for(exc, default=15.0) == 15.0


def test_connection_reset_is_retryable():
    """Four concurrent execution agents against one provider drops a
    connection often enough to fail a run. A reset is worth retrying."""
    exc = RuntimeError("[WinError 10054] An existing connection was forcibly closed by the remote host")
    assert _is_rate_limit(exc) is False
    assert retry_on_rate_limit  # decorator still the public entry point

    calls = []

    @retry_on_rate_limit(max_attempts=3, wait_seconds=0.01)
    def flaky_connection():
        calls.append(1)
        if len(calls) < 2:
            raise RuntimeError("[WinError 10054] An existing connection was forcibly closed by the remote host")
        return "ok"

    assert flaky_connection() == "ok"
    assert len(calls) == 2


def test_connection_reset_retries_promptly_not_after_a_full_window():
    """Nothing is refilling on a dropped connection, so waiting out a
    rate-limit window would just waste a minute."""
    exc = RuntimeError("ConnectError: server disconnected")
    assert _wait_for(exc, default=15.0) < 5.0


def test_retries_until_success_on_rate_limit():
    calls = []

    @retry_on_rate_limit(max_attempts=3, wait_seconds=0.01)
    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise RuntimeError("rate_limit_exceeded: slow down")
        return "ok"

    assert flaky() == "ok"
    assert len(calls) == 3


def test_does_not_retry_other_errors():
    calls = []

    @retry_on_rate_limit(max_attempts=3, wait_seconds=0.01)
    def broken():
        calls.append(1)
        raise ValueError("schema validation failed")

    with pytest.raises(ValueError):
        broken()
    assert len(calls) == 1, "non-rate-limit errors must fail fast, not burn retries"


def test_retries_when_rate_limit_is_only_in_the_wrapped_cause():
    """ADK reports the failure as a bare 'Dynamic node X failed' -- the 429
    only survives in __cause__. Matching the outer message alone misses it."""
    calls = []

    @retry_on_rate_limit(max_attempts=3, wait_seconds=0.01)
    def adk_style():
        calls.append(1)
        if len(calls) < 2:
            try:
                raise RuntimeError("429 RESOURCE_EXHAUSTED: quota exceeded")
            except RuntimeError as inner:
                raise RuntimeError("Dynamic node strategy_agent failed") from inner
        return "ok"

    assert adk_style() == "ok"
    assert len(calls) == 2


def test_retries_on_implicit_context_chain():
    """Same, but raised during handling rather than with `from` -- the error
    lands in __context__ instead of __cause__."""
    calls = []

    @retry_on_rate_limit(max_attempts=3, wait_seconds=0.01)
    def implicit_chain():
        calls.append(1)
        if len(calls) < 2:
            try:
                raise RuntimeError("too many requests")
            except RuntimeError:
                raise RuntimeError("node failed")
        return "ok"

    assert implicit_chain() == "ok"
    assert len(calls) == 2


def test_reraises_after_max_attempts():
    calls = []

    @retry_on_rate_limit(max_attempts=2, wait_seconds=0.01)
    def always_limited():
        calls.append(1)
        raise RuntimeError("rate_limit_exceeded")

    with pytest.raises(RuntimeError):
        always_limited()
    assert len(calls) == 2


# ------------------------------------------------- bad samples, not bad requests --

# The exact payload that killed a live run at the Analytics step: Groq's JSON
# mode rejected the completion and handed back what the model actually emitted.
_GROQ_JSON_FAILURE = (
    'litellm.BadRequestError: GroqException - {"error":{"message":"Failed to generate '
    "JSON. Please adjust your prompt. See 'failed_generation' for more details.\","
    '"type":"invalid_request_error","code":"json_validate_failed",'
    '"failed_generation":"{\u03a3"}}'
)

# The CrewAI/forced-tool-calling equivalent, from an earlier failed run.
_GROQ_TOOL_FAILURE = (
    "InstructorRetryException: litellm.BadRequestError: GroqException - "
    '{"error":{"message":"tool call validation failed: parameters for tool '
    'MarketingOutputSchema did not match schema"}}'
)


@pytest.mark.parametrize("message", [_GROQ_JSON_FAILURE, _GROQ_TOOL_FAILURE])
def test_a_bad_sample_is_retryable(message):
    """The request was fine; the model emitted junk. Re-sampling usually fixes it.

    Both arrive as BadRequestError, which normally means "do not retry" -- but
    these say the model failed to produce schema-valid output, not that we sent
    a bad request.
    """
    assert _is_retryable(RuntimeError(message))


def test_a_bad_sample_retries_promptly_rather_than_waiting_out_a_window():
    """No quota is refilling, so a full-window wait would only waste a minute."""
    wait = _wait_for(RuntimeError(_GROQ_JSON_FAILURE), default=15.0)
    assert wait == pytest.approx(1.5)
    assert wait < FULL_WINDOW_SECONDS


def test_a_bad_sample_is_retried_until_it_decodes():
    attempts = []

    @retry_on_rate_limit(max_attempts=4, wait_seconds=0.01)
    def flaky():
        attempts.append(1)
        if len(attempts) < 3:
            raise RuntimeError(_GROQ_JSON_FAILURE)
        return "valid json at last"

    assert flaky() == "valid json at last"
    assert len(attempts) == 3


def test_a_genuinely_malformed_request_still_fails_fast():
    """The narrowness is the point: retrying an unknown model eight times
    helps nobody and delays the error the founder needs to see."""
    calls = []

    @retry_on_rate_limit(max_attempts=5, wait_seconds=0.01)
    def broken():
        calls.append(1)
        raise RuntimeError(
            "litellm.BadRequestError: GroqException - "
            '{"error":{"message":"The model `qwen/nonexistent` does not exist",'
            '"type":"invalid_request_error","code":"model_not_found"}}'
        )

    with pytest.raises(RuntimeError):
        broken()
    assert len(calls) == 1
