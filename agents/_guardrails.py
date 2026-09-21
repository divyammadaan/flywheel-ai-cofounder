"""Checks on model output that must hold whatever the model says.

Strategy's plan feeds every other agent, so a plan that describes the wrong
business, prices in the wrong units, or talks about people and places in
demeaning terms is rejected here and sent back once for a fix. In testing,
Strategy described a filter-coffee subscription as an "Indian grocery box"
priced "per 4 lb", and targeted families "excluding slum communities like
Koramangala" -- none of which may reach a founder.

Funding's roadmap is checked the same way: in testing it proposed a
"pre-seed" round of Rs 3-7 crore, and a traction milestone of 80-100
subscribers next to a revenue milestone that needed ~1,500.

These are deliberately simple, explainable rules rather than another model
call: they are fast, testable, and can't be talked out of their answer.
"""

import re

from agents._text import as_text

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


_TOOL_MARKUP = re.compile(r"\s*</?(?:parameter|function|invoke|tool_call)\b.*", re.IGNORECASE | re.DOTALL)


def strip_tool_markup(text):
    """Cut off raw tool-call markup a model leaked into a text field.

    Seen in a live run: Sales' lead-to-customer steps ended with
    '<parameter name="lead_sources">[...' -- the model's own function-call
    syntax. Everything from the first such tag onwards is dropped.
    """
    return _TOOL_MARKUP.sub("", text).rstrip() if isinstance(text, str) else text


def clean_text_fields(value):
    """strip_tool_markup applied to every string inside nested lists and dicts."""
    if isinstance(value, str):
        return strip_tool_markup(value)
    if isinstance(value, list):
        return [clean_text_fields(v) for v in value]
    if isinstance(value, dict):
        return {k: clean_text_fields(v) for k, v in value.items()}
    return value


_PLACEHOLDER_ACTION = re.compile(r"^\s*(?:action|what to do)\s+for\b", re.IGNORECASE)
_PLACEHOLDER_MESSAGE = re.compile(r"^\s*(?:hi \{name\},?\s*)?(?:win-back\s+)?message\s+for\b", re.IGNORECASE)


def crm_output_problems(data: dict) -> list[str]:
    """Whether the local CRM model's reply is a real plan or a placeholder echo.

    In one live run every action came back as "Action for best customers",
    every message as "message for slipping away", and every spend as 0 -- the
    model repeated field labels instead of writing a plan.
    """
    problems = []
    actions = [str(v or "") for k, v in data.items() if k.endswith("_action")]
    if any(not a.strip() or (_PLACEHOLDER_ACTION.match(a) and len(a.split()) <= 6) for a in actions):
        problems.append("Some actions are placeholders like 'Action for best customers' instead of real steps.")
    messages = [str(v or "") for k, v in data.items() if k.endswith("_message")]
    if any(not m.strip() or _PLACEHOLDER_MESSAGE.match(m) for m in messages):
        problems.append("Some messages are placeholders like 'message for slipping away' instead of real text.")
    if not sum(float(v or 0) for k, v in data.items() if k.endswith("_spend")):
        problems.append("No spend was planned for any group.")
    return problems


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
    # as_text, not str(): rationale is a list of points now, and str() on a
    # list would wrap every reason in quotes and brackets before the word
    # checks below ever see it.
    text = " ".join(
        as_text(getattr(plan, field, "")) for field in ("positioning", "target_customer", "price_unit", "rationale")
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


# ---------------------------------------------------------------- funding --

_MONEY = re.compile(
    r"(?:₹|rs\.?|inr|\$|usd)\s*(\d[\d,]*(?:\.\d+)?)\s*"
    r"(?:(?:-|–|to)\s*(?:₹|rs\.?|inr|\$|usd)?\s*(\d[\d,]*(?:\.\d+)?))?\s*"
    r"(crores?|cr|lakhs?|lac|l|k|thousand|million|mn|m)?\b",
    re.IGNORECASE,
)
_UNIT_VALUE = {
    "crore": 1e7, "crores": 1e7, "cr": 1e7, "lakh": 1e5, "lakhs": 1e5, "lac": 1e5, "l": 1e5,
    "k": 1e3, "thousand": 1e3, "million": 1e6, "mn": 1e6, "m": 1e6,
}
_CUSTOMER_COUNT = re.compile(
    r"(\d[\d,]*)(?:\s*(?:-|–|to)\s*(\d[\d,]*))?\+?\s+(?:paying\s+|active\s+|monthly\s+|repeat\s+)?"
    r"(?:subscribers|subscriptions|customers|users|clients|members)",
    re.IGNORECASE,
)

# Rough upper bounds on round size by stage -- rules of thumb for flagging an
# implausible number, not investment advice.
ROUND_SIZE_CAPS = {
    "INR": {"pre_seed": 3e7, "seed": 1.5e8, "series_a": 1.5e9},
    "USD": {"pre_seed": 1e6, "seed": 5e6, "series_a": 3e7},
}
STAGE_LABELS = {"pre_seed": "pre-seed", "seed": "seed", "series_a": "Series A"}
MAX_TRACTION_MISMATCH = 3.0


def _number(text: str) -> float:
    return float(text.replace(",", ""))


def money_amounts(text: str) -> list[tuple[float, float]]:
    """(low, high) amounts in plain units: "₹3–7 crore" -> (3e7, 7e7)."""
    amounts = []
    for low, high, unit in _MONEY.findall(text or ""):
        scale = _UNIT_VALUE.get(unit.lower(), 1.0) if unit else 1.0
        low_value = _number(low) * scale
        amounts.append((low_value, _number(high) * scale if high else low_value))
    return amounts


def _stage(text: str) -> str | None:
    t = (text or "").lower()
    if "series a" in t:
        return "series_a"
    if re.search(r"pre[- ]?seed", t):
        return "pre_seed"
    if "seed" in t:
        return "seed"
    return None


def _monthly_revenue(text: str) -> float | None:
    amounts = money_amounts(text)
    if not amounts:
        return None
    value = amounts[0][0]
    if re.search(r"month|mrr|/mo\b", text, re.IGNORECASE):
        return value
    if re.search(r"annual|arr\b|year|/yr\b", text, re.IGNORECASE):
        return value / 12
    return None


def funding_problems(plan, currency: str, price: float | None = None) -> list[str]:
    """What doesn't add up in a Funding roadmap.

    `plan` needs target_stage, readiness, revenue_milestone and
    traction_milestones; `price` is the plan's price per customer per month.
    """
    problems = []

    stage = _stage(f"{plan.target_stage} {plan.readiness}")
    caps = ROUND_SIZE_CAPS.get(currency)
    amounts = money_amounts(plan.target_stage)
    if stage and caps and amounts:
        largest = max(high for _, high in amounts)
        if largest > caps[stage]:
            problems.append(
                f"A {STAGE_LABELS[stage]} round of up to {largest:,.0f} {currency} is far above the usual size "
                f"for that stage (roughly up to {caps[stage]:,.0f}). Either shrink the round or name the right stage."
            )

    monthly = _monthly_revenue(plan.revenue_milestone)
    counts = [
        _number(high or low) for low, high in _CUSTOMER_COUNT.findall(as_text(plan.traction_milestones))
    ]
    if price and monthly and counts:
        implied = monthly / price
        count = max(counts)
        if count * MAX_TRACTION_MISMATCH < implied or count > implied * MAX_TRACTION_MISMATCH:
            problems.append(
                f"The traction milestone ({count:,.0f} customers) doesn't match the revenue milestone, which "
                f"needs about {implied:,.0f} customers at {price:,.0f} {currency} each. Make them consistent."
            )
    return problems
