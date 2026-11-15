"""The plan as one validated object, with JSON and Markdown exports."""

import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.main import app
from observability.decision_record import DecisionRecord, log_decision, reset_records
from orchestration.final_plan import FinalPlan, build_final_plan, to_markdown
from storage import update_run


def _rec(cycle, agent, decision, snapshot=None):
    log_decision(DecisionRecord(cycle, agent, snapshot or {}, decision))


def _run_with_a_plan():
    run = reset_records()
    update_run(run, mode="new_idea", label="Filter coffee in Bangalore", status="done")
    _rec(0, "intake", {"mode": "new_idea", "business_summary": "Filter coffee", "industry": "F&B", "currency": "INR", "raw_input": "secret pitch"})
    _rec(0, "founder_advisor", {"verdict": "PIVOT", "rationale": ["Narrow the niche."], "seed_positioning": "x", "seed_price": 899, "seed_price_unit": "per month", "seed_priorities": {"marketing": 0.5}})
    _rec(1, "strategy_rejected", {}, {"attempt": 1, "problems": ["The price must be above zero."]})
    _rec(1, "strategy", {"positioning": "Fresh", "target_customer": "Professionals", "price": 899.0, "price_unit": "per month", "priorities": {"marketing": 0.5}, "rationale": ["why"]})
    _rec(1, "finance", {"total_budget": 900000.0, "marketing": 360000.0, "product": 270000.0, "sales": 270000.0, "crm": 0.0, "rationale": "split", "health": {}})
    _rec(1, "marketing", {"budget": 360000.0, "campaigns": [{"channel": "Instagram", "where": "Bangalore", "ad_format": "reel", "objective": "sign-ups", "duration": "4 weeks", "budget": 100000.0}],
                          "ad_copy": "Fresh coffee", "image_prompt": "cup", "ad_image_path": "C:/server/data/ads/cycle_1.jpg", "budget_adjusted": False})
    _rec(1, "marketing", {"budget": 360000.0, "campaigns": [], "ad_copy": "Revised copy", "image_prompt": "cup", "ad_image_path": None})
    return run


def test_the_plan_is_gathered_into_one_validated_model():
    run = _run_with_a_plan()
    plan = build_final_plan(run)
    assert isinstance(plan, FinalPlan)
    assert plan.mode == "new_idea" and plan.status == "done" and plan.cycle == 1 and plan.currency == "INR"
    assert plan.verdict.verdict == "PIVOT" and plan.strategy.price == 899.0
    assert plan.finance.total_budget == 900000.0
    assert plan.sales is None and plan.crm is None  # not produced in this run: absent, not invented


def test_the_newest_record_wins_and_the_revision_is_recorded():
    plan = build_final_plan(_run_with_a_plan())
    assert plan.marketing.ad_copy == "Revised copy"
    revised = {p.agent: p.revised for p in plan.provenance}
    assert revised["marketing"] is True and revised["strategy"] is False


def test_nothing_private_or_server_specific_leaks_into_the_export():
    plan = build_final_plan(_run_with_a_plan())
    dumped = plan.model_dump_json()
    assert "secret pitch" not in dumped  # the founder's raw text is not exported
    assert "C:/server" not in dumped and "ad_image_path" not in dumped


def test_checks_that_sent_a_draft_back_are_listed():
    plan = build_final_plan(_run_with_a_plan())
    assert plan.guardrail_rejections == ["Strategy: The price must be above zero."]


def test_a_run_in_progress_is_a_valid_partial_plan():
    run = reset_records()
    update_run(run, mode="new_idea", status="running")
    plan = build_final_plan(run)
    assert plan.strategy is None and plan.provenance == []
    assert FinalPlan.model_validate_json(plan.model_dump_json()).run_id == run


def test_markdown_has_tables_and_the_provenance_trail():
    md = to_markdown(build_final_plan(_run_with_a_plan()))
    assert "## Budget" in md and "| Area | Amount | Share |" in md
    assert "## Provenance" in md and "marketing" in md
    assert "Revised copy" in md


def test_the_api_serves_the_plan_as_json_and_markdown():
    with TestClient(app) as client:
        run = _run_with_a_plan()
        as_json = client.get(f"/runs/{run}/plan.json")
        assert as_json.status_code == 200
        assert FinalPlan.model_validate(as_json.json()).run_id == run
        md = client.get(f"/runs/{run}/plan.md?download=true")
        assert md.status_code == 200 and "attachment" in md.headers["content-disposition"]
        assert md.text.startswith("# Filter coffee in Bangalore")
        assert client.get("/runs/999999/plan.json").status_code == 404
