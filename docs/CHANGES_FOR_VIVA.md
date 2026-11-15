# What changed for the end term, in plain language

For each change: what it is, why it was needed, where the code is, and the one-sentence
answer if you are asked about it. Read the code named here before the viva; the handout
says every team member must be able to explain and modify any part.

## 1. Safety on the way in (`agents/_input_guard.py`)

**What.** Before any text reaches a model it is checked. The founder's own text (idea,
answers, change notes) is refused with a reason if it contains abusive language or an
instruction aimed at overriding the assistant ("ignore all previous instructions…").
Text a *tool* brings back (web-search snippets) is treated as untrusted: its type is
checked, markup is stripped and instruction-like sentences are cut out.

**Why.** Anyone can publish a web page that says "ignore your instructions", and a search
result is read by the model. The course lists prompt injection and tool-return validation
explicitly.

**Where.** `check_user_text` is called by the request schemas (`api/schemas.py`) and by
`IntakeAgent.process`. `clean_sources` runs on search results (`tools/web_search.py`, and
inside the MCP `web_search` tool). Tests: `tests/test_input_guard.py`.

**Say.** "Rules, not another model: they are fast, testable offline and cannot be talked
out of their answer. They are a baseline, not a complete defence."

Also: the advisor's verdict is now a strict `GO | PIVOT | NO_GO` type (`agents/founder_advisor.py`),
so a reworded "no go" can no longer slip past the stop.

## 2. Callbacks that watch every agent (`observability/callbacks.py`)

**What.** Both frameworks have hooks that fire as an agent works. One module attaches them:
CrewAI's `step_callback`, `task_callback` and a task `guardrail`; ADK's agent, model and tool
callbacks (before, after, and on error). Each writes a `monitor` event to the run and a line to
the terminal. The ADK model callback also cuts injected lines out of a prompt; the ADK tool
callback type-checks a tool's return.

**Why.** The brief asks for monitoring through callbacks, covering intermediate outputs, flow
and errors.

**Where.** `crew_kwargs` / `task_kwargs` are spread into every CrewAI `Crew(...)`/`Task(...)`;
`adk_callbacks` into the two ADK `LlmAgent(...)`s. Tests: `tests/test_callbacks.py`.

**Say.** "Callbacks are the framework's own extension points, so we watch an agent without
changing what it does."

## 3. Live agent trace (`observability/trace.py`)

**What.** The server terminal (and the command-line flows) print each agent starting, its model
call with tokens and time, finishing and saving, in order.

**Why.** The agents run on background threads and used to report only to the database, so there
was nothing to see in the terminal.

**How.** A `@traced("agent")` decorator on every agent's entry method, plus a print in the two
places every agent already reports to (`log_decision`, `record_usage`).

## 4. Langfuse tracing (`observability/langfuse_setup.py`)

**What.** Every model call from both frameworks is sent to Langfuse with its prompt, reply,
tokens, latency and cost, named by agent and grouped by run.

**How.** CrewAI and ADK both call models through LiteLLM, which has a Langfuse integration; one
callback sees everything. Two details worth knowing: CrewAI wipes LiteLLM's callback list each
time it creates a model object, so the logger is registered in the success/failure lists that
CrewAI leaves alone; and CrewAI's structured-output step makes the call without the tags set on
the agent, so the agent is recovered from the prompt itself (the same lookup the usage tracking
uses). The CRM call is **masked** before it leaves, because it contains customer names.

**Say.** "One integration point under both frameworks, off unless the keys are set."

## 5. Tools through MCP (`tools/mcp_server.py`, `tools/mcp_client_tool.py`)

**What.** The project's tools sit behind the Model Context Protocol: web search, a cash
calculator, an order-file parser and the decision-record history. The engine calls them over
stdio in a separate process. Market Research's web evidence, Finance's reserve and break-even,
and CRM's comparison with last period all come through it.

**Why.** The brief asks for tool integration using MCP, with at least two tools.

**Safety net.** Each use has a local fallback (`with_fallback`), so an MCP failure costs a
little time, never a plan. Before this change a failing MCP lookup killed the whole plan.

**Say.** "The arithmetic is identical either way; MCP changes how the tool is reached, and a
test proves the MCP answer equals the local function's."

## 6. A2A between ADK and CrewAI (`orchestration/a2a_bridge.py`, `adk_coordinator.py`)

**What.** Marketing, Sales, Product and CRM are CrewAI agents. They are published over the A2A
protocol, each with an Agent Card. A Google ADK `ParallelAgent` whose members are
`RemoteA2aAgent`s calls them at the same time. The ADK side never imports a CrewAI agent: it
knows only a card URL and a message shape.

**Why.** The brief asks for A2A, with the example of one agent in ADK and another in CrewAI.

**State.** The ADK session carries the shared context: the brief, the budgets, and a snapshot
of the plan so far (`FinalPlan`).

**Fallback.** If the A2A agents cannot be reached the same agents run in-process, and the
decision record says which path ran (`transport`).

**Say.** "The coordinator is ADK, the workers are CrewAI, and they meet only at the protocol."

## 7. The plan as one structured object (`orchestration/final_plan.py`)

**What.** `FinalPlan` is a Pydantic model that gathers every agent's newest result for a run. It
is the run's state while it is being built and its final output when done; exported as JSON
(`/runs/{id}/plan.json`) and Markdown (`/plan.md`).

**Why.** The brief asks for final output in a structured form using Pydantic.

## 8. CRM moved to Groq — and what that costs

**What.** CRM was a local Ollama model so customer names never left the machine. A hosted
deployment cannot use a model on a laptop, so CRM is now a CrewAI agent on Groq. It takes about
3 seconds instead of about a minute.

**The honest consequence.** The CRM prompt contains customer names and spend, and Groq processes
it. They are masked in Langfuse. The handout's local-LLM outcome (CO2) is no longer demonstrated
by the running system. Say this plainly if asked; do not claim customer data stays local.

## 9. Making it work on Postgres

Found by testing against the real hosted database:

- Hosts hand out `postgresql://`; the code now names the installed driver (`storage/db.py: normalise_url`).
- Event numbers were allocated as "highest + 1", which two concurrent writers both read as the
  same number: on Postgres 15 of 20 simultaneous events were lost to a unique-key error. Writes
  are now serialised on every database.
- Two threads starting at once could both create the tables; the engine is now built under a lock and published only after its tables exist.
- Ad images lived on the server's disk, which a host wipes on restart; they are stored in the database (`run_assets`, migration 0004).

## 10. Protecting a public deployment (`api/security.py`)

A shared access code (`FLYWHEEL_ACCESS_CODE`) is required on every request except `/health` and
the docs; the website asks for it once. A per-address rate limit caps how many plans can be
started an hour. Both exist because every plan spends the owner's free model quota.

## 11. Smaller fixes made on the way

- The parallel agents lost track of which run they belonged to (a `ContextVar` is not inherited by a pool thread), so their usage and events could land on a different run. Fixed with a copied context.
- **Retries made the request bigger each time** (found by the evaluation). The two ADK agents keep a conversation session; when a call failed (for example a Groq rate limit) the retry sent the same message again into the same session, so the second request carried it twice, the third three times, and so on. One Strategy request reached 7,958 tokens against Groq's 7,000-per-minute input limit and could never succeed. Each failed attempt now starts a clean session (`_reset_session` in `agents/strategy.py` and `agents/analytics.py`); a deliberate revision after a good reply keeps its session, because there the earlier answer is wanted. `tests/test_adk_sessions.py` shows 1, 1, 1, 1 messages per request with the fix and 1, 2, 3, 4 without it.
- The test suite made real model calls from a test (one test resumed a run with the real advisor) and leaked background jobs into later tests. Tests now run with a dummy key and wait for every job.

## Questions you may be asked

- **Is this really agentic, or just calling Groq?** Specialised agents with their own roles and
  structured outputs; a coordinator (ADK) delegating to workers (CrewAI) over A2A; tools through
  MCP; a check that sends a bad plan back; a human who is asked questions and can redo one part.
  The honest limit: each agent's reasoning is one structured call, not a free tool-choosing loop.
- **Why is Finance not an AI?** Money maths must be exact and testable; the evaluation compares
  it with a single prompt to the same model.
- **What happens when a tool or A2A is down?** Each falls back to the in-process path; the plan
  completes and the record says which path ran.
- **How do you know a plan is valid?** It must parse as `FinalPlan`, the budget split cannot exceed
  the budget, no area exceeds 60%, and the evaluation checks these on live runs.
- **What is not finished?** See the end of `docs/REQUIREMENTS_MAP.md`.
