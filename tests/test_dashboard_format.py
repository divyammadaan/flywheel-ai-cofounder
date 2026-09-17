"""The dashboard's text-shaping helpers. They must never mangle model prose
into looking structured -- when there's no clear structure, they leave it be."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from observability.dashboard.format import as_bullets, clause_items, headline, numbered_items, shorten


def test_a_numbered_outline_becomes_items():
    # A real pitch deck outline from a run.
    outline = (
        "1. Hook: boutique Bangalore filter-coffee subscription, 12 months, Rs 24.0L revenue. 2. Problem. "
        "3. Solution: Rs 899/mo 500g single-origin. 4. Target: 25-45 professionals."
    )
    items = numbered_items(outline)
    assert len(items) == 4
    assert items[0].startswith("Hook: boutique Bangalore")
    assert items[1] == "Problem"


def test_semicolon_clauses_become_items_only_when_each_is_substantial():
    text = "Revenue-based financing while recurring revenue exists; an MSME working-capital loan for inventory"
    assert len(clause_items(text)) == 2
    assert clause_items("a; b; c") == []


def test_a_multi_sentence_paragraph_becomes_bullets():
    text = (
        "The business is bleeding value through churn and needs to act now. "
        "Slipping-away customers represent 27% of revenue this period. "
        "Revenue dropped 17% in the last quarter."
    )
    assert len(as_bullets(text)) == 3


def test_a_single_sentence_is_left_alone():
    assert as_bullets("Boutique single-origin filter coffee subscriptions for Bangalore.") == []


def test_headline_splits_the_lead_from_the_rest():
    lead, rest = headline(
        "Net margin fell to -7.5% this year. Revenue dropped 17% in the last quarter. "
        "Retention now matters more than winning new customers."
    )
    assert lead == "Net margin fell to -7.5% this year."
    assert len(rest) == 2


def test_headline_of_empty_text_is_empty():
    assert headline("") == ("", [])


def test_shorten_keeps_short_text_and_trims_long_text():
    assert shorten("Short enough", 40) == "Short enough"
    assert shorten("x" * 200, 40).endswith("…")
    assert len(shorten("x" * 200, 40)) == 40
