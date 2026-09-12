# Flywheel — An AI Co-Founder


A founder describes a business — a new idea, or one they already run — and Flywheel takes it from there: researches the market, asks the questions it still needs answered, rules GO / PIVOT / NO-GO, lays out how to incorporate, then actually *runs* the business through repeated **plan → fund → execute → measure → revise** cycles, and finally tells them whether they're ready to raise.

The part that makes it more than a pipeline: the engine's decisions in one cycle are judged by outcomes in the next. Strategy revises because CAC came in too high, not because a script said to.

---

## Why this is different from a typical agent demo

Most multi-agent projects fan out a set of agents in parallel and merge their outputs once. Flywheel is a **closed loop with persistent state**: decisions made in one cycle are judged by outcomes in the next, and agents must compete for a fixed, limited budget rather than act independently. This forces genuine multi-agent negotiation, dependency-aware orchestration, and cross-cycle memory — not just concurrent API calls.

A real run, unedited: Cycle 1 spent 45% of budget on marketing and came back with CAC $150 against $100 revenue per customer and 18.9% churn. Strategy read that and moved budget out of marketing into CRM/retention on its own. Cycle 2: CAC $75, churn 8%, revenue up. Nobody scripted the correction.

---

## Architecture

```
  founder's pitch (text or voice)
            │
      ┌─────▼─────┐
      │  Intake   │  normalise idea OR existing financials
      └─────┬─────┘
      ┌─────▼──────────┐
      │ Market Research│  size it, name rivals, ask what's still unknown
      └─────┬──────────┘
            │  ← founder answers clarifying questions
      ┌─────▼──────────┐
      │Founder Advisor │  GO / PIVOT / NO-GO  ──► NO-GO stops here
      └─────┬──────────┘
      ┌─────▼──────────┐
      │Company Formation│ entity, registrations, licences, cost/timeline
      └─────┬──────────┘
            │  seed plan
╔═══════════▼════════════════════════════════════════╗
║  THE ENGINE                                        ║
║        ┌────────────┐                              ║
║        │  Strategy   │◄──────────────────────┐     ║
║        └─────┬──────┘                        │     ║
║        ┌─────▼──────┐                        │     ║
║        │  Finance    │  (budget negotiation)  │     ║
║        └─────┬──────┘                        │     ║
║              │  fan-out (parallel)            │     ║
║   ┌──────────┼──────────┬──────────┐          │     ║
║   ▼          ▼          ▼          ▼          │     ║
║Marketing  Product     Sales       CRM          │     ║
║   └──────────┴──────────┴──────────┘           │     ║
║              │  fan-in                          │     ║
║        ┌─────▼──────┐                          │     ║
║        │ Simulator   │  (rule-based, not an LLM)│     ║
║        └─────┬──────┘                          │     ║
║        ┌─────▼──────┐                          │     ║
║        │ Analytics   │──────────────────────────┘     ║
║        └─────┬──────┘   feeds next cycle             ║
╚══════════════│═════════════════════════════════════╝
            ┌──▼──────┐
            │ Funding │  ready to raise? if not, what has to be true first
            └─────────┘
```

**Flow per engine cycle:**
1. **Strategy** reads the previous cycle's Analytics report and revises the business plan (serial — depends on prior cycle).
2. **Finance** allocates a fixed budget across the four execution agents based on their requests (serial — depends on Strategy).
3. **Marketing, Product, Sales, CRM** act concurrently, each within its approved budget (parallel — independent of each other).
4. **Market Simulator** (rule-based, not an LLM) converts their combined output into synthetic demand and conversion events — keeps the system free to run and fully reproducible.
5. **Analytics** aggregates everything into KPIs and a summary, which becomes Strategy's input for the next cycle — closing the loop.

---

## Agents

**Validation & advisory** — runs once, before/after the engine:

| Agent | Role |
|---|---|
| **Intake** | Normalises a raw pitch, or an existing business's revenue/PAT/EBITDA/debt, into structured input. Told explicitly not to invent numbers the founder didn't give |
| **Market Research** | Market sizing, competitor landscape, risks — and the clarifying questions that must be answered before a verdict (budget, sourcing, capacity). Reasons from general knowledge; says so, since no live search is wired in yet |
| **Founder Advisor** | GO / PIVOT / NO-GO plus the seed plan that becomes Cycle 1's input. Instructed not to sugarcoat — it returns NO-GO when the budget doesn't match the market |
| **Company Formation** | Entity type, registration steps, licences, tax registrations, cost/timeline — region-aware (Pvt Ltd/MCA/DIN for India, LLC/EIN for the US). Not legal advice, and says so |
| **Funding** | Ready to raise? Grounded in the engine's *measured* KPIs, not a fresh guess. Names investor **type and profile**, never specific firms — fund mandates go stale and would send founders at the wrong people |

**The engine** — runs every cycle:

| Agent | Role |
|---|---|
| **Strategy** | Sets and revises positioning, pricing, and budget priorities each cycle based on prior results |
| **Finance** | Allocates a fixed shared budget across Marketing, Product, Sales, and CRM; enforces hard spend caps (guardrail) |
| **Marketing** | Generates ad copy within its approved budget (ad visuals still to come) |
| **Product** | Decides one concrete product/storefront change per cycle |
| **Sales** | Sets outreach effort and approach against the leads carried over from last cycle |
| **CRM** | Tracks churn signals and retention effort — **runs on a local model**, so customer data never leaves the machine |
| **Analytics** | Aggregates agent + simulator output into KPIs (revenue, conversion, CAC, churn) and the natural-language summary that closes the loop |
| **Market Simulator** *(non-agent)* | Rule-based module converting execution output into synthetic demand/conversion events — seeded, so runs are reproducible |

---

## Key features

- **Two entry points** — validate a new idea from a raw pitch, or run the engine directly on a plan you already have
- **A verdict that can say no** — the Advisor returns NO-GO and stops the run when the numbers don't support the idea
- **Closed-loop orchestration** — a genuine cycle with persistent cross-cycle state, not a one-shot DAG
- **Real budget negotiation** — Finance allocates limited resources across competing agents every cycle
- **Guardrails enforced in code, not prompts** — the per-agent spend cap is plain Python (`compute_capped_allocation`), so it holds even if a model reasons its way to a bad number. The LLM only narrates the allocation; it never computes it
- **Privacy slice** — CRM, the agent touching customer/churn data, runs on a local Ollama model; that data never leaves the machine
- **Funding advice grounded in measured results** — the Funding agent reads the engine's actual KPI history back out of the Decision Records
- **Full observability** — every agent action logged as a structured **Decision Record** (agent, cycle, input snapshot, decision), inspectable in the dashboard

---

## Tech stack

- **Agent orchestration:** CrewAI (execution + advisory agents), Google ADK (Strategy/Finance/Analytics, session state/memory)
- **Agent-to-tool:** MCP — a real FastMCP server exposing Decision Record history, which CRM queries over stdio as a separate process
- **Agent-to-agent:** A2A — not yet implemented
- **LLMs:** Groq free tier (`qwen/qwen3.8-27b`) for the 9 hosted agents; Ollama (`qwen3:4b`, local) for CRM. Gemini supported via a per-agent `model=` override — see `docs/setup.md` for why it isn't the default
- **Storage:** SQLite (Decision Records)
- **Dashboard:** Streamlit (React planned)

---

## Project structure

```
flywheel/
├── agents/
│   ├── _retry.py           # shared rate-limit backoff (all 10 agents)
│   ├── intake.py           # ─┐
│   ├── market_research.py  #  │ validation & advisory
│   ├── founder_advisor.py  #  │ (CrewAI + Groq)
│   ├── company_formation.py#  │
│   ├── funding.py          # ─┘
│   ├── strategy.py         # ADK + Groq, session memory
│   ├── finance.py          # guardrail deterministic; ADK + Groq narrates it
│   ├── marketing.py        # CrewAI + Groq
│   ├── product.py          # CrewAI + Groq
│   ├── sales.py            # CrewAI + Groq
│   ├── crm.py              # CrewAI + local Ollama (qwen3:4b) -- privacy slice
│   └── analytics.py        # ADK + Groq, session memory
├── simulator/
│   └── market_simulator.py
├── orchestration/
│   ├── validate_flow.py    # front door: pitch -> verdict -> engine -> funding
│   ├── cycle.py            # the engine loop
│   └── a2a_bridge.py       # cross-framework agent communication -- TODO
├── observability/
│   ├── decision_record.py
│   └── dashboard/          # Streamlit
├── tools/
│   ├── mcp_server.py       # FastMCP server: Decision Record query tools
│   └── mcp_client_tool.py  # CrewAI tool, talks to mcp_server.py over stdio
├── data/                   # SQLite store (gitignored)
├── tests/
├── docs/
│   ├── setup.md
│   ├── installed-versions.lock.txt
│   └── project_report.md
├── requirements.txt
└── README.md
```

**Status.** All 12 agents are genuinely LLM-backed, no placeholders. MCP is
real — a FastMCP server queried by CRM over stdio as a separate process.
Still open: A2A, ad image generation for Marketing, a live deployable
storefront for Product, and live web search for Market Research (which
currently reasons from general knowledge and labels every estimate as such).

---

## Getting started

```bash
git clone <repo-url>
cd flywheel

python -m venv .venv && .venv/Scripts/activate   # Windows
# source .venv/bin/activate                       # macOS/Linux
```

Install in **stages** — one shot fails, see `docs/setup.md` for why:

```bash
pip install crewai && pip install google-adk && pip install mcp a2a-sdk
pip install ollama groq google-genai && pip install fastapi uvicorn python-dotenv pydantic
pip install chromadb && pip install streamlit && pip install pytest
```

Local model for CRM, plus your free Groq key:

```bash
winget install --id Ollama.Ollama -e   # or see ollama.com
ollama pull qwen3:4b

cp .env.example .env                   # then add GROQ_API_KEY (console.groq.com/keys)
```

Run it:

```bash
# the full product: pitch -> research -> verdict -> formation -> engine -> funding
python orchestration/validate_flow.py --cycles 2

# just the engine, on a generic cold start
python orchestration/cycle.py --cycles 3

# dashboard -- must be the venv python, a system streamlit shadows it
.venv/Scripts/python -m streamlit run observability/dashboard/app.py

pytest tests/ -q
```

---

## Course context

- **CO1** — foundational agent/LLM principles
- **CO2** — agentic design patterns + local LLMs for secure, privacy-preserving solutions
- **CO3** — multi-agent, multimodal, multi-step automation

---

## Team

| Name | Focus area (rotates across phases) |
|---|---|
| *Member A* | Strategy + Finance |
| *Member B* | Product + Simulator |
| *Member C* | Marketing + Analytics + Dashboard |

---

## License

