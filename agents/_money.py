"""Money helpers shared by every agent that plans spend.

Two jobs, both deliberately plain Python rather than left to a model:

1. Formatting. Amounts are always shown in the founder's own currency.
   Hardcoding "$" everywhere is what put "Rs 799/month" prose next to
   "$1,000" budgets in the same Decision Record.

2. Keeping line items inside a budget. Marketing, Sales and Product each
   break their allocation into items with amounts. Models are unreliable at
   arithmetic and sometimes overspend, so -- like Finance's per-area cap --
   the check that items fit happens here, in code, whatever the model returns.
"""

import math

CURRENCY_SYMBOLS = {"INR": "₹", "USD": "$", "EUR": "€", "GBP": "£"}
SUPPORTED_CURRENCIES = tuple(CURRENCY_SYMBOLS)


def fmt_money(amount: float | None, currency: str) -> str:
    """'₹1,500,000' / '$12.50'. Missing amounts show as a dash, never as 0."""
    if amount is None:
        return "—"
    # Sign before the symbol: "-₹15,000", not "₹-15,000".
    sign = "-" if amount < 0 else ""
    value = abs(amount)
    digits = f"{value:,.0f}" if value >= 100 else f"{value:,.2f}"
    symbol = CURRENCY_SYMBOLS.get(currency)
    return f"{sign}{symbol}{digits}" if symbol else f"{sign}{currency} {digits}"


def fit_to_budget(amounts: list[float], budget: float) -> tuple[list[float], bool]:
    """Scale amounts down proportionally so they sum to at most `budget`.

    Returns (amounts, adjusted). Negative amounts count as zero. When scaling
    is needed, each amount is rounded DOWN to 2 decimals, so rounding can
    never push the total back over the budget.
    """
    cleaned = [max(float(a), 0.0) for a in amounts]
    total = sum(cleaned)
    if total <= budget + 1e-6:
        rounded = [round(a, 2) for a in cleaned]
        if sum(rounded) <= budget + 1e-6:
            return rounded, False
    scale = min(1.0, budget / total) if total else 0.0
    return [math.floor(a * scale * 100 + 1e-9) / 100 for a in cleaned], True
