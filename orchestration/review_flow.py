"""Review flow -- for an OPERATING business, planned from its real numbers.

    Intake (description) -> Analytics on the founder's numbers + uploaded orders
      -> Strategy -> Finance -> [Marketing, Sales, Product, CRM]
      -> Funding roadmap -> launch page (data/site/index.html)

Every number comes from the founder. Required: revenue, net profit, total
debt, and the budget they can deploy next period. The optional numbers
(EBITDA, cash, marketing spend, customer counts) sharpen the analysis;
anything left out is reported as "not reported", never estimated.

Upload the order history with --orders (a .csv or .xlsx, one row per order:
customer, order date, amount). It powers the CRM plan and adds order figures
to Analytics. No file handy? Generate one: python tools/sample_data.py

    python orchestration/review_flow.py --description "..." --currency INR \\
        --period "FY2025-26" --revenue 4200000 --net-profit 350000 \\
        --debt 800000 --budget 600000 --cash 900000 --orders data/sample_orders.xlsx

Add --append to record another period for the same business: earlier periods
are kept so Analytics and CRM can compare against them. Without it, the
history starts fresh.
"""

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# See validate_flow.py -- Windows cp1252 consoles crash on characters the
# models routinely emit (arrows, em-dashes, currency symbols).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv

load_dotenv()

from agents._money import SUPPORTED_CURRENCIES, fmt_money
from agents.analytics import PeriodMetrics
from agents.intake import BusinessInput, IntakeAgent
from observability.decision_record import DB_PATH, DecisionRecord, get_records, log_decision
from observability.usage import usage_summary
from orchestration.cycle import PRECYCLE, PlanBlocked, next_review_cycle, run_business_review, run_funding
from orchestration.report import print_analytics, print_funding, print_plan, print_usage, rule
from tools.landing_page import write_landing_page
from tools.orders_file import OrdersFileError, load_orders


def stored_business() -> BusinessInput | None:
    """The business recorded by the first review, for --append."""
    records = get_records(cycle=PRECYCLE, agent="intake")
    return BusinessInput(**json.loads(records[-1]["decision"])) if records else None


def review(
    description: str | None,
    currency: str,
    metrics: PeriodMetrics,
    budget: float,
    orders_path: str | None = None,
    append: bool = False,
    skip_funding: bool = False,
) -> None:
    # Read the file first: a bad upload should fail before any model call.
    orders = None
    if orders_path:
        try:
            orders = load_orders(orders_path)
        except (OrdersFileError, FileNotFoundError) as exc:
            raise SystemExit(f"Can't use the orders file: {exc}")
        skipped = orders.attrs.get("skipped_rows", 0)
        print(f"Orders file: {len(orders):,} orders loaded" + (f", {skipped} unusable rows skipped" if skipped else ""))

    if append:
        business = stored_business()
        if business is None:
            raise SystemExit("--append needs an earlier review to add to. Run once without it first.")
        if business.currency != currency:
            print(f"Using this business's recorded currency, {business.currency}.")
    else:
        if not description:
            raise SystemExit("--description is required unless you use --append.")
        DB_PATH.unlink(missing_ok=True)
        rule("INTAKE")
        business = IntakeAgent().process(description)
        business.mode = "existing_business"
        business.currency = currency

    # The founder's numbers are the single source of truth -- they replace
    # anything the model may have read out of the description.
    business.existing_metrics = asdict(metrics)
    if not append:
        log_decision(DecisionRecord(PRECYCLE, "intake", {"raw_input": description}, business.__dict__))
        print(f"Summary : {business.business_summary}")
        print(f"Industry: {business.industry} ({business.offering_type})")
        print(f"Region  : {business.target_region}")

    cycle = next_review_cycle()
    print(f"\nPeriod {cycle}: {metrics.period_label}, budget to deploy {fmt_money(budget, business.currency)}")
    if orders is None:
        print("No orders file, so no CRM plan. Add --orders to get one.")

    try:
        plan = run_business_review(business, metrics, budget, cycle, orders)
    except PlanBlocked as blocked:
        rule("PLAN BLOCKED")
        print(blocked)
        print_usage(usage_summary())
        return
    print_analytics(plan.analytics)
    print_plan(plan)

    page = write_landing_page(asdict(business), asdict(plan.strategy), asdict(plan.marketing))
    print(f"\nLanding page: {page}")

    if not skip_funding:
        print_funding(run_funding(business, plan))

    print_usage(usage_summary())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Plan an operating business's next period from its real numbers")
    parser.add_argument("--description", type=str, default=None, help="what you sell, where, to whom")
    parser.add_argument("--currency", choices=SUPPORTED_CURRENCIES, default="INR")
    parser.add_argument("--period", required=True, help='label for this period, e.g. "FY2025-26"')
    parser.add_argument("--period-months", type=int, default=12, help="how many months the numbers cover")
    parser.add_argument("--revenue", type=float, required=True)
    parser.add_argument("--net-profit", type=float, required=True, help="negative for a loss")
    parser.add_argument("--debt", type=float, required=True, help="total outstanding debt")
    parser.add_argument("--budget", type=float, required=True, help="budget you can deploy next period")
    parser.add_argument("--ebitda", type=float, default=None)
    parser.add_argument("--cash", type=float, default=None, help="cash in bank")
    parser.add_argument("--marketing-spend", type=float, default=None)
    parser.add_argument("--new-customers", type=int, default=None)
    parser.add_argument("--customers-at-start", type=int, default=None)
    parser.add_argument("--customers-lost", type=int, default=None)
    parser.add_argument("--orders", type=str, default=None, help="order history file (.csv or .xlsx)")
    parser.add_argument("--append", action="store_true", help="add this period to the existing business history")
    parser.add_argument("--skip-funding", action="store_true", help="skip the funding roadmap")
    args = parser.parse_args()

    if args.budget <= 0:
        parser.error("--budget must be above zero")

    review(
        args.description,
        args.currency,
        PeriodMetrics(
            period_label=args.period,
            revenue=args.revenue,
            net_profit=args.net_profit,
            total_debt=args.debt,
            period_months=args.period_months,
            ebitda=args.ebitda,
            cash_in_bank=args.cash,
            marketing_spend=args.marketing_spend,
            new_customers=args.new_customers,
            customers_at_start=args.customers_at_start,
            customers_lost=args.customers_lost,
        ),
        args.budget,
        orders_path=args.orders,
        append=args.append,
        skip_funding=args.skip_funding,
    )
