"""Main cycle loop: Strategy -> Finance -> [Marketing, Product, Sales, CRM]
(parallel) -> Market Simulator -> Analytics -> next cycle's Strategy input.

Run with: python orchestration/cycle.py --cycles 5
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

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


def run(num_cycles: int) -> None:
    strategy = StrategyAgent()
    finance = FinanceAgent(total_budget_per_cycle=TOTAL_BUDGET_PER_CYCLE)
    marketing = MarketingAgent()
    product = ProductAgent()
    sales = SalesAgent()
    crm = CRMAgent()
    analytics = AnalyticsAgent()
    simulator = MarketSimulator(seed=SIM_SEED)

    previous_summary = None

    for cycle in range(1, num_cycles + 1):
        print(f"\n=== Cycle {cycle} ===")

        decision = strategy.decide(cycle, previous_summary)
        log_decision(DecisionRecord(cycle, "strategy", {"previous_summary": previous_summary}, decision.__dict__))

        allocation = finance.allocate(cycle, decision.priorities)
        log_decision(DecisionRecord(cycle, "finance", {"priorities": decision.priorities}, allocation.__dict__))

        mkt_out = marketing.execute(cycle, allocation.marketing, decision.positioning)
        prod_out = product.execute(cycle, allocation.product)
        sales_out = sales.execute(cycle, allocation.sales, leads=0)  # leads unknown pre-simulation
        crm_out = crm.execute(cycle, allocation.crm)
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Flywheel business cycles")
    parser.add_argument("--cycles", type=int, default=1, help="number of cycles to run")
    args = parser.parse_args()
    run(args.cycles)
