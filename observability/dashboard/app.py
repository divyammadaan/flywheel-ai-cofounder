"""Flywheel dashboard — the founder-facing front end.

Two entry points, mirroring the product:
  1. Validate an idea: pitch -> market research -> clarifying questions ->
     GO/PIVOT/NO-GO -> company formation -> engine -> funding assessment
  2. Run the engine directly on an existing plan

Plus the observability view over everything that happened: KPI trends,
budget allocation, and the full agent decision trail.

Run with (must be the venv's Python -- a system-wide streamlit shadows it):
    .venv/Scripts/python -m streamlit run observability/dashboard/app.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(page_title="Flywheel", layout="wide", page_icon="🔄")

# There is a system-wide `streamlit` on PATH that shadows the venv's. Running
# plain `streamlit run app.py` therefore starts fine and only dies here, on
# the first render, with a bare ModuleNotFoundError -- the server boots
# either way because Streamlit doesn't import the script until a browser
# connects. Catch it and say what to actually do.
try:
    from agents.company_formation import CompanyFormationAgent
    from agents.founder_advisor import FounderAdvisorAgent
    from agents.funding import FundingAgent
    from agents.intake import IntakeAgent
    from agents.market_research import MarketResearchAgent
    from observability.decision_record import DB_PATH, DecisionRecord, get_records, log_decision
    from orchestration.cycle import run as run_cycles
    from orchestration.validate_flow import PRECYCLE, kpi_history
except ModuleNotFoundError as exc:
    st.error(
        f"**Missing dependency: `{exc.name}`** — this is almost certainly the wrong Python.\n\n"
        "A system-wide `streamlit` shadows the one in `.venv`, so plain `streamlit run ...` "
        "runs against system Python, which doesn't have this project's packages.\n\n"
        "Run it through the venv instead:\n\n"
        "```\n.venv/Scripts/python -m streamlit run observability/dashboard/app.py\n```\n\n"
        "(or activate the venv first: `.venv/Scripts/activate`)"
    )
    st.stop()


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
# Validation is a two-step round trip: Market Research has to run before we
# know what to ask the founder, and the Advisor can't rule until they've
# answered. session_state carries the half-finished state across the rerun
# that Streamlit does on every interaction.
st.session_state.setdefault("stage", "idle")

with st.sidebar:
    st.header("Start")
    mode = st.radio("Entry point", ["Validate an idea", "Run engine only"], key="entry_mode")
    num_cycles = st.number_input("Engine cycles", min_value=1, max_value=10, value=2)

    if mode == "Validate an idea":
        pitch = st.text_area(
            "Describe your business",
            placeholder="I want to open an e-commerce store selling sneakers in Bangalore...\n\n"
            "Or, for an existing business: revenue, EBITDA, debt, industry, where you sell.",
            height=160,
            key="pitch_text",
        )
        do_formation = st.checkbox("Include company formation plan", value=True)
        do_funding = st.checkbox("Include funding assessment", value=True)

        # Groq's free tier caps output tokens/minute, so most of a run's wall
        # time is spent waiting out rate limits rather than generating. Give a
        # real estimate instead of an indefinite spinner.
        est = 40 + 25 * int(num_cycles) + (30 if do_formation else 0) + (30 if do_funding else 0)
        st.caption(
            f"~{est // 60}m {est % 60}s expected. Real LLM calls, and Groq's free tier "
            "rate-limits output tokens per minute, so much of that is waiting."
        )

        if st.button("Analyse my idea", type="primary", use_container_width=True, disabled=not pitch.strip()):
            DB_PATH.unlink(missing_ok=True)
            with st.spinner("Intake + market research (real LLM calls, ~30s)..."):
                business = IntakeAgent().process(pitch)
                log_decision(DecisionRecord(PRECYCLE, "intake", {"raw_input": pitch}, business.__dict__))
                report = MarketResearchAgent().research(business)
                log_decision(DecisionRecord(PRECYCLE, "market_research", business.__dict__, report.__dict__))
            st.session_state.update(
                stage="awaiting_answers",
                business=business,
                report=report,
                do_formation=do_formation,
                do_funding=do_funding,
                num_cycles=num_cycles,
            )
            st.rerun()
    else:
        st.caption(
            "Runs the execution engine on a generic cold start, skipping validation. "
            "Strategy/Finance/Analytics/Marketing/Product/Sales on Groq, CRM on local Ollama."
        )
        if st.button("Run engine", type="primary", use_container_width=True):
            DB_PATH.unlink(missing_ok=True)
            with st.spinner(f"Running {num_cycles} cycle(s) -- real LLM calls, ~30-60s per cycle..."):
                run_cycles(num_cycles)
            st.rerun()

    if st.session_state.stage != "idle" and st.button("Reset", use_container_width=True):
        st.session_state.stage = "idle"
        st.rerun()

st.title("🔄 Flywheel")

# ------------------------------------------------- clarifying question step --
if st.session_state.stage == "awaiting_answers":
    business = st.session_state.business
    report = st.session_state.report

    st.subheader("A few questions before I can give you a verdict")
    st.caption(f"{business.business_summary}  ·  {business.industry}  ·  {business.target_region}")

    with st.form("clarifying"):
        answers = {}
        for i, q in enumerate(report.clarifying_questions):
            answers[q] = st.text_input(q, key=f"answer_{i}")
        submitted = st.form_submit_button("Get my verdict", type="primary")

    if submitted:
        with st.spinner("Founder Advisor is deciding..."):
            decision = FounderAdvisorAgent().decide(business, report, answers)
            log_decision(DecisionRecord(PRECYCLE, "founder_advisor", {"qa_answers": answers}, decision.__dict__))

        if decision.verdict != "NO_GO":
            if st.session_state.do_formation:
                with st.spinner("Drafting company formation plan..."):
                    formation = CompanyFormationAgent().plan(business)
                    log_decision(
                        DecisionRecord(PRECYCLE, "company_formation", business.__dict__, formation.__dict__)
                    )

            seed_context = (
                f"Market Research found: {report.market_size_estimate} "
                f"Competitors: {report.key_competitors} Opportunities: {report.opportunities} "
                f"Risks: {report.risks}\n"
                f"Founder Advisor verdict: {decision.verdict} -- {decision.rationale}\n"
                f"Recommended starting plan: positioning '{decision.seed_positioning}' at "
                f"${decision.seed_pricing:.2f}, budget priorities {decision.seed_priorities}."
            )
            with st.spinner(f"Running {st.session_state.num_cycles} engine cycle(s)..."):
                run_cycles(st.session_state.num_cycles, initial_context=seed_context)

            if st.session_state.do_funding:
                with st.spinner("Assessing funding readiness..."):
                    funding = FundingAgent().assess(business, kpi_history())
                    log_decision(
                        DecisionRecord(PRECYCLE, "funding", {"kpi_history": kpi_history()}, funding.__dict__)
                    )

        st.session_state.stage = "done"
        st.rerun()

    st.stop()

records = load_records()
if not records:
    st.info(
        "Nothing run yet. Describe your business in the sidebar and hit **Analyse my idea**, "
        "or switch to **Run engine only** to skip validation."
    )
    st.stop()

# Cycle 0 is the pre-engine validation gate (intake/research/advisor/
# formation/funding), not a business cycle -- keep it out of the KPI and
# budget charts, which are about engine cycles only.
cycles = sorted({r["cycle"] for r in records if r["cycle"] > 0})
precycle = {r["agent"]: r["decision"] for r in records if r["cycle"] == 0}
analytics = by_agent(records, "analytics")
finance = by_agent(records, "finance")
strategy = by_agent(records, "strategy")

# ------------------------------------------------------ validation gate --
if precycle:
    st.subheader("Validation & advisory")

    if "intake" in precycle:
        d = precycle["intake"]
        c1, c2, c3 = st.columns(3)
        c1.metric("Industry", d.get("industry", "—"))
        c2.metric("Region", d.get("target_region", "—"))
        c3.metric("Mode", d.get("mode", "—"))
        st.caption(md_escape(d.get("business_summary", "")))

    if "founder_advisor" in precycle:
        d = precycle["founder_advisor"]
        verdict = d.get("verdict", "?")
        badge = {"GO": "🟢", "PIVOT": "🟡", "NO_GO": "🔴"}.get(verdict, "⚪")
        with st.expander(f"{badge} Founder Advisor verdict: {verdict}", expanded=True):
            st.markdown(md_escape(d.get("rationale", "")))
            if d.get("seed_positioning"):
                st.markdown(f"**Seed positioning:** {md_escape(d['seed_positioning'])}")
                st.markdown(f"**Seed pricing:** \\${d.get('seed_pricing', 0):.2f}")

    if "market_research" in precycle:
        d = precycle["market_research"]
        with st.expander("🔍 Market research", expanded=False):
            for label, key in (
                ("Market size", "market_size_estimate"),
                ("Competitors", "key_competitors"),
                ("Opportunities", "opportunities"),
                ("Risks", "risks"),
            ):
                st.markdown(f"**{label}:** {md_escape(d.get(key, ''))}")
            if d.get("clarifying_questions"):
                st.markdown("**Questions asked the founder:**")
                for q in d["clarifying_questions"]:
                    st.markdown(f"- {md_escape(q)}")

    if "company_formation" in precycle:
        d = precycle["company_formation"]
        with st.expander(f"🏛️ Company formation — {d.get('recommended_entity', '')}", expanded=False):
            st.markdown(f"**Why:** {md_escape(d.get('entity_rationale', ''))}")
            for label, key in (
                ("Registration steps", "registration_steps"),
                ("Licences & permits", "licenses_and_permits"),
                ("Tax registrations", "tax_registrations"),
            ):
                st.markdown(f"**{label}:**")
                st.markdown(md_escape(d.get(key, "")))
            c1, c2 = st.columns(2)
            c1.metric("Est. cost", d.get("estimated_cost", "—"))
            c2.metric("Est. timeline", d.get("estimated_timeline", "—"))
            st.warning(d.get("disclaimer", ""))

    if "funding" in precycle:
        d = precycle["funding"]
        with st.expander(f"💸 Funding readiness: {d.get('readiness', '?')}", expanded=False):
            st.markdown(md_escape(d.get("readiness_rationale", "")))
            for label, key in (
                ("Timing", "recommended_timing"),
                ("Metrics to hit first", "metrics_to_hit"),
                ("Investor profile to target", "investor_profile"),
                ("Non-equity alternatives", "alternative_funding"),
                ("Pitch deck outline", "pitch_deck_outline"),
            ):
                st.markdown(f"**{label}:**")
                st.markdown(md_escape(d.get(key, "")))

if not cycles:
    st.info("Validation ran, but no engine cycles yet (a NO_GO verdict stops before the engine).")
    st.stop()

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
kpi_df = pd.DataFrame(kpi_rows)
# String index keeps the axis reading "Cycle 1" instead of "1.000000".
kpi_df["cycle"] = kpi_df["cycle"].map(lambda c: f"Cycle {c}")
kpi_df = kpi_df.set_index("cycle")

KPIS = (
    ("Revenue", "revenue", "${:,.2f}", "higher is better"),
    ("CAC", "cac", "${:,.2f}", "lower is better"),
    ("Conversion", "conversion_rate", "{:.0%}", "higher is better"),
    ("Churn", "churn_rate", "{:.1%}", "lower is better"),
)

if len(kpi_df) == 1:
    # A one-point line chart draws nothing useful -- show the numbers, and
    # say plainly that a trajectory needs more than one cycle.
    st.caption("One cycle so far — run more to see a trajectory.")
    for col, (label, key, fmt, _) in zip(st.columns(4), KPIS):
        value = kpi_df.iloc[0][key]
        col.metric(label, fmt.format(value) if pd.notna(value) else "N/A")
else:
    col1, col2 = st.columns(2)
    for i, (label, key, _, direction) in enumerate(KPIS):
        target = col1 if i % 2 == 0 else col2
        with target:
            st.caption(f"{label} — {direction}")
            st.line_chart(kpi_df[[key]])

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
    budget_df = pd.DataFrame(budget_rows)
    budget_df["cycle"] = budget_df["cycle"].map(lambda c: f"Cycle {c}")
    st.bar_chart(budget_df.set_index("cycle"))

# --------------------------------------------------------- per-cycle trail --
st.subheader("Agent decision trail")
# select_slider needs >1 option; with a single cycle there's nothing to pick.
if len(cycles) > 1:
    selected_cycle = st.select_slider("Cycle", options=cycles, value=cycles[-1])
else:
    selected_cycle = cycles[0]
    st.caption(f"Cycle {selected_cycle}")

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
            record = cycle_records[agent]

            # The generated ad creative, shown above its copy so the pair
            # reads as the actual ad. Guarded on existence: image generation
            # is allowed to fail without failing the cycle, and old runs may
            # reference files since cleaned up.
            if agent == "marketing":
                image_path = record.get("ad_image_path")
                if image_path and Path(image_path).exists():
                    st.image(image_path, use_container_width=True)
                elif image_path:
                    st.caption("_(ad image missing from disk)_")

            st.caption(extract(record))

            if agent == "crm" and record.get("at_risk_segments"):
                st.caption("At risk: " + ", ".join(record["at_risk_segments"]))
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
