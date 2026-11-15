"""Langfuse tracing for every model call, switched on by environment variables.

Both agent frameworks reach their model through LiteLLM (CrewAI's `LLM`, ADK's
`LiteLlm`), so one LiteLLM callback sees every call from every agent: prompt,
reply, tokens, latency and cost, exported to Langfuse over OpenTelemetry.

What this adds on top of the plain integration:

  trace name + session   each call is tagged with its agent and with the run
                         (`session_id = run-<id>`), so Langfuse can show one run
                         as a session and one agent as a named trace.
                         `llm_metadata()` builds the tags; every agent passes
                         them when it creates its model object.
  customer privacy       the CRM agent's prompt and reply contain customer names
                         and spend. They are replaced before the call is sent to
                         Langfuse (the model still receives the real text).

Off unless LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are both set, so tests,
the CLI and a laptop without keys behave exactly as before.

    LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY   from the Langfuse project
    LANGFUSE_HOST                              e.g. https://us.cloud.langfuse.com
    LANGFUSE_REGION                            EU or US, used when no host is set
"""

import copy
import os

MASK_AGENTS = {"crm"}
MASKED_TEXT = "[customer data withheld from tracing]"
_HOSTS = {"EU": "https://cloud.langfuse.com", "US": "https://us.cloud.langfuse.com"}
_installed = False
_logger = None


def enabled() -> bool:
    return bool(os.environ.get("LANGFUSE_PUBLIC_KEY", "").strip() and os.environ.get("LANGFUSE_SECRET_KEY", "").strip())


def _run_label() -> str:
    """The run a call belongs to: this thread's run if it has one, else the newest.

    litellm reports calls from its own logging thread, which carries no run, so
    the newest run is the fallback (right whenever one plan is running at a time).
    Never opens a run: a tracing lookup must not create database rows.
    """
    try:
        from storage import runs

        return str(runs._current_run_id.get() or runs.latest_run_id() or "unknown")
    except Exception:  # noqa: BLE001
        return "unknown"


def llm_metadata(agent: str) -> dict:
    """Keyword arguments to pass when creating an agent's model object ({} when off).

    CrewAI's `LLM(...)` and ADK's `LiteLlm(...)` both forward extra keyword
    arguments to every LiteLLM call, which is how the tags reach the callback.
    """
    if not enabled():
        return {}
    return {"metadata": _tags(agent)}


def _tags(agent: str) -> dict:
    return {
        "trace_name": agent,
        "generation_name": agent,
        "session_id": f"run-{_run_label()}",
        "tags": ["flywheel", agent],
    }


def enrich(kwargs: dict) -> dict:
    """The call's kwargs with agent tags added if they are missing.

    CrewAI's structured-output step makes the model call through a path that does
    not carry the tags set on the agent's LLM, so the agent is recovered from the
    prompt itself -- the same lookup the usage tracking uses.
    """
    params = (kwargs or {}).get("litellm_params") or {}
    if (params.get("metadata") or {}).get("trace_name"):
        return kwargs
    try:
        from observability.usage import agent_for_messages

        found = agent_for_messages(kwargs.get("messages"))
    except Exception:  # noqa: BLE001
        found = None
    if not found:
        return kwargs
    merged = {**(params.get("metadata") or {}), **_tags(found[0])}
    return {**kwargs, "litellm_params": {**params, "metadata": merged}}


def _is_masked(kwargs: dict) -> bool:
    metadata = ((kwargs or {}).get("litellm_params") or {}).get("metadata") or {}
    return metadata.get("trace_name") in MASK_AGENTS


def masked(kwargs: dict, response_obj):
    """(kwargs, response) as Langfuse should see them -- copies, never the originals.

    The response object is what the agent goes on to read, so it is copied before
    any text in it is replaced.
    """
    kwargs = enrich(kwargs)
    if not _is_masked(kwargs):
        return kwargs, response_obj
    safe = dict(kwargs)
    safe["messages"] = [
        {**m, "content": MASKED_TEXT} if isinstance(m, dict) else m for m in (kwargs.get("messages") or [])
    ]
    safe_response = response_obj
    try:
        safe_response = copy.deepcopy(response_obj)
        for choice in getattr(safe_response, "choices", None) or []:
            message = getattr(choice, "message", None)
            if message is not None and getattr(message, "content", None):
                message.content = MASKED_TEXT
    except Exception:  # noqa: BLE001 - if it cannot be copied, send no reply text at all
        safe_response = None
    return safe, safe_response


def _build_logger():
    from litellm.integrations.langfuse.langfuse_otel import LangfuseOtelLogger

    class MaskedLangfuseOtel(LangfuseOtelLogger):
        def log_success_event(self, kwargs, response_obj, start_time, end_time):
            safe, response = masked(kwargs, response_obj)
            return super().log_success_event(safe, response, start_time, end_time)

        async def async_log_success_event(self, kwargs, response_obj, start_time, end_time):
            safe, response = masked(kwargs, response_obj)
            return await super().async_log_success_event(safe, response, start_time, end_time)

        def log_failure_event(self, kwargs, response_obj, start_time, end_time):
            safe, response = masked(kwargs, response_obj)
            return super().log_failure_event(safe, response, start_time, end_time)

        async def async_log_failure_event(self, kwargs, response_obj, start_time, end_time):
            safe, response = masked(kwargs, response_obj)
            return await super().async_log_failure_event(safe, response, start_time, end_time)

    # callback_name selects LiteLLM's Langfuse-specific attribute code (trace name,
    # session, tags); without it the span carries only the generic fields.
    return MaskedLangfuseOtel(callback_name="langfuse_otel")


def install() -> bool:
    """Start exporting model calls to Langfuse. Safe to call more than once."""
    global _installed, _logger
    if _installed:
        return True
    if not enabled():
        return False
    region = os.environ.get("LANGFUSE_REGION", "").strip().upper()
    if not os.environ.get("LANGFUSE_HOST") and region in _HOSTS:
        os.environ["LANGFUSE_HOST"] = _HOSTS[region]
    try:
        import litellm

        _logger = _build_logger()
        # The success/failure lists, not `litellm.callbacks`: CrewAI replaces
        # `litellm.callbacks` with an empty list every time it creates a model
        # object, which silently removed the logger after the first agent.
        for name in ("success_callback", "failure_callback", "_async_success_callback", "_async_failure_callback"):
            registered = getattr(litellm, name, None)
            if registered is not None and _logger not in registered:
                registered.append(_logger)
        _installed = True
        return True
    except Exception as exc:  # noqa: BLE001 - an unreachable tracer must not stop the app
        print(f"langfuse tracing not started: {type(exc).__name__}: {exc}")
        return False


def flush() -> None:
    """Send anything still queued. Spans are exported in batches in the background,
    so a short-lived process (a script, a test of the integration) calls this
    before it exits."""
    try:
        from opentelemetry import trace

        provider = trace.get_tracer_provider()
        if hasattr(provider, "force_flush"):
            provider.force_flush(10_000)
    except Exception:  # noqa: BLE001
        pass
    if _logger is not None:
        try:
            _logger.tracer_provider.force_flush(10_000)  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass
