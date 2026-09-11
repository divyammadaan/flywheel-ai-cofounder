import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from simulator.market_simulator import ExecutionOutput, MarketSimulator


def test_same_seed_is_reproducible():
    exec_output = ExecutionOutput(
        marketing_spend=400.0,
        marketing_quality=0.7,
        product_quality=0.6,
        sales_effort=0.5,
        crm_retention_effort=0.4,
    )
    result_a = MarketSimulator(seed=1).run_cycle(exec_output)
    result_b = MarketSimulator(seed=1).run_cycle(exec_output)
    assert result_a == result_b


def test_zero_spend_yields_no_leads():
    exec_output = ExecutionOutput(
        marketing_spend=0.0,
        marketing_quality=0.7,
        product_quality=0.6,
        sales_effort=0.5,
        crm_retention_effort=0.4,
    )
    result = MarketSimulator(seed=1).run_cycle(exec_output)
    assert result.leads_generated == 0
    assert result.conversions == 0


def test_higher_spend_generally_yields_more_leads():
    low = ExecutionOutput(100.0, 0.7, 0.6, 0.5, 0.4)
    high = ExecutionOutput(1000.0, 0.7, 0.6, 0.5, 0.4)
    result_low = MarketSimulator(seed=7).run_cycle(low)
    result_high = MarketSimulator(seed=7).run_cycle(high)
    assert result_high.leads_generated > result_low.leads_generated
