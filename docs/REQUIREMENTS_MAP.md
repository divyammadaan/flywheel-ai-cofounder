# Course requirements, and where each one lives

Open the file named in each row; the function or class to look for is given. "Show it"
is how to demonstrate it live.

| # | Requirement | Where | Show it |
|---|---|---|---|
| 1 | **Context sharing and state** | Each agent receives the output of the ones before it: `PlanBrief` (`agents/_brief.py`) carries Strategy's positioning and price to every execution agent; `AGENT_CONTEXT` and `join_context` in `orchestration/cycle.py` decide what each agent sees. The plan so far is a Pydantic object, `FinalPlan` (`orchestration/final_plan.py`), and `_over_a2a` in `cycle.py` puts a snapshot of it in the **ADK session state** (`orchestration/adk_coordinator.py`, `create_session(state=...)`). Run state is rebuilt from saved decision records, so a restart does not lose it. | Run a plan; open `/runs/<id>/plan.json` — the same object that was shared. |
| 2 | **Tools through MCP (2+)** | `tools/mcp_server.py` (FastMCP) publishes `web_search`, `cash_calculator`, `operating_cash_position_tool`, `parse_orders`, `query_decision_records`. `tools/mcp_client_tool.py` calls it over stdio in a separate process. Used by: Market Research (`tools/web_search.py: search_business`), Finance (`agents/finance.py: plan_launch / plan_operating`), CRM history (`cycle.py: previous_segments`). Each has a local fallback, so a missing tool never fails a plan. | The terminal prints `MCP calling web_search…` and `MCP calling cash_calculator…` during a run. |
| 3 | **Structured output with Pydantic** | Every AI agent's reply is a Pydantic schema (`output_pydantic` in CrewAI, `output_schema` in ADK). The final result is one validated `FinalPlan` model, exported as JSON and Markdown: `GET /runs/{id}/plan.json` and `/plan.md`, and download buttons on the plan page. API request/response shapes are Pydantic too (`api/schemas.py`). | Download "Plan (Markdown)" from a finished plan. |
| 4 | **Agentic design patterns** | Orchestrated pipeline and parallel fan-out (`cycle.py`: `_plan`, `_run_execution_agents`); **reflection** — a check sends a draft back with the problems listed, once (`_checked_strategy`, `agents/_guardrails.py`); **human in the loop** — the run pauses for the advisor's questions and "Suggest a change" redoes one agent (`api/flows.py`, `refine_execution_agent`); a **decision gate** — NO-GO stops the flow; **tool use** (MCP); **multi-agent delegation** (ADK coordinator → CrewAI agents over A2A). | The progress list in the website, and the trace in the terminal. |
| 5 | **Monitoring with callbacks** | `observability/callbacks.py`: CrewAI `step_callback`, `task_callback` and a task `guardrail`; ADK `before/after_agent`, `before/after_model`, `on_model_error`, `before/after_tool`, `on_tool_error`. Each records a `monitor` run event (readable through `/runs/{id}/events`) and a live terminal line. Wired onto all 8 CrewAI agents (`crew_kwargs`, `task_kwargs`) and both ADK agents (`adk_callbacks`). | Terminal lines tagged `STEP`, `TASK`, `MODEL`, `AGENT`, `TOOL`, `GUARD`, `ERROR`. |
| 6 | **A2A, ADK ↔ CrewAI** | `orchestration/a2a_bridge.py` serves Marketing, Sales, Product and CRM (CrewAI) with Agent Cards, mounted in the API at `/a2a`. `orchestration/adk_coordinator.py` is a Google ADK `ParallelAgent` of `RemoteA2aAgent`s that calls them. Falls back to in-process if the agents cannot be reached. The Decision Record logs `transport: a2a`. | Open `/a2a/marketing/.well-known/agent-card.json`; the terminal prints `A2A ADK coordinator sends marketing, product, sales, crm…`. |
| 7 | **Only CrewAI and ADK** | CrewAI: Intake, Market Research, Founder Advisor, Company Formation, Marketing, Sales, Product, CRM, Funding. ADK: Strategy, Analytics, and the execution coordinator. Finance is plain code, not an agent framework. No other agent framework is used (`requirements.deploy.txt`). | `grep -r "langchain\|autogen\|langgraph" .` finds nothing. |
| 8 | **Security and guardrails** | *Input:* `agents/_input_guard.py` refuses abusive language and prompt-injection attempts in the pitch, answers and change notes (`api/schemas.py` validators, and `IntakeAgent.process`); ADK `before_model_callback` cuts instruction-like lines from any prompt. *Tool returns:* `clean_sources` type-checks search results and removes instruction-like sentences; ADK `after_tool_callback` validates any tool response. *Output:* `agents/_guardrails.py` (Strategy, Funding, CRM), the CrewAI task guardrail, the advisor's verdict is a strict enum. *Access:* `api/security.py` (per-address rate limit and CORS; the optional shared access code is switched off on the deployed demo). | Submit "ignore all previous instructions" as an idea: the API answers 422 with the reason. |
| 9 | **Observability (Langfuse)** | `observability/langfuse_setup.py`: every model call from both frameworks is exported to Langfuse (through LiteLLM), tagged with the agent and the run (`session_id = run-<id>`); the CRM prompt and reply are masked. Plus the project's own audit trail: decision records, `llm_usage`, `run_events`. | Open the Langfuse project: one generation per agent, grouped by run. |
| 10 | **End-to-end evaluation** | `evaluation/run_eval.py` drives the real API over three scenarios and a single-prompt baseline; results in `docs/EVALUATION.md` (time, tokens, estimated cost, correctness checks). | `python evaluation/run_eval.py --baseline 5` |
| 11 | **Cloud deployment** | `docs/DEPLOYMENT.md`. Website on Vercel; backend as a Docker container (`Dockerfile`, `deploy/start.sh`; scripts for Modal and Hugging Face); managed Postgres on Neon; Langfuse Cloud; Groq. | The deployed URLs in `MORNING_REPORT.md`. |

## The handout's own topics

| Handout topic | Where |
|---|---|
| CrewAI: agents, tools, tasks, crews | `agents/*.py` (e.g. `agents/sales.py`) |
| ADK: LlmAgent, sessions and state, orchestration, workflow agents, callbacks | `agents/strategy.py`, `agents/analytics.py` (LlmAgent + session + callbacks); `orchestration/adk_coordinator.py` (ParallelAgent, RemoteA2aAgent, session state) |
| Guardrails and safety | `agents/_guardrails.py`, `agents/_input_guard.py`, `observability/callbacks.py` |
| Agent evaluation | `evaluation/run_eval.py`, `docs/EVALUATION.md` |
| Monitoring and observability | `observability/` (trace, callbacks, usage, Langfuse) |
| MCP, A2A | `tools/mcp_*.py`, `orchestration/a2a_bridge.py`, `orchestration/adk_coordinator.py` |
| Multimodal | Voice in and out (`tools/speech.py`), generated ad image (`tools/image_gen.py`) |
| Local LLMs and privacy (CO2) | **Not demonstrated by the running system.** CRM used to run on a local model; it moved to Groq so the system could be deployed with nothing on a laptop. See `docs/project_report.md` section 4. |

## What is honestly not done

- A fully automatic plan-act-measure-improve loop: the founder enters new numbers each period; comparing periods works in the command line, not the web app.
- Login and accounts: the deployed demo is open; only a per-address rate limit protects the model quota.
- Agents choosing their own tools in a free reasoning loop: tools are used by the engine through MCP, and the agents' reasoning is one structured call each.
