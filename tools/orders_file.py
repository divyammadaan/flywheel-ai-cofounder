"""Load a business's order history (CSV or Excel) and turn it into numbers.

Expects one row per order -- the shape Shopify, WooCommerce, POS systems and
most spreadsheets export. Column names are matched loosely ("Customer Name",
"customer", "client" all work), so founders don't have to rename columns.

Required columns: who ordered, when, and how much.
Optional columns: city/area, product, channel.

Everything here is plain arithmetic on the file -- no model involved.
"""

from pathlib import Path

import pandas as pd

REQUIRED = ("customer", "order_date", "amount")

# Checked in order, so the most specific names win.
ALIASES = {
    "customer": (
        "customer", "customer name", "customer id", "client", "client name", "buyer", "name", "email", "phone",
    ),
    "order_date": ("order date", "date", "created at", "purchase date", "invoice date", "ordered at"),
    "amount": ("amount", "order total", "total", "grand total", "net amount", "revenue", "value", "price"),
    "city": ("city", "area", "locality", "location", "region", "pincode"),
    "product": ("product", "item", "sku", "plan"),
    "channel": ("channel", "source", "platform", "acquisition channel"),
}


class OrdersFileError(ValueError):
    """A problem the founder can fix in their file -- the message says how."""


def _normalise(name) -> str:
    return " ".join(str(name).strip().lower().replace("_", " ").split())


def _read_raw(source, filename: str) -> pd.DataFrame:
    suffix = Path(filename).suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(source)
    if suffix == ".xlsx":
        return pd.read_excel(source, engine="openpyxl")
    if suffix == ".xls":
        raise OrdersFileError("Old .xls files aren't supported. Open the file in Excel and save it as .xlsx or .csv.")
    raise OrdersFileError(f"Unsupported file type '{suffix or filename}'. Upload a .csv or .xlsx file.")


def _parse_dates(column: pd.Series) -> pd.Series:
    # ISO first (2026-03-04, and real dates from Excel). Only if most values
    # fail do we fall back to day-first, the Indian/UK convention (04/03/2026).
    iso = pd.to_datetime(column, errors="coerce", format="ISO8601")
    if iso.notna().mean() >= 0.9:
        return iso
    return pd.to_datetime(column, errors="coerce", dayfirst=True, format="mixed")


def load_orders(source, filename: str | None = None) -> pd.DataFrame:
    """Read and clean an order file.

    `source` is a path, or a file-like object (e.g. a Streamlit upload) with
    `filename` given so the format can be detected. Returns columns
    customer, order_date, amount (+ city/product/channel if present), sorted
    by date. Rows with no customer, an unreadable date or a non-numeric amount
    are dropped and counted in `.attrs["skipped_rows"]`.
    """
    raw = _read_raw(source, filename or str(source))
    if raw.empty:
        raise OrdersFileError("The file has no rows.")

    lookup = {_normalise(c): c for c in raw.columns}
    columns = {}
    for field, aliases in ALIASES.items():
        match = next((lookup[a] for a in aliases if a in lookup and lookup[a] not in columns.values()), None)
        if match is not None:
            columns[field] = match

    missing = [f for f in REQUIRED if f not in columns]
    if missing:
        raise OrdersFileError(
            f"Couldn't find a column for: {', '.join(missing)}. "
            f"Columns in your file: {', '.join(map(str, raw.columns))}. "
            "Name them e.g. 'customer', 'order_date' and 'amount'."
        )

    orders = pd.DataFrame({field: raw[col] for field, col in columns.items()})
    orders["customer"] = orders["customer"].astype("string").str.strip()
    orders["order_date"] = _parse_dates(orders["order_date"])
    # Strip currency symbols and thousands separators: "₹1,599.00" -> 1599.0
    orders["amount"] = pd.to_numeric(
        orders["amount"].astype("string").str.replace(r"[^\d.\-]", "", regex=True), errors="coerce"
    )

    valid = orders["customer"].fillna("").ne("") & orders["order_date"].notna() & orders["amount"].notna()
    skipped = int((~valid).sum())
    orders = orders[valid].sort_values("order_date").reset_index(drop=True)
    if orders.empty:
        raise OrdersFileError("No usable rows: every row was missing a customer, a readable date or an amount.")

    orders.attrs["skipped_rows"] = skipped
    return orders


def order_metrics(orders: pd.DataFrame) -> dict:
    """Headline numbers from the order history, all computed from the file."""
    revenue = float(orders["amount"].sum())
    per_customer = orders.groupby("customer")["amount"].size()
    monthly = orders.set_index("order_date")["amount"].resample("MS").sum()

    change = None
    if len(monthly) >= 6:
        recent, prior = float(monthly.iloc[-3:].sum()), float(monthly.iloc[-6:-3].sum())
        change = round((recent - prior) / prior, 4) if prior else None

    return {
        "first_order": orders["order_date"].min().date().isoformat(),
        "last_order": orders["order_date"].max().date().isoformat(),
        "orders": int(len(orders)),
        "customers": int(len(per_customer)),
        "revenue": round(revenue, 2),
        "average_order_value": round(revenue / len(orders), 2),
        "repeat_customer_rate": round(float((per_customer >= 2).mean()), 4),
        "revenue_change_last_3m_vs_prior_3m": change,
        "monthly_revenue": {ts.strftime("%Y-%m"): round(float(v), 2) for ts, v in monthly.items()},
        "skipped_rows": int(orders.attrs.get("skipped_rows", 0)),
    }
