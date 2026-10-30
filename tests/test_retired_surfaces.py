"""Retired server surfaces stay gone, and live pages do not route through them.

Spine items X1-X5. `/legacy/connections` is deliberately kept: it is the tested
no-JavaScript path for connection keys and acknowledgements (tests/test_connections.py).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hutch.models import Bot
from hutch.server.app import create_app
from tests.fakes import FakeOllama

TEMPLATES = Path(__file__).resolve().parent.parent / "src" / "hutch" / "server" / "templates"
BROWSER = {"accept": "text/html"}
DEAD_TEMPLATES = ("home.html", "bots.html", "bot_new.html", "approvals.html", "runs.html", "run.html")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    ollama = FakeOllama({})
    monkeypatch.setenv("OLLAMA_HOST", ollama.url)
    from hutch.runtime.ladder import reset_provider_cache
    reset_provider_cache()
    try:
        with TestClient(create_app()) as test_client:
            yield test_client
    finally:
        ollama.close()


@pytest.mark.parametrize("path", ["/legacy", "/legacy/"])
def test_legacy_spa_copy_is_not_served(client, path):
    """`/legacy` served the same document as `/`; the app has one entry point."""
    assert client.get(path, headers=BROWSER, follow_redirects=False).status_code == 404


@pytest.mark.parametrize("name", DEAD_TEMPLATES)
def test_templates_with_no_renderer_are_gone(name):
    assert not (TEMPLATES / name).exists(), f"{name} has no render call; delete it"


def test_bots_redirect_does_no_roster_work(client, monkeypatch):
    """The old `/bots` page redirects at once; it must not build and discard a roster first."""
    store = client.app.state.store

    def boom(*_args, **_kwargs):
        raise AssertionError("the redirect computed roster aggregates it then threw away")

    monkeypatch.setattr(store, "roster_aggregates", boom)
    response = client.get("/bots", follow_redirects=False)
    assert response.status_code == 302 and response.headers["location"] == "/#/bots"


def test_usage_links_assistants_to_the_app_not_the_old_bot_page(client):
    client.app.state.store.create_bot(Bot(name="usage-link", display_name="Usage Link"))
    text = client.get("/usage", headers=BROWSER).text
    assert 'href="/#/bot/usage-link"' in text
    assert 'href="/bots/usage-link"' not in text


@pytest.mark.parametrize("path", ["/models", "/usage"])
def test_live_pages_link_straight_to_apps_and_ai(client, path):
    text = client.get(path, headers=BROWSER).text
    assert not re.search(r'href="/connections"', text), "the redirect hop is gone; link to /#/connections"
