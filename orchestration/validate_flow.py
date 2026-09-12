"""Validate flow -- the founder's front door, end to end.

    Intake -> Market Research -> clarifying Q&A -> Founder Advisor verdict
      -> (GO/PIVOT) Company Formation plan
      -> execution engine cycles
      -> Funding assessment grounded in the engine's real KPIs

Run interactively:
    python orchestration/validate_flow.py --cycles 3

Run scripted (for demos -- answers are consumed in the order Market Research
asks its questions, so they can land mismatched if the model reorders them;
interactive mode is the honest experience):
    python orchestration/validate_flow.py --pitch "..." --answers "a,b,c" --cycles 3

Skip stages to save API calls / time:
    --skip-formation --skip-funding
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Windows consoles default to cp1252, which cannot encode characters the
# models emit constantly (arrows, em-dashes, currency symbols, smart
# quotes) -- printing one raises UnicodeEncodeError and kills the run
# mid-report. errors="replace" keeps output flowing even on a terminal
# that still can't render a given glyph.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv

load_dotenv()

from agents.company_formation import CompanyFormationAgent
from agents.founder_advisor import FounderAdvisorAgent
from agents.funding import FundingAgent
from agents.intake import IntakeAgent
from agents.market_research import MarketResearchAgent
from observability.decision_record import DecisionRecord, get_records, log_decision
from orchestration.cycle import run as run_cycles

# Pre-cycle agents log under cycle 0 -- there's no business cycle yet, just
# the validation gate before one starts.
PRECYCLE = 0


def _rule(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


def kpi_history() -> list[dict]:
    """Pull the engine's measured KPIs back out of the Decision Records so
    Funding reasons over what actually happened, not a fresh guess."""
    history = []
    for r in get_records(agent="analytics"):
        d = json.loads(r["decision"])
        history.append(
            {
                "cycle": d["cycle"],
                "revenue": d["revenue"],
                "conversion_rate": d["conversion_rate"],
                "cac": d["cac"],
                "churn_rate": d["churn_rate"],
            }
        )
    return sorted(history, key=lambda k: k["cycle"])


def validate(
    raw_pitch: str,
    num_cycles: int,
    scripted_answers: list[str] | None = None,
    skip_formation: bool = False,
    skip_funding: bool = False,
) -> None:
    _rule("INTAKE")
    business = IntakeAgent().process(raw_pitch)
    log_decision(DecisionRecord(PRECYCLE, "intake", {"raw_input": raw_pitch}, business.__dict__))
    print(f"Summary : {business.business_summary}")
    print(f"Industry: {business.industry}")
    print(f"Region  : {business.target_region}")
    print(f"Mode    : {business.mode}")
    if business.existing_metrics:
        print(f"Financials: {business.existing_metrics}")

    _rule("MARKET RESEARCH")
    report = MarketResearchAgent().research(business)
    log_decision(DecisionRecord(PRECYCLE, "market_research", business.__dict__, report.__dict__))
    print(f"Market size  : {report.market_size_estimate}\n")
    print(f"Competitors  : {report.key_competitors}\n")
    print(f"Opportunities: {report.opportunities}\n")
    print(f"Risks        : {report.risks}")

    _rule("CLARIFYING QUESTIONS")
    qa_answers = {}
    for i, question in enumerate(report.clarifying_questions):
        if scripted_answers is not None and i < len(scripted_answers):
            answer = scripted_answers[i]
            print(f"Q: {question}\nA: {answer}  [scripted]\n")
        else:
            print(f"Q: {question}")
            answer = input("A: ")
            print()
        qa_answers[question] = answer

    _rule("FOUNDER ADVISOR")
    decision = FounderAdvisorAgent().decide(business, report, qa_answers)
    log_decision(DecisionRecord(PRECYCLE, "founder_advisor", {"qa_answers": qa_answers}, decision.__dict__))
    print(f"VERDICT: {decision.verdict}\n")
    print(f"{decision.rationale}")

    if decision.verdict == "NO_GO":
        print("\nAdvisor recommends NO-GO. Stopping here rather than running the engine.")
        return

    print(f"\nSeed plan: '{decision.seed_positioning}' at ${decision.seed_pricing:.2f}")
    print(f"Seed budget priorities: {decision.seed_priorities}")

    if not skip_formation:
        _rule("COMPANY FORMATION")
        formation = CompanyFormationAgent().plan(business)
        log_decision(DecisionRecord(PRECYCLE, "company_formation", business.__dict__, formation.__dict__))
        print(f"Recommended entity: {formation.recommended_entity}")
        print(f"Why              : {formation.entity_rationale}\n")
        print(f"Registration steps:\n{formation.registration_steps}\n")
        print(f"Licences/permits :\n{formation.licenses_and_permits}\n")
        print(f"Tax registrations:\n{formation.tax_registrations}\n")
        print(f"Estimated cost   : {formation.estimated_cost}")
        print(f"Estimated timeline: {formation.estimated_timeline}\n")
        print(f"!! {formation.disclaimer}")

    seed_context = (
        f"Market Research found: {report.market_size_estimate} Competitors: {report.key_competitors} "
        f"Opportunities: {report.opportunities} Risks: {report.risks}\n"
        f"Founder Advisor verdict: {decision.verdict} -- {decision.rationale}\n"
        f"Recommended starting plan: positioning '{decision.seed_positioning}' at "
        f"${decision.seed_pricing:.2f}, budget priorities {decision.seed_priorities}."
    )

    _rule(f"EXECUTION ENGINE ({num_cycles} cycle(s))")
    run_cycles(num_cycles, initial_context=seed_context)

    if not skip_funding:
        _rule("FUNDING ASSESSMENT")
        funding = FundingAgent().assess(business, kpi_history())
        log_decision(DecisionRecord(PRECYCLE, "funding", {"kpi_history": kpi_history()}, funding.__dict__))
        print(f"Readiness: {funding.readiness}\n")
        print(f"{funding.readiness_rationale}\n")
        print(f"Timing           : {funding.recommended_timing}\n")
        print(f"Metrics to hit   : {funding.metrics_to_hit}\n")
        print(f"Investor profile : {funding.investor_profile}\n")
        print(f"Alternatives     : {funding.alternative_funding}\n")
        print(f"Pitch deck outline:\n{funding.pitch_deck_outline}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Validate a business idea, then run the engine")
    parser.add_argument("--pitch", type=str, default=None, help="raw pitch text (interactive prompt if omitted)")
    parser.add_argument("--cycles", type=int, default=3, help="engine cycles to run after a GO/PIVOT")
    parser.add_argument("--answers", type=str, default=None, help="comma-separated scripted answers, in order")
    parser.add_argument("--skip-formation", action="store_true", help="skip the company formation stage")
    parser.add_argument("--skip-funding", action="store_true", help="skip the funding assessment stage")
    args = parser.parse_args()

    pitch = args.pitch or input("Describe your business idea (or existing business): ")
    answers = args.answers.split(",") if args.answers else None
    validate(
        pitch,
        args.cycles,
        scripted_answers=answers,
        skip_formation=args.skip_formation,
        skip_funding=args.skip_funding,
    )
