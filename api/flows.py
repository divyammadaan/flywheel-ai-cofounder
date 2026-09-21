"""The two founder journeys, as background jobs.

No planning logic lives here. Each function drives the same
`orchestration/` entry points the CLIs use, and adds two things the CLIs do
not need: progress events, and the ability to stop halfway and resume.

**Why the new-idea flow is split in two.** Market Research decides what it
still needs to know, and the Founder Advisor cannot rule until the founder has
answered. That pause can last minutes or days, so the second half is a
separate request. Nothing is held in memory between them: `resume_new_idea`
rebuilds the business and the research report out of the run's own Decision
Records, which is what makes a plan survive a reload, a new tab, or a server
restart.
"""

from dataclasses import asdict

import pandas as pd

from agents.analytics import PeriodMetrics
from agents.company_formation import CompanyFormationAgent
from agents.founder_advisor import AdvisorDecision, FounderAdvisorAgent
from agents.intake import BusinessInput, IntakeAgent
from agents.market_research import MarketResearchAgent, MarketResearchReport
from api.jobs import Progress, as_payload
from observability.decision_record import DecisionRecord, log_decision
from orchestration.cycle import (
    PRECYCLE,
    next_review_cycle,
    run_business_review,
    run_funding,
    run_launch_plan,
)
from storage import fetch_records, update_run

NO_GO = "NO_GO"


# ------------------------------------------------------------- new idea --


def start_new_idea(
    run_id: int,
    pitch: str,
    currency: str,
    starting_capital: float,
    monthly_fixed_costs: float | None,
    unit_cost: float | None,
    runway_months: int,
) -> None:
    """Intake and Market Research, then stop and ask the founder."""
    progress = Progress(run_id)

    with progress.step("intake", "Reading your idea"):
        business = IntakeAgent().process(pitch)
        # Money always comes from the founder, never from the model's reading
        # of the pitch.
        business.currency = currency
        business.starting_capital = starting_capital
        business.monthly_fixed_costs = monthly_fixed_costs
        business.unit_cost = unit_cost
        business.runway_months = runway_months
        log_decision(DecisionRecord(PRECYCLE, "intake", {"raw_input": pitch}, business.__dict__))
        update_run(run_id, mode=business.mode, label=business.business_summary)

    with progress.step("market_research", "Researching the market"):
        report = MarketResearchAgent().research(business)
        log_decision(DecisionRecord(PRECYCLE, "market_research", business.__dict__, report.__dict__))

    # Event first, then status -- see the invariant in api/jobs.submit.
    progress.event(
        "awaiting_answers",
        message="A few questions before a verdict",
        payload={"questions": report.clarifying_questions},
    )
    update_run(run_id, status="awaiting_answers")


def resume_new_idea(
    run_id: int,
    answers: dict[str, str],
    include_formation: bool = True,
    include_funding: bool = True,
) -> None:
    """The verdict and, unless it is NO_GO, the launch plan."""
    progress = Progress(run_id)
    update_run(run_id, status="running")

    business = _business_from_records(run_id)
    report = _research_from_records(run_id)

    with progress.step("founder_advisor", "Weighing it up"):
        decision = FounderAdvisorAgent().decide(business, report, answers)
        log_decision(DecisionRecord(PRECYCLE, "founder_advisor", {"qa_answers": answers}, decision.__dict__))

    if decision.verdict == NO_GO:
        # A NO_GO is the product working: it stops the founder spending money
        # on a bad idea. It ends the run successfully, not as a failure.
        progress.event(
            "finished",
            message="The advisor ruled NO-GO, so there is no launch plan.",
            payload={"verdict": decision.verdict},
        )
        update_run(run_id, status="done")
        return

    if include_formation:
        with progress.step("company_formation", "Working out how to incorporate"):
            formation = CompanyFormationAgent().plan(business)
            log_decision(
                DecisionRecord(PRECYCLE, "company_formation", business.__dict__, formation.__dict__)
            )

    with progress.step("planning", "Building the launch plan"):
        plan = run_launch_plan(business, report, decision, answers)

    if include_funding:
        with progress.step("funding", "Mapping the road to funding"):
            run_funding(business, plan)

    progress.event("finished", message="Your launch plan is ready.")
    update_run(run_id, status="done")


# --------------------------------------------------- existing business --


def start_business_review(
    run_id: int,
    description: str,
    currency: str,
    metrics: PeriodMetrics,
    budget: float,
    orders: pd.DataFrame | None,
    include_funding: bool = True,
) -> None:
    progress = Progress(run_id)

    with progress.step("intake", "Reading your business"):
        business = IntakeAgent().process(description)
        business.mode = "existing_business"
        business.currency = currency
        business.existing_metrics = asdict(metrics)
        log_decision(DecisionRecord(PRECYCLE, "intake", {"raw_input": description}, business.__dict__))
        update_run(run_id, mode=business.mode, label=business.business_summary)

    cycle = next_review_cycle()
    with progress.step("planning", "Reading your numbers and planning the period"):
        plan = run_business_review(business, metrics, budget, cycle, orders)

    if include_funding:
        with progress.step("funding", "Mapping the road to funding"):
            run_funding(business, plan)

    progress.event("finished", message="Your plan is ready.")
    update_run(run_id, status="done")


# ------------------------------------------------------------- helpers --


def _record(run_id: int, agent: str) -> dict:
    records = fetch_records(agent=agent, run_id=run_id, as_json_text=False)
    if not records:
        raise LookupError(f"this run has no {agent} record yet")
    return records[-1]["decision"]


def _business_from_records(run_id: int) -> BusinessInput:
    """Rebuild the founder's business from what Intake recorded.

    Reconstructed rather than cached in memory, so the second half of a
    new-idea run works after a server restart or from a different process.
    """
    data = _record(run_id, "intake")
    fields = {f for f in BusinessInput.__dataclass_fields__}
    return BusinessInput(**{k: v for k, v in data.items() if k in fields})


def _research_from_records(run_id: int) -> MarketResearchReport:
    data = _record(run_id, "market_research")
    fields = {f for f in MarketResearchReport.__dataclass_fields__}
    return MarketResearchReport(**{k: v for k, v in data.items() if k in fields})


def advisor_from_records(run_id: int) -> AdvisorDecision | None:
    records = fetch_records(agent="founder_advisor", run_id=run_id, as_json_text=False)
    if not records:
        return None
    data = records[-1]["decision"]
    fields = {f for f in AdvisorDecision.__dataclass_fields__}
    return AdvisorDecision(**{k: v for k, v in data.items() if k in fields})


__all__ = [
    "as_payload",
    "resume_new_idea",
    "start_business_review",
    "start_new_idea",
]
