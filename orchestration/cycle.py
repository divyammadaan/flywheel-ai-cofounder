"""Main cycle loop: Strategy -> Finance -> [Marketing, Product, Sales, CRM]
(parallel) -> Market Simulator -> Analytics -> next cycle's Strategy input.

Run with: python orchestration/cycle.py --cycles 5
"""

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# See validate_flow.py -- Windows cp1252 consoles crash on characters the
# models routinely emit (arrows, em-dashes, currency symbols).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv

load_dotenv()

from agents.analytics import AnalyticsAgent
from agents.crm import CRMAgent
from agents.finance import FinanceAgent
from agents.marketing import MarketingAgent
from agents.product import ProductAgent
from agents.sales import SalesAgent
from agents.strategy import StrategyAgent
from observability.decision_record import DecisionRecord, log_decision
from simulator.market_simulator import ExecutionOutput, MarketSimulator

TOTAL_BUDGET_PER_CYCLE = 1000.0
SIM_SEED = 42


def run(num_cycles: int, initial_context: str | None = None) -> None:
    """Run num_cycles of the engine. If initial_context is given (e.g. from
    validate_flow.py's Market Research + Founder Advisor output), Strategy's
    first decision is grounded in that instead of a generic cold-start
    prompt -- Strategy's interface already accepts arbitrary prior context
    as a string, so no special-casing is needed here.
    """
    strategy = StrategyAgent()
    finance = FinanceAgent(total_budget_per_cycle=TOTAL_BUDGET_PER_CYCLE)
    marketing = MarketingAgent()
    product = ProductAgent()
    sales = SalesAgent()
    crm = CRMAgent()
    analytics = AnalyticsAgent()
    simulator = MarketSimulator(seed=SIM_SEED)

    previous_summary = initial_context
    previous_churn_rate = None
    previous_leads = 0

    for cycle in range(1, num_cycles + 1):
        print(f"\n=== Cycle {cycle} ===")

        decision = strategy.decide(cycle, previous_summary)
        log_decision(DecisionRecord(cycle, "strategy", {"previous_summary": previous_summary}, decision.__dict__))

        allocation = finance.allocate(cycle, decision.priorities)
        log_decision(DecisionRecord(cycle, "finance", {"priorities": decision.priorities}, allocation.__dict__))

        # The four execution agents are genuinely independent: each needs only
        # its own budget from Finance, and nothing reads another's output
        # until the Simulator fans them back in. Running them concurrently
        # cuts the heaviest stage from the sum of four calls to the slowest
        # one. They sit on different providers (see agents/_models.py) so
        # firing together doesn't just move the queue to one rate limit.
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {
                "marketing": pool.submit(
                    marketing.execute, cycle, allocation.marketing, decision.positioning, decision.pricing
                ),
                "product": pool.submit(product.execute, cycle, allocation.product, decision.positioning),
                "sales": pool.submit(sales.execute, cycle, allocation.sales, previous_leads),
                "crm": pool.submit(crm.execute, cycle, allocation.crm, previous_churn_rate),
            }
            # .result() re-raises in the caller, so a failing agent still
            # surfaces rather than being silently swallowed by the pool.
            mkt_out = futures["marketing"].result()
            prod_out = futures["product"].result()
            sales_out = futures["sales"].result()
            crm_out = futures["crm"].result()

        for name, out in (("marketing", mkt_out), ("product", prod_out), ("sales", sales_out), ("crm", crm_out)):
            log_decision(DecisionRecord(cycle, name, {"budget": getattr(allocation, name)}, out.__dict__))

        exec_output = ExecutionOutput(
            marketing_spend=mkt_out.budget_spent,
            marketing_quality=mkt_out.quality_score,
            product_quality=prod_out.quality_score,
            sales_effort=sales_out.outreach_effort,
            crm_retention_effort=crm_out.retention_effort,
        )
        sim_result = simulator.run_cycle(exec_output)
        log_decision(DecisionRecord(cycle, "simulator", exec_output.__dict__, sim_result.__dict__))

        report = analytics.summarize(cycle, sim_result, leads=sim_result.leads_generated)
        log_decision(DecisionRecord(cycle, "analytics", sim_result.__dict__, report.__dict__))

        print(report.summary)
        previous_summary = report.summary
        previous_churn_rate = report.churn_rate
        previous_leads = sim_result.leads_generated


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Flywheel business cycles")
    parser.add_argument("--cycles", type=int, default=1, help="number of cycles to run")
    args = parser.parse_args()
    run(args.cycles)
