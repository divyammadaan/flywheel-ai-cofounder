"""The plan as one structured, validated object.

Every agent's result is saved as its own decision record. `FinalPlan` gathers the
newest record of each agent for a run into a single Pydantic model, so the whole
plan can be validated, exported as JSON, rendered as Markdown, and shared as
state between agents:

  - `build_final_plan(run_id)` works on a finished run (the final output) and on
    one still in progress (every section not produced yet is simply None), which
    is what makes it the run's *state*: the ADK coordinator puts a snapshot of it
    in its session state, so the execution agents are working from the same
    picture of the business that Strategy and Finance produced.
  - `to_markdown(plan)` is the human-readable form: tables for budgets, campaigns,
    lead sources and inventory.

Sections have typed fields for what the product shows; `extra="allow"` carries
anything an agent adds later without breaking older exports.
"""

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from agents._money import fmt_money
from storage import fetch_records, get_run

SCHEMA_VERSION = "1.0"


class _Section(BaseModel):
    model_config = ConfigDict(extra="allow")


class BusinessSection(_Section):
    mode: str
    business_summary: str
    industry: str = ""
    product_or_service: str = ""
    target_region: str = ""
    currency: str = "INR"
    offering_type: str = "physical"
    starting_capital: float = 0.0


class ResearchSection(_Section):
    market_size_estimate: str = ""
    key_competitors: list[str] = Field(default_factory=list)
    opportunities: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    clarifying_questions: list[str] = Field(default_factory=list)
    sources: list[dict] = Field(default_factory=list)


class VerdictSection(_Section):
    verdict: Literal["GO", "PIVOT", "NO_GO"]
    rationale: list[str] = Field(default_factory=list)
    seed_positioning: str = ""
    seed_price: float = 0.0
    seed_price_unit: str = ""
    seed_priorities: dict[str, float] = Field(default_factory=dict)


class FormationSection(_Section):
    recommended_entity: str = ""
    entity_rationale: str = ""
    registration_steps: list[str] = Field(default_factory=list)
    licenses_and_permits: list[str] = Field(default_factory=list)
    tax_registrations: list[str] = Field(default_factory=list)
    estimated_cost: str = ""
    estimated_timeline: str = ""
    disclaimer: str = ""


class AnalyticsSection(_Section):
    period_label: str = ""
    headline: str = ""
    points: list[str] = Field(default_factory=list)
    summary: str = ""
    kpis: dict = Field(default_factory=dict)


class StrategySection(_Section):
    positioning: str
    target_customer: str
    price: float
    price_unit: str
    priorities: dict[str, float] = Field(default_factory=dict)
    rationale: list[str] = Field(default_factory=list)


class FinanceSection(_Section):
    total_budget: float
    marketing: float = 0.0
    product: float = 0.0
    sales: float = 0.0
    crm: float = 0.0
    rationale: str = ""
    health: dict = Field(default_factory=dict)


class MarketingSection(_Section):
    budget: float = 0.0
    campaigns: list[dict] = Field(default_factory=list)
    ad_copy: str = ""
    image_prompt: str = ""
    has_ad_image: bool = False
    budget_adjusted: bool = False


class SalesSection(_Section):
    budget: float = 0.0
    lead_sources: list[dict] = Field(default_factory=list)
    conversion_process: list[str] = Field(default_factory=list)


class ProductSection(_Section):
    budget: float = 0.0
    plan_type: str = ""
    line_items: list[dict] = Field(default_factory=list)
    line_items_total: float = 0.0
    sourcing_plan: list[str] = Field(default_factory=list)
    replenish_policy: list[str] = Field(default_factory=list)
    cost_basis: str = ""


class CRMSection(_Section):
    budget: float = 0.0
    segments: dict = Field(default_factory=dict)
    changes: dict = Field(default_factory=dict)
    actions: dict[str, str] = Field(default_factory=dict)
    spend: dict[str, float] = Field(default_factory=dict)
    slipping_message: str = ""
    lost_message: str = ""
    message_previews: list[dict] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class FundingSection(_Section):
    readiness: str = ""
    readiness_rationale: list[str] = Field(default_factory=list)
    target_raise_date: str = ""
    target_stage: str = ""
    revenue_milestone: str = ""
    profit_milestone: str = ""
    traction_milestones: list[str] = Field(default_factory=list)
    investor_profile: str = ""
    alternative_funding: str = ""
    pitch_deck_outline: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class Provenance(BaseModel):
    """Which agent produced which section, and when -- the audit trail."""

    agent: str
    saved_at: str
    revised: bool = False


class FinalPlan(BaseModel):
    schema_version: str = SCHEMA_VERSION
    run_id: int
    status: str = "running"
    mode: str | None = None
    label: str | None = None
    generated_at: str
    cycle: int = 0
    currency: str = "INR"

    business: BusinessSection | None = None
    research: ResearchSection | None = None
    verdict: VerdictSection | None = None
    formation: FormationSection | None = None
    analytics: AnalyticsSection | None = None
    strategy: StrategySection | None = None
    finance: FinanceSection | None = None
    marketing: MarketingSection | None = None
    sales: SalesSection | None = None
    product: ProductSection | None = None
    crm: CRMSection | None = None
    funding: FundingSection | None = None

    # What the checks sent back, so a reader sees the plan was verified, not just produced.
    guardrail_rejections: list[str] = Field(default_factory=list)
    provenance: list[Provenance] = Field(default_factory=list)


# agent name in the decision records -> (FinalPlan field, section model)
_SECTIONS = {
    "intake": ("business", BusinessSection),
    "market_research": ("research", ResearchSection),
    "founder_advisor": ("verdict", VerdictSection),
    "company_formation": ("formation", FormationSection),
    "analytics": ("analytics", AnalyticsSection),
    "strategy": ("strategy", StrategySection),
    "finance": ("finance", FinanceSection),
    "marketing": ("marketing", MarketingSection),
    "sales": ("sales", SalesSection),
    "product": ("product", ProductSection),
    "crm": ("crm", CRMSection),
    "funding": ("funding", FundingSection),
}
_REJECTIONS = {"strategy_rejected": "Strategy", "funding_rejected": "Funding"}


def build_final_plan(run_id: int) -> FinalPlan:
    """The plan so far for a run: each agent's newest record in the latest planned cycle."""
    run = get_run(run_id) or {}
    records = fetch_records(run_id=run_id, as_json_text=False)

    planned_cycles = [r["cycle"] for r in records if r["cycle"] > 0]
    target = max(planned_cycles) if planned_cycles else 0

    newest: dict[str, dict] = {}
    counts: dict[str, int] = {}
    rejections: list[str] = []
    for record in records:  # oldest first, so a later record replaces an earlier one
        agent = record["agent"]
        if agent in _REJECTIONS:
            problems = (record.get("input_snapshot") or {}).get("problems") or []
            rejections.extend(f"{_REJECTIONS[agent]}: {p}" for p in problems)
            continue
        if record["cycle"] in (0, target):
            newest[agent] = record
            counts[agent] = counts.get(agent, 0) + 1

    sections: dict = {}
    provenance: list[Provenance] = []
    for agent, (field_name, model) in _SECTIONS.items():
        record = newest.get(agent)
        if record is None:
            continue
        data = dict(record["decision"] or {})
        if agent == "marketing":
            data["has_ad_image"] = bool(data.get("ad_image_path"))
            data.pop("ad_image_path", None)  # a server path means nothing to a reader
        if agent == "intake":
            data.pop("raw_input", None)
        sections[field_name] = model.model_validate(data)
        provenance.append(Provenance(agent=agent, saved_at=record["timestamp"], revised=counts[agent] > 1))

    business = sections.get("business")
    return FinalPlan(
        run_id=run_id,
        status=run.get("status") or "running",
        mode=run.get("mode"),
        label=run.get("label"),
        generated_at=datetime.now(timezone.utc).isoformat(),
        cycle=target,
        currency=business.currency if business else "INR",
        guardrail_rejections=rejections,
        provenance=provenance,
        **sections,
    )


# ---------------------------------------------------------------- Markdown --


def _table(headers: list[str], rows: list[list]) -> str:
    if not rows:
        return "_None._\n"
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(str(c).replace("|", "/").replace("\n", " ") for c in row) + " |")
    return "\n".join(lines) + "\n"


def _bullets(items: list) -> str:
    return "".join(f"- {item}\n" for item in items) if items else "_None._\n"


def to_markdown(plan: FinalPlan) -> str:
    """The plan as a Markdown document."""
    money = lambda amount: fmt_money(amount, plan.currency)  # noqa: E731
    out = [f"# {plan.label or 'Flywheel plan'}\n"]
    out.append(f"_Run {plan.run_id} · {plan.mode or 'plan'} · status: {plan.status} · generated {plan.generated_at[:19]}Z_\n")

    if plan.business:
        b = plan.business
        out.append(f"**Business:** {b.business_summary}  \n**Industry:** {b.industry} · **Region:** {b.target_region} · **Currency:** {b.currency}\n")

    if plan.verdict:
        out.append(f"## Verdict: {plan.verdict.verdict.replace('_', '-')}\n")
        out.append(_bullets(plan.verdict.rationale))
    if plan.research:
        r = plan.research
        out.append("## Market research\n")
        out.append(f"**Market size:** {r.market_size_estimate}\n\n**Competitors**\n\n{_bullets(r.key_competitors)}\n**Opportunities**\n\n{_bullets(r.opportunities)}\n**Risks**\n\n{_bullets(r.risks)}")
        if r.sources:
            out.append("**Sources**\n\n" + "".join(f"{i}. [{s.get('title') or s.get('url')}]({s.get('url')})\n" for i, s in enumerate(r.sources, 1)))
    if plan.formation:
        f = plan.formation
        out.append("## Company formation\n")
        out.append(f"**Recommended entity:** {f.recommended_entity} — {f.entity_rationale}\n\n**Registration steps**\n\n{_bullets(f.registration_steps)}\n**Licences and permits**\n\n{_bullets(f.licenses_and_permits)}\n**Tax registrations**\n\n{_bullets(f.tax_registrations)}\n_Cost: {f.estimated_cost} · Timeline: {f.estimated_timeline}_\n\n> {f.disclaimer}\n")
    if plan.analytics:
        a = plan.analytics
        out.append(f"## Analytics ({a.period_label})\n\n**{a.headline}**\n\n{_bullets(a.points)}")
    if plan.strategy:
        s = plan.strategy
        out.append("## Strategy\n")
        out.append(f"**Positioning:** {s.positioning}\n\n**Target customer:** {s.target_customer}\n\n**Price:** {money(s.price)} {s.price_unit}\n\n{_bullets(s.rationale)}")
    if plan.finance:
        fin = plan.finance
        out.append("## Budget\n")
        out.append(_table(["Area", "Amount", "Share"], [
            [name.title(), money(getattr(fin, name)), f"{getattr(fin, name) / fin.total_budget:.0%}" if fin.total_budget else "-"]
            for name in ("marketing", "product", "sales", "crm") if getattr(fin, name)
        ] + [["**Total**", money(fin.total_budget), ""]]))
        out.append(f"\n{fin.rationale}\n")
    if plan.marketing:
        m = plan.marketing
        out.append("## Marketing\n")
        out.append(_table(["Channel", "Where", "Format", "Objective", "Duration", "Spend"], [
            [c.get("channel", "-"), c.get("where", "-"), c.get("ad_format", "-"), c.get("objective", "-"), c.get("duration", "-"),
             money(c["budget"]) if c.get("budget") is not None else "-"]
            for c in m.campaigns
        ]))
        out.append(f"\n**Ad copy:** {m.ad_copy}\n")
    if plan.sales:
        out.append("## Sales\n")
        out.append(_table(["Where", "How", "Weekly actions", "Spend"], [
            [c.get("where", "-"), c.get("how", "-"), c.get("weekly_actions", "-"), money(c["budget"]) if c.get("budget") is not None else "-"]
            for c in plan.sales.lead_sources
        ]))
        out.append("\n**From lead to customer**\n\n" + "".join(f"{i}. {step}\n" for i, step in enumerate(plan.sales.conversion_process, 1)))
    if plan.product:
        p = plan.product
        out.append(f"## Product ({p.plan_type})\n")
        out.append(_table(["Item", "Units", "Unit cost", "Total"], [
            [i.get("item", "-"), f"{i.get('units', '-')} {i.get('unit', '')}".strip(), money(i["unit_cost"]) if i.get("unit_cost") is not None else "-",
             money(i["total_cost"]) if i.get("total_cost") is not None else "-"]
            for i in p.line_items
        ]))
        out.append(f"\n**Sourcing**\n\n{_bullets(p.sourcing_plan)}\n**Replenishment**\n\n{_bullets(p.replenish_policy)}")
    if plan.crm:
        c = plan.crm
        out.append("## Customer retention\n")
        groups = (c.segments or {}).get("segments") or {}
        out.append(_table(["Group", "Customers", "Share of revenue", "Action", "Spend"], [
            [(groups.get(g) or {}).get("label", g), (groups.get(g) or {}).get("customers", "-"),
             f"{(groups.get(g) or {}).get('revenue_share', 0):.0%}" if groups.get(g) else "-", c.actions.get(g, "-"), money(c.spend.get(g, 0.0))]
            for g in c.actions
        ]))
        if c.slipping_message:
            out.append(f"\n**Message to slipping customers:** {c.slipping_message}\n")
        out.extend(f"\n> {w}\n" for w in c.warnings)
    if plan.funding:
        fu = plan.funding
        out.append("## Funding roadmap\n")
        out.append(f"**Readiness:** {fu.readiness}\n\n{_bullets(fu.readiness_rationale)}\n**Target:** {fu.target_stage} by {fu.target_raise_date}\n\n**Revenue milestone:** {fu.revenue_milestone}\n\n**Traction milestones**\n\n{_bullets(fu.traction_milestones)}")

    if plan.guardrail_rejections:
        out.append("## Checks that sent a draft back\n\n" + _bullets(plan.guardrail_rejections))
    out.append("## Provenance\n\n" + _table(["Agent", "Saved at (UTC)", "Revised"], [[p.agent, p.saved_at[:19], "yes" if p.revised else ""] for p in plan.provenance]))
    return "\n".join(out)
