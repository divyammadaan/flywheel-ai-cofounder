import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from agents.finance import BudgetAllocation, MAX_SHARE_PER_AGENT, compute_capped_allocation


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
