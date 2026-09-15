"""Validate flow -- the founder's front door for a NEW idea, end to end.

    Intake -> Market Research (web search) -> clarifying Q&A -> Founder Advisor
      -> (GO/PIVOT) Company Formation plan
      -> launch plan: Strategy -> Finance -> [Marketing, Sales, Product]
      -> Funding roadmap -> launch page (data/site/index.html)

No simulator, Analytics or CRM here: the business hasn't launched, so there's
nothing to measure and no customers yet. For an operating business, use
orchestration/review_flow.py instead.

Run interactively:
    python orchestration/validate_flow.py --capital 1500000 --currency INR

With running costs, so Finance can hold back a reserve and work out break-even:
    python orchestration/validate_flow.py --capital 1500000 --fixed-costs 100000 --unit-cost 350

Run scripted (for demos -- answers are consumed in the order Market Research
asks its questions, so they can land mismatched if the model reorders them;
interactive mode is the honest experience):
    python orchestration/validate_flow.py --pitch "..." --capital 1500000 --answers "a,b,c"

Skip stages to save API calls / time:
    --skip-formation --skip-funding

Each run starts a fresh Decision Record history (data/flywheel.db). Identical
inputs reuse saved model answers (data/llm_cache); set FLYWHEEL_LLM_CACHE=0 to
force fresh calls.
"""

import argparse
import sys
from dataclasses import asdict
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

from agents._cash import DEFAULT_RUNWAY_MONTHS
from agents._money import SUPPORTED_CURRENCIES, fmt_money
from agents.company_formation import CompanyFormationAgent
from agents.founder_advisor import FounderAdvisorAgent
from agents.intake import IntakeAgent
from agents.market_research import MarketResearchAgent
from observability.decision_record import DecisionRecord, log_decision, reset_records
from observability.usage import usage_summary
from orchestration.cycle import PRECYCLE, PlanBlocked, run_funding, run_launch_plan
from orchestration.report import print_funding, print_plan, print_sources, print_usage, rule
from tools.landing_page import write_landing_page


def validate(
    raw_pitch: str,
    capital: float,
    currency: str,
    monthly_fixed_costs: float | None = None,
    unit_cost: float | None = None,
    runway_months: int = DEFAULT_RUNWAY_MONTHS,
    scripted_answers: list[str] | None = None,
    skip_formation: bool = False,
    skip_funding: bool = False,
) -> None:
    reset_records()

    rule("INTAKE")
    business = IntakeAgent().process(raw_pitch)
    # Money comes from the founder directly, never from the model's reading
    # of the pitch.
    business.currency = currency
    business.starting_capital = capital
    business.monthly_fixed_costs = monthly_fixed_costs
    business.unit_cost = unit_cost
    business.runway_months = runway_months
    log_decision(DecisionRecord(PRECYCLE, "intake", {"raw_input": raw_pitch}, business.__dict__))
    print(f"Summary : {business.business_summary}")
    print(f"Industry: {business.industry} ({business.offering_type})")
    print(f"Region  : {business.target_region}")
    print(f"Mode    : {business.mode}")
    print(f"Capital : {fmt_money(capital, currency)}")

    if business.mode == "existing_business":
        print("\nThis sounds like an existing business. Its plan should come from your real numbers,")
        print("so run orchestration/review_flow.py instead.")
        return

    rule("MARKET RESEARCH")
    report = MarketResearchAgent().research(business)
    log_decision(DecisionRecord(PRECYCLE, "market_research", business.__dict__, report.__dict__))
    print(f"Market size  : {report.market_size_estimate}\n")
    print(f"Competitors  : {report.key_competitors}\n")
    print(f"Opportunities: {report.opportunities}\n")
    print(f"Risks        : {report.risks}")
    print_sources(report.sources)

    rule("CLARIFYING QUESTIONS")
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

    rule("FOUNDER ADVISOR")
    decision = FounderAdvisorAgent().decide(business, report, qa_answers)
    log_decision(DecisionRecord(PRECYCLE, "founder_advisor", {"qa_answers": qa_answers}, decision.__dict__))
    print(f"VERDICT: {decision.verdict}\n")
    print(f"{decision.rationale}")

    if decision.verdict == "NO_GO":
        print("\nAdvisor recommends NO-GO. Stopping here rather than building a launch plan.")
        print_usage(usage_summary())
        return

    print(f"\nSeed plan: '{decision.seed_positioning}' at {fmt_money(decision.seed_price, currency)} {decision.seed_price_unit}")
    print(f"Seed budget priorities: {decision.seed_priorities}")

    if not skip_formation:
        rule("COMPANY FORMATION")
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

    try:
        plan = run_launch_plan(business, report, decision, qa_answers)
    except PlanBlocked as blocked:
        rule("PLAN BLOCKED")
        print(blocked)
        print_usage(usage_summary())
        return
    print_plan(plan)

    page = write_landing_page(asdict(business), asdict(plan.strategy), asdict(plan.marketing))
    print(f"\nLaunch page: {page}")

    if not skip_funding:
        print_funding(run_funding(business, plan))

    print_usage(usage_summary())


def _ask_capital(currency: str) -> float:
    while True:
        raw = input(f"Capital you can put into the launch ({currency}): ").replace(",", "").strip()
        try:
            value = float(raw)
        except ValueError:
            continue
        if value > 0:
            return value


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Validate a new business idea, then build its launch plan")
    parser.add_argument("--pitch", type=str, default=None, help="raw pitch text (interactive prompt if omitted)")
    parser.add_argument("--capital", type=float, default=None, help="capital you can put into the launch")
    parser.add_argument("--currency", choices=SUPPORTED_CURRENCIES, default="INR")
    parser.add_argument("--fixed-costs", type=float, default=None, help="monthly fixed costs (rent, salaries, subscriptions)")
    parser.add_argument("--unit-cost", type=float, default=None, help="cost to deliver one unit of what you sell")
    parser.add_argument("--runway-months", type=int, default=DEFAULT_RUNWAY_MONTHS, help="months of fixed costs to keep in reserve")
    parser.add_argument("--answers", type=str, default=None, help="comma-separated scripted answers, in order")
    parser.add_argument("--skip-formation", action="store_true", help="skip the company formation stage")
    parser.add_argument("--skip-funding", action="store_true", help="skip the funding roadmap")
    args = parser.parse_args()

    pitch = args.pitch or input("Describe your business idea: ")
    capital = args.capital if args.capital and args.capital > 0 else _ask_capital(args.currency)
    answers = args.answers.split(",") if args.answers else None
    validate(
        pitch,
        capital,
        args.currency,
        monthly_fixed_costs=args.fixed_costs,
        unit_cost=args.unit_cost,
        runway_months=args.runway_months,
        scripted_answers=answers,
        skip_formation=args.skip_formation,
        skip_funding=args.skip_funding,
    )
