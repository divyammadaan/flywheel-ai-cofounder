"""PlanBrief -- the one bundle of context every planning agent receives.

Before this, Marketing/Product/Sales/CRM were each handed a budget and a
positioning line and nothing else, which is why their output was generic:
an agent told only "$300 and 'farm-direct coffee'" can't name a Bangalore
locality or a supplier region. Giving every planning agent the same brief
keeps them grounded in the same business, region, currency, customer and price.
"""

from dataclasses import dataclass

from agents._money import fmt_money

LAUNCH = "launch"  # not launched yet: plan from research, there are no results
EXISTING = "existing"  # operating business: plan from the founder's real numbers

OFFERING_LABELS = {"physical": "physical products", "service": "a service", "software": "software"}


@dataclass
class PlanBrief:
    cycle: int
    mode: str
    business_summary: str
    industry: str
    product_or_service: str
    region: str
    currency: str
    positioning: str
    target_customer: str
    price: float
    price_unit: str
    context: str = ""
    offering_type: str = "physical"

    def describe(self, budget: float, budget_label: str) -> str:
        """The brief as prompt text, with this agent's own budget line."""
        if self.mode == LAUNCH:
            stage = (
                "PRE-LAUNCH: the business has not launched, so there are no sales, customers "
                "or revenue yet. Plan the launch; never describe results as if they happened."
            )
        else:
            stage = "OPERATING BUSINESS: plan the next period using the founder's real reported numbers below."
        return (
            f"{stage}\n"
            f"Business: {self.business_summary}\n"
            f"Industry: {self.industry}. Sells: {self.product_or_service} "
            f"({OFFERING_LABELS.get(self.offering_type, self.offering_type)}). Region: {self.region}.\n"
            f"Positioning: {self.positioning}\n"
            f"Target customer: {self.target_customer}\n"
            f"Price: {fmt_money(self.price, self.currency)} {self.price_unit}\n"
            f"{budget_label}: {fmt_money(budget, self.currency)} "
            f"(every amount you return must be in {self.currency}).\n"
            f"Context: {self.context}"
        )
