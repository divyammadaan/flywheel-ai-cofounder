# Setup

## Installing dependencies

`pip install -r requirements.txt` in one shot fails: pip's resolver hits
`resolution-too-deep` trying to jointly solve `crewai` + `google-adk` +
`a2a-sdk` + `chromadb` — their transitive dependency trees (esp.
`google-adk`'s google-cloud-* stack) are large enough that combined
resolution blows past pip's search depth.

Install in stages instead, so each pip invocation resolves a smaller graph:

```bash
python -m venv .venv
.venv/Scripts/activate        # Windows
# source .venv/bin/activate   # macOS/Linux

pip install --upgrade pip
pip install crewai
pip install google-adk
pip install mcp a2a-sdk
pip install ollama groq google-genai
pip install fastapi uvicorn python-dotenv pydantic
pip install chromadb
pip install streamlit
pip install pytest
```

If a later stage still backtracks badly, pin the offending package to a
specific version (`pip index versions <pkg>` to see choices) rather than
letting pip search the whole history.

## API keys

Copy `.env.example` to `.env` and fill in:
- `GROQ_API_KEY` — used by all 6 hosted-LLM agents (Strategy/Finance/
  Analytics via ADK's LiteLlm wrapper, Marketing/Product/Sales via CrewAI's
  native `groq/` model string). Get a free key at console.groq.com/keys.
- `GEMINI_API_KEY` — not currently used by default (see Known issues below),
  but every agent's `model` param accepts a plain Gemini model string
  (e.g. `"gemini-3.6-flash"`) as a manual override if you want it.

`.env` is gitignored; never commit it.

## Local LLM (Ollama)

CRM deliberately runs on a local model, not a hosted API — customer/churn
data is the most privacy-sensitive slice of the project, so it never leaves
the machine. Satisfies the course's local-LLM / data-privacy requirement.

```bash
winget install --id Ollama.Ollama -e   # Windows; see ollama.com for other OS
ollama pull qwen3:4b
```

`qwen3:4b` was picked over a larger model because this is a CPU-only,
no-GPU dev machine (Ryzen 7 5800U, 16GB RAM) — 7-8B models are painfully
slow at that spec. qwen3:4b is a reasoning model, so a single call takes
~15-20s even for a trivial prompt; that's fine for CRM (not on any latency-
critical path) but don't route anything time-sensitive through it.

## Known issues

- **Why Groq, not Gemini, is the default**: `gemini-3.6-flash` on Gemini's
  free Developer API tier is capped at 20 requests/day per project -- a
  single full 6-agent cycle burns 6 of those, so testing exhausts it fast
  (429 `RESOURCE_EXHAUSTED`, and the daily reset does not follow local
  midnight). Switched all 6 hosted-LLM agents to Groq's free tier instead.
  Every agent's `model` constructor param still accepts a plain Gemini
  string to switch back per-agent if wanted.
- **Groq's free tier has its own limit**: ~1000 output tokens/minute per
  model, not per-day. Running several agents back-to-back can trip it
  (`litellm.RateLimitError` / `rate_limit_exceeded`), but it clears in
  seconds (the error message includes the exact wait), and CrewAI/ADK's
  built-in retry usually absorbs it without any code change needed. If it
  persists, wait ~10-40s and retry.
- **google-adk[extensions] is NOT required for Groq**: `litellm` is already
  installed (a CrewAI dependency), which is all `google.adk.models.lite_llm.
  LiteLlm` actually checks for. Installing the `[extensions]` extra pulls in
  `protobuf>=6.33.5` (via `google-cloud-firestore`), which conflicts with
  `google-ai-generativelanguage`/`a2a-sdk` (both want `protobuf<6`/`<7`) --
  a genuinely unresolvable joint constraint. Don't install it.
- **CrewAI event bus + Windows console**: tool-call logging can throw a
  `'charmap' codec` error on Windows (cp1252 can't encode some characters
  CrewAI tries to print). Cosmetic only -- doesn't affect results. Set
  `PYTHONIOENCODING=utf-8` before running if the noise bothers you.
