"""The Models page, price editing and slot-wait explanation reaching the browser."""

from __future__ import annotations

import json
import re

import pytest
from fastapi.testclient import TestClient

from hutch.models import Bot
from hutch.providers.pricing import PriceBook
from hutch.server.app import create_app
from tests.fakes import FakeOllama


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    s = FakeOllama({"fake:8b": {}, "tiny:1b": {"params": "1B", "size": 500_000_000},
                    "huge:70b": {"params": "70B", "size": 45_000_000_000, "ctx": 131072}})
    monkeypatch.setenv("OLLAMA_HOST", s.url)
    from hutch.runtime.ladder import reset_provider_cache
    reset_provider_cache()
    with TestClient(create_app()) as c:
        c.state_dir = tmp_path / "state"
        yield c
    s.close()


def csrf(c):
    return re.search(r'name="csrf" content="([^"]+)"', c.get("/models").text).group(1)


def test_models_page_renders_every_section(client):
    r = client.get("/models")
    assert r.status_code == 200
    for needle in ("Runtimes and connections", "Installed models", "Task presets on this machine",
                   "Swap cost between models", "Hosted prices", "fake:8b", "Router", "hutch models swap-test"):
        assert needle in r.text, needle
    # The shared sidebar marks the current destination with aria-current only.
    assert re.search(r'<a href="/models"[^>]*aria-current="page"', r.text), "Models entry is current"


def test_models_page_is_honest_about_defaults_and_assistant_routing(client):
    """The top of the page answers who uses what; false/duplicate model options are gone (S6a)."""
    client.app.state.store.create_bot(Bot(name="design-partner", display_name="Design Partner",
                                          model="demo", tools=[]))
    html = client.get("/models").text
    assert "AI services and assistant routing" in html
    assert "Design Partner" in html and "Needs a model route" in html
    assert 'href="/#/bot/design-partner"' in html
    assert "The route new built-in assistants start from is set in Settings" in html
    assert "Add or repair a service" in html
    assert "cannot run" in html, "a saved route that cannot run is not presented as ready"
    assert "<option value=\"chatgpt\">" not in html
    assert "Hosted fallback:" not in html
    assert "Open Apps &amp; AI" in html


def test_page_flags_what_wont_fit_and_shows_real_context(client):
    import html
    t = html.unescape(client.get("/models").text)
    assert "won't fit" in t.lower()                      # huge:70b cannot fit any normal machine
    assert "the weights alone are" in t, "a model that cannot fit says why, in plain words"
    assert "gets 0 tokens" not in t, "a model that does not fit must not claim a context window"
    assert re.search(r"gets [\d,.]+k? tokens", t), "a model that fits shows the context it will really get"


def test_price_rows_show_source_and_verified_date(client):
    t = client.get("/models").text
    assert "2026-10-07" in t and "platform.claude.com" in t


def test_saving_a_price_stamps_today_and_is_used(client):
    tok = csrf(client)
    r = client.post("/models/prices/save", data={"csrf": tok, "model": "opencode-go/glm-5.3", "input": "0.4",
                                                 "output": "1.6", "source": "https://opencode.ai/docs/go/"},
                    follow_redirects=False)
    assert r.status_code == 303
    book = PriceBook(client.state_dir / "prices.json")
    p = book.lookup("opencode-go", "glm-5.3")
    assert p and p.input == 0.4 and p.output == 1.6 and p.user and p.verified_on
    t = client.get("/models").text
    assert "opencode-go/glm-5.3" in t and ">yours<" in t


@pytest.mark.parametrize("bad", [{"input": "abc", "output": "1"}, {"input": "-1", "output": "1"},
                                 {"input": "nan", "output": "1"}, {"input": "1", "output": ""},
                                 {"input": "1e9", "output": "1"}])
def test_bad_prices_are_rejected_with_a_reason_and_nothing_is_written(client, bad):
    tok = csrf(client)
    r = client.post("/models/prices/save", data={"csrf": tok, "model": "x/y", **bad}, follow_redirects=True)
    assert "must be" in r.text or "required" in r.text
    assert not (client.state_dir / "prices.json").exists()


def test_local_models_cannot_get_a_price_row(client):
    tok = csrf(client)
    r = client.post("/models/prices/save", data={"csrf": tok, "model": "ollama/llama", "input": "1", "output": "1"},
                    follow_redirects=True)
    assert "cost nothing" in r.text


def test_reset_restores_the_bundled_row(client):
    tok = csrf(client)
    client.post("/models/prices/save", data={"csrf": tok, "model": "anthropic/claude-opus-5-5", "input": "9",
                                             "output": "9"})
    assert PriceBook(client.state_dir / "prices.json").lookup("anthropic", "claude-opus-5-5").input == 9
    client.post("/models/prices/reset", data={"csrf": tok, "model": "anthropic/claude-opus-5-5"})
    assert PriceBook(client.state_dir / "prices.json").lookup("anthropic", "claude-opus-5-5").input == 4.0


def test_price_edits_require_the_csrf_token(client):
    assert client.post("/models/prices/save", data={"model": "a/b", "input": "1", "output": "1"}).status_code == 403


def test_missing_model_or_keys_rejected_safely_without_crash(client):
    tok = csrf(client)
    r = client.post("/models/prices/save", data={"csrf": tok, "input": "1.0", "output": "2.0"}, follow_redirects=True)
    assert "model is required" in r.text
    r2 = client.post("/models/prices/save", data={"csrf": tok, "model": "test/model", "output": "2.0"}, follow_redirects=True)
    assert "input is required" in r2.text
    r3 = client.post("/models/prices/reset", data={"csrf": tok}, follow_redirects=True)
    assert "model is required" in r3.text


def test_reset_button_has_accessible_name_and_confirmation(client):
    tok = csrf(client)
    client.post("/models/prices/save", data={"csrf": tok, "model": "opencode-go/glm-5.3", "input": "0.5", "output": "1.5"})
    page_html = client.get("/models").text
    assert 'data-hutch-confirm-form="reset-price-confirm-' in page_html
    assert "Reset this price override?" in page_html
    assert 'aria-label="Reset price for opencode-go/glm-5.3"' in page_html
    assert "data-confirm=" not in page_html


def test_malformed_url_source_does_not_crash(client):
    tok = csrf(client)
    r = client.post("/models/prices/save", data={"csrf": tok, "model": "custom/test", "input": "1.0", "output": "2.0", "source": "http://"}, follow_redirects=False)
    assert r.status_code == 303
    page_html = client.get("/models").text
    assert "custom/test" in page_html


def test_bot_model_assignment_without_prefix_resolves(client):
    from hutch.models import Bot
    client.app.state.store.create_bot(Bot(name="bot-unprefixed", model="fake:8b", tools=[]))
    page_html = client.get("/models").text
    assert 'href="/bots/bot-unprefixed"' in page_html

