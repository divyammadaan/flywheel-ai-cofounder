# Flywheel — an AI co-founder

A founder describes a business, and Flywheel plans it with them.

- **New idea (not launched):** researches the market, asks what it still needs to know, rules GO / PIVOT / NO-GO, lays out how to incorporate, checks the cash (reserve, break-even), and builds a launch plan — campaigns, lead sources, stock, and a funding roadmap.
- **Existing business:** the founder enters their real numbers and uploads their order history. Flywheel analyses both, finds which customers are slipping away, and plans the next period from there.

No revenue is invented. A business that hasn't launched has no results, so the launch plan never pretends it does — every budget and cost is the founder's own figure.

---

## Every agent has a real job

Where arithmetic is involved, code does the maths and the model does the judgement and the writing — so numbers are exact and the model can't miscalculate them.

| Agent | Runs for | What it does |
|---|---|---|
| Intake | both | Turns a free-text description into structured fields |
| Market Research | new idea | Market size and competitors from live web search (sources cited), flags risks, asks what's still unknown |
| Founder Advisor | new idea | GO / PIVOT / NO-GO — can stop a bad idea before money is spent |
| Company Formation | new idea | Region-specific incorporation checklist: entity, registrations, licences, cost, timeline |
| Analytics | existing | Ratios from the founder's numbers and orders, computed in code; the model writes what they mean |
| Strategy | both | Positioning, target customer, a real price, budget priorities |
| Finance | both | Cash reserve, break-even, runway, debt load, budget split — all code, no model call |
| Marketing | both | 2–4 campaigns with copy and a matching ad image |
| Sales | both | 2–4 lead sources with a weekly cadence, and the steps from lead to customer |
| Product | both | Opening inventory or delivery capacity, priced and cut to fit the budget |
| CRM | existing, with an upload | Code groups customers (best/regular/new/slipping/lost); the model writes actions and win-back messages for each group |
| Funding | both | Target raise date, stage, and the milestones to hit first |

There's no CRM in a launch plan (no customers yet to retain) and no Analytics (nothing has happened yet).

---

## Architecture

```
   NEW IDEA                                  EXISTING BUSINESS
   pitch + capital + running costs           description + real numbers
        │                                    + order history (.csv/.xlsx)
  ┌─────▼──────┐                                  │
  │   Intake   │                            ┌─────▼──────┐
  └─────┬──────┘                            │   Intake   │
  ┌─────▼───────────┐                       └─────┬──────┘
  │ Market Research │ asks what's unknown   ┌─────▼──────┐
  └─────┬───────────┘                       │ Analytics  │ numbers + orders,
        │ ← founder answers                 └─────┬──────┘ ratios in code
  ┌─────▼───────────┐                             │
  │ Founder Advisor │ GO / PIVOT / NO-GO          │
  └─────┬───────────┘ (NO-GO stops here)          │
  ┌─────▼─────────────┐                           │
  │ Company Formation │                           │
  └─────┬─────────────┘                           │
        └───────────────────┬─────────────────────┘
╔═══════════════════════════▼═════════════════════════════╗
║  THE PLANNING ENGINE                                    ║
║                    ┌────────────┐                       ║
║                    │  Strategy  │ positioning, customer,║
║                    └─────┬──────┘ real price            ║
║                    ┌─────▼──────┐ cash check in code,   ║
║                    │  Finance   │ then splits the budget║
║                    └─────┬──────┘                       ║
║                          │ fan-out (parallel)           ║
║      ┌───────────────┬───┴───────────┬───────────────┐  ║
║      ▼               ▼               ▼               ▼  ║
║  Marketing         Sales          Product           CRM ║
║  campaigns,     lead sources,   inventory or   (existing║
║  copy, image    weekly cadence  capacity       + upload)║
╚═══════════════════════════╤═════════════════════════════╝
                       ┌────▼────┐
                       │ Funding │ target raise date, revenue
                       └─────────┘ and profit milestones
```

Agent output is structured data (arrays of points, not paragraphs), so the UI renders real lists instead of guessing where to split prose. The whole plan is also one validated Pydantic object (`orchestration/final_plan.py`), downloadable as JSON or Markdown.

**How the execution stage runs.** Marketing, Sales, Product and CRM are CrewAI agents served over **A2A** (agent cards at `/a2a/<agent>/.well-known/agent-card.json`). A Google ADK `ParallelAgent` made of `RemoteA2aAgent`s calls them concurrently, with the plan so far carried as ADK session state (`orchestration/adk_coordinator.py`). If the A2A agents can't be reached, the same agents run in-process, so a plan never fails over the protocol.

**Guardrails in code, not prompts:**
- `agents/_input_guard.py` — what comes in: abusive language and prompt-injection attempts in the founder's text are refused; web-search results are type-checked and have instruction-like sentences cut out before a model sees them.
- `agents/_guardrails.py` — every Strategy plan is checked (describes this business, metric units, price near what customers pay, no demeaning wording) before other agents use it. A failing plan is sent back once, then the run stops.
- `agents/_cash.py` — reserve, break-even, runway, debt ratio.
- `agents/finance.py` — no budget area gets more than 60% of the total.
- `agents/_money.py` — campaign and lead-source spends are cut to fit the budget.
- `agents/_segments.py` — customer groups, with cut-offs scaled to how often this business's customers actually re-order.
- `tools/orders_file.py` — reads messy exports (loose column names, currency-formatted amounts, day-first dates).
- Funding roadmaps are checked for a round too big for its stage, or milestones that contradict each other.

---

## Stack

- **Backend:** FastAPI, wrapping the same orchestration functions the CLIs call. Long-running plans run on a worker thread; progress is written as rows a client can resume from after a reload.
- **Frontend:** Next.js, TypeScript, Tailwind. Types generated from the live API schema.
- **Storage:** SQLAlchemy over SQLite or Postgres (`FLYWHEEL_DATABASE_URL`), Alembic migrations. Plans are scoped to runs, not overwritten.
- **Agents:** CrewAI (Intake, Market Research, Founder Advisor, Company Formation, Marketing, Sales, Product, CRM, Funding) and Google ADK (Strategy, Analytics, and the coordinator that calls the execution agents). Finance is plain code.
- **Agent-to-tool:** MCP — a FastMCP server (`tools/mcp_server.py`) with web search, a cash calculator, an order-file parser and the decision-record history; the engine calls it over stdio, with a local fallback.
- **Agent-to-agent:** A2A — see above.
- **Monitoring:** callbacks on both frameworks (`observability/callbacks.py`) record steps, model calls, tool calls and errors; `observability/trace.py` prints them live in the server terminal.
- **Observability:** every model call is traced in Langfuse (`observability/langfuse_setup.py`), tagged by agent and run; customer data is masked there.
- **LLMs:** Groq, for every agent. The prompt CRM sends contains real customer names and spend, so **customer data is processed by Groq**; it is masked in Langfuse traces.
- **Web search:** DuckDuckGo via `ddgs`, no API key, reached through the MCP tool.

---

## Project structure

```
flywheel/
├── agents/            # intake, research, advisor, strategy, finance, marketing, sales, product, crm, funding
├── orchestration/     # the two flows (new idea / existing business) and the shared planning engine
├── api/               # FastAPI: endpoints, background jobs, request/response schemas
├── web/               # Next.js frontend
├── storage/           # SQLAlchemy models, runs, decision records, usage
├── migrations/        # Alembic
├── observability/     # decision records, usage, callbacks, live trace, Langfuse
├── tools/              # order file parsing, web search, MCP server and client, landing page, image gen
├── evaluation/        # end-to-end evaluation (time, tokens, cost, correctness)
├── deploy/            # Dockerfile entry point, Hugging Face and Modal deploy scripts
├── tests/
└── docs/              # setup, deployment, evaluation, requirements map
```

---

## Running it

```bash
git clone <repo-url> && cd flywheel
python -m venv .venv && .venv/Scripts/activate   # Windows
# source .venv/bin/activate                       # macOS/Linux
```

Install in stages (see `docs/setup.md`):

```bash
pip install crewai && pip install google-adk && pip install mcp a2a-sdk
pip install groq google-genai && pip install fastapi uvicorn python-dotenv pydantic
pip install sqlalchemy alembic "psycopg[binary]"
pip install pandas openpyxl ddgs && pip install pytest
```

Or, to get exactly the versions this was built and tested with: `pip install -r requirements.deploy.txt`.

```bash
cp .env.example .env   # add GROQ_API_KEY (console.groq.com/keys)
```

**API + web app:**

```bash
.venv/Scripts/python -m uvicorn api.main:app --reload --port 8000
cd web && npm install && npm run dev
```

**CLIs:**

```bash
python orchestration/validate_flow.py --capital 1500000 --fixed-costs 100000 --unit-cost 350

python tools/sample_data.py --out data/sample_orders.xlsx
python orchestration/review_flow.py --description "..." --period "FY2025-26" \
    --revenue 2400000 --net-profit 180000 --debt 500000 --budget 400000 --cash 700000 \
    --orders data/sample_orders.xlsx

pytest tests/ -q
```

The CLI flows print each agent starting, calling its model, finishing and saving, as they run (`FLYWHEEL_TRACE=0` silences it); the API server prints the same lines in its terminal.

---

## Deployment

The website is on Vercel and the backend is a Docker container (`Dockerfile`) that serves the API, the A2A agents and the MCP-backed tools from one process, against a managed Postgres (Neon). See `docs/DEPLOYMENT.md` for the steps, the access-code protection and the free-hosting notes.

## More

- `docs/REQUIREMENTS_MAP.md` — each course requirement and where it lives in the code.
- `docs/EVALUATION.md` — measured time, tokens, cost and correctness checks.
- `docs/CHANGES_FOR_VIVA.md` — the end-term changes explained in plain language.
