"""Studio shell contract tests.

These pin the accessibility and truthful-state decisions in the SPA shell so a future
edit cannot quietly regress them:

* the whole ``<main>`` must not be a live region (it announced the entire page on
  every poll); announcements go through the bounded ``#live-status`` region instead;
* the daemon badge must not claim a hardcoded "live" before health is confirmed.

They read the served shell + static assets rather than a browser, so they run in the
default offline suite; the browser-level behaviour is covered by tests/e2e.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from hutch.server.app import create_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    app = create_app()
    with TestClient(app) as c:
        yield c


def test_main_is_not_a_live_region(client):
    html = client.get("/").text
    # The main landmark must not carry aria-live (it re-rendered on every poll).
    assert 'id="view"' in html
    assert 'id="view" aria-live' not in html


def test_bounded_status_region_exists(client):
    html = client.get("/").text
    assert 'id="live-status"' in html
    assert 'aria-live="polite"' in html


def test_daemon_badge_does_not_hardcode_live(client):
    html = client.get("/").text
    assert 'id="daemon-pill"' in html
    # Static markup must start unconfirmed, not green.
    assert 'data-state="connecting"' in html
    assert 'id="daemon-pill" class="pill pulse"' not in html


def test_static_assets_expose_new_behaviour(client):
    js = client.get("/static/app.js").text
    css = client.get("/static/style.css").text
    assert "function announce(" in js
    assert "function pollHealth(" in js
    assert "function typingHtml(" in js
    assert 'label: "Stopping"' in js
    assert '"Status unavailable"' in js
    assert "return statusInfo[status] ? !statusInfo[status].terminal : true" in js
    assert 'status.replace("_", " ")' not in js
    assert ".typing-dots" in css
    assert "typing-bounce" in css
