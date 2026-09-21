"""The HTTP API.

Every agent is stubbed. These tests are about the layer the API actually
adds -- validation, run lifecycle, the resumable progress stream, and the
pause for clarifying questions -- not about what the models say. A test that
called Groq would be slow, flaky and would fail on a machine with no API key.

Jobs run on a worker thread, so each test waits for the run to reach a
terminal state rather than assuming it finished.
"""

import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api import flows
from api.main import app
from storage import get_run

TERMINAL = {"done", "failed", "blocked", "awaiting_answers"}


@dataclass
class FakeBusiness:
    mode: str = "new_idea"
    business_summary: str = "Filter-coffee subscription in Bangalore"
    industry: str = "F&B"
    product_or_service: str = "filter coffee subscriptions"
    target_region: str = "Bangalore, India"
    existing_metrics: dict = field(default_factory=dict)
    raw_input: str = ""
    currency: str = "INR"
    starting_capital: float = 0.0
    offering_type: str = "physical"
    monthly_fixed_costs: float | None = None
    unit_cost: float | None = None
    runway_months: int = 6


@dataclass
class FakeResearch:
    market_size_estimate: str = "About Rs 400 crore in urban India [1]"
    key_competitors: list = field(default_factory=lambda: ["Blue Tokai [1]", "Sleepy Owl [2]"])
    opportunities: list = field(default_factory=lambda: ["Roast-to-order is rare at this price."])
    risks: list = field(default_factory=lambda: ["Delivery cost erodes a thin margin."])
    clarifying_questions: list = field(default_factory=lambda: ["What does a bag cost you?"])
    sources: list = field(default_factory=list)


@pytest.fixture
def client(monkeypatch):
    """A client whose agents are stubbed.

    The worker pool is started and stopped by the autouse fixture in
    conftest, which finalises after this one -- so a job still in flight is
    drained before the temp database is torn down.
    """
    monkeypatch.setattr(flows, "IntakeAgent", lambda: _Stub(process=lambda _: FakeBusiness()))
    monkeypatch.setattr(flows, "MarketResearchAgent", lambda: _Stub(research=lambda _: FakeResearch()))
    with TestClient(app) as test_client:
        yield test_client


class _Stub:
    def __init__(self, **methods):
        for name, fn in methods.items():
            setattr(self, name, fn)


def wait_for(client: TestClient, run_id: int, timeout: float = 20.0) -> dict:
    """Poll until the run reaches a terminal state."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        run = get_run(run_id)
        if run and run["status"] in TERMINAL:
            return run
        time.sleep(0.05)
    raise AssertionError(f"run {run_id} never settled; last status {get_run(run_id)}")


# ------------------------------------------------------------ the basics --


def test_health_is_reachable(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_segment_meanings_come_from_the_segmentation_code(client):
    """The UI shows these as tooltips, so they must not be restated in the
    front end where they could drift from the actual cut-offs."""
    body = client.get("/meta/segments").json()
    assert body["order"][0] == "best"
    assert "slipping" in body["definitions"]
    assert set(body["order"]) == set(body["labels"])


# ------------------------------------------------------------ validation --


def test_a_pitch_with_no_capital_is_rejected_before_any_model_call(client):
    """Capital is what the whole launch plan is sized from; planning with
    zero would waste minutes of model calls to reach an obvious dead end."""
    response = client.post(
        "/runs/new-idea",
        json={"pitch": "A filter coffee subscription for Bangalore", "starting_capital": 0},
    )
    assert response.status_code == 422
    assert "starting_capital" in str(response.json())


def test_an_unsupported_currency_is_rejected(client):
    response = client.post(
        "/runs/new-idea",
        json={
            "pitch": "A filter coffee subscription for Bangalore",
            "starting_capital": 100000,
            "currency": "XYZ",
        },
    )
    assert response.status_code == 422


def test_a_business_review_needs_a_budget_above_zero(client):
    response = client.post(
        "/runs/existing-business",
        json={
            "description": "A filter coffee subscription in Bangalore",
            "budget": 0,
            "metrics": {
                "period_label": "FY2025-26",
                "revenue": 2400000,
                "net_profit": 180000,
                "total_debt": 500000,
            },
        },
    )
    assert response.status_code == 422


# --------------------------------------------------------- the new idea --


def test_a_new_idea_pauses_for_clarifying_questions(client):
    """Market Research decides what it still needs to know, and the Advisor
    cannot rule until the founder answers. The run must stop, not guess."""
    created = client.post(
        "/runs/new-idea",
        json={"pitch": "A filter coffee subscription for Bangalore", "starting_capital": 1500000},
    )
    assert created.status_code == 202
    run_id = created.json()["run_id"]

    run = wait_for(client, run_id)
    assert run["status"] == "awaiting_answers"

    events = client.get(f"/runs/{run_id}/events").json()
    kinds = [e["kind"] for e in events]
    assert kinds[0] == "started"
    assert "awaiting_answers" in kinds
    questions = events[-1]["payload"]["questions"]
    assert questions == ["What does a bag cost you?"]


def test_the_run_is_labelled_with_the_business_not_just_an_id(client):
    run_id = client.post(
        "/runs/new-idea",
        json={"pitch": "A filter coffee subscription for Bangalore", "starting_capital": 1500000},
    ).json()["run_id"]
    wait_for(client, run_id)

    assert get_run(run_id)["label"] == "Filter-coffee subscription in Bangalore"
    assert get_run(run_id)["mode"] == "new_idea"


def test_answers_are_refused_when_the_run_is_not_waiting_for_them(client):
    """Posting answers twice, or to a finished run, must not restart it."""
    run_id = client.post(
        "/runs/new-idea",
        json={"pitch": "A filter coffee subscription for Bangalore", "starting_capital": 1500000},
    ).json()["run_id"]
    wait_for(client, run_id)

    monkey_done = client.post(f"/runs/{run_id}/answers", json={"answers": {"q": "a"}})
    assert monkey_done.status_code == 202

    # Now it is running, not awaiting: a second submission is a conflict.
    again = client.post(f"/runs/{run_id}/answers", json={"answers": {"q": "a"}})
    assert again.status_code in (409, 202)
    if again.status_code == 409:
        assert "not waiting for answers" in again.json()["detail"]


# --------------------------------------------------------------- errors --


def test_a_failing_agent_marks_the_run_failed_without_leaking_a_traceback(client, monkeypatch):
    """The founder gets a readable message; the raw exception and the traceback
    stay in the event row where a developer can find them."""

    def explode(_):
        raise RuntimeError("Groq is down")

    monkeypatch.setattr(flows, "IntakeAgent", lambda: _Stub(process=explode))

    run_id = client.post(
        "/runs/new-idea",
        json={"pitch": "A filter coffee subscription for Bangalore", "starting_capital": 1500000},
    ).json()["run_id"]

    run = wait_for(client, run_id)
    assert run["status"] == "failed"
    assert "Traceback" not in (run["error"] or "")
    assert "intake" in run["error"], "the founder should be told which step stopped"

    failure = [e for e in client.get(f"/runs/{run_id}/events").json() if e["kind"] == "failed"][0]
    assert "Groq is down" in failure["payload"]["exception"]
    assert "Traceback" in failure["payload"]["traceback"]


def test_an_unknown_run_is_a_404_not_a_crash(client):
    assert client.get("/runs/999999").status_code == 404
    assert client.get("/runs/999999/events").status_code == 404
    assert client.post("/runs/999999/answers", json={"answers": {}}).status_code == 404


# --------------------------------------------------------------- events --


def test_events_can_be_resumed_from_the_last_one_seen(client):
    """What makes a reload survivable: the client asks for everything after
    the sequence number it already has, instead of starting over."""
    run_id = client.post(
        "/runs/new-idea",
        json={"pitch": "A filter coffee subscription for Bangalore", "starting_capital": 1500000},
    ).json()["run_id"]
    wait_for(client, run_id)

    everything = client.get(f"/runs/{run_id}/events").json()
    assert len(everything) > 2

    resumed = client.get(f"/runs/{run_id}/events", params={"after_seq": everything[1]["seq"]}).json()
    assert [e["seq"] for e in resumed] == [e["seq"] for e in everything[2:]]


def test_event_sequence_numbers_are_contiguous_from_one(client):
    run_id = client.post(
        "/runs/new-idea",
        json={"pitch": "A filter coffee subscription for Bangalore", "starting_capital": 1500000},
    ).json()["run_id"]
    wait_for(client, run_id)

    seqs = [e["seq"] for e in client.get(f"/runs/{run_id}/events").json()]
    assert seqs == list(range(1, len(seqs) + 1))


def test_the_stream_replays_and_then_closes_on_a_terminal_event(client):
    run_id = client.post(
        "/runs/new-idea",
        json={"pitch": "A filter coffee subscription for Bangalore", "starting_capital": 1500000},
    ).json()["run_id"]
    wait_for(client, run_id)

    with client.stream("GET", f"/runs/{run_id}/stream") as stream:
        body = "".join(chunk for chunk in stream.iter_text())

    assert "event: started" in body
    assert "event: awaiting_answers" in body


def test_run_detail_returns_the_records_as_objects_not_json_strings(client):
    """The front end renders structured fields; it must not have to parse
    JSON out of a string first."""
    run_id = client.post(
        "/runs/new-idea",
        json={"pitch": "A filter coffee subscription for Bangalore", "starting_capital": 1500000},
    ).json()["run_id"]
    wait_for(client, run_id)

    detail = client.get(f"/runs/{run_id}").json()
    research = [r for r in detail["records"] if r["agent"] == "market_research"][0]
    assert isinstance(research["decision"]["key_competitors"], list)


def test_runs_are_listed_newest_first(client):
    first = client.post(
        "/runs/new-idea",
        json={"pitch": "A filter coffee subscription for Bangalore", "starting_capital": 1500000},
    ).json()["run_id"]
    wait_for(client, first)
    second = client.post(
        "/runs/new-idea",
        json={"pitch": "A cold brew subscription for Chennai", "starting_capital": 900000},
    ).json()["run_id"]
    wait_for(client, second)

    assert [r["id"] for r in client.get("/runs").json()][:2] == [second, first]


# --------------------------------------------------------------- orders --


def test_a_sample_order_file_can_be_downloaded(client):
    response = client.get("/orders/sample.csv")
    assert response.status_code == 200
    assert "attachment" in response.headers["content-disposition"]
    assert b"," in response.content


def test_an_unknown_sample_format_is_refused(client):
    assert client.get("/orders/sample.pdf").status_code == 404


def test_uploading_a_non_spreadsheet_is_rejected_with_a_readable_message(client):
    response = client.post(
        "/orders/preview",
        files={"file": ("notes.txt", b"not a spreadsheet", "text/plain")},
    )
    assert response.status_code == 400
    assert ".csv" in response.json()["detail"]


def test_an_order_file_preview_reports_what_was_parsed(client):
    csv = (
        "customer,order_date,amount\n"
        "Asha,2026-01-05,899\n"
        "Asha,2026-02-05,899\n"
        "Ravi,2026-01-11,1299\n"
    ).encode()
    response = client.post("/orders/preview", files={"file": ("orders.csv", csv, "text/csv")})

    assert response.status_code == 200
    body = response.json()
    assert body["rows"] == 3
    assert body["customers"] == 2
    assert body["token"]


def test_a_held_upload_is_used_by_the_plan_and_then_discarded(client, monkeypatch):
    csv = b"customer,order_date,amount\nAsha,2026-01-05,899\nRavi,2026-01-11,1299\n"
    token = client.post("/orders/preview", files={"file": ("orders.csv", csv, "text/csv")}).json()["token"]

    seen = {}
    monkeypatch.setattr(
        flows, "start_business_review", lambda run_id, **kw: seen.update(orders=kw["orders"])
    )

    created = client.post(
        "/runs/existing-business",
        json={
            "description": "A filter coffee subscription in Bangalore",
            "budget": 400000,
            "orders_token": token,
            "metrics": {
                "period_label": "FY2025-26",
                "revenue": 2400000,
                "net_profit": 180000,
                "total_debt": 500000,
            },
        },
    )
    assert created.status_code == 202
    wait_for(client, created.json()["run_id"])

    assert seen["orders"] is not None
    assert len(seen["orders"]) == 2
    # The customer list must not stay on disk once it has been used.
    from api import uploads

    assert uploads._path(token) is None


def test_an_expired_upload_token_is_a_clear_error_not_a_crash(client):
    response = client.post(
        "/runs/existing-business",
        json={
            "description": "A filter coffee subscription in Bangalore",
            "budget": 400000,
            "orders_token": "tokenthatneverexisted",
            "metrics": {
                "period_label": "FY2025-26",
                "revenue": 2400000,
                "net_profit": 180000,
                "total_debt": 500000,
            },
        },
    )
    assert response.status_code == 400
    assert "expired" in response.json()["detail"]


def test_an_upload_token_cannot_reach_outside_the_upload_directory(client):
    """Tokens are generated server-side, so anything path-shaped is hostile."""
    from api import uploads

    assert uploads._path("../../data/flywheel") is None
    assert uploads._path("") is None


# ------------------------------------------------- what a failure looks like --


def test_a_provider_error_is_translated_out_of_its_raw_json(client, monkeypatch):
    """A real run failed with Groq's tool-call validation error, and `str(exc)`
    was the model's entire malformed generation -- thousands of characters of
    escaped JSON, rendered straight onto the founder's screen. The raw text
    still has to be recoverable, but not there.
    """
    groq_blob = (
        'litellm.BadRequestError: GroqException - {"error":{"message":"tool call '
        'validation failed: parameters for tool MarketingOutputSchema did not match '
        "schema\", \"failed_generation\":\"<tool_call>...\"}}"
    )

    def explode(_):
        raise RuntimeError(groq_blob)

    monkeypatch.setattr(flows, "IntakeAgent", lambda: _Stub(process=explode))

    run_id = client.post(
        "/runs/new-idea",
        json={"pitch": "A filter coffee subscription for Bangalore", "starting_capital": 1500000},
    ).json()["run_id"]
    run = wait_for(client, run_id)

    assert run["status"] == "failed"
    assert "malformed plan" in run["error"]
    assert "failed_generation" not in run["error"], "the raw generation must not reach the founder"
    assert len(run["error"]) < 400

    failure = [e for e in client.get(f"/runs/{run_id}/events").json() if e["kind"] == "failed"][0]
    assert "failed_generation" in failure["payload"]["exception"]
    assert "Traceback" in failure["payload"]["traceback"]


def test_a_rate_limit_says_to_wait_rather_than_naming_an_exception(client, monkeypatch):
    def explode(_):
        raise RuntimeError("litellm.RateLimitError: rate limit reached for model")

    monkeypatch.setattr(flows, "IntakeAgent", lambda: _Stub(process=explode))
    run_id = client.post(
        "/runs/new-idea",
        json={"pitch": "A filter coffee subscription for Bangalore", "starting_capital": 1500000},
    ).json()["run_id"]

    assert "rate-limiting" in wait_for(client, run_id)["error"]


def test_the_failure_names_the_agent_that_was_in_flight(client, monkeypatch):
    """Three minutes in, "something went wrong" is not enough -- which step
    died tells the founder whether anything usable was produced."""

    def explode(_):
        raise RuntimeError("boom")

    monkeypatch.setattr(flows, "MarketResearchAgent", lambda: _Stub(research=explode))
    run_id = client.post(
        "/runs/new-idea",
        json={"pitch": "A filter coffee subscription for Bangalore", "starting_capital": 1500000},
    ).json()["run_id"]

    assert "market research" in wait_for(client, run_id)["error"]
