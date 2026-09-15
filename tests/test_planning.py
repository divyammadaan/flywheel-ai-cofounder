"""Which agents plan for which business -- the rules that keep every agent
tied to a real use case."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents._brief import EXISTING, LAUNCH
from agents.intake import _offering_type
from orchestration.cycle import planning_areas


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
