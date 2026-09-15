"""Generate a realistic sample order-history file for demos and tests.

Real founders upload their own export; this exists so the existing-business
flow can be shown without real customer data. It's seeded, so the same
arguments always produce the same file.

Customers follow believable patterns rather than uniform noise, so the CRM
segments come out meaningfully different:
  loyal    orders about every `cycle_days`, still active
  regular  two orders so far, the second within the last cycle
  fading   ordered regularly, stopped roughly 2-3 cycles ago
  churned  ordered a few times early on, gone for months
  new      first and only order within the last cycle
  one_off  a single order some time ago

    python tools/sample_data.py --out data/sample_orders.xlsx
    python tools/sample_data.py --out data/sample_orders.csv --customers 500 --price 1299 --cycle-days 45
"""

import argparse
import random
from datetime import date, timedelta
from io import BytesIO
from pathlib import Path

import pandas as pd

FIRST_NAMES = (
    "Aarav", "Aditi", "Akash", "Ananya", "Arjun", "Diya", "Harsh", "Ishaan", "Kavya", "Kiran", "Meera", "Neha",
    "Nikhil", "Pooja", "Priya", "Rahul", "Riya", "Rohan", "Sanjana", "Shreya", "Siddharth", "Sneha", "Tanvi",
    "Varun", "Vikram", "Yash", "Zoya", "Aditya", "Divya", "Karthik",
)
LAST_NAMES = (
    "Sharma", "Iyer", "Reddy", "Nair", "Rao", "Menon", "Gupta", "Patel", "Kulkarni", "Shetty", "Bhat", "Joshi",
    "Mehta", "Pillai", "Das", "Hegde", "Krishnan", "Singh", "Verma", "Kapoor",
)
AREAS = (
    "Indiranagar", "Koramangala", "HSR Layout", "Whitefield", "Jayanagar", "JP Nagar", "Malleshwaram", "Hebbal",
    "Bellandur", "Electronic City",
)
CHANNELS = ("Instagram", "Google Search", "Referral", "WhatsApp", "Walk-in")
MIX = {"loyal": 0.25, "regular": 0.10, "fading": 0.20, "churned": 0.20, "new": 0.12, "one_off": 0.13}


def generate_orders(
    customers: int = 300,
    months: int = 12,
    end: date = date(2026, 8, 31),
    price: float = 799.0,
    cycle_days: int = 30,
    product: str = "Monthly filter coffee subscription",
    seed: int = 42,
) -> pd.DataFrame:
    rng = random.Random(seed)
    start = end - timedelta(days=int(months * 30.4))
    span = (end - start).days

    def clamp(d: date) -> date:
        return min(max(d, start), end)

    rows, used_names = [], set()
    for _ in range(customers):
        kind = rng.choices(list(MIX), weights=list(MIX.values()))[0]
        name = f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"
        while name in used_names:
            name = f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)} {rng.randint(2, 99)}"
        used_names.add(name)
        area, channel = rng.choice(AREAS), rng.choice(CHANNELS)

        if kind == "loyal":
            first = start + timedelta(days=rng.randint(0, span // 2))
            last = end - timedelta(days=rng.randint(0, cycle_days // 2))
        elif kind == "regular":
            last = end - timedelta(days=rng.randint(0, cycle_days // 2))
            first = last - timedelta(days=int(cycle_days * rng.uniform(0.8, 1.2)))
        elif kind == "fading":
            first = start + timedelta(days=rng.randint(0, span // 3))
            last = end - timedelta(days=int(cycle_days * rng.uniform(1.8, 2.8)))
        elif kind == "churned":
            first = start + timedelta(days=rng.randint(0, max(span // 4, 1)))
            last = min(first + timedelta(days=int(cycle_days * rng.uniform(1, 3))), end - timedelta(days=int(cycle_days * 3.5)))
        elif kind == "new":
            first = last = end - timedelta(days=rng.randint(0, cycle_days - 1))
        else:  # one_off
            first = last = start + timedelta(days=rng.randint(0, max(span - cycle_days * 2, 1)))
        first, last = clamp(first), clamp(last)
        first = min(first, last)

        day = first
        while day <= last:
            quantity = rng.choice((1, 1, 1, 1, 2))
            discount = 0.9 if rng.random() < 0.1 else 1.0
            rows.append(
                {
                    "order_date": day,
                    "customer": name,
                    "city": area,
                    "product": product,
                    "channel": channel,
                    "amount": round(price * quantity * discount, 2),
                }
            )
            if kind in ("new", "one_off"):
                break
            if kind == "regular":
                # Exactly two orders: the first, then the last.
                day = last if day < last else last + timedelta(days=1)
                continue
            day += timedelta(days=max(1, int(rng.gauss(cycle_days, cycle_days * 0.15))))

    orders = pd.DataFrame(rows).sort_values(["order_date", "customer"]).reset_index(drop=True)
    orders.insert(0, "order_id", [f"ORD-{10001 + i}" for i in range(len(orders))])
    return orders


def to_file_bytes(orders: pd.DataFrame, fmt: str) -> bytes:
    """The order table as a downloadable .csv or .xlsx file."""
    if fmt == "csv":
        return orders.to_csv(index=False).encode("utf-8")
    if fmt == "xlsx":
        buffer = BytesIO()
        orders.to_excel(buffer, index=False, engine="openpyxl")
        return buffer.getvalue()
    raise ValueError(f"Unsupported format: {fmt}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate a sample order-history file")
    parser.add_argument("--out", default="data/sample_orders.xlsx", help="output path, .csv or .xlsx")
    parser.add_argument("--customers", type=int, default=300)
    parser.add_argument("--months", type=int, default=12)
    parser.add_argument("--end", type=date.fromisoformat, default=date(2026, 8, 31), help="last order date, YYYY-MM-DD")
    parser.add_argument("--price", type=float, default=799.0)
    parser.add_argument("--cycle-days", type=int, default=30, help="how often a loyal customer re-orders")
    parser.add_argument("--product", default="Monthly filter coffee subscription")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    out = Path(args.out)
    fmt = out.suffix.lower().lstrip(".")
    data = generate_orders(args.customers, args.months, args.end, args.price, args.cycle_days, args.product, args.seed)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(to_file_bytes(data, fmt))
    print(f"Wrote {len(data)} orders from {data['customer'].nunique()} customers to {out}")
