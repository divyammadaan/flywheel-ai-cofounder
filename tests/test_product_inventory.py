"""Tests for the Product agent's plan pricing -- the code that computes line
totals and keeps a plan inside its budget. No LLM involved."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.product import CAPACITY, INVENTORY, plan_type_for, price_line_items


def _item(name, units, unit_cost, unit="unit"):
    return {"item": name, "units": units, "unit": unit, "unit_cost": unit_cost}


def test_line_totals_are_computed_in_code():
    priced, total, adjusted = price_line_items([_item("coffee", 300, 180.0, "250g bag")], 100000)
    assert priced[0]["total_cost"] == 54000.0
    assert total == 54000.0
    assert adjusted is False


def test_a_plan_over_budget_is_cut_to_whole_units_that_fit():
    items = [_item("coffee", 1000, 180.0), _item("boxes", 1000, 20.0)]
    priced, total, adjusted = price_line_items(items, 100000)
    assert adjusted is True
    assert total <= 100000
    assert all(isinstance(p["units"], int) for p in priced)
    assert priced[0]["units"] < 1000


def test_free_items_are_kept_when_the_plan_is_scaled():
    items = [_item("samples", 50, 0.0), _item("coffee", 1000, 180.0)]
    priced, total, adjusted = price_line_items(items, 90000)
    assert adjusted is True
    assert total <= 90000
    assert priced[0]["units"] == 50


def test_negative_quantities_from_the_model_are_treated_as_zero():
    priced, total, _ = price_line_items([_item("coffee", -10, 180.0)], 1000)
    assert priced[0]["units"] == 0
    assert total == 0


def test_only_physical_goods_get_an_inventory_plan():
    assert plan_type_for("physical") == INVENTORY
    assert plan_type_for("service") == CAPACITY
    assert plan_type_for("software") == CAPACITY
