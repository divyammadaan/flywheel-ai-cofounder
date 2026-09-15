import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents._brief import EXISTING, LAUNCH, PlanBrief


def _brief(mode: str) -> PlanBrief:
    return PlanBrief(
        cycle=1,
        mode=mode,
        business_summary="Filter coffee subscription",
        industry="D2C coffee",
        product_or_service="filter coffee",
        region="Bangalore",
        currency="INR",
        positioning="Farm-direct filter coffee",
        target_customer="Professionals aged 25-40 in Indiranagar",
        price=799,
        price_unit="per month",
    )


def test_launch_brief_tells_agents_nothing_has_happened_yet():
    text = _brief(LAUNCH).describe(200000, "Marketing budget")
    assert "not launched" in text
    assert "Marketing budget: ₹200,000" in text
    assert "₹799 per month" in text


def test_existing_brief_points_agents_at_the_real_numbers():
    assert "real reported numbers" in _brief(EXISTING).describe(1000, "Sales budget")
