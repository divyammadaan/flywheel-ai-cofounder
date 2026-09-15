import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents._money import fit_to_budget, fmt_money


def test_fmt_money_uses_the_founders_currency_symbol():
    assert fmt_money(1500000, "INR") == "₹1,500,000"
    assert fmt_money(799, "USD") == "$799"


def test_fmt_money_keeps_decimals_on_small_amounts():
    assert fmt_money(12.5, "INR") == "₹12.50"


def test_fmt_money_falls_back_to_the_code_for_unknown_currencies():
    assert fmt_money(2500, "AED") == "AED 2,500"


def test_fmt_money_puts_the_minus_sign_before_the_symbol():
    assert fmt_money(-15000, "INR") == "-₹15,000"
    assert fmt_money(-2500, "AED") == "-AED 2,500"


def test_fmt_money_shows_a_missing_amount_as_a_dash_not_zero():
    assert fmt_money(None, "INR") == "—"


def test_fit_to_budget_leaves_items_alone_when_they_fit():
    amounts, adjusted = fit_to_budget([80000, 70000, 50000], 200000)
    assert amounts == [80000, 70000, 50000]
    assert adjusted is False


def test_fit_to_budget_scales_overspend_down_keeping_proportions():
    amounts, adjusted = fit_to_budget([150000, 100000], 200000)
    assert adjusted is True
    assert sum(amounts) <= 200000
    assert amounts == [120000, 80000]


def test_fit_to_budget_never_rounds_back_over_the_budget():
    amounts, _ = fit_to_budget([1, 1, 1], 1)
    assert sum(amounts) <= 1


def test_fit_to_budget_treats_negative_amounts_as_zero():
    amounts, adjusted = fit_to_budget([-500, 300], 1000)
    assert amounts == [0, 300]
    assert adjusted is False
