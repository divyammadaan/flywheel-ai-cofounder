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

## Running it

```bash
# full product: pitch -> research -> Q&A -> verdict -> formation -> engine -> funding
python orchestration/validate_flow.py --cycles 2

# skip stages to save API calls while iterating
python orchestration/validate_flow.py --cycles 1 --skip-formation --skip-funding

# engine only, generic cold start
python orchestration/cycle.py --cycles 3

# dashboard -- must be the venv python, a system streamlit shadows it
.venv/Scripts/python -m streamlit run observability/dashboard/app.py
```

`--answers` exists for scripted demos but is **order-dependent**: it feeds
answers positionally into whatever questions Market Research generates that
run, and the model reorders them between runs, so answers can land against
the wrong questions. Interactive mode is the honest path.

## Ad images

Marketing generates a real ad image per cycle into `data/ads/cycle_N.jpg`
(gitignored). No key or setup needed — it uses Pollinations, which is
keyless.

Why not a hosted provider: **Gemini's image models have a free-tier quota of
literally `0`** (the API returns `limit: 0`, not an exhausted quota), so they
need billing and would block anyone cloning this repo. NVIDIA NIM has no
image model on its chat-completions endpoint, and local diffusion is far too
slow CPU-only.

Generation is allowed to fail without failing the cycle — the ad copy is the
substantive output, so a flaky image service returns `None` and the run
continues. Note the free service stamps a small watermark despite
`nologo=true`.

## A2A (optional)

Marketing is also reachable over Google's Agent2Agent protocol. Start the
bridge in a second terminal:

```bash
.venv/Scripts/python orchestration/a2a_bridge.py
# Agent Card: http://127.0.0.1:8600/.well-known/agent-card.json
```

With it running, the engine calls Marketing over A2A; with it stopped, it
falls back to an in-process call. Either way the run completes — check
`transport` in the marketing Decision Record to see which path was taken.

Three things that cost time here, worth knowing before touching this file:

- The JSON-RPC method is **`SendMessage`**, not the `message/send` spelling
  in some A2A docs. This SDK routes by gRPC service method name; the other
  spelling returns `-32601 Method not found`.
- The **`A2A-Version: 1.0` header is required**. A missing header is read as
  protocol `0.3` and rejected with `-32009`, not defaulted to current.
- The server is **Starlette, not FastAPI**. `add_a2a_routes_to_fastapi()`
  makes FastAPI generate an OpenAPI schema over the A2A protobuf types,
  which crashes in a2a's own `_proto_schema.py` (`FieldDescriptor` has no
  `is_repeated`) against the pinned protobuf. Both route builders work fine
  on their own — only the FastAPI schema pass fails.

## Known issues

- **Why Groq, not Gemini, is the default**: `gemini-3.6-flash` on Gemini's
  free Developer API tier is capped at 20 requests/day per project -- a
  single full 6-agent cycle burns 6 of those, so testing exhausts it fast
  (429 `RESOURCE_EXHAUSTED`, and the daily reset does not follow local
  midnight). Switched all 6 hosted-LLM agents to Groq's free tier instead.
  Every agent's `model` constructor param still accepts a plain Gemini
  string to switch back per-agent if wanted.
- **`streamlit run ...` uses the WRONG Python.** There is a system-wide
  `streamlit.exe` on PATH that shadows the venv's. Because Streamlit doesn't
  import the app until a browser connects, the server starts normally and
  then dies on first render with `ModuleNotFoundError: No module named
  'crewai'`. Always launch via `.venv/Scripts/python -m streamlit run ...`
  (or activate the venv first). The dashboard now catches this and prints
  the fix instead of a raw traceback.
- **Groq's free tier has its own limit**: output tokens per minute (not
  per-day), and it throttles *down* under sustained use. Two error shapes,
  both retryable:
  - `"Rate limit reached ... Please try again in 4.26s"` — transient, clears
    in seconds.
  - `"Request too large ... expected output tokens exceed the enforced
    limit"` — reads permanent but isn't. It means the per-minute budget is
    throttled down right now; the identical request succeeds after a window
    reset (verified: a 2000-token completion this rejected went through fine
    minutes later).

  `agents/_retry.py` handles both on every agent, parsing Groq's own
  "try again in Xs" hint where present. Do **not** rely on CrewAI's or ADK's
  built-in retry — CrewAI/instructor gives up after one attempt in practice,
  and ADK discards the 429 entirely and reports only
  `DynamicNodeFailError: Dynamic node <name> failed`.
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
