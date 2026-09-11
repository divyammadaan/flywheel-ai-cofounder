import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from agents.finance import FinanceAgent, MAX_SHARE_PER_AGENT


def test_allocation_respects_total_budget():
    finance = FinanceAgent(total_budget_per_cycle=1000.0)
    allocation = finance.allocate(1, {"marketing": 0.4, "product": 0.3, "sales": 0.2, "crm": 0.1})
    spent = allocation.marketing + allocation.product + allocation.sales + allocation.crm
    assert spent <= allocation.total_budget


def test_allocation_respects_guardrail_cap():
    finance = FinanceAgent(total_budget_per_cycle=1000.0)
    # Strategy asks to dump everything into marketing; guardrail should cap it.
    allocation = finance.allocate(1, {"marketing": 1.0, "product": 0.0, "sales": 0.0, "crm": 0.0})
    assert allocation.marketing <= 1000.0 * MAX_SHARE_PER_AGENT + 1e-6


def test_invalid_allocation_raises():
    with pytest.raises(ValueError):
        from agents.finance import BudgetAllocation
        BudgetAllocation(cycle=1, total_budget=100.0, marketing=80.0, product=80.0, sales=0.0, crm=0.0)
