# Flywheel — Self-Revising Multi-Agent Business Engine


Flywheel is a self-revising multi-agent system that runs a simulated business through repeated **plan → execute → measure → revise** cycles, instead of a single-shot agent pipeline. Each cycle, a Strategy agent sets direction based on the *previous* cycle's real performance, a Finance agent negotiates a shared budget across four competing execution agents, and an Analytics agent closes the loop by feeding results back into Strategy — making the system adapt over time rather than just execute once.

---

## Why this is different from a typical agent demo

Most multi-agent projects fan out a set of agents in parallel and merge their outputs once. Flywheel is a **closed loop with persistent state**: decisions made in one cycle are judged by outcomes in the next, and agents must compete for a fixed, limited budget rather than act independently. This forces genuine multi-agent negotiation, dependency-aware orchestration, and cross-cycle memory — not just concurrent API calls.

---

## Architecture

```
        ┌────────────┐
        │  Strategy   │◄──────────────────────┐
        └─────┬──────┘                        │
              │                                │
        ┌─────▼──────┐                        │
        │  Finance    │  (budget negotiation)  │
        └─────┬──────┘                        │
              │  fan-out (parallel)            │
   ┌──────────┼──────────┬──────────┐          │
   ▼          ▼          ▼          ▼          │
Marketing  Product     Sales       CRM          │
   │          │          │          │           │
   └──────────┴──────────┴──────────┘           │
              │  fan-in                          │
        ┌─────▼──────┐                          │
        │ Simulator   │  (rule-based, not an LLM)│
        └─────┬──────┘                          │
              │                                 │
        ┌─────▼──────┐                          │
        │ Analytics   │──────────────────────────┘
        └────────────┘   feeds next cycle
```

**Flow per cycle:**
1. **Strategy** reads the previous cycle's Analytics report and revises the business plan (serial — depends on prior cycle).
2. **Finance** allocates a fixed budget across the four execution agents based on their requests (serial — depends on Strategy).
3. **Marketing, Product, Sales, CRM** act concurrently, each within its approved budget (parallel — independent of each other).
4. **Market Simulator** (rule-based, not an LLM) converts their combined output into synthetic demand and conversion events — keeps the system free to run and fully reproducible.
5. **Analytics** aggregates everything into KPIs and a summary, which becomes Strategy's input for the next cycle — closing the loop.

---

## Agents

| Agent | Role |
|---|---|
| **Strategy** | Sets and revises the business plan, positioning, and pricing each cycle based on prior results |
| **Finance** | Negotiates and allocates a fixed shared budget across Marketing, Product, Sales, and CRM; enforces hard spend caps (guardrail) |
| **Marketing** | Generates ad copy **and visuals** (multimodal) within its approved budget |
| **Product** | Writes, tests, and ships a real, deployable change to the storefront/landing page each cycle |
| **Sales** | Handles simulated inbound leads, drafts outreach, closes simulated deals |
| **CRM** | Tracks customer interactions/segments, flags churn signals |
| **Analytics** | Aggregates all agent + simulator output into KPIs (revenue, conversion rate, CAC, churn) and a natural-language summary |
| **Market Simulator** *(non-agent)* | Rule-based module that converts execution output into synthetic demand/conversion events |

---

## Key features

- **Closed-loop orchestration** — a genuine cycle with persistent cross-cycle state, not a one-shot DAG
- **Real budget negotiation** — Finance allocates limited resources across competing agents every cycle
- **Multimodal Marketing** — copy and ad visuals, evaluated together
- **Live Product artifact** — an actual deployable storefront that evolves cycle over cycle
- **Full observability** — every agent action logged as a structured **Decision Record** (agent, cycle, input snapshot, reasoning trace, decision, confidence), inspectable via dashboard
- **Guardrails** — hard budget caps and safety checks enforced on every agent action
- **Zero-cost inference** — local LLMs for the bulk of reasoning, free-tier hosted models for the highest-stakes steps

---

## Tech stack

- **Agent orchestration:** CrewAI (Flows, parallel execution agents), Google ADK (Strategy/Finance/Analytics, session state)
- **Agent-to-tool / agent-to-agent communication:** MCP, A2A
- **LLMs:** Ollama (Llama 3.1 8B / Qwen2.5 7B, local) + Groq / Google Gemini free tier (hosted, for critical reasoning)
- **Backend:** Python, FastAPI
- **Storage:** SQLite (Decision Records, business state), ChromaDB (embeddings)
- **Dashboard:** React or Streamlit
- **Infra:** Docker, GitHub

---

## Project structure

```
flywheel/
├── agents/
│   ├── strategy.py        # ADK + Gemini, session memory
│   ├── finance.py         # guardrail deterministic; ADK + Gemini narrates it
│   ├── marketing.py       # CrewAI + Gemini
│   ├── product.py         # CrewAI + Gemini
│   ├── sales.py           # CrewAI + Gemini
│   ├── crm.py             # CrewAI + local Ollama (qwen3:4b) -- privacy slice
│   └── analytics.py       # ADK + Gemini, session memory
├── simulator/
│   └── market_simulator.py
├── orchestration/
│   ├── cycle.py           # main cycle loop
│   └── a2a_bridge.py      # cross-framework agent communication -- TODO
├── observability/
│   ├── decision_record.py
│   └── dashboard/         # Streamlit
├── tools/
│   ├── mcp_server.py      # FastMCP server: Decision Record query tools
│   └── mcp_client_tool.py # CrewAI tool, talks to mcp_server.py over stdio
├── data/                  # SQLite + ChromaDB stores (gitignored)
├── tests/
├── docs/
│   ├── setup.md
│   ├── installed-versions.lock.txt
│   └── project_report.md
├── requirements.txt
└── README.md
```

Status: Strategy, Finance, Analytics, Marketing, Product, Sales, and CRM
are all genuinely LLM-backed (not placeholders). MCP is real (FastMCP
server + stdio client tool, wired into CRM). A2A is not yet implemented.

---

## Getting started

```bash
# clone the repo
git clone <repo-url>
cd flywheel

# install dependencies
pip install -r requirements.txt

# pull the local model
ollama pull llama3.1:8b

# set free-tier API keys (optional, for Strategy/Finance reasoning)
export GROQ_API_KEY=<your-key>
export GEMINI_API_KEY=<your-key>

# run one full business cycle
python orchestration/cycle.py --cycles 1

# launch the observability dashboard
streamlit run observability/dashboard/app.py
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

