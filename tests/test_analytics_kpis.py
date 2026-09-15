"""Tests for the ratios Analytics computes from a founder's reported numbers.

The rule under test: every ratio comes from numbers the founder gave, and a
ratio whose inputs weren't given is None -- never an estimate."""

import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.analytics import PeriodMetrics, compute_kpis, describe_file_metrics, describe_period


def _metrics(**overrides) -> PeriodMetrics:
    base = dict(period_label="FY2025-26", revenue=4_000_000, net_profit=400_000, total_debt=1_000_000)
    base.update(overrides)
    return PeriodMetrics(**base)


def test_ratios_come_from_the_reported_numbers():
    k = compute_kpis(
        _metrics(ebitda=600_000, marketing_spend=200_000, new_customers=400, customers_at_start=1000, customers_lost=100)
    )
    assert k["net_margin"] == 0.1
    assert k["ebitda_margin"] == 0.15
    assert k["debt_to_revenue"] == 0.25
    assert k["cac"] == 500.0
    assert k["churn_rate"] == 0.1
    assert k["customers_at_end"] == 1300
    assert k["revenue_per_customer"] == round(4_000_000 / 1300, 4)


def test_unreported_inputs_give_none_never_a_guess():
    k = compute_kpis(_metrics())
    for key in ("ebitda_margin", "cac", "churn_rate", "customers_at_end", "revenue_per_customer"):
        assert k[key] is None


def test_zero_revenue_does_not_divide_by_zero():
    k = compute_kpis(_metrics(revenue=0, net_profit=-50_000))
    assert k["net_margin"] is None
    assert k["debt_to_revenue"] is None


def test_debt_ratio_uses_a_year_of_revenue_for_shorter_periods():
    assert compute_kpis(_metrics(revenue=100_000, total_debt=600_000, period_months=1))["debt_to_revenue"] == 0.5


def test_description_uses_the_currency_and_marks_gaps_as_not_reported():
    m = _metrics()
    text = describe_period(asdict(m), compute_kpis(m), "INR")
    assert "₹4,000,000" in text
    assert "not reported" in text


def test_file_metrics_description_uses_the_currency_and_trend():
    fm = {
        "first_order": "2026-01-01", "last_order": "2026-08-31", "orders": 10, "customers": 4,
        "revenue": 8000.0, "average_order_value": 800.0, "repeat_customer_rate": 0.5,
        "revenue_change_last_3m_vs_prior_3m": 0.1, "monthly_revenue": {"2026-08": 1000.0},
    }
    text = describe_file_metrics(fm, "INR")
    assert "₹8,000" in text
    assert "+10%" in text
