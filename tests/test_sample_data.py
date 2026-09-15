import sys
from io import BytesIO, StringIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents._segments import SEGMENTS, customer_table
from tools.orders_file import load_orders
from tools.sample_data import generate_orders, to_file_bytes


def test_same_seed_gives_the_same_file():
    assert generate_orders(seed=7).equals(generate_orders(seed=7))


def test_generated_file_round_trips_through_the_upload_loader():
    orders = generate_orders(customers=120, seed=3)
    from_csv = load_orders(StringIO(to_file_bytes(orders, "csv").decode("utf-8")), "sample.csv")
    from_xlsx = load_orders(BytesIO(to_file_bytes(orders, "xlsx")), "sample.xlsx")
    assert len(from_csv) == len(from_xlsx) == len(orders)
    assert from_csv.attrs["skipped_rows"] == 0
    assert (from_csv["amount"] > 0).all()


def test_sample_customers_cover_every_segment():
    table, meta = customer_table(load_orders(StringIO(to_file_bytes(generate_orders(), "csv").decode()), "s.csv"))
    assert set(table["segment"]) == set(SEGMENTS)
    assert meta["gap_measured"] is True
