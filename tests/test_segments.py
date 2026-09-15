import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from agents._segments import (
    FALLBACK_GAP_DAYS,
    SEGMENT_LABELS,
    SEGMENTS,
    customer_table,
    describe_segments,
    segment_changes,
    segment_summary,
    typical_gap_days,
)


def _orders(rows):
    return pd.DataFrame(
        [{"customer": c, "order_date": pd.Timestamp(d), "amount": a} for c, d, a in rows]
    )


# Latest order in the file is 2026-08-31, and every repeat gap is 30 days, so
# "slipping" starts after 45 days without an order and "lost" after 90.
SAMPLE = _orders(
    [
        ("A", "2026-07-02", 1000), ("A", "2026-08-01", 1000), ("A", "2026-08-31", 1000),  # 3 orders, 0 days ago
        ("B", "2026-06-02", 1000), ("B", "2026-07-02", 1000), ("B", "2026-08-01", 1000),  # 3 orders, 30 days ago
        ("C", "2026-06-17", 1000), ("C", "2026-07-17", 1000),                              # 2 orders, 45 days ago
        ("D", "2026-04-03", 1000), ("D", "2026-05-03", 1000), ("D", "2026-06-02", 1000),  # 90 days ago
        ("E", "2026-01-03", 1000), ("E", "2026-02-02", 1000), ("E", "2026-03-04", 1000),  # 180 days ago
        ("F", "2026-08-20", 500),                                                          # 1 order, 11 days ago
        ("G", "2026-07-01", 500),                                                          # 1 order, 61 days ago
    ]
)


def _summary():
    table, meta = customer_table(SAMPLE)
    return segment_summary(table, meta)


def test_typical_gap_is_measured_from_repeat_customers():
    assert typical_gap_days(SAMPLE) == (30.0, True)


def test_typical_gap_falls_back_when_too_few_customers_repeat():
    few = _orders([("A", "2026-07-01", 1), ("A", "2026-08-10", 1), ("B", "2026-08-01", 1)])
    assert typical_gap_days(few) == (FALLBACK_GAP_DAYS, False)


def test_customers_land_in_the_right_segment():
    table, _ = customer_table(SAMPLE)
    segments = dict(zip(table["customer"], table["segment"]))
    assert segments == {
        "A": "best", "B": "best", "C": "regular", "D": "slipping", "E": "lost", "F": "new", "G": "slipping",
    }


def test_summary_counts_everyone_and_is_json_safe():
    summary = _summary()
    json.dumps(summary)  # goes into a Decision Record, so it must serialise
    assert sum(s["customers"] for s in summary["segments"].values()) == 7
    assert summary["as_of"] == "2026-08-31"


def test_top_slipping_customers_are_ordered_by_spend():
    assert [c["customer"] for c in _summary()["top_slipping"]] == ["D", "G"]


def test_changes_compare_with_the_previous_period():
    previous = {"segments": {k: {"customers": 1} for k in SEGMENTS}}
    changes = segment_changes(_summary(), previous)
    assert changes["best"] == 1
    assert changes["slipping"] == 1
    assert changes["regular"] == 0


def test_no_previous_period_means_no_changes():
    assert segment_changes(_summary(), None) == {}


def test_description_names_every_group_and_the_reorder_gap():
    text = describe_segments(_summary())
    for label in SEGMENT_LABELS.values():
        assert label in text
    assert "every 30 days (measured)" in text
