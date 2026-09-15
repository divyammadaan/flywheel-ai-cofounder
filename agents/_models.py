"""Shared model configuration -- which provider each agent talks to.

Agents are deliberately spread across providers rather than all pointed at
one. Rate limits are enforced per provider, so concentrating every agent on
a single one serialises the whole run behind that provider's cap; spreading
them means the four execution agents can genuinely run in parallel (see
orchestration/cycle.py) instead of queuing behind each other.

Assignment is driven by CALL FREQUENCY, which differs a lot by agent:
  - Advisory agents fire once per run.
  - Engine agents fire once per CYCLE, so a 3-cycle run is 18 engine calls
    against 5 advisory ones. Never put a per-day-capped provider there.

Providers, measured on a REAL agent call (one MarketingAgent.execute), not
on a toy "say OK" prompt -- the two differ by two orders of magnitude and
the toy benchmark is what made NVIDIA look viable:

  Groq        1.1s/call. Capped at ~1000 OUTPUT tokens/minute (a limit the
              rate-limit headers don't report), so a long run spends its
              wall time waiting rather than generating.
  Gemini      11.7s/call, and 20 requests/DAY. The daily cap rules it out
              for anything per-cycle.
  NVIDIA NIM  140s/call. Its ~40 req/min headroom is irrelevant at that
              latency -- routing the fan-out agents here took a 2-cycle run
              from 255s to 667s. Tested and rejected; don't retry it
              without re-measuring on a real agent call.
  Ollama      local, no limit, ~15-20s/call on CPU.

So everything hosted sits on Groq: 1.1s/call beats the alternatives by so
much that its token cap is still the better trade. The remaining levers on
run time are output length (hence the "BE CONCISE" instructions) and
parallelism (the fan-out in orchestration/cycle.py), not provider choice.

Model choice notes:
  - Most of NVIDIA's 82-model catalogue 404s on the free tier, and
    deepseek-v4-flash returns 504 after ~300s. glm-5.3-flash and
    nemotron-3.5-lightning both verified working (4/4 structured-output
    calls, 16-26s each through CrewAI).
  - Groq's gpt-oss variants are fast but fail CrewAI's forced tool-calling
    ("Tool choice is required, but model did not call a tool") -- they emit
    valid JSON as content instead of calling the tool. Passing
    response_format to CrewAI's LLM() does not route around it; CrewAI still
    uses tool-calling for output_pydantic. Don't re-try this without also
    replacing output_pydantic.
  - Strategy is the only agent on ADK's output_schema, which has no
    response_format equivalent and parses whatever text comes back, so it
    needs a model that emits bare JSON with no preamble. qwen is verified.

Every agent takes a `model=` argument, so all of this is overridable.
"""

# --- NVIDIA NIM: tested and rejected at ~140s per real agent call (see the
# docstring above). Not routed to any agent; kept so one can still opt in
# with model=NVIDIA_MODEL.
NVIDIA_MODEL = "nvidia_nim/z-ai/glm-5.3-flash"

# --- Groq: fast per call, low output-token ceiling. Carries every hosted agent.
GROQ_MODEL = "groq/qwen/qwen3.8-27b"

# Strategy specifically (ADK output_schema -- needs bare JSON, no preamble).
GROQ_MODEL_ADK_JSON = "groq/qwen/qwen3.8-27b"

# --- Gemini: 20 req/DAY, so only agents that fire once per run.
GEMINI_MODEL = "gemini/gemini-3.6-flash"

# --- Ollama: CRM stays local on purpose. Customer/churn data never leaves
# the machine.
# A plain Ollama model name, not a litellm "ollama/..." string: CRM calls
# Ollama's native /api/chat directly (think:false + JSON schema). See crm.py.
OLLAMA_MODEL = "qwen3:4b"
OLLAMA_BASE_URL = "http://localhost:11434"


# Per-agent assignment, so the routing is visible in one place instead of
# being buried in eleven constructors.
AGENT_MODELS = {
    # advisory -- once per run
    "intake": GROQ_MODEL,
    "company_formation": GROQ_MODEL,
    "market_research": GROQ_MODEL,
    "founder_advisor": GROQ_MODEL,
    "funding": GROQ_MODEL,
    # engine -- once per cycle
    "strategy": GROQ_MODEL_ADK_JSON,
    "finance": GROQ_MODEL,
    "analytics": GROQ_MODEL,
    # engine fan-out -- run concurrently (see orchestration/cycle.py)
    "marketing": GROQ_MODEL,
    "product": GROQ_MODEL,
    "sales": GROQ_MODEL,
    "crm": OLLAMA_MODEL,
}

# Reply-length caps per agent, in output tokens. They stop a runaway answer
# without cutting off a normal one -- a truncated JSON reply fails to parse, so
# each cap keeps generous headroom over the longest reply measured in real runs
# (see the llm_usage table and the dashboard's "Model usage" panel). Output
# tokens are also what Groq's free tier rate-limits per minute.
AGENT_MAX_TOKENS = {
    "intake": 600,
    "market_research": 1200,
    "founder_advisor": 1000,
    "company_formation": 1400,
    "strategy": 900,
    "analytics": 700,
    "marketing": 1400,
    "sales": 2000,
    "product": 1400,
    "funding": 1600,
    "crm": 1024,
}
