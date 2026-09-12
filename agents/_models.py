"""Shared model configuration.

One place, because the model id was previously copy-pasted into eleven
agent modules and changing provider meant eleven edits with nothing
stopping them drifting apart.

Model choice has to satisfy two constraints at once, and every candidate
tested fails one of them.

1. Throughput. Groq's free tier enforces an output-tokens-per-minute cap
   that the rate-limit headers don't report. qwen3.8-27b's is ~1000 OTPM,
   low enough that back-to-back agent calls spend most of their time
   waiting. Three consecutive 1200-token completions:

       qwen/qwen3.8-27b     1 succeeded, 2 rate-limited immediately
       openai/gpt-oss-120b  3 succeeded, no rate limits

2. Structured output. Every agent returns a pydantic schema, which CrewAI
   obtains via *forced tool-calling*. Both gpt-oss variants generate valid
   JSON but emit it as plain content rather than calling the tool, so Groq
   rejects the call: "Tool choice is required, but model did not call a
   tool" (tool_use_failed).

Things tried for (2), and why they didn't land:
  - Passing response_format=<schema> to CrewAI's LLM(). Groq DOES support
    json_schema mode at the raw API level (verified directly), but CrewAI
    still routes output_pydantic through tool-calling, so the flag doesn't
    change behaviour. An isolated test appeared to pass; that was luck --
    in a real run the same call failed four times consecutively.
  - gpt-oss for ADK agents. ADK's output_schema has no response_format
    equivalent; it asks for JSON and parses whatever returns, and gpt-oss
    prefaces with reasoning ("We need to output JSON...") which fails
    validation.

So the default stays on qwen3.8-27b: correctness first, because a fast run
that can't parse its own output is worthless. Throughput is instead managed
by keeping output short (the "BE CONCISE" lines in each agent instruction),
since the cap is on output tokens specifically.

Cost of that choice, measured: a full validate run (2 cycles, all stages,
~16 calls) takes ~4 minutes, most of it waiting out rate limits.

To make this genuinely fast, one of these is needed:
  - Stop using CrewAI's output_pydantic and parse JSON from raw text
    ourselves, which frees us to use gpt-oss-120b; or
  - A paid Groq tier, which lifts the OTPM cap.

Agents take a `model=` argument, so any of this can be overridden per-agent.
"""

# Hosted default for the non-CRM agents (litellm-style provider prefix).
GROQ_MODEL = "groq/qwen/qwen3.8-27b"

# Strategy is the one agent using ADK's output_schema, which needs a model
# that returns bare JSON with no preamble. Same model today, kept separate
# so switching GROQ_MODEL doesn't silently break Strategy's parsing.
GROQ_MODEL_ADK_JSON = "groq/qwen/qwen3.8-27b"

# CRM stays local on purpose -- customer/churn data never leaves the machine.
OLLAMA_MODEL = "ollama/qwen3:4b"
OLLAMA_BASE_URL = "http://localhost:11434"
