"""Flywheel dashboard — the founder-facing front end.

Two entry points, one per kind of business:
  1. New idea (not launched): pitch + capital (+ running costs) -> market
     research -> clarifying questions -> GO/PIVOT/NO-GO -> company formation ->
     launch plan -> funding roadmap. Nothing is simulated.
  2. Existing business: description + real numbers + order history upload
     (.csv/.xlsx) -> Analytics -> plan for the next period, including CRM on
     the uploaded customers -> funding roadmap.

Every amount and budget comes from the founder. Below the inputs sits the
plan itself and the full agent decision trail.

Run with (must be the venv's Python -- a system-wide streamlit shadows it):
    .venv/Scripts/python -m streamlit run observability/dashboard/app.py
"""

import json
import sys
from dataclasses import asdict
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
    from agents._cash import DEFAULT_RUNWAY_MONTHS
    from agents._money import SUPPORTED_CURRENCIES, fmt_money
    from agents._segments import SEGMENT_LABELS, SEGMENTS
    from agents.analytics import PeriodMetrics
    from agents.company_formation import CompanyFormationAgent
    from agents.finance import MAX_SHARE_PER_AGENT
    from agents.founder_advisor import FounderAdvisorAgent
    from agents.intake import BusinessInput, IntakeAgent
    from agents.market_research import MarketResearchAgent
    from observability.decision_record import DecisionRecord, get_records, log_decision, reset_records
    from orchestration.cycle import (
        PRECYCLE,
        PlanBlocked,
        next_review_cycle,
        run_business_review,
        run_funding,
        run_launch_plan,
    )
    from observability.usage import usage_summary
    from tools.landing_page import build_landing_page
    from tools.orders_file import OrdersFileError, load_orders
    from tools.sample_data import generate_orders, to_file_bytes
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

AREAS = ("marketing", "product", "sales", "crm")
NEW_IDEA = "New idea (not launched)"
EXISTING_BUSINESS = "Existing business"


def load_records() -> list[dict]:
    records = get_records()
    for r in records:
        r["input_snapshot"] = json.loads(r["input_snapshot"])
        r["decision"] = json.loads(r["decision"])
    return records


def md_escape(text) -> str:
    """Escape $ before st.markdown: Streamlit renders $...$ as LaTeX math,
    which mangles LLM-generated text containing plain dollar amounts (e.g.
    "revenue growing to $144.00" silently ate everything up to the next $
    into a math span)."""
    return str(text or "").replace("$", "\\$")


def money(amount, currency: str) -> str:
    """Formatted in the founder's currency and $-escaped for st.markdown."""
    return md_escape(fmt_money(amount, currency))


def pct(value) -> str:
    return f"{value:.1%}" if value is not None and pd.notna(value) else "not reported"


@st.cache_data
def sample_files() -> tuple[bytes, bytes]:
    orders = generate_orders()
    return to_file_bytes(orders, "csv"), to_file_bytes(orders, "xlsx")


def run_safely(step) -> bool:
    """Run a plan step; a PlanBlocked (e.g. no cash left after the reserve)
    is shown to the founder instead of crashing the page."""
    try:
        step()
        return True
    except PlanBlocked as blocked:
        st.session_state.plan_error = str(blocked)
        return False


# ---------------------------------------------------------------- sidebar --
# Validation is a two-step round trip: Market Research has to run before we
# know what to ask the founder, and the Advisor can't rule until they've
# answered. session_state carries the half-finished state across the rerun
# that Streamlit does on every interaction.
st.session_state.setdefault("stage", "idle")

records = load_records()
precycle = {r["agent"]: r["decision"] for r in records if r["cycle"] == PRECYCLE}
has_review_history = any(r["agent"] == "analytics" for r in records) and "intake" in precycle

with st.sidebar:
    st.header("Start")
    mode = st.radio("What are you planning?", [NEW_IDEA, EXISTING_BUSINESS], key="entry_mode")
    currency = st.selectbox("Currency", SUPPORTED_CURRENCIES, key="currency")

    if mode == NEW_IDEA:
        pitch = st.text_area(
            "Describe your idea",
            placeholder="A subscription service delivering fresh filter coffee to homes in Bangalore, "
            "for professionals aged 25-40...",
            height=150,
            key="pitch_text",
        )
        capital = st.number_input(
            f"Capital you can put into the launch ({currency})",
            min_value=0.0,
            value=None,
            step=10000.0,
            placeholder="e.g. 1500000",
            key="capital",
        )
        with st.expander("Running costs (for reserve and break-even)"):
            fixed_costs = st.number_input(
                f"Monthly fixed costs ({currency})",
                min_value=0.0,
                value=None,
                step=5000.0,
                help="Rent, salaries, subscriptions: what you pay every month whatever you sell.",
            )
            unit_cost = st.number_input(
                f"Cost to deliver one unit ({currency})",
                min_value=0.0,
                value=None,
                step=10.0,
                help="e.g. beans, packaging and delivery for one monthly subscription.",
            )
            runway_months = st.number_input(
                "Months of fixed costs to keep in reserve", min_value=0, max_value=36, value=DEFAULT_RUNWAY_MONTHS
            )
        do_formation = st.checkbox("Include company formation plan", value=True)
        do_funding = st.checkbox("Include funding roadmap", value=True)
        if not capital:
            st.caption("The plan works from exactly this capital — nothing is assumed.")

        # Groq's free tier caps output tokens/minute, so most of a run's wall
        # time is spent waiting out rate limits rather than generating.
        st.caption("Takes a few minutes: real LLM calls on Groq's rate-limited free tier.")

        if st.button("Analyse my idea", type="primary", width="stretch", disabled=not (pitch.strip() and capital)):
            reset_records()
            st.session_state.plan_error = None
            with st.spinner("Intake + market research..."):
                business = IntakeAgent().process(pitch)
                business.currency = currency
                business.starting_capital = float(capital)
                business.monthly_fixed_costs = fixed_costs
                business.unit_cost = unit_cost
                business.runway_months = int(runway_months)
                log_decision(DecisionRecord(PRECYCLE, "intake", {"raw_input": pitch}, business.__dict__))
                report = MarketResearchAgent().research(business)
                log_decision(DecisionRecord(PRECYCLE, "market_research", business.__dict__, report.__dict__))
            st.session_state.update(
                stage="awaiting_answers",
                business=business,
                report=report,
                do_formation=do_formation,
                do_funding=do_funding,
            )
            st.rerun()
    else:
        append = False
        if has_review_history:
            append = st.checkbox(
                "Add as a new period for the current business",
                value=False,
                help="Keeps earlier periods so Analytics and CRM can compare. Unticked starts a fresh business.",
            )
        if append:
            currency = precycle["intake"].get("currency", currency)
            st.caption(f"Using {currency}, to match this business's earlier periods.")

        description = st.text_area(
            "Describe your business",
            placeholder="What you sell, where, to whom, and how long you've been operating.",
            height=100,
            key="business_text",
            disabled=append,
        )

        with st.expander("No order file handy? Download a sample"):
            st.caption("300 made-up customers of a Bangalore coffee subscription, 12 months of orders.")
            csv_bytes, xlsx_bytes = sample_files()
            c1, c2 = st.columns(2)
            c1.download_button("CSV", csv_bytes, "sample_orders.csv", "text/csv")
            c2.download_button(
                "Excel",
                xlsx_bytes,
                "sample_orders.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

        with st.form("numbers"):
            orders_upload = st.file_uploader(
                "Order history (.csv or .xlsx)",
                type=["csv", "xlsx"],
                help="One row per order with the customer, order date and amount. City, product and channel "
                "are optional. Powers the CRM plan and adds order figures to Analytics.",
            )
            st.caption("Your real numbers for the period. Fields marked * are required.")
            period_label = st.text_input("Period *", placeholder="e.g. FY2025-26 or Aug 2026")
            period_months = st.number_input("Months the numbers cover *", min_value=1, max_value=12, value=12)
            revenue = st.number_input(f"Revenue * ({currency})", min_value=0.0, value=None, step=10000.0)
            net_profit = st.number_input(f"Net profit * ({currency}, negative for a loss)", value=None, step=10000.0)
            total_debt = st.number_input(f"Total debt * ({currency})", min_value=0.0, value=None, step=10000.0)
            budget = st.number_input(
                f"Budget you can deploy next period * ({currency})", min_value=0.0, value=None, step=10000.0
            )
            st.caption("Optional — leave blank if you don't track it. Nothing is estimated.")
            cash = st.number_input(f"Cash in bank ({currency})", min_value=0.0, value=None, step=10000.0)
            ebitda = st.number_input(f"EBITDA ({currency})", value=None, step=10000.0)
            marketing_spend = st.number_input(
                f"Marketing spend this period ({currency})", min_value=0.0, value=None, step=1000.0
            )
            new_customers = st.number_input("New customers this period", min_value=0, value=None, step=1)
            customers_at_start = st.number_input("Customers at start of period", min_value=0, value=None, step=1)
            customers_lost = st.number_input("Customers lost this period", min_value=0, value=None, step=1)
            do_funding_review = st.checkbox("Include funding roadmap", value=True)
            submitted_numbers = st.form_submit_button("Review my business", type="primary", width="stretch")

        if submitted_numbers:
            missing = [
                label
                for label, value in (
                    ("Period", period_label.strip() or None),
                    ("Revenue", revenue),
                    ("Net profit", net_profit),
                    ("Total debt", total_debt),
                    ("Budget to deploy", budget),
                )
                if value is None
            ]
            if not append and not description.strip():
                missing.insert(0, "Business description")
            if budget is not None and budget <= 0:
                missing.append("a budget above zero")

            orders = None
            if orders_upload is not None:
                try:
                    orders = load_orders(orders_upload, orders_upload.name)
                except OrdersFileError as exc:
                    st.error(f"Order file: {exc}")
                    missing.append("a usable order file")

            if missing:
                st.error("Please fill in: " + ", ".join(missing))
            else:
                metrics = PeriodMetrics(
                    period_label=period_label.strip(),
                    revenue=float(revenue),
                    net_profit=float(net_profit),
                    total_debt=float(total_debt),
                    period_months=int(period_months),
                    ebitda=ebitda,
                    cash_in_bank=cash,
                    marketing_spend=marketing_spend,
                    new_customers=new_customers,
                    customers_at_start=customers_at_start,
                    customers_lost=customers_lost,
                )
                if append:
                    business = BusinessInput(**precycle["intake"])
                else:
                    reset_records()
                    with st.spinner("Intake..."):
                        business = IntakeAgent().process(description)
                    business.mode = "existing_business"
                    business.currency = currency
                # The form's numbers are the single source of truth -- they
                # replace anything the model read out of the description.
                business.existing_metrics = asdict(metrics)
                if not append:
                    log_decision(DecisionRecord(PRECYCLE, "intake", {"raw_input": description}, business.__dict__))

                st.session_state.plan_error = None
                result_box = {}

                def review_step():
                    with st.spinner("Analytics on your numbers, then planning the next period..."):
                        result_box["plan"] = run_business_review(
                            business, metrics, float(budget), next_review_cycle(), orders
                        )

                if run_safely(review_step) and do_funding_review:
                    with st.spinner("Building the funding roadmap..."):
                        run_funding(business, result_box["plan"])
                st.session_state.stage = "done"
                st.rerun()

    if st.session_state.stage != "idle" and st.button("Reset", width="stretch"):
        st.session_state.stage = "idle"
        st.session_state.plan_error = None
        st.rerun()

st.title("🔄 Flywheel")

if st.session_state.get("plan_error"):
    st.error(f"**The plan couldn't go ahead.** {md_escape(st.session_state.plan_error)}")

# ------------------------------------------------- clarifying question step --
if st.session_state.stage == "awaiting_answers":
    business = st.session_state.business
    report = st.session_state.report

    st.subheader("A few questions before I can give you a verdict")
    st.caption(
        f"{md_escape(business.business_summary)}  ·  {business.industry}  ·  {business.target_region}  ·  "
        f"capital {money(business.starting_capital, business.currency)}"
    )
    if business.mode == "existing_business":
        st.warning(
            "This sounds like an existing business. For a plan built on your real numbers, "
            "choose **Existing business** in the sidebar."
        )

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
            result_box = {}

            def launch_step():
                with st.spinner("Building the launch plan: strategy, cash check, then marketing, sales and product..."):
                    result_box["plan"] = run_launch_plan(business, report, decision, answers)

            if run_safely(launch_step) and st.session_state.do_funding:
                with st.spinner("Building the funding roadmap..."):
                    run_funding(business, result_box["plan"])

        st.session_state.stage = "done"
        st.rerun()

    st.stop()

if not records:
    st.info(
        "Nothing planned yet. Pick **New idea** to validate an idea and get a launch plan, or "
        "**Existing business** to plan from your real numbers and order history."
    )
    st.stop()

intake = precycle.get("intake", {})
cur = intake.get("currency", "INR")
operating = intake.get("mode") == "existing_business"
cycles = sorted({r["cycle"] for r in records if r["cycle"] > PRECYCLE})
analytics = {r["cycle"]: r["decision"] for r in records if r["agent"] == "analytics"}

# ------------------------------------------------------------ the business --
st.subheader("Your business")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Industry", intake.get("industry", "—"))
c2.metric("Region", intake.get("target_region", "—"))
c3.metric("Stage", "Operating" if operating else "Pre-launch")
if operating:
    c4.metric("Periods reported", len(analytics))
else:
    c4.metric("Launch capital", fmt_money(intake.get("starting_capital") or None, cur))
st.caption(md_escape(intake.get("business_summary", "")))

if "founder_advisor" in precycle:
    d = precycle["founder_advisor"]
    verdict = d.get("verdict", "?")
    badge = {"GO": "🟢", "PIVOT": "🟡", "NO_GO": "🔴"}.get(verdict, "⚪")
    with st.expander(f"{badge} Founder Advisor verdict: {verdict}", expanded=True):
        st.markdown(md_escape(d.get("rationale", "")))
        if d.get("seed_positioning"):
            st.markdown(f"**Seed positioning:** {md_escape(d['seed_positioning'])}")
            st.markdown(f"**Seed price:** {money(d.get('seed_price'), cur)} {md_escape(d.get('seed_price_unit', ''))}")

if "market_research" in precycle:
    d = precycle["market_research"]
    with st.expander("🔍 Market research", expanded=False):
        st.caption(
            "Grounded in live web search; [n] refers to the sources listed below."
            if d.get("sources")
            else "No web search results were available, so figures are estimates."
        )
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
        if d.get("sources"):
            st.markdown("**Sources:**")
            for i, source in enumerate(d["sources"], 1):
                st.markdown(f"\\[{i}\\] [{md_escape(source.get('title') or source.get('url'))}]({source.get('url')})")

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

if not cycles:
    st.info("No plan yet (a NO_GO verdict stops before the launch plan).")
    st.stop()

# ------------------------------------------------- reported numbers (ops) --
if operating and analytics:
    st.subheader("Your reported numbers")
    rows = []
    for c in sorted(analytics):
        a = analytics[c]
        m, k = a.get("metrics", {}), a.get("kpis", {})
        rows.append(
            {
                "Period": a.get("period_label") or f"Period {c}",
                "Revenue": m.get("revenue"),
                "Net profit": m.get("net_profit"),
                "Total debt": m.get("total_debt"),
                "Cash in bank": m.get("cash_in_bank"),
                "EBITDA": m.get("ebitda"),
                "Marketing spend": m.get("marketing_spend"),
                "CAC": k.get("cac"),
                "New customers": m.get("new_customers"),
                "Customers lost": m.get("customers_lost"),
                "Net margin": k.get("net_margin"),
                "Churn": k.get("churn_rate"),
            }
        )
    numbers = pd.DataFrame(rows).set_index("Period")
    shown = numbers.astype(object)
    for col in ("Revenue", "Net profit", "Total debt", "Cash in bank", "EBITDA", "Marketing spend", "CAC"):
        shown[col] = numbers[col].map(lambda v: fmt_money(v, cur) if pd.notna(v) else "not reported")
    for col in ("New customers", "Customers lost"):
        shown[col] = numbers[col].map(lambda v: f"{int(v):,}" if pd.notna(v) else "not reported")
    for col in ("Net margin", "Churn"):
        shown[col] = numbers[col].map(pct)
    st.dataframe(shown, width="stretch")

    if len(numbers) > 1:
        left, right = st.columns(2)
        with left:
            st.caption(f"Revenue and net profit ({cur})")
            st.line_chart(numbers[["Revenue", "Net profit"]].astype(float))
        with right:
            ratio_cols = [c for c in ("Net margin", "Churn") if numbers[c].notna().any()]
            if ratio_cols:
                st.caption("Net margin and churn")
                st.line_chart(numbers[ratio_cols].astype(float))

# ------------------------------------------------------------------ plan --
st.subheader("Plan for the next period" if operating else "Launch plan")
if len(cycles) > 1:
    labels = {c: analytics.get(c, {}).get("period_label") or f"Period {c}" for c in cycles}
    selected = st.select_slider("Plan after period", options=cycles, value=cycles[-1], format_func=labels.get)
else:
    selected = cycles[0]

trail = {r["agent"]: r["decision"] for r in records if r["cycle"] == selected}
transport = next(
    (r["input_snapshot"].get("transport") for r in records if r["cycle"] == selected and r["agent"] == "marketing"),
    None,
)

if "analytics" in trail:
    a = trail["analytics"]
    k = a.get("kpis", {})
    with st.expander(f"📊 Analytics — {a.get('period_label', '')}", expanded=True):
        st.markdown(md_escape(a.get("summary", "")))
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Net margin", pct(k.get("net_margin")))
        m2.metric("Debt / annual revenue", pct(k.get("debt_to_revenue")))
        m3.metric("CAC", fmt_money(k.get("cac"), cur) if k.get("cac") is not None else "not reported")
        m4.metric("Churn", pct(k.get("churn_rate")))
        fm = a.get("file_metrics")
        if fm:
            st.markdown(f"**From your uploaded orders** ({fm['first_order']} to {fm['last_order']})")
            f1, f2, f3, f4 = st.columns(4)
            f1.metric("Orders", f"{fm['orders']:,}")
            f2.metric("Average order", fmt_money(fm["average_order_value"], cur))
            f3.metric("Repeat customers", f"{fm['repeat_customer_rate']:.0%}")
            change = fm.get("revenue_change_last_3m_vs_prior_3m")
            f4.metric("Last 3 months vs previous 3", f"{change:+.0%}" if change is not None else "—")
            if fm.get("monthly_revenue"):
                st.caption(f"Monthly revenue from the file ({cur})")
                st.bar_chart(pd.Series(fm["monthly_revenue"], name="revenue"))
            if fm.get("skipped_rows"):
                st.caption(f"{fm['skipped_rows']} unusable rows in the file were skipped.")

if "strategy" in trail:
    d = trail["strategy"]
    with st.expander("🎯 Strategy", expanded=True):
        for rejected in (r for r in records if r["cycle"] == selected and r["agent"] == "strategy_rejected"):
            st.caption(
                "The plan checker sent a draft back: "
                + md_escape(" ".join(rejected["input_snapshot"].get("problems", [])))
            )
        left, right = st.columns([2, 1])
        with left:
            st.markdown(f"**Positioning:** {md_escape(d.get('positioning', ''))}")
            st.markdown(f"**Target customer:** {md_escape(d.get('target_customer', '—'))}")
            st.markdown(f"**Rationale:** {md_escape(d.get('rationale', ''))}")
        with right:
            st.metric("Price", fmt_money(d.get("price"), cur))
            st.caption(md_escape(d.get("price_unit", "")))

if "finance" in trail:
    d = trail["finance"]
    health = d.get("health", {})
    st.markdown(f"#### 💰 Finance — {money(d.get('total_budget'), cur)} to spend")
    h1, h2, h3, h4 = st.columns(4)
    if "launch_budget" in health:
        h1.metric("Capital", fmt_money(health.get("capital"), cur))
        reserve_months = health.get("runway_months_reserved")
        h2.metric(
            "Held in reserve",
            fmt_money(health.get("reserve"), cur),
            help=f"{reserve_months} months of fixed costs" if reserve_months else "No fixed costs given",
        )
        h3.metric("Launch budget", fmt_money(health.get("launch_budget"), cur))
        be = health.get("break_even_units_per_month")
        h4.metric("Break-even", f"{be:,} units/month" if be is not None else "—")
    elif health:
        h1.metric("Monthly net profit", fmt_money(health.get("monthly_net_profit"), cur))
        runway = health.get("runway_months")
        h2.metric("Runway", "No burn" if health.get("profitable") else (f"{runway} months" if runway else "—"))
        h3.metric("Debt / annual revenue", pct(health.get("debt_to_annual_revenue")))
        h4.metric("Budget as share of cash", pct(health.get("budget_share_of_cash")))
    for warning in health.get("warnings", []):
        st.warning(md_escape(warning))

    spent_areas = [key for key in AREAS if d.get(key)]
    for col, key in zip(st.columns(max(len(spent_areas), 1)), spent_areas):
        col.metric("CRM" if key == "crm" else key.capitalize(), fmt_money(d.get(key), cur))
    unallocated = (d.get("total_budget") or 0) - sum(d.get(k) or 0 for k in AREAS)
    if unallocated > 0.5:
        st.caption(
            f"{money(unallocated, cur)} left unallocated: no area may take more than "
            f"{MAX_SHARE_PER_AGENT:.0%} of the budget."
        )
    st.caption(md_escape(d.get("rationale", "")))

tab_names = ["📣 Marketing", "📈 Sales", "📦 Product"]
if "crm" in trail:
    tab_names.append("🤝 CRM")
tabs = st.tabs(tab_names)

with tabs[0]:
    d = trail.get("marketing")
    if not d:
        st.caption("—")
    else:
        st.caption(f"Budget {money(d.get('budget'), cur)} · delivered via {transport or 'unknown'}")
        left, right = st.columns([1, 2])
        with left:
            image_path = d.get("ad_image_path")
            # Guarded on existence: image generation is allowed to fail
            # without failing the plan, and old runs may reference files
            # since cleaned up.
            if image_path and Path(image_path).exists():
                st.image(image_path, width="stretch")
            elif image_path:
                st.caption("_(ad image missing from disk)_")
            st.markdown(f"> {md_escape(d.get('ad_copy', ''))}")
        with right:
            for c in d.get("campaigns", []):
                with st.container(border=True):
                    st.markdown(f"**{md_escape(c.get('channel'))}** — {money(c.get('budget'), cur)}")
                    st.markdown(f"**Where:** {md_escape(c.get('where'))}")
                    st.caption(
                        f"{md_escape(c.get('ad_format'))} · {md_escape(c.get('objective'))} · "
                        f"{md_escape(c.get('duration'))}"
                    )
            if d.get("budget_adjusted"):
                st.warning("The campaigns asked for more than the marketing budget, so they were scaled down to fit.")

with tabs[1]:
    d = trail.get("sales")
    if not d:
        st.caption("—")
    else:
        st.caption(f"Budget {money(d.get('budget'), cur)}")
        for src in d.get("lead_sources", []):
            with st.container(border=True):
                st.markdown(f"**{md_escape(src.get('where'))}** — {money(src.get('budget'), cur)}")
                st.markdown(f"**How:** {md_escape(src.get('how'))}")
                st.markdown(f"**Every week:** {md_escape(src.get('weekly_actions'))}")
        if d.get("budget_adjusted"):
            st.warning("The lead sources asked for more than the sales budget, so they were scaled down to fit.")
        st.markdown("**From lead to paying customer:**")
        st.markdown(md_escape(d.get("conversion_process", "")))

with tabs[2]:
    d = trail.get("product")
    if not d:
        st.caption("—")
    else:
        is_inventory = d.get("plan_type") == "inventory"
        st.caption(
            ("Opening inventory" if is_inventory else "Delivery capacity: tools, equipment and hires")
            + f" · budget {money(d.get('budget'), cur)}"
        )
        items = d.get("line_items", [])
        if items:
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "Item": i.get("item"),
                            "Quantity": f"{i.get('units', 0):,} × {i.get('unit', '')}",
                            "Unit cost": fmt_money(i.get("unit_cost"), cur),
                            "Line total": fmt_money(i.get("total_cost"), cur),
                        }
                        for i in items
                    ]
                ),
                hide_index=True,
                width="stretch",
            )
        st.metric("Total", fmt_money(d.get("line_items_total"), cur))
        if d.get("budget_adjusted"):
            st.warning("The plan cost more than the product budget, so quantities were cut to fit.")
        st.markdown(f"**Sourcing:** {md_escape(d.get('sourcing_plan'))}")
        st.markdown(f"**{'Reorder' if is_inventory else 'Adding capacity'}:** {md_escape(d.get('replenish_policy'))}")
        st.caption(f"Cost basis: {md_escape(d.get('cost_basis'))}")

if "crm" in trail:
    with tabs[3]:
        d = trail["crm"]
        for warning in d.get("warnings", []):
            st.warning(md_escape(warning))
        seg = d.get("segments", {})
        changes = d.get("changes") or {}
        st.caption(
            f"From your uploaded orders, as of {seg.get('as_of', '—')} · customers typically re-order every "
            f"{seg.get('typical_gap_days', '—')} days · runs on the local model, so customer data stays on this machine"
        )
        rows = []
        for key in SEGMENTS:
            s = seg.get("segments", {}).get(key, {})
            rows.append(
                {
                    "Group": SEGMENT_LABELS[key],
                    "Customers": s.get("customers", 0),
                    "Change": f"{changes[key]:+d}" if key in changes else "—",
                    "Share of revenue": pct(s.get("revenue_share")),
                    "What to do": d.get("actions", {}).get(key, ""),
                    "Spend": fmt_money(d.get("spend", {}).get(key), cur),
                }
            )
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

        if seg.get("top_slipping"):
            st.markdown("**Worth a personal call — your biggest spenders going quiet:**")
            for c in seg["top_slipping"]:
                st.markdown(
                    f"- {md_escape(c['customer'])}: {money(c['spent'], cur)} over {c['orders']} orders, "
                    f"{c['days_since_last_order']} days since the last one"
                )
        m1, m2 = st.columns(2)
        with m1:
            st.markdown("**Message for customers slipping away**")
            st.code(d.get("slipping_message", ""), language=None, wrap_lines=True)
        with m2:
            st.markdown("**Win-back message for lost customers**")
            st.code(d.get("lost_message", ""), language=None, wrap_lines=True)
        spent = sum((d.get("spend") or {}).values())
        st.caption(f"Planned spend {money(spent, cur)} of the {money(d.get('budget'), cur)} CRM budget.")
        if d.get("budget_adjusted"):
            st.warning("The suggested spends added up to more than the CRM budget, so they were scaled down to fit.")
        if d.get("message_previews"):
            st.markdown("**Ready to send to the customers above:**")
            for preview in d["message_previews"]:
                st.markdown(f"- **{md_escape(preview['customer'])}:** {md_escape(preview['message'])}")
elif operating:
    st.caption("Upload your order history to also get a CRM plan: customer groups, retention actions and messages.")

if "funding" in trail:
    d = trail["funding"]
    st.subheader("💸 Funding roadmap")
    c1, c2 = st.columns(2)
    c1.metric("Ready to raise now?", d.get("readiness", "?"))
    c2.metric("Target raise", d.get("target_raise_date", "—"))
    st.markdown(f"**Stage:** {md_escape(d.get('target_stage'))}")
    for warning in d.get("warnings", []):
        st.warning("Check this: " + md_escape(warning))
    if not d.get("warnings") and any(r["cycle"] == selected and r["agent"] == "funding_rejected" for r in records):
        st.caption("The checker sent a first draft back for numbers that didn't add up; this version passed.")
    st.markdown(md_escape(d.get("readiness_rationale", "")))
    m1, m2, m3 = st.columns(3)
    for col, label, key in (
        (m1, "Revenue milestone", "revenue_milestone"),
        (m2, "Profit milestone", "profit_milestone"),
        (m3, "Traction milestones", "traction_milestones"),
    ):
        with col:
            with st.container(border=True):
                st.markdown(f"**{label}**")
                st.markdown(md_escape(d.get(key, "")))
    for label, key in (
        ("Investor profile to target", "investor_profile"),
        ("Non-equity alternatives", "alternative_funding"),
        ("Pitch deck outline", "pitch_deck_outline"),
    ):
        st.markdown(f"**{label}:**")
        st.markdown(md_escape(d.get(key, "")))

# ------------------------------------------------------------ launch page --
if "strategy" in trail:
    st.download_button(
        "Download launch page (HTML)",
        build_landing_page(intake, trail["strategy"], trail.get("marketing")),
        file_name="index.html",
        mime="text/html",
        help="A one-page site built from this plan, ready for any static host. "
        "Connect its form to a form service to collect sign-ups.",
    )

# ------------------------------------------------------------ model usage --
usage = usage_summary()
if usage["agents"]:
    totals = usage["totals"]
    with st.expander(
        f"🧮 Model usage this run — {totals['calls']} calls, "
        f"{totals['prompt_tokens'] + totals['completion_tokens']:,} tokens"
    ):
        u1, u2, u3, u4 = st.columns(4)
        u1.metric("Model calls", totals["calls"])
        u2.metric("Reused from cache", totals["cache_hits"])
        u3.metric("Tokens in", f"{totals['prompt_tokens']:,}")
        u4.metric("Tokens out", f"{totals['completion_tokens']:,}")
        st.dataframe(pd.DataFrame(usage["agents"]), hide_index=True, width="stretch")
        st.caption("Finance makes no model call: its maths and its explanation are both code.")

# -------------------------------------------------------------- raw table --
with st.expander("Raw Decision Records"):
    agents = sorted({r["agent"] for r in records})
    filter_agent = st.selectbox("Filter by agent", ["all"] + agents)
    filtered = records if filter_agent == "all" else [r for r in records if r["agent"] == filter_agent]
    st.dataframe(filtered, width="stretch")
