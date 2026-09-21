"""Redoing one agent's output on the founder's own instruction.

Every execution agent is stubbed -- these tests are about what
`refine_execution_agent` does around the model call (reconstructing the
brief, keeping history, rejecting the wrong agent), not what a real model
says. `conftest.py`'s autouse fixture gives each test its own database.
"""

import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents._brief import LAUNCH, PlanBrief
from observability.decision_record import DecisionRecord, log_decision
from orchestration import cycle
from storage import start_run


def seed_business(mode: str = "new_idea", currency: str = "INR") -> None:
    from agents.intake import BusinessInput

    business = BusinessInput(
        mode=mode,
        business_summary="A filter-coffee subscription in Bangalore",
        industry="F&B",
        product_or_service="filter coffee subscriptions",
        target_region="Bangalore, India",
        currency=currency,
        starting_capital=1500000.0,
    )
    log_decision(DecisionRecord(cycle.PRECYCLE, "intake", {}, business.__dict__))


def seed_brief_record(cycle_num: int, agent: str, budget: float, decision: dict, extra_snapshot: dict | None = None) -> None:
    brief = PlanBrief(
        cycle=cycle_num,
        mode=LAUNCH,
        business_summary="A filter-coffee subscription in Bangalore",
        industry="F&B",
        product_or_service="filter coffee subscriptions",
        region="Bangalore, India",
        currency="INR",
        positioning="Roast-to-order coffee for busy professionals",
        target_customer="Working professionals, 25-40",
        price=899.0,
        price_unit="per month",
        context="Some prior context the original call was given.",
    )
    snapshot = {"budget": budget, "brief": asdict(brief), **(extra_snapshot or {})}
    log_decision(DecisionRecord(cycle_num, agent, snapshot, decision))


@dataclass
class FakeSales:
    cycle: int = 1
    budget: float = 50000.0
    currency: str = "INR"
    lead_sources: list = field(default_factory=list)
    conversion_process: list = field(default_factory=list)
    budget_adjusted: bool = False


def test_refining_an_agent_keeps_the_old_record_and_adds_a_new_one(monkeypatch):
    start_run()
    seed_brief_record(1, "sales", 50000.0, asdict(FakeSales(lead_sources=[{"where": "old"}])))

    seen_briefs = []

    def fake_execute(self, brief, budget):
        seen_briefs.append(brief)
        return FakeSales(budget=budget, lead_sources=[{"where": "free channels only"}])

    monkeypatch.setattr(cycle, "SalesAgent", type("S", (), {"execute": fake_execute}))

    result = cycle.refine_execution_agent(1, "sales", "Only free channels, please.")

    assert result.lead_sources == [{"where": "free channels only"}]
    # The feedback reaches the model as part of the brief's context, not as
    # a side channel it could silently ignore.
    assert "Only free channels" in seen_briefs[0].context
    # And the founder's original context is still in there -- refine adds to
    # the brief, it doesn't replace it.
    assert "Some prior context" in seen_briefs[0].context

    records = cycle.get_records(cycle=1, agent="sales")
    assert len(records) == 2, "the original record must survive, not be overwritten"


def test_the_new_record_is_what_the_ui_treats_as_current():
    """toPlan() on the front end takes the LAST record for an agent as
    current -- so a refine only has to log a new row for this to work; no
    other change is needed to make the redone version "the" plan."""
    start_run()
    seed_brief_record(1, "sales", 50000.0, {"note": "original"})
    log_decision(DecisionRecord(1, "sales", {"budget": 50000.0, "brief": {}}, {"note": "refined"}))

    records = cycle.get_records(cycle=1, agent="sales")
    import json

    assert json.loads(records[-1]["decision"])["note"] == "refined"


def test_an_agent_that_feeds_the_rest_of_the_plan_cannot_be_refined_directly():
    start_run()
    seed_brief_record(1, "strategy", 0.0, {"positioning": "x"})

    with pytest.raises(cycle.RefineError, match="strategy can't be refined"):
        cycle.refine_execution_agent(1, "strategy", "Reposition it.")


def test_blank_feedback_is_rejected_before_any_model_call(monkeypatch):
    start_run()
    seed_brief_record(1, "sales", 50000.0, asdict(FakeSales()))

    called = []
    monkeypatch.setattr(
        cycle, "SalesAgent", type("S", (), {"execute": lambda self, b, bud: called.append(1)})
    )

    with pytest.raises(cycle.RefineError, match="Say what you'd like changed"):
        cycle.refine_execution_agent(1, "sales", "   ")

    assert not called


def test_refining_an_agent_with_no_prior_record_fails_clearly():
    start_run()
    with pytest.raises(cycle.RefineError, match="no sales plan yet"):
        cycle.refine_execution_agent(1, "sales", "Cut the budget in half.")


def test_crm_refine_reuses_the_segments_from_its_own_last_record(monkeypatch):
    """CRM's segments are computed from the founder's order file, not
    something a refine should ever have to recompute -- they come straight
    back out of the prior CRM record."""
    start_run()
    fake_segments = {"customers": 300, "segments": {"best": {"customers": 40}}}
    seed_brief_record(1, "crm", 20000.0, {"segments": fake_segments, "actions": {}})

    seen = {}

    @dataclass
    class FakeCrmOut:
        segments: dict
        actions: dict

    def fake_execute(self, brief, budget, segments, previous):
        seen["segments"] = segments
        return FakeCrmOut(segments=segments, actions={"best": "say thanks"})

    monkeypatch.setattr(cycle, "CRMAgent", type("C", (), {"execute": fake_execute}))

    cycle.refine_execution_agent(1, "crm", "Be warmer in tone.")

    assert seen["segments"] == fake_segments


def test_marketing_refine_records_which_transport_was_used(monkeypatch):
    start_run()
    seed_brief_record(1, "marketing", 100000.0, {"campaigns": [], "ad_copy": "old copy"}, {"transport": "direct"})

    @dataclass
    class FakeMarketingOut:
        campaigns: list
        ad_copy: str

    fake_output = FakeMarketingOut(campaigns=[], ad_copy="new, punchier copy")
    monkeypatch.setattr(cycle, "request_marketing", lambda brief, budget: (fake_output, "direct"))

    result = cycle.refine_execution_agent(1, "marketing", "Make the copy punchier.")

    assert result.ad_copy == "new, punchier copy"
    records = cycle.get_records(cycle=1, agent="marketing")
    import json

    assert json.loads(records[-1]["input_snapshot"])["transport"] == "direct"


def test_funding_refine_rebuilds_the_business_from_the_intake_record(monkeypatch):
    start_run()
    seed_business()
    seed_brief_record(
        1, "funding", 0.0, {"readiness": "NOT_READY"}, {"plan_summary": "Positioning: x. Price: 899."}
    )

    seen = {}

    @dataclass
    class FakeFundingPlan:
        readiness: str
        readiness_rationale: list
        target_raise_date: str
        warnings: list = field(default_factory=list)

    def fake_assess(self, business, mode, summary, history, feedback):
        seen["business"] = business
        seen["feedback"] = feedback
        return FakeFundingPlan(readiness="READY_PRE_SEED", readiness_rationale=[], target_raise_date="Q1 2028")

    monkeypatch.setattr(cycle, "FundingAgent", type("F", (), {"assess": fake_assess}))
    monkeypatch.setattr(cycle, "funding_problems", lambda plan, currency, price: [])

    cycle.refine_execution_agent(1, "funding", "We're ready sooner than this suggests.")

    assert seen["business"].business_summary == "A filter-coffee subscription in Bangalore"
    assert "ready sooner" in seen["feedback"]
