"""Server pages wear the same shell as the SPA (spine items C1, C3, C4, N6).

Same brand label, the assistants roster beside the navigation, no absolute state
path in the footer, and the Assistants destination shown by the same rule: from
ten assistants, or when it is the active destination.
"""

from __future__ import annotations

import html
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hutch.models import Bot
from hutch.server.app import create_app
from tests.fakes import FakeOllama

INDEX = Path(__file__).resolve().parent.parent / "src" / "hutch" / "server" / "static" / "index.html"
BROWSER = {"accept": "text/html"}


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


def _sidebar(text: str) -> str:
    start = text.index('<aside class="workspace"')
    return text[start:text.index("</aside>", start) + len("</aside>")]


def test_brand_link_label_matches_the_spa(client):
    spa = re.search(r'class="brand"[^>]*aria-label="([^"]+)"', INDEX.read_text(encoding="utf-8"))
    server = re.search(r'class="brand"[^>]*aria-label="([^"]+)"', _sidebar(client.get("/models", headers=BROWSER).text))
    assert spa and server
    assert html.unescape(server.group(1)) == html.unescape(spa.group(1))


@pytest.mark.parametrize("path", ["/models", "/usage"])
def test_footer_does_not_print_the_state_directory(client, path):
    state_dir = str(client.app.state.config.state_dir)
    response = client.get(path, headers=BROWSER)
    assert response.status_code == 200
    assert state_dir not in html.unescape(response.text), "absolute paths leak into pages and screenshots"
    assert re.search(r'<footer class="foot">[^<]*hutch', response.text), "the version footer stays"


def test_sidebar_lists_the_assistants_roster_with_a_new_assistant_link(client):
    client.app.state.store.create_bot(Bot(name="alpha-bot", display_name="Alpha"))
    client.app.state.store.create_bot(Bot(name="beta-bot", display_name="Beta"))
    sidebar = _sidebar(client.get("/usage", headers=BROWSER).text)
    assert 'class="ws-roster"' in sidebar and 'aria-label="Your assistants"' in sidebar
    assert re.search(r'<h2 class="roster-title">Assistants</h2>', sidebar)
    new = re.search(r'<a [^>]*href="/#/assistant/new"[^>]*>', sidebar)
    assert new and 'aria-label="New assistant"' in new.group(0)
    for name, shown in (("alpha-bot", "Alpha"), ("beta-bot", "Beta")):
        row = re.search(rf'<a [^>]*href="/#/chat/{name}"[^>]*>(.*?)</a>', sidebar, re.S)
        assert row, name
        assert shown in html.unescape(row.group(1)), (name, row.group(1))


def test_assistants_row_appears_at_ten_assistants_or_when_active(client):
    store = client.app.state.store
    for index in range(2):
        store.create_bot(Bot(name=f"few-{index}"))
    models = _sidebar(client.get("/models", headers=BROWSER).text)
    assert 'data-nav="bots"' not in models, "below ten the manager is not offered (PRODUCT.md)"
    deleting = _sidebar(client.get("/bots/delete", headers=BROWSER).text)
    assert re.search(r'<a [^>]*data-nav="bots"[^>]*aria-current="page"', deleting), \
        "the active destination is always shown"
    for index in range(2, 10):
        store.create_bot(Bot(name=f"few-{index}"))
    assert 'data-nav="bots"' in _sidebar(client.get("/models", headers=BROWSER).text)
