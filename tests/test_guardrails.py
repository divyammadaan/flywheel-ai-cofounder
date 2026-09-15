"""The checks every Strategy plan and Funding roadmap must pass. The failing
examples are taken from real runs."""

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents._guardrails import (
    clean_text_fields,
    crm_output_problems,
    demeaning_terms,
    funding_problems,
    money_amounts,
    strategy_problems,
    strip_tool_markup,
)

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


def _roadmap(**overrides):
    base = dict(
        readiness="NOT_READY",
        target_stage="Pre-seed, ₹1.5–2.5 crore",
        revenue_milestone="₹15 lakh monthly recurring revenue",
        traction_milestones="1,500 active subscribers with churn under 6%",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


# ------------------------------------------------------------- strategy --


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


# ------------------------------------------------------------------ crm --

_GROUPS = ("best_customers", "regulars", "new_customers", "slipping", "lost")


def test_a_placeholder_crm_reply_is_caught():
    # Exactly what the local model returned in one live run.
    reply = {f"{g}_action": f"Action for {g.replace('_', ' ')}" for g in _GROUPS}
    reply |= {f"{g}_spend": 0.0 for g in _GROUPS}
    reply |= {"slipping_message": "Hi {name}, message for slipping away", "lost_message": "message for lost customers"}
    assert len(crm_output_problems(reply)) == 3


def test_a_real_crm_reply_passes():
    reply = {f"{g}_action": "Call them personally this week with a tasting invite" for g in _GROUPS}
    reply |= {f"{g}_spend": 1500.0 for g in _GROUPS}
    reply |= {"slipping_message": "Hi {name}, we roasted a fresh batch this week.", "lost_message": "Hi {name}, we miss you!"}
    assert crm_output_problems(reply) == []


# ---------------------------------------------------------- tool markup --


def test_leaked_tool_call_markup_is_cut_off():
    # Taken from a live Sales run.
    leaked = '1) Share a Rs 199 trial offer. 2) Call to confirm.\n<parameter name="lead_sources">[{"where": "HSR"}]'
    assert strip_tool_markup(leaked) == "1) Share a Rs 199 trial offer. 2) Call to confirm."


def test_clean_text_fields_reaches_nested_values_and_leaves_numbers_alone():
    value = {"steps": "Call them. </parameter>", "sources": [{"how": "Visit. <function=x>"}], "budget": 144000.0}
    assert clean_text_fields(value) == {"steps": "Call them.", "sources": [{"how": "Visit."}], "budget": 144000.0}


# -------------------------------------------------------------- funding --


def test_money_amounts_understand_indian_units_and_ranges():
    assert money_amounts("Pre-Seed, ₹3–7 crore") == [(3e7, 7e7)]
    assert money_amounts("Rs 8 lakh MRR") == [(8e5, 8e5)]
    assert money_amounts("(₹3,00,00,000 – ₹7,00,00,000)") == [(3e7, 7e7)]


def test_a_consistent_roadmap_passes():
    assert funding_problems(_roadmap(), "INR", price=999) == []


def test_an_oversized_pre_seed_round_is_caught():
    problems = funding_problems(_roadmap(target_stage="Pre-Seed, ₹3–7 crore on a SAFE"), "INR", price=999)
    assert any("far above the usual size" in p for p in problems)


def test_traction_that_cannot_produce_the_revenue_milestone_is_caught():
    problems = funding_problems(_roadmap(traction_milestones="80–100 paying subscribers before the round"), "INR", price=999)
    assert any("doesn't match the revenue milestone" in p for p in problems)
