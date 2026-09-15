"""The checks every Strategy plan must pass before other agents use it.
The failing examples are taken from a real run."""

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents._guardrails import demeaning_terms, strategy_problems

COFFEE = SimpleNamespace(product_or_service="filter coffee subscriptions", currency="INR")


def _plan(**overrides):
    base = dict(
        positioning="Farm-direct filter coffee from Chikmagalur, roasted to order and delivered monthly",
        target_customer="Professionals aged 25-40 in Indiranagar, Koramangala and HSR Layout",
        price=899.0,
        price_unit="per month, 1kg subscription",
        rationale="Stays under the Rs 900 customers said they would pay.",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_a_sound_plan_passes():
    assert strategy_problems(_plan(), COFFEE, reference_price=960) == []


def test_demeaning_wording_is_caught():
    plan = _plan(target_customer="Dual-income families (excluding slum communities like Koramangala, HSR Layout)")
    problems = strategy_problems(plan, COFFEE)
    assert any("demeaning" in p for p in problems)
    assert demeaning_terms("low-class areas and ghettos") == ["ghettos", "low-class"]


def test_a_plan_about_a_different_product_is_caught():
    plan = _plan(positioning="Premium, ingredient-traceable Indian grocery box for urban households", rationale="")
    assert any("doesn't describe what this business actually sells" in p for p in strategy_problems(plan, COFFEE))


def test_imperial_units_are_caught_for_an_indian_business_only():
    plan = _plan(price_unit="per 4 lb monthly subscription box")
    assert any("imperial" in p for p in strategy_problems(plan, COFFEE))
    us_coffee = SimpleNamespace(product_or_service="filter coffee subscriptions", currency="USD")
    assert not any("imperial" in p for p in strategy_problems(plan, us_coffee))


def test_a_price_far_from_what_customers_pay_is_caught():
    assert any("far from" in p for p in strategy_problems(_plan(price=4999), COFFEE, reference_price=960))
    assert not any("far from" in p for p in strategy_problems(_plan(price=1499), COFFEE, reference_price=960))
