"""Monitoring and validation callbacks for both agent frameworks.

One module, so what is watched and what is checked is the same for every
agent whichever framework it was built with:

  CrewAI   step_callback and task_callback on the Crew, a guardrail on the Task
  ADK      before/after agent, model and tool callbacks, plus model and tool
           error callbacks, on the LlmAgent

Each callback does two things:

  monitor   record what happened -- intermediate steps, model requests and
            replies, tool calls, errors -- as a `monitor` run event (readable
            from the API and the website's execution log) and, when the trace is
            on, as a line in the terminal.
  validate  check data crossing a boundary: instruction-like text is cut from
            what goes into a model, a tool's return is type-checked and
            sanitised, and a reply that is abusive, demeaning or has been
            hijacked by injected text is sent back.

Monitoring never raises: a bookkeeping failure must not fail a plan. The events
carry agent=None on purpose, so the website's step list (keyed by agent) is not
disturbed; the agent's name is in the payload.
"""

from agents._input_guard import output_problems, redact_instructions, sanitize_untrusted
from observability import trace
from storage.events import add_event

PREVIEW_CHARS = 300


def log(phase: str, agent: str, message: str, payload: dict | None = None) -> None:
    """One monitored moment: a terminal line and a saved `monitor` event."""
    trace.note(phase.upper(), f"{agent:<18}{message}")
    try:
        add_event(
            "monitor",
            message=f"{agent}: {message}",
            payload={"agent": agent, "phase": phase, **(payload or {})},
        )
    except Exception:  # noqa: BLE001 - bookkeeping must never break a model call
        pass


def _preview(value, limit: int = PREVIEW_CHARS) -> str:
    text = value if isinstance(value, str) else repr(value)
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


# ---------------------------------------------------------------- CrewAI --


def crew_step_callback(agent: str):
    """After each step of a CrewAI agent: a tool call, or the final answer."""

    def on_step(step) -> None:
        tool = getattr(step, "tool", None)
        if tool:
            log("step", agent, f"tool call: {tool}", {"tool": tool, "input": _preview(getattr(step, "tool_input", ""))})
        else:
            log("step", agent, "final answer ready", {"preview": _preview(getattr(step, "output", step))})

    return on_step


def crew_task_callback(agent: str):
    """After a CrewAI task completes: its output, as an intermediate result."""

    def on_task(output) -> None:
        raw = getattr(output, "raw", "") or ""
        log("task", agent, f"output ready ({len(raw)} chars)", {"preview": _preview(raw)})

    return on_task


def crew_output_guard(output):
    """CrewAI task guardrail: (ok, result-or-feedback). A failure sends the agent back once."""
    problems = output_problems(getattr(output, "raw", "") or "")
    if problems:
        log("guard", "crewai", "reply rejected: " + "; ".join(problems))
        return False, "Rewrite your answer: " + "; ".join(problems) + "."
    # The raw text, not the TaskOutput: CrewAI re-reads the structured
    # (Pydantic) result from it, whereas a returned TaskOutput lost it.
    return True, getattr(output, "raw", output)


def crew_kwargs(agent: str) -> dict:
    """Keyword arguments for `Crew(...)`."""
    return {"step_callback": crew_step_callback(agent), "task_callback": crew_task_callback(agent)}


def task_kwargs() -> dict:
    """Keyword arguments for `Task(...)`: the output guardrail and one retry."""
    return {"guardrail": crew_output_guard, "guardrail_max_retries": 1}


# ------------------------------------------------------------------- ADK --


def adk_callbacks(agent: str) -> dict:
    """Keyword arguments for `LlmAgent(...)`: every ADK callback, wired to `agent`."""

    def before_agent(callback_context):
        log("agent", agent, "started")
        return None

    def after_agent(callback_context):
        log("agent", agent, "finished")
        return None

    def before_model(callback_context, llm_request):
        cut = 0
        messages = 0
        for content in getattr(llm_request, "contents", None) or []:
            for part in getattr(content, "parts", None) or []:
                text = getattr(part, "text", None)
                if text:
                    messages += 1
                    redacted, removed = redact_instructions(text)
                    if removed:
                        part.text = redacted
                        cut += removed
        if cut:
            log("guard", agent, f"cut instruction-like text from {cut} line(s) before the model saw it")
        log("model", agent, f"request sent ({messages} text part(s))")
        return None

    def after_model(callback_context, llm_response):
        usage = getattr(llm_response, "usage_metadata", None)
        tokens = {
            "prompt_tokens": getattr(usage, "prompt_token_count", None),
            "completion_tokens": getattr(usage, "candidates_token_count", None),
        }
        log("model", agent, "reply received", tokens)
        return None

    def on_model_error(callback_context, llm_request, error):
        log("error", agent, f"model error: {type(error).__name__}: {_preview(str(error), 160)}")
        return None

    def before_tool(tool, args, tool_context):
        log("tool", agent, f"calling {getattr(tool, 'name', tool)}", {"args": _preview(args)})
        return None

    def after_tool(tool, args, tool_context, tool_response):
        return validate_tool_response(agent, getattr(tool, "name", str(tool)), tool_response)

    def on_tool_error(tool, args, tool_context, error):
        log("error", agent, f"tool {getattr(tool, 'name', tool)} failed: {type(error).__name__}: {_preview(str(error), 160)}")
        return None

    return {
        "before_agent_callback": before_agent,
        "after_agent_callback": after_agent,
        "before_model_callback": before_model,
        "after_model_callback": after_model,
        "on_model_error_callback": on_model_error,
        "before_tool_callback": before_tool,
        "after_tool_callback": after_tool,
        "on_tool_error_callback": on_tool_error,
    }


def validate_tool_response(agent: str, tool: str, response):
    """A tool's return, type-checked and made safe -- or None to keep it as it is.

    Anything that is not a mapping is wrapped, text fields lose instruction-like
    sentences and markup, and the result is what the model gets. Returning None
    tells ADK to keep the original; a dict replaces it.
    """
    if not isinstance(response, dict):
        log("guard", agent, f"tool {tool} returned {type(response).__name__}, expected a dict; wrapped")
        response = {"result": response}
        changed = True
    else:
        changed = False

    cleaned, cut = {}, 0
    for key, value in response.items():
        if isinstance(value, str):
            clean, flagged = sanitize_untrusted(value)
            cut += flagged
            cleaned[key] = clean
        else:
            cleaned[key] = value
    if cut:
        log("guard", agent, f"cut instruction-like text from tool {tool}'s reply ({cut} field(s))")
    log("tool", agent, f"{tool} returned", {"preview": _preview(cleaned)})
    return cleaned if (cut or changed) else None
