"""Flywheel observability dashboard — KPI trends, budget allocation, and the
full per-cycle agent decision trail, backed by the real Decision Record DB.

Run with: streamlit run observability/dashboard/app.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from observability.decision_record import DB_PATH, get_records
from orchestration.cycle import run as run_cycles

st.set_page_config(page_title="Flywheel Dashboard", layout="wide", page_icon="🔄")


def load_records() -> list[dict]:
    records = get_records()
    for r in records:
        r["input_snapshot"] = json.loads(r["input_snapshot"])
        r["decision"] = json.loads(r["decision"])
    return records


def by_agent(records: list[dict], agent: str) -> dict[int, dict]:
    return {r["cycle"]: r["decision"] for r in records if r["agent"] == agent}


def md_escape(text: str) -> str:
    """Escape $ before st.markdown: Streamlit renders $...$ as LaTeX math,
    which mangles LLM-generated text containing plain dollar amounts (e.g.
    "revenue growing to $144.00" silently ate everything up to the next $
    into a math span)."""
    return text.replace("$", "\\$")


# ---------------------------------------------------------------- sidebar --
with st.sidebar:
    st.header("Run simulation")
    num_cycles = st.number_input("Cycles to run", min_value=1, max_value=10, value=3)
    st.caption(
        "Starts a fresh run (clears existing Decision Records). "
        "Strategy/Finance/Analytics on Groq, Marketing/Product/Sales on Groq, "
        "CRM on local Ollama."
    )
    if st.button("Run new simulation", type="primary", use_container_width=True):
        DB_PATH.unlink(missing_ok=True)
        with st.spinner(f"Running {num_cycles} cycle(s) -- this calls real LLMs, expect ~10-30s per cycle..."):
            run_cycles(num_cycles)
        st.rerun()

st.title("🔄 Flywheel — Decision Record Dashboard")

records = load_records()
if not records:
    st.info("No decision records yet. Click **Run new simulation** in the sidebar, or run `python orchestration/cycle.py --cycles N` from the terminal.")
    st.stop()

cycles = sorted({r["cycle"] for r in records})
analytics = by_agent(records, "analytics")
finance = by_agent(records, "finance")
strategy = by_agent(records, "strategy")

# ------------------------------------------------------------ KPI trends --
st.subheader("KPI trajectory")
kpi_rows = []
for c in cycles:
    a = analytics.get(c)
    if not a:
        continue
    kpi_rows.append(
        {
            "cycle": c,
            "revenue": a["revenue"],
            "conversion_rate": a["conversion_rate"],
            "cac": a["cac"] if a["cac"] is not None and a["cac"] >= 0 else None,
            "churn_rate": a["churn_rate"],
        }
    )
kpi_df = pd.DataFrame(kpi_rows).set_index("cycle")

col1, col2 = st.columns(2)
with col1:
    st.caption("Revenue ($)")
    st.line_chart(kpi_df[["revenue"]])
    st.caption("Conversion rate")
    st.line_chart(kpi_df[["conversion_rate"]])
with col2:
    st.caption("CAC ($) -- lower is better")
    st.line_chart(kpi_df[["cac"]])
    st.caption("Churn rate -- lower is better")
    st.line_chart(kpi_df[["churn_rate"]])

# ------------------------------------------------------ budget allocation --
st.subheader("Budget allocation by cycle")
budget_rows = []
for c in cycles:
    f = finance.get(c)
    if not f:
        continue
    budget_rows.append(
        {"cycle": c, "marketing": f["marketing"], "product": f["product"], "sales": f["sales"], "crm": f["crm"]}
    )
if budget_rows:
    budget_df = pd.DataFrame(budget_rows).set_index("cycle")
    st.bar_chart(budget_df)

# --------------------------------------------------------- per-cycle trail --
st.subheader("Agent decision trail")
selected_cycle = st.select_slider("Cycle", options=cycles, value=cycles[-1])

cycle_records = {r["agent"]: r["decision"] for r in records if r["cycle"] == selected_cycle}

if "strategy" in cycle_records:
    d = cycle_records["strategy"]
    with st.expander(f"🎯 Strategy -- {d['positioning'][:80]}...", expanded=True):
        c1, c2 = st.columns([2, 1])
        with c1:
            st.markdown(f"**Positioning:** {md_escape(d['positioning'])}")
            st.markdown(f"**Rationale:** {md_escape(d['rationale'])}")
        with c2:
            st.metric("Price point", f"${d['pricing']:.2f}")
            st.bar_chart(pd.Series(d["priorities"], name="priority"))

if "finance" in cycle_records:
    d = cycle_records["finance"]
    with st.expander("💰 Finance -- budget allocation", expanded=False):
        cols = st.columns(4)
        for col, key in zip(cols, ("marketing", "product", "sales", "crm")):
            col.metric(key.capitalize(), f"${d[key]:.2f}")
        st.markdown(f"**Rationale:** {md_escape(d['rationale'])}")

exec_cols = st.columns(4)
exec_agents = [
    ("marketing", "📣 Marketing", lambda d: md_escape(d.get("ad_copy", ""))),
    ("product", "🛠️ Product", lambda d: md_escape(d.get("change_description", ""))),
    ("sales", "📈 Sales", lambda d: f"Outreach effort: {d.get('outreach_effort', 0):.0%}"),
    ("crm", "🤝 CRM (local Ollama)", lambda d: f"Retention effort: {d.get('retention_effort', 0):.0%}"),
]
for col, (agent, label, extract) in zip(exec_cols, exec_agents):
    with col:
        st.markdown(f"**{label}**")
        if agent in cycle_records:
            st.caption(extract(cycle_records[agent]))
            if agent == "crm" and cycle_records[agent].get("at_risk_segments"):
                st.caption("At risk: " + ", ".join(cycle_records[agent]["at_risk_segments"]))
        else:
            st.caption("—")

if "analytics" in cycle_records:
    d = cycle_records["analytics"]
    with st.expander("📊 Analytics summary", expanded=True):
        st.markdown(md_escape(d["summary"]))
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Revenue", f"${d['revenue']:.2f}")
        m2.metric("Conversion", f"{d['conversion_rate']:.0%}")
        m3.metric("CAC", f"${d['cac']:.2f}" if d["cac"] >= 0 else "N/A")
        m4.metric("Churn", f"{d['churn_rate']:.1%}")

# -------------------------------------------------------------- raw table --
with st.expander("Raw Decision Records"):
    agents = sorted({r["agent"] for r in records})
    filter_agent = st.selectbox("Filter by agent", ["all"] + agents)
    filtered = records if filter_agent == "all" else [r for r in records if r["agent"] == filter_agent]
    st.dataframe(filtered, use_container_width=True)
