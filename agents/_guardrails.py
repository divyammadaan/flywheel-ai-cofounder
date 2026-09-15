"""Checks on model output that must hold whatever the model says.

Strategy's plan feeds every other agent, so a plan that describes the wrong
business, prices in the wrong units, or talks about people and places in
demeaning terms is rejected here and sent back once for a fix. In testing,
Strategy described a filter-coffee subscription as an "Indian grocery box"
priced "per 4 lb", and targeted families "excluding slum communities like
Koramangala" -- none of which may reach a founder.

These are deliberately simple, explainable rules rather than another model
call: they are fast, testable, and can't be talked out of their answer.
"""

import re

_DEMEANING = re.compile(
    r"\b(slums?|ghettos?|shanty ?towns?|low[- ]?class|lower[- ]class|uncivili[sz]ed|"
    r"backward (?:areas?|people|communit(?:y|ies)))\b",
    re.IGNORECASE,
)
_IMPERIAL_UNITS = re.compile(r"\b(lbs?|pounds?|oz|ounces?)\b", re.IGNORECASE)

# Words too generic to show a plan is about THIS business's product.
_GENERIC_WORDS = {
    "subscription", "subscriptions", "service", "services", "product", "products", "delivery", "deliveries",
    "online", "store", "stores", "shop", "shops", "platform", "business", "company", "brand", "home", "homes",
    "based", "premium", "fresh", "local", "custom", "made", "order",
}
MAX_PRICE_RATIO = 3.0


def demeaning_terms(text: str) -> list[str]:
    return sorted({m.group(0).lower() for m in _DEMEANING.finditer(text or "")})


def _word_stems(text: str) -> set[str]:
    # First five letters, so "subscription"/"subscriptions" and "cake"/"cakes" match.
    return {w[:5] for w in re.findall(r"[a-z]{4,}", (text or "").lower())}


def strategy_problems(plan, business, reference_price: float | None = None) -> list[str]:
    """What's wrong with a Strategy plan, in words the model can act on.

    `plan` needs positioning, target_customer, price, price_unit, rationale;
    `business` needs product_or_service and currency. `reference_price` is
    what customers are known to pay (average order, or the advisor's seed
    price), if known.
    """
    problems = []
    text = " ".join(
        str(getattr(plan, field, "") or "") for field in ("positioning", "target_customer", "price_unit", "rationale")
    )

    bad = demeaning_terms(text)
    if bad:
        problems.append(
            f"It describes people or places in demeaning terms ({', '.join(bad)}). Describe customers by "
            "what they want and can afford, never with stereotypes about areas or communities."
        )

    product_words = [
        w for w in re.findall(r"[a-z]{4,}", (business.product_or_service or "").lower()) if w not in _GENERIC_WORDS
    ]
    if product_words and not ({w[:5] for w in product_words} & _word_stems(text)):
        problems.append(f"It doesn't describe what this business actually sells ({business.product_or_service}).")

    if business.currency == "INR" and _IMPERIAL_UNITS.search(f"{plan.price_unit} {plan.positioning}"):
        problems.append("It uses imperial units (lb/oz). This business is in India, so use grams, kg or ml.")

    if not plan.price or plan.price <= 0:
        problems.append("The price must be above zero.")
    elif reference_price:
        ratio = plan.price / reference_price
        if ratio > MAX_PRICE_RATIO or ratio < 1 / MAX_PRICE_RATIO:
            problems.append(
                f"The price ({plan.price:,.0f} {business.currency}) is far from what customers are known to pay "
                f"(about {reference_price:,.0f})."
            )
    return problems
