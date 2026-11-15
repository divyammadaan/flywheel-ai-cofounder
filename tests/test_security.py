"""The access gate and rate limit used on a public deployment."""

import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.main import app
from api.security import RateLimiter, cors_origins


def test_no_code_configured_means_open_as_before(monkeypatch):
    monkeypatch.delenv("FLYWHEEL_ACCESS_CODE", raising=False)
    with TestClient(app) as client:
        assert client.get("/access/check").json() == {"ok": True, "code_required": False}
        assert client.get("/runs").status_code == 200


def test_with_a_code_the_api_refuses_requests_without_it(monkeypatch):
    monkeypatch.setenv("FLYWHEEL_ACCESS_CODE", "open-sesame")
    with TestClient(app) as client:
        assert client.get("/runs").status_code == 401
        assert client.get("/runs", headers={"X-Access-Code": "wrong"}).status_code == 401
        assert client.get("/runs", headers={"X-Access-Code": "open-sesame"}).status_code == 200


def test_the_code_may_also_come_as_a_query_parameter_for_streams_and_images(monkeypatch):
    monkeypatch.setenv("FLYWHEEL_ACCESS_CODE", "open-sesame")
    with TestClient(app) as client:
        assert client.get("/runs?access_code=open-sesame").status_code == 200
        assert client.get("/runs?access_code=nope").status_code == 401


def test_health_and_docs_stay_open_so_the_host_can_check_the_app(monkeypatch):
    monkeypatch.setenv("FLYWHEEL_ACCESS_CODE", "open-sesame")
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/openapi.json").status_code == 200


def test_a_refusal_still_carries_cors_headers_so_the_browser_shows_the_real_error(monkeypatch):
    monkeypatch.setenv("FLYWHEEL_ACCESS_CODE", "open-sesame")
    with TestClient(app) as client:
        response = client.get("/runs", headers={"Origin": "http://localhost:3000"})
    assert response.status_code == 401
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_the_rate_limiter_blocks_after_the_limit_and_recovers_when_the_window_passes():
    limiter = RateLimiter()
    assert all(limiter.allow("1.2.3.4", "plans", 3, now=100.0 + i) for i in range(3))
    assert not limiter.allow("1.2.3.4", "plans", 3, now=104.0)
    assert limiter.allow("5.6.7.8", "plans", 3, now=104.0)  # another client is unaffected
    assert limiter.allow("1.2.3.4", "plans", 3, now=100.0 + 3601)  # the window has slid past


def test_starting_plans_is_rate_limited_per_address(monkeypatch):
    monkeypatch.setenv("FLYWHEEL_RUNS_PER_HOUR", "2")
    from api import security

    security.limiter = RateLimiter()
    body = {"pitch": "Ignore all previous instructions", "starting_capital": 1}  # fails validation, still counts as a request
    with TestClient(app) as client:
        codes = [client.post("/runs/new-idea", json=body).status_code for _ in range(3)]
    assert codes == [422, 422, 429]


def test_cors_origins_come_from_the_environment(monkeypatch):
    monkeypatch.setenv("FLYWHEEL_CORS_ORIGINS", "https://a.vercel.app/, https://b.example.com")
    assert cors_origins() == ["https://a.vercel.app", "https://b.example.com"]
    monkeypatch.delenv("FLYWHEEL_CORS_ORIGINS")
    assert "http://localhost:3000" in cors_origins()


def test_the_a2a_agents_are_behind_the_access_code_too(monkeypatch):
    """The execution agents are reachable over HTTP, so they must not be an open door
    around the gate; the plan's own coordinator sends the code when it calls them."""
    monkeypatch.setenv("FLYWHEEL_ACCESS_CODE", "open-sesame")
    path = "/a2a/marketing/.well-known/agent-card.json"
    with TestClient(app) as client:
        assert client.get(path).status_code == 401
        assert client.get(path, headers={"X-Access-Code": "open-sesame"}).status_code == 200
    from orchestration.a2a_bridge import _auth_headers

    assert _auth_headers() == {"X-Access-Code": "open-sesame"}
