import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tools.web_search as web_search
from tools.landing_page import build_landing_page

BUSINESS = SimpleNamespace(
    product_or_service="filter coffee subscriptions", industry="D2C coffee", target_region="Bangalore, India"
)


def test_search_results_are_deduplicated_and_capped(monkeypatch):
    def fake_search(query, max_results=5):
        return [{"title": f"{query} {i}", "href": f"https://example.com/{i}", "body": "x" * 500} for i in range(6)]

    monkeypatch.setattr(web_search, "search", fake_search)
    sources = web_search.search_business(BUSINESS)
    assert len(sources) == 6  # both queries return the same six URLs
    assert all(len(s["snippet"]) <= web_search.SNIPPET_CHARS for s in sources)


def test_no_results_tells_the_agent_to_label_estimates():
    assert "estimate" in web_search.describe_sources([])


def test_landing_page_uses_the_plan_and_escapes_model_text(tmp_path):
    image = tmp_path / "ad.jpg"
    image.write_bytes(b"\xff\xd8fakejpeg")
    page = build_landing_page(
        {"product_or_service": "filter coffee subscriptions", "currency": "INR"},
        {"positioning": "Fresh filter coffee <script>alert(1)</script>", "price": 899, "price_unit": "per month",
         "target_customer": "Professionals in HSR Layout", "currency": "INR"},
        {"ad_copy": "Roasted this week.", "ad_image_path": str(image)},
    )
    assert "₹899" in page
    assert "&lt;script&gt;" in page and "<script>" not in page
    assert "data:image/jpeg;base64," in page


def test_landing_page_works_without_an_image():
    page = build_landing_page({"product_or_service": "cakes"}, {"positioning": "Cakes", "price": 500, "currency": "INR"})
    assert "<img" not in page
