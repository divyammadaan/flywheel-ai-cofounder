import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from agents.finance import BudgetAllocation, MAX_SHARE_PER_AGENT, compute_capped_allocation, explain_allocation


def test_allocation_respects_total_budget():
    amounts = compute_capped_allocation(1000.0, {"marketing": 0.4, "product": 0.3, "sales": 0.2, "crm": 0.1})
    assert sum(amounts.values()) <= 1000.0


def test_allocation_respects_guardrail_cap():
    # Strategy asks to dump everything into marketing; guardrail should cap it.
    amounts = compute_capped_allocation(1000.0, {"marketing": 1.0, "product": 0.0, "sales": 0.0, "crm": 0.0})
    assert amounts["marketing"] <= 1000.0 * MAX_SHARE_PER_AGENT + 1e-6


def test_invalid_allocation_raises():
    with pytest.raises(ValueError):
        BudgetAllocation(cycle=1, total_budget=100.0, marketing=80.0, product=80.0, sales=0.0, crm=0.0)


def test_valid_allocation_from_computed_amounts():
    amounts = compute_capped_allocation(1000.0, {"marketing": 0.4, "product": 0.3, "sales": 0.2, "crm": 0.1})
    allocation = BudgetAllocation(cycle=1, total_budget=1000.0, **amounts)
    assert allocation.marketing == amounts["marketing"]


# The explanation used to be an LLM call; it's now written from the numbers.


def test_explanation_states_the_split_and_the_main_cash_risk():
    priorities = {"marketing": 0.2, "product": 0.5, "sales": 0.3, "crm": 0.0}
    amounts = compute_capped_allocation(960_000, priorities)
    health = {"launch_budget": 960_000, "break_even_units_per_month": 137, "contribution_margin": 659, "warnings": []}
    text = explain_allocation(960_000, priorities, amounts, health, "INR")
    assert "₹960,000" in text
    assert "product ₹480,000 (50%)" in text
    assert "137 units a month" in text


def test_explanation_mentions_a_capped_area_and_what_is_left():
    priorities = {"marketing": 1.0, "product": 0.0, "sales": 0.0, "crm": 0.0}
    text = explain_allocation(100_000, priorities, compute_capped_allocation(100_000, priorities), {}, "INR")
    assert "capped" in text
    assert "₹40,000 unallocated" in text


def test_a_cash_warning_is_the_risk_that_gets_mentioned():
    priorities = {"marketing": 0.5, "sales": 0.5}
    health = {"warnings": ["At the current loss rate, cash lasts about 3.0 months."], "profitable": False}
    text = explain_allocation(1000, priorities, compute_capped_allocation(1000, priorities), health, "INR")
    assert text.endswith("cash lasts about 3.0 months.")
