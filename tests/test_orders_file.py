import sys
from io import StringIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import pytest

from tools.orders_file import OrdersFileError, load_orders, order_metrics


def _csv(text: str) -> StringIO:
    return StringIO(text.strip())


def test_loose_column_names_and_currency_formatting_are_understood():
    orders = load_orders(
        _csv('Customer Name,Order Date,Order Total\nRiya Nair,2026-08-01,"₹1,599.00"\nArjun Rao,2026-08-02,799'),
        "orders.csv",
    )
    assert list(orders.columns[:3]) == ["customer", "order_date", "amount"]
    assert orders["amount"].tolist() == [1599.0, 799.0]


def test_iso_dates_are_read_year_month_day():
    orders = load_orders(_csv("customer,order_date,amount\nA,2026-03-04,100"), "o.csv")
    assert orders["order_date"].iloc[0] == pd.Timestamp("2026-03-04")


def test_slash_dates_are_read_day_first():
    orders = load_orders(_csv("customer,order_date,amount\nA,05/09/2026,100\nB,25/09/2026,100"), "o.csv")
    assert orders["order_date"].iloc[0] == pd.Timestamp("2026-09-05")


def test_missing_required_column_names_what_is_missing():
    with pytest.raises(OrdersFileError, match="amount"):
        load_orders(_csv("customer,order_date\nA,2026-03-04"), "o.csv")


def test_unusable_rows_are_skipped_and_counted():
    orders = load_orders(_csv("customer,order_date,amount\nA,2026-03-04,100\n,2026-03-05,100\nC,not a date,100"), "o.csv")
    assert len(orders) == 1
    assert orders.attrs["skipped_rows"] == 2


def test_old_xls_files_get_a_fixable_message():
    with pytest.raises(OrdersFileError, match="save it as .xlsx"):
        load_orders("orders.xls")


def test_xlsx_files_load(tmp_path):
    path = tmp_path / "orders.xlsx"
    pd.DataFrame({"customer": ["A"], "order_date": [pd.Timestamp("2026-08-01")], "amount": [799]}).to_excel(
        path, index=False
    )
    assert load_orders(path)["amount"].iloc[0] == 799


def test_order_metrics_come_from_the_file():
    orders = load_orders(_csv("customer,order_date,amount\nX,2026-07-01,100\nX,2026-08-01,300\nY,2026-08-02,200"), "o.csv")
    m = order_metrics(orders)
    assert m["revenue"] == 600
    assert m["orders"] == 3
    assert m["customers"] == 2
    assert m["average_order_value"] == 200
    assert m["repeat_customer_rate"] == 0.5
    assert m["monthly_revenue"] == {"2026-07": 100, "2026-08": 500}
