# Flywheel — An AI Co-Founder


A founder describes a business and Flywheel plans it with them.

- **New idea (not launched):** it researches the market, asks the questions it still needs answered, rules GO / PIVOT / NO-GO, lays out how to incorporate, checks the cash (reserve, break-even), and builds a specific launch plan: which campaigns to run and where, where the first leads come from, what stock or tools to buy and from whom, and when to aim for funding.
- **Existing business:** the founder enters their real numbers and uploads their order history (.csv or .xlsx). Flywheel analyses both, finds which customers are slipping away, and plans the next period from there.

No revenue is invented. A business that hasn't launched has no results, so the launch plan never pretends it does, and every budget and cost is the founder's own figure.

---

## Every agent has a real job

An agent is only here if it does something a founder would otherwise do by hand. Where arithmetic is involved, **code does the maths and the model does the judgement and the writing** — so numbers are exact and the AI can't miscalculate them.

| Agent | Runs for | What it actually does for the founder |
|---|---|---|
| **Intake** | both | Turns a free-text description into structured fields, and classifies what the business delivers (physical / service / software) |
| **Market Research** | new idea | Sizes the market, names competitors and risks, asks the questions still needed for a verdict |
| **Founder Advisor** | new idea | GO / PIVOT / NO-GO — can stop a bad idea before money is spent |
| **Company Formation** | new idea | Region-specific incorporation checklist: entity, registrations, licences, cost, timeline |
| **Analytics** | existing | Ratios from the founder's numbers and their uploaded orders (average order, repeat rate, revenue trend) — computed in code; the model writes what they mean |
| **Strategy** | both | Positioning, target customer, a real price, and budget priorities |
| **Finance** | both | **Cash math in code:** launch reserve and break-even for a new idea; runway, debt load and budget-vs-cash for an existing business. Then splits the spendable budget with a hard per-area cap |
| **Marketing** | both | 2–4 specific campaigns (platform, localities/audience, format, timing, spend) plus ad copy and a matching ad image |
| **Sales** | both | 2–4 lead sources with a weekly cadence and spend, and the steps from lead to paying customer |
| **Product** | both | Physical goods: opening inventory and sourcing. Services/software: tools, equipment and hires needed to deliver. Totals computed in code and cut to fit the budget |
| **CRM** | existing, with an upload | **Code** groups the uploaded customers (best, regular, new, slipping away, lost) and tracks change since last period; the **local model** writes an action per group and ready-to-send win-back messages. Runs locally because it sees real customer data |
| **Funding** | both | Target raise date and stage, and the revenue/profit/traction milestones to hit first |

There is deliberately **no CRM in a launch plan** — a business with no customers has nothing to retain — and no Analytics, because nothing has happened yet.

The rule-based market simulator from earlier versions is **parked**: it produced synthetic revenue, so neither flow uses it. Its code and tests are kept.

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

**Guardrails in code, not prompts:**
- `agents/_guardrails.py` — every Strategy plan is checked before other agents use it: it must describe this business, use metric units in India, price near what customers pay, and contain no demeaning wording. A failing plan goes back once with the problems listed; a second failure stops the run
- `agents/_cash.py` — reserve, break-even, runway, debt ratio
- `agents/finance.py` `compute_capped_allocation` — no area gets more than 60% of the budget
- `agents/_money.py` `fit_to_budget` — campaign and lead-source spends are cut to fit
- `agents/product.py` `price_line_items` — line totals multiplied by the program, quantities cut to fit
- `agents/_segments.py` — customer groups, with cut-offs scaled to how often *this* business's customers re-order
- `tools/orders_file.py` — reads messy exports (loose column names, `₹1,599.00`, day-first dates)

---

## Tech stack

- **Agent orchestration:** CrewAI (planning + advisory agents), Google ADK (Strategy/Finance/Analytics)
- **Agent-to-tool:** MCP — a real FastMCP server exposing Decision Record history; the engine fetches last period's CRM record from it over stdio, as a separate process
- **Agent-to-agent:** A2A — Marketing is exposed as an A2A server with a discoverable Agent Card; the engine calls it over the protocol and falls back to an in-process call if the server is down
- **LLMs:** Groq free tier (`qwen/qwen3.8-27b`) for the hosted agents; Ollama (`qwen3:4b`, local, thinking turned off) for CRM. Gemini supported via a per-agent `model=` override — see `docs/setup.md`
- **Data:** pandas + openpyxl for uploaded order files; SQLite for Decision Records
- **Dashboard:** Streamlit

---

## Project structure

```
flywheel/
├── agents/
│   ├── _brief.py           # PlanBrief: the shared context every planning agent gets
│   ├── _cash.py            # reserve, break-even, runway (Finance's maths)
│   ├── _money.py           # currency formatting + fit_to_budget guardrail
│   ├── _segments.py        # customer groups from an order history (CRM's maths)
│   ├── _models.py          # which provider each agent talks to
│   ├── _retry.py           # shared rate-limit backoff
│   ├── intake.py           # ─┐
│   ├── market_research.py  #  │ validation & advisory
│   ├── founder_advisor.py  #  │ (CrewAI + Groq)
│   ├── company_formation.py# ─┘
│   ├── analytics.py        # ADK + Groq (existing businesses)
│   ├── strategy.py         # ADK + Groq
│   ├── finance.py          # cash math + capped split in code; ADK + Groq explains it
│   ├── marketing.py        # CrewAI + Groq; campaigns + copy + image
│   ├── sales.py            # CrewAI + Groq; lead sources
│   ├── product.py          # CrewAI + Groq; inventory or delivery capacity
│   ├── crm.py              # direct local Ollama call; retention on uploaded customers
│   └── funding.py          # CrewAI + Groq; funding roadmap
├── simulator/
│   └── market_simulator.py # parked: not used by either flow
├── orchestration/
│   ├── validate_flow.py    # new idea: pitch -> verdict -> launch plan -> funding
│   ├── review_flow.py      # existing business: numbers + orders -> plan -> funding
│   ├── cycle.py            # the planning engine both flows share
│   ├── report.py           # terminal printing for the two CLIs
│   └── a2a_bridge.py       # A2A server + client for Marketing
├── observability/
│   ├── decision_record.py
│   └── dashboard/          # Streamlit
├── tools/
│   ├── orders_file.py      # read + clean uploaded .csv/.xlsx order histories
│   ├── sample_data.py      # generate realistic sample order files for demos
│   ├── image_gen.py        # ad image generation (keyless, fails soft)
│   ├── mcp_server.py       # FastMCP server: Decision Record query tools
│   └── mcp_client_tool.py  # MCP client over stdio
├── data/                   # SQLite store + generated ad images (gitignored)
├── tests/
├── docs/
├── requirements.txt
└── README.md
```

**Status.** All agents are genuinely LLM-backed. MCP is real (a separate-process FastMCP server queried over stdio). A2A is real — the Decision Record logs `transport: a2a` vs `direct` (start `orchestration/a2a_bridge.py` first, or it falls back). Marketing generates a real ad image per plan into `data/ads/`. Still open: live web search for Market Research, and a deployable storefront.

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
pip install chromadb && pip install pandas openpyxl && pip install streamlit && pip install pytest
```

Local model for CRM, plus your free Groq key:

```bash
winget install --id Ollama.Ollama -e   # or see ollama.com
ollama pull qwen3:4b

cp .env.example .env                   # then add GROQ_API_KEY (console.groq.com/keys)
```

Run it:

```bash
# new idea: pitch -> research -> verdict -> formation -> cash check -> launch plan -> funding
python orchestration/validate_flow.py --capital 1500000 --fixed-costs 100000 --unit-cost 350

# existing business: generate a sample order file, then plan from numbers + orders
python tools/sample_data.py --out data/sample_orders.xlsx
python orchestration/review_flow.py --description "..." --period "FY2025-26" \
    --revenue 2400000 --net-profit 180000 --debt 500000 --budget 400000 --cash 700000 \
    --orders data/sample_orders.xlsx

# optional: serve Marketing over A2A (the engine falls back to a direct call without it)
python orchestration/a2a_bridge.py

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

