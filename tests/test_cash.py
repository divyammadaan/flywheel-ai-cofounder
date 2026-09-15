import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents._cash import launch_cash_plan, operating_cash_position


def test_launch_holds_back_a_reserve_and_computes_break_even():
    plan = launch_cash_plan(capital=1_500_000, price=799, monthly_fixed_costs=100_000, unit_cost=350, runway_months=6)
    assert plan["reserve"] == 600_000
    assert plan["launch_budget"] == 900_000
    assert plan["contribution_margin"] == 449
    assert plan["break_even_units_per_month"] == 223  # 100,000 / 449 rounded up
    assert plan["warnings"] == []


def test_launch_without_fixed_costs_reserves_nothing_and_says_so():
    plan = launch_cash_plan(capital=1_000_000, price=799, unit_cost=350)
    assert plan["reserve"] == 0
    assert plan["launch_budget"] == 1_000_000
    assert plan["break_even_units_per_month"] is None
    assert any("fixed costs" in w for w in plan["warnings"])


def test_launch_without_unit_cost_cannot_compute_break_even():
    plan = launch_cash_plan(capital=1_000_000, price=799, monthly_fixed_costs=50_000)
    assert plan["contribution_margin"] is None
    assert any("Cost per unit" in w for w in plan["warnings"])


def test_price_below_cost_is_flagged():
    plan = launch_cash_plan(capital=1_000_000, price=300, monthly_fixed_costs=50_000, unit_cost=350)
    assert plan["break_even_units_per_month"] is None
    assert any("loses money" in w for w in plan["warnings"])


def test_reserve_never_exceeds_capital():
    plan = launch_cash_plan(capital=300_000, price=799, monthly_fixed_costs=100_000, unit_cost=350)
    assert plan["reserve"] == 300_000
    assert plan["launch_budget"] == 0
    assert any("uses all the capital" in w for w in plan["warnings"])


def test_loss_making_business_gets_a_runway():
    pos = operating_cash_position(
        revenue=1_200_000, net_profit=-240_000, total_debt=300_000, budget=50_000, period_months=12, cash_in_bank=100_000
    )
    assert pos["monthly_net_profit"] == -20_000
    assert pos["runway_months"] == 5.0
    assert pos["debt_to_annual_revenue"] == 0.25
    assert any("about 5.0 months" in w for w in pos["warnings"])


def test_profitable_business_has_no_runway_limit():
    pos = operating_cash_position(revenue=1_200_000, net_profit=120_000, total_debt=0, budget=50_000, cash_in_bank=500_000)
    assert pos["profitable"] is True
    assert pos["runway_months"] is None


def test_monthly_period_is_annualised_for_debt():
    pos = operating_cash_position(revenue=100_000, net_profit=10_000, total_debt=900_000, budget=10_000, period_months=1)
    assert pos["annualised_revenue"] == 1_200_000
    assert pos["debt_to_annual_revenue"] == 0.75
    assert any("half a year" in w for w in pos["warnings"])


def test_budget_above_cash_and_missing_cash_are_flagged():
    over = operating_cash_position(revenue=1, net_profit=0, total_debt=0, budget=200_000, cash_in_bank=100_000)
    assert any("more than the cash" in w for w in over["warnings"])
    unknown = operating_cash_position(revenue=1, net_profit=-5, total_debt=0, budget=1)
    assert unknown["runway_months"] is None
    assert any("Cash in bank not given" in w for w in unknown["warnings"])
