"""Product agent — what the business needs in order to deliver, and where it
comes from. The plan depends on what the business sells:

  physical goods     inventory: what stock to buy up front, from whom, when to reorder
  service/software   capacity: the tools, equipment, subscriptions and hires needed
                     to deliver, where to get them, and when to add more

Runs concurrently with Marketing/Sales (and CRM for existing businesses).

The model proposes line items (item, units, unit cost). Line totals and the
plan total are then computed in plain Python (price_line_items): a model's
multiplication isn't trusted, and if the plan costs more than Product's
allocation the quantities are cut to fit rather than silently overspending.
"""

from dataclasses import dataclass

from crewai import LLM, Agent, Crew, Task
from pydantic import BaseModel, Field

from agents._brief import LAUNCH, PlanBrief
from agents._models import AGENT_MODELS
from agents._money import fit_to_budget
from agents._retry import retry_on_rate_limit

DEFAULT_MODEL = AGENT_MODELS["product"]

INVENTORY = "inventory"
CAPACITY = "capacity"


class StockItem(BaseModel):
    item: str = Field(description="What to buy, specifically, e.g. 'roasted Chikmagalur arabica in 250g valve bags'")
    units: int = Field(description="How many units to buy up front")
    unit: str = Field(description="The unit, e.g. '250g bag', 'kg', 'carton of 100'")
    unit_cost: float = Field(description="Cost per unit in the plan currency")


class CapacityItem(BaseModel):
    item: str = Field(
        description="A tool, piece of equipment, subscription or hire needed to deliver, e.g. 'Canva Pro team plan', 'part-time stylist'"
    )
    units: int = Field(description="How many: seats, machines, people or months")
    unit: str = Field(description="The unit, e.g. 'seat per month', 'chair', 'part-time hire per month'")
    unit_cost: float = Field(description="Cost per unit in the plan currency")


class InventoryPlanSchema(BaseModel):
    line_items: list[StockItem] = Field(description="1-5 line items: stock, packaging, equipment")
    sourcing_plan: str = Field(
        description="Who to source from and where (supplier type and region), payment terms and lead time"
    )
    replenish_policy: str = Field(description="When to reorder and how much")
    cost_basis: str = Field(
        description="Where the unit costs come from: the founder's own figures, or clearly labelled estimates"
    )


class CapacityPlanSchema(BaseModel):
    line_items: list[CapacityItem] = Field(
        description="1-5 line items: the tools, equipment, subscriptions or hires needed to deliver"
    )
    sourcing_plan: str = Field(description="Which vendors or where to hire from, with terms")
    replenish_policy: str = Field(
        description="When to add capacity, e.g. 'hire a second stylist once bookings pass 60 a week'"
    )
    cost_basis: str = Field(
        description="Where the unit costs come from: the founder's own figures, or clearly labelled estimates"
    )


@dataclass
class ProductOutput:
    cycle: int
    budget: float
    currency: str
    plan_type: str
    line_items: list
    line_items_total: float
    sourcing_plan: str
    replenish_policy: str
    cost_basis: str
    budget_adjusted: bool = False


def plan_type_for(offering_type: str) -> str:
    return INVENTORY if offering_type == "physical" else CAPACITY


def price_line_items(items: list[dict], budget: float) -> tuple[list[dict], float, bool]:
    """Price a plan's line items in code and make them fit the budget.

    Line totals are units x unit_cost, computed here. If the plan costs more
    than the budget, each line is scaled down proportionally and rounded DOWN
    to whole units, so the plan never exceeds the budget.

    Returns (lines with total_cost, plan_total, adjusted).
    """
    clean = [
        {**i, "units": max(int(i["units"]), 0), "unit_cost": max(float(i["unit_cost"]), 0.0)} for i in items
    ]
    allowed, adjusted = fit_to_budget([i["units"] * i["unit_cost"] for i in clean], budget)

    priced = []
    for item, limit in zip(clean, allowed):
        units = item["units"]
        if adjusted and item["unit_cost"] > 0:
            units = min(units, int(limit // item["unit_cost"]))
        priced.append({**item, "units": units, "total_cost": round(units * item["unit_cost"], 2)})
    return priced, round(sum(p["total_cost"] for p in priced), 2), adjusted


class ProductAgent:
    """CrewAI agent backed by Groq -- inventory or delivery capacity, grounded
    in the shared PlanBrief."""

    def __init__(self, model: str = DEFAULT_MODEL):
        llm = LLM(model=model)
        self._agent = Agent(
            role="Product & Operations Lead",
            goal="Plan exactly what the business needs to deliver, from whom, and when to add more",
            backstory=(
                "You run product and operations for a lean startup. You plan like someone paying "
                "for it: specific items, quantities, unit costs and suppliers, sized so cash isn't "
                "locked up in stock or tools the business won't use yet. If the founder gave you "
                "costs you use them; otherwise you say plainly that your costs are estimates."
            ),
            llm=llm,
            verbose=False,
        )

    @retry_on_rate_limit()
    def execute(self, brief: PlanBrief, budget: float) -> ProductOutput:
        plan_type = plan_type_for(brief.offering_type)
        stage = (
            "This is before launch: size it for the first weeks, not a full year."
            if brief.mode == LAUNCH
            else "Size it for the next period from the reported numbers (customers, revenue)."
        )
        if plan_type == INVENTORY:
            schema, ask = InventoryPlanSchema, "Plan the opening inventory: 1-5 stock line items, sourcing and reordering."
        else:
            schema, ask = (
                CapacityPlanSchema,
                "This business delivers a service or software, so plan delivery capacity, not stock: "
                "1-5 line items for tools, equipment, subscriptions or hires, where to get them, and "
                "when to add capacity.",
            )
        task = Task(
            description=(
                f"{brief.describe(budget, 'Product budget')}\n\n"
                f"{ask} {stage}\nState your cost basis. BE CONCISE: every text field under ~40 words."
            ),
            expected_output="A JSON object matching the required schema.",
            agent=self._agent,
            output_pydantic=schema,
        )
        crew = Crew(agents=[self._agent], tasks=[task], verbose=False)
        crew.kickoff()
        parsed = task.output.pydantic

        lines, total, adjusted = price_line_items([i.model_dump() for i in parsed.line_items], budget)

        return ProductOutput(
            cycle=brief.cycle,
            budget=budget,
            currency=brief.currency,
            plan_type=plan_type,
            line_items=lines,
            line_items_total=total,
            sourcing_plan=parsed.sourcing_plan,
            replenish_policy=parsed.replenish_policy,
            cost_basis=parsed.cost_basis,
            budget_adjusted=adjusted,
        )
