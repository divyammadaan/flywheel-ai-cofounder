"""Flywheel's MCP server -- the project's tools, behind the Model Context Protocol.

Any agent, whichever framework it was built with, reaches these through the same
standard interface instead of importing the code behind them:

  web_search               search the web (DuckDuckGo, no key) for market research
  cash_calculator          launch reserve, runway and break-even from the founder's numbers
  operating_cash_position  runway, debt load and affordability for an existing business
  parse_orders             read an order file (CSV text) into totals and customer counts
  query_decision_records   what each agent decided, and why, per cycle
  get_latest_analytics_summary

The planning engine calls them through `tools/mcp_client_tool.py`: Market Research's
web evidence comes from `web_search`, Finance's cash figures from `cash_calculator`,
and CRM's comparison with last period from `query_decision_records`. Every result is
type-checked and sanitised by the caller before a model sees it.

Run standalone (stdio transport, for use with an MCP-compatible client):
    python tools/mcp_server.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp.server.fastmcp import FastMCP

from agents._cash import launch_cash_plan, operating_cash_position
from agents._input_guard import clean_sources
from observability.decision_record import get_records
from tools.web_search import SNIPPET_CHARS, search

mcp = FastMCP(
    name="flywheel-decision-records",
    instructions=(
        "Flywheel's tools: web search, cash calculators, an order-file parser, and the "
        "Decision Record history of what each agent decided, and why, per cycle."
    ),
)


def _parse_record(record: dict) -> dict:
    """get_records() stores decision/input_snapshot as raw JSON text; parse
    them back to dicts so MCP clients get structured data, not JSON-in-a-
    string."""
    parsed = dict(record)
    parsed["input_snapshot"] = json.loads(record["input_snapshot"])
    parsed["decision"] = json.loads(record["decision"])
    return parsed


@mcp.tool()
def web_search(query: str, max_results: int = 5) -> list[dict]:
    """Search the web and return sources as {title, url, snippet} records.

    Results are validated and stripped of instruction-like text before they are
    returned, because a web page is untrusted input to whatever model reads it.

    Args:
        query: what to search for.
        max_results: how many results to return (1-10).
    """
    limit = max(1, min(int(max_results), 10))
    found = [
        {"title": (r.get("title") or "").strip(), "url": r.get("href"), "snippet": (r.get("body") or "").strip()[:SNIPPET_CHARS]}
        for r in search(query, limit)
    ]
    return clean_sources(found)


@mcp.tool()
def cash_calculator(
    capital: float,
    price: float,
    monthly_fixed_costs: float | None = None,
    unit_cost: float | None = None,
    runway_months: int = 6,
) -> dict:
    """Work out how much of a launch capital can be spent, and what break-even takes.

    Holds back monthly fixed costs x runway months as a reserve, and gives the units a
    month whose margin covers the fixed costs. Anything that needs an input that was not
    given comes back as null with a warning naming it -- nothing is estimated.

    Args:
        capital: money available for the launch.
        price: selling price per unit.
        monthly_fixed_costs: rent, salaries and subscriptions per month, if known.
        unit_cost: cost to deliver one unit, if known.
        runway_months: months of fixed costs to keep in reserve.
    """
    return launch_cash_plan(capital, price, monthly_fixed_costs, unit_cost, runway_months)


@mcp.tool()
def operating_cash_position_tool(
    revenue: float,
    net_profit: float,
    total_debt: float,
    budget: float,
    period_months: int = 12,
    cash_in_bank: float | None = None,
) -> dict:
    """Runway, debt load, and whether next period's budget fits, for an operating business.

    Args:
        revenue: revenue for the period.
        net_profit: profit for the period (negative for a loss).
        total_debt: outstanding debt.
        budget: what the founder wants to deploy next period.
        period_months: how many months the figures cover.
        cash_in_bank: cash on hand, if known.
    """
    return operating_cash_position(revenue, net_profit, total_debt, budget, period_months, cash_in_bank)


@mcp.tool()
def parse_orders(csv_text: str) -> dict:
    """Read an order file given as CSV text; return its totals and customer counts.

    Loose column names and currency symbols are accepted, and rows that cannot be
    read are skipped and counted rather than failing the file.

    Args:
        csv_text: the file's contents (columns for customer, order date and amount).
    """
    import io

    from tools.orders_file import load_orders, order_metrics

    orders = load_orders(io.BytesIO(csv_text.encode("utf-8")), "orders.csv")
    metrics = order_metrics(orders)
    return json.loads(json.dumps(metrics, default=str))


@mcp.tool()
def query_decision_records(cycle: int | None = None, agent: str | None = None) -> list[dict]:
    """Return Decision Records, optionally filtered by cycle and/or agent name.

    Args:
        cycle: only return records from this cycle number, if given.
        agent: only return records from this agent (e.g. "strategy", "finance",
            "marketing", "product", "sales", "crm", "analytics", "funding"),
            if given.
    """
    return [_parse_record(r) for r in get_records(cycle=cycle, agent=agent)]


@mcp.tool()
def get_latest_analytics_summary() -> str | None:
    """Return the most recent cycle's Analytics natural-language summary, or
    None if no cycles have run yet."""
    records = [_parse_record(r) for r in get_records(agent="analytics")]
    if not records:
        return None
    latest = max(records, key=lambda r: r["cycle"])
    return latest["decision"].get("summary")


if __name__ == "__main__":
    mcp.run(transport="stdio")
