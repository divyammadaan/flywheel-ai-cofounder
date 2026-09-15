"""Terminal printing for the CLI flows (validate_flow.py, review_flow.py) --
kept apart from the engine so orchestration/cycle.py holds no presentation
code."""

from agents._money import fmt_money
from agents._segments import SEGMENT_LABELS, SEGMENTS
from agents.analytics import describe_file_metrics, describe_period


def rule(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


def _print_health(health: dict, currency: str) -> None:
    def m(amount):
        return fmt_money(amount, currency)

    if "launch_budget" in health:
        print(f"Capital          : {m(health['capital'])}")
        if health.get("runway_months_reserved"):
            print(f"Reserve          : {m(health['reserve'])} ({health['runway_months_reserved']} months of fixed costs)")
        print(f"Launch budget    : {m(health['launch_budget'])}")
        if health.get("break_even_units_per_month") is not None:
            print(f"Break-even       : {health['break_even_units_per_month']:,} units a month "
                  f"(margin {m(health['contribution_margin'])} per unit)")
    else:
        print(f"Monthly net      : {m(health['monthly_net_profit'])}")
        runway = health.get("runway_months")
        print(f"Runway           : {'profitable, no burn' if health['profitable'] else (f'{runway} months' if runway else 'unknown')}")
        if health.get("debt_to_annual_revenue") is not None:
            print(f"Debt / revenue   : {health['debt_to_annual_revenue']:.0%} of a year's revenue")
    for warning in health.get("warnings", []):
        print(f"!! {warning}")


def print_plan(result) -> None:
    currency = result.brief.currency

    def m(amount):
        return fmt_money(amount, currency)

    s = result.strategy
    rule("STRATEGY")
    print(f"Positioning     : {s.positioning}")
    print(f"Target customer : {s.target_customer}")
    print(f"Price           : {m(s.price)} {s.price_unit}")
    print(f"Rationale       : {s.rationale}")

    a = result.allocation
    rule(f"FINANCE -- {m(a.total_budget)} to spend")
    _print_health(a.health, currency)
    print()
    for name in ("marketing", "product", "sales", "crm"):
        if getattr(a, name):
            print(f"  {name:<10} {m(getattr(a, name))}")
    print(f"\n{a.rationale}")

    mk = result.marketing
    rule(f"MARKETING -- {m(mk.budget)} (via {result.marketing_transport})")
    for i, c in enumerate(mk.campaigns, 1):
        print(f"{i}. {c['channel']} -- {m(c['budget'])}")
        print(f"   Where : {c['where']}")
        print(f"   Format: {c['ad_format']}  |  Objective: {c['objective']}  |  When: {c['duration']}")
    if mk.budget_adjusted:
        print("   (campaign budgets were scaled down to fit the marketing allocation)")
    print(f"\nAd copy : {mk.ad_copy}")
    if mk.ad_image_path:
        print(f"Ad image: {mk.ad_image_path}")

    sa = result.sales
    rule(f"SALES -- {m(sa.budget)}")
    for i, src in enumerate(sa.lead_sources, 1):
        print(f"{i}. {src['where']} -- {m(src['budget'])}")
        print(f"   How   : {src['how']}")
        print(f"   Weekly: {src['weekly_actions']}")
    if sa.budget_adjusted:
        print("   (lead-source budgets were scaled down to fit the sales allocation)")
    print(f"\nLead -> customer:\n{sa.conversion_process}")

    p = result.product
    rule(f"PRODUCT ({p.plan_type}) -- {m(p.budget)}")
    for item in p.line_items:
        print(f"  {item['units']:>6,} x {item['unit']:<22} {item['item']}")
        print(f"         @ {m(item['unit_cost'])} = {m(item['total_cost'])}")
    note = "  (quantities cut to fit the budget)" if p.budget_adjusted else ""
    print(f"  Total: {m(p.line_items_total)}{note}")
    print(f"\nSourcing : {p.sourcing_plan}")
    print(f"{'Reorder' if p.plan_type == 'inventory' else 'Scale up'} : {p.replenish_policy}")
    print(f"Costs    : {p.cost_basis}")

    cr = result.crm
    if cr is None:
        return
    rule(f"CRM -- {m(cr.budget)} (local Ollama, from your uploaded orders)")
    for key in SEGMENTS:
        seg = cr.segments["segments"][key]
        change = f"  ({cr.changes[key]:+d} since last period)" if cr.changes else ""
        print(f"{seg['label']:<16} {seg['customers']:>5} customers{change}  -- spend {m(cr.spend[key])}")
        print(f"   -> {cr.actions[key]}")
    if cr.budget_adjusted:
        print("   (spends were scaled down to fit the CRM budget)")
    for c in cr.segments["top_slipping"]:
        print(f"   worth a personal call: {c['customer']} ({m(c['spent'])}, {c['days_since_last_order']} days quiet)")
    print(f"\nMessage to {SEGMENT_LABELS['slipping'].lower()}: {cr.slipping_message}")
    print(f"Message to lost customers: {cr.lost_message}")
    for preview in cr.message_previews:
        print(f"   to {preview['customer']}: {preview['message']}")


def print_analytics(report) -> None:
    rule(f"ANALYTICS -- {report.period_label}")
    print(describe_period(report.metrics, report.kpis, report.currency))
    if report.file_metrics:
        print(f"\n{describe_file_metrics(report.file_metrics, report.currency)}")
    print(f"\n{report.summary}")


def print_funding(plan) -> None:
    rule("FUNDING ROADMAP")
    print(f"Ready to raise now : {plan.readiness}")
    print(f"{plan.readiness_rationale}\n")
    print(f"Target raise       : {plan.target_raise_date} -- {plan.target_stage}")
    print(f"Revenue milestone  : {plan.revenue_milestone}")
    print(f"Profit milestone   : {plan.profit_milestone}")
    print(f"Traction milestones: {plan.traction_milestones}\n")
    print(f"Investor profile   : {plan.investor_profile}")
    print(f"Alternatives       : {plan.alternative_funding}\n")
    print(f"Pitch deck outline:\n{plan.pitch_deck_outline}")
