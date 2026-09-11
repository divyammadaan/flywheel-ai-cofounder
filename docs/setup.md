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
- `GEMINI_API_KEY` — used by Strategy/Finance/Analytics (Google ADK LlmAgent,
  Gemini free tier via aistudio.google.com/apikey)
- `GROQ_API_KEY` — not yet wired to any agent

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

- **Gemini free-tier daily quota**: `gemini-3.6-flash` on the free Developer
  API tier is capped at 20 requests/day per project. A single full 6-agent
  cycle uses 6 of those. Running the whole thing a few times in one day
  will exhaust it -- if you hit a 429 `RESOURCE_EXHAUSTED` error, that's
  why. Options: wait for the daily reset, enable billing, or add Groq as a
  second hosted backend (not yet wired to any agent).
- **CrewAI event bus + Windows console**: tool-call logging can throw a
  `'charmap' codec` error on Windows (cp1252 can't encode some characters
  CrewAI tries to print). Cosmetic only -- doesn't affect results. Set
  `PYTHONIOENCODING=utf-8` before running if the noise bothers you.
