"""Customer segments from an order history -- plain arithmetic, no model.

The CRM agent's AI only writes the actions and messages; who belongs to which
group is decided here, so it's exact and explainable.

Two choices worth knowing:
- Recency is measured against the latest order in the file, not today, so a
  file exported last month (or generated sample data) isn't read as everyone
  having gone quiet.
- The cut-offs scale with how often THIS business's customers re-order: the
  median gap between a repeat customer's orders. A monthly coffee
  subscription and a yearly furniture buyer shouldn't share one "slipping"
  threshold.
"""

import numpy as np
import pandas as pd

FALLBACK_GAP_DAYS = 30.0
MIN_REPEAT_CUSTOMERS = 5  # fewer repeaters than this and the median gap isn't trustworthy
SLIPPING_AFTER = 1.5  # x typical gap without an order
LOST_AFTER = 3.0

SEGMENTS = ("best", "regular", "new", "slipping", "lost")
SEGMENT_LABELS = {
    "best": "Best customers",
    "regular": "Regulars",
    "new": "New customers",
    "slipping": "Slipping away",
    "lost": "Lost",
}
# What each group means, for the CRM prompt. Without these the model offered
# "new customers" a discount on their first order -- they've already placed it.
SEGMENT_DEFINITIONS = {
    "best": "3 or more orders and still ordering on schedule",
    "regular": "2 orders and still ordering on schedule",
    "new": "exactly one order, placed recently; the goal is their second order",
    "slipping": f"used to order but now overdue (no order for over {SLIPPING_AFTER:g}x their usual gap)",
    "lost": f"no order for over {LOST_AFTER:g}x the usual gap",
}


def typical_gap_days(orders: pd.DataFrame) -> tuple[float, bool]:
    """Median days between consecutive orders of repeat customers.

    Returns (gap, measured). Falls back to 30 days when there aren't enough
    repeat customers to measure it.
    """
    ordered = orders.sort_values(["customer", "order_date"])
    repeaters = int((ordered.groupby("customer").size() >= 2).sum())
    gaps = ordered.groupby("customer")["order_date"].diff().dt.days.dropna()
    if repeaters < MIN_REPEAT_CUSTOMERS or gaps.empty:
        return FALLBACK_GAP_DAYS, False
    return max(float(gaps.median()), 1.0), True


def customer_table(orders: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """One row per customer with orders, spend, recency and segment."""
    as_of = orders["order_date"].max()
    gap, measured = typical_gap_days(orders)

    table = orders.groupby("customer").agg(
        orders=("amount", "size"),
        spent=("amount", "sum"),
        first_order=("order_date", "min"),
        last_order=("order_date", "max"),
    )
    table["days_since_last_order"] = (as_of - table["last_order"]).dt.days

    days = table["days_since_last_order"]
    table["segment"] = np.select(
        [days > LOST_AFTER * gap, days > SLIPPING_AFTER * gap, table["orders"] >= 3, table["orders"] == 1],
        ["lost", "slipping", "best", "new"],
        default="regular",
    )
    meta = {"as_of": as_of, "typical_gap_days": gap, "gap_measured": measured}
    return table.reset_index(), meta


def segment_summary(table: pd.DataFrame, meta: dict, top_n: int = 5) -> dict:
    """JSON-safe summary of the segments, plus the highest-spending customers
    who are slipping away -- the ones most worth a personal message."""
    total_revenue = float(table["spent"].sum())
    segments = {}
    for key in SEGMENTS:
        part = table[table["segment"] == key]
        revenue = float(part["spent"].sum())
        segments[key] = {
            "label": SEGMENT_LABELS[key],
            "customers": int(len(part)),
            "revenue": round(revenue, 2),
            "revenue_share": round(revenue / total_revenue, 4) if total_revenue else None,
            "avg_orders": round(float(part["orders"].mean()), 2) if len(part) else None,
        }

    slipping = table[table["segment"] == "slipping"].nlargest(top_n, "spent")
    top_slipping = [
        {
            "customer": str(row.customer),
            "orders": int(row.orders),
            "spent": round(float(row.spent), 2),
            "days_since_last_order": int(row.days_since_last_order),
        }
        for row in slipping.itertuples()
    ]

    return {
        "as_of": meta["as_of"].date().isoformat(),
        "typical_gap_days": round(float(meta["typical_gap_days"]), 1),
        "gap_measured": bool(meta["gap_measured"]),
        "customers": int(len(table)),
        "segments": segments,
        "top_slipping": top_slipping,
    }


def segment_changes(current: dict, previous: dict | None) -> dict:
    """Change in customers per segment since the previous period. Empty when
    there's no earlier period to compare with."""
    if not previous:
        return {}
    earlier = previous.get("segments", {})
    return {
        key: current["segments"][key]["customers"] - earlier.get(key, {}).get("customers", 0) for key in SEGMENTS
    }


def describe_segments(summary: dict) -> str:
    """The segment summary as one line of prompt text."""
    parts = []
    for key in SEGMENTS:
        s = summary["segments"][key]
        share = f"{s['revenue_share']:.0%} of revenue" if s["revenue_share"] is not None else "no revenue"
        parts.append(f"{s['label']}: {s['customers']} customers, {share}")
    basis = "measured" if summary["gap_measured"] else "assumed, too few repeat customers to measure"
    return (
        f"{'; '.join(parts)}. Customers typically re-order every {summary['typical_gap_days']:g} days "
        f"({basis}); as of {summary['as_of']}."
    )
