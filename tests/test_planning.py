"""Which agents plan for which business, and what context each one gets --
the rules that keep every agent tied to a real use case and every prompt lean."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents._brief import EXISTING, LAUNCH
from agents.intake import _offering_type
from orchestration.cycle import AGENT_CONTEXT, join_context, planning_areas

SECTIONS = {
    key: key.upper()
    for key in ("capital_costs", "research", "founder_answers", "advisor", "numbers", "analytics", "orders", "segments")
}


def test_a_launch_plan_has_no_crm_because_there_are_no_customers():
    assert "crm" not in planning_areas(LAUNCH, has_orders=True)


def test_an_existing_business_gets_crm_only_with_uploaded_orders():
    assert "crm" in planning_areas(EXISTING, has_orders=True)
    assert "crm" not in planning_areas(EXISTING, has_orders=False)


def test_offering_type_is_normalised():
    assert _offering_type("Physical") == "physical"
    assert _offering_type("SaaS platform") == "software"
    assert _offering_type("consulting services") == "service"
    assert _offering_type("apparel") == "physical"


def test_each_planning_agent_gets_only_the_context_it_uses():
    product = join_context(SECTIONS, AGENT_CONTEXT["product"])
    assert "CAPITAL_COSTS" in product and "RESEARCH" not in product
    assert "RESEARCH" in join_context(SECTIONS, AGENT_CONTEXT["marketing"])
    assert join_context(SECTIONS, AGENT_CONTEXT["crm"]) == "ANALYTICS"


def test_strategy_sees_every_section():
    full = join_context(SECTIONS)
    assert all(value in full for value in SECTIONS.values())


def test_empty_sections_are_left_out():
    assert join_context({"research": "R", "analytics": ""}, ("research", "analytics", "orders")) == "R"
