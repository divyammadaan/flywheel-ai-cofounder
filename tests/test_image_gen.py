"""Tests for ad image generation.

No network: the point is the contract around failure, since image generation
is explicitly allowed to fail without failing a business cycle.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
import pytest

from tools import image_gen


class _FakeResponse:
    def __init__(self, content=b"", content_type="image/jpeg", status=200):
        self.content = content
        self.headers = {"content-type": content_type}
        self._status = status

    def raise_for_status(self):
        if self._status >= 400:
            raise httpx.HTTPStatusError("boom", request=None, response=None)


def test_writes_image_and_returns_path(tmp_path, monkeypatch):
    monkeypatch.setattr(image_gen.httpx, "get", lambda *a, **k: _FakeResponse(b"\xff\xd8fake-jpeg"))
    path = image_gen.generate_ad_image("a cake", cycle=3, out_dir=tmp_path)
    assert path is not None
    assert Path(path).exists()
    assert Path(path).name == "cycle_3.jpg"
    assert Path(path).read_bytes() == b"\xff\xd8fake-jpeg"


def test_returns_none_when_service_errors(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise httpx.ConnectError("service down")

    monkeypatch.setattr(image_gen.httpx, "get", boom)
    assert image_gen.generate_ad_image("a cake", cycle=1, out_dir=tmp_path) is None


def test_returns_none_when_response_is_not_an_image(tmp_path, monkeypatch):
    """The service answers 200 with an HTML error page under load, so a 200
    status alone isn't enough to trust the body."""
    monkeypatch.setattr(
        image_gen.httpx,
        "get",
        lambda *a, **k: _FakeResponse(b"<html>rate limited</html>", content_type="text/html"),
    )
    assert image_gen.generate_ad_image("a cake", cycle=1, out_dir=tmp_path) is None


def test_failure_leaves_no_partial_file_behind(tmp_path, monkeypatch):
    monkeypatch.setattr(
        image_gen.httpx,
        "get",
        lambda *a, **k: _FakeResponse(b"<html>nope</html>", content_type="text/html"),
    )
    image_gen.generate_ad_image("a cake", cycle=7, out_dir=tmp_path)
    assert not (tmp_path / "cycle_7.jpg").exists()


def test_prompt_is_url_encoded(tmp_path, monkeypatch):
    """Prompts are free text from an LLM -- spaces, commas and quotes must
    not produce a malformed URL."""
    seen = {}

    def capture(url, **kwargs):
        seen["url"] = url
        return _FakeResponse(b"img")

    monkeypatch.setattr(image_gen.httpx, "get", capture)
    image_gen.generate_ad_image('a cake, "fancy" & bright', cycle=1, out_dir=tmp_path)
    assert " " not in seen["url"]
    assert '"' not in seen["url"]
