"""Cash math for the Finance agent: reserve, runway, break-even.

Plain arithmetic on numbers the founder gave. Anything that needs a missing
input comes back as None, with a warning naming the input that would unlock
it -- nothing is estimated.
"""

import math

DEFAULT_RUNWAY_MONTHS = 6
SHORT_RUNWAY_MONTHS = 6  # warn below this much runway
HIGH_DEBT_TO_REVENUE = 0.5  # warn when debt exceeds half a year's revenue


def launch_cash_plan(
    capital: float,
    price: float,
    monthly_fixed_costs: float | None = None,
    unit_cost: float | None = None,
    runway_months: int = DEFAULT_RUNWAY_MONTHS,
) -> dict:
    """How much of the capital can go into the launch, and what break-even takes.

    Fixed costs x runway months is held back as a reserve, so the launch can't
    spend the money needed to keep the lights on. Break-even is the number of
    units a month whose margin covers the fixed costs.
    """
    warnings = []

    if monthly_fixed_costs is None:
        reserve = 0.0
        warnings.append("Monthly fixed costs not given, so no cash is held back for running costs.")
    else:
        reserve = min(capital, monthly_fixed_costs * runway_months)
        if reserve >= capital:
            warnings.append(
                f"{runway_months} months of fixed costs uses all the capital, so nothing is left for the launch."
            )

    margin = break_even = None
    if unit_cost is None:
        warnings.append("Cost per unit not given, so break-even can't be calculated.")
    else:
        margin = round(price - unit_cost, 2)
        if margin <= 0:
            warnings.append("The price doesn't cover the cost per unit, so every sale loses money.")
        elif monthly_fixed_costs is not None:
            break_even = math.ceil(monthly_fixed_costs / margin)

    return {
        "capital": round(capital, 2),
        "monthly_fixed_costs": monthly_fixed_costs,
        "runway_months_reserved": runway_months if monthly_fixed_costs is not None else None,
        "reserve": round(reserve, 2),
        "launch_budget": round(capital - reserve, 2),
        "price": price,
        "unit_cost": unit_cost,
        "contribution_margin": margin,
        "break_even_units_per_month": break_even,
        "warnings": warnings,
    }


def operating_cash_position(
    revenue: float,
    net_profit: float,
    total_debt: float,
    budget: float,
    period_months: int = 12,
    cash_in_bank: float | None = None,
) -> dict:
    """Runway, debt load and whether next period's budget is affordable."""
    warnings = []
    months = max(int(period_months), 1)
    monthly_net = round(net_profit / months, 2)
    annual_revenue = revenue * 12 / months

    runway = None
    if cash_in_bank is None:
        warnings.append("Cash in bank not given, so runway can't be calculated.")
    elif monthly_net < 0:
        runway = round(cash_in_bank / -monthly_net, 1)
        if runway < SHORT_RUNWAY_MONTHS:
            warnings.append(f"At the current loss rate, cash lasts about {runway} months.")

    debt_ratio = round(total_debt / annual_revenue, 4) if annual_revenue else None
    if debt_ratio is not None and debt_ratio > HIGH_DEBT_TO_REVENUE:
        warnings.append("Debt is more than half a year's revenue.")

    budget_share = round(budget / cash_in_bank, 4) if cash_in_bank else None
    if cash_in_bank is not None and budget > cash_in_bank:
        warnings.append("Next period's budget is more than the cash in the bank.")

    return {
        "period_months": months,
        "monthly_net_profit": monthly_net,
        "profitable": net_profit >= 0,
        "runway_months": runway,
        "annualised_revenue": round(annual_revenue, 2),
        "debt_to_annual_revenue": debt_ratio,
        "budget_share_of_cash": budget_share,
        "warnings": warnings,
    }
