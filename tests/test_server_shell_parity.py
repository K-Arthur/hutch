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

from datetime import timedelta

from hutch.models import Bot, Run, RunStatus, iso, utcnow
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


@pytest.mark.parametrize("path,title", [
    ("/models", "Models"), ("/usage", "Usage"),
    ("/legacy/connections", "Connections"), ("/bots/delete", "Permanently delete an assistant"),
])
def test_the_page_title_lives_in_the_shell_header(client, path, title):
    """One header contract: the page's h1 is in the shell header, not a second heading in the body."""
    text = client.get(path, headers=BROWSER).text
    header = text[text.index('<div class="app-top-context">'):text.index('<div class="app-top-status">')]
    assert re.search(rf"<h1[^>]*>.*{re.escape(title)}.*</h1>", header, re.S), path
    main = text[text.index('<main id="main"'):text.index("</main>")]
    assert "<h1" not in main, f"{path} still carries a page heading inside main"


def test_global_stop_and_work_status_track_running_work(client):
    store = client.app.state.store
    idle = client.get("/usage", headers=BROWSER).text
    assert "/stop-all" not in idle and '<a class="app-top-work"' not in idle
    bot = store.create_bot(Bot(name="work-bot"))
    run = store.create_run(Run(bot_id=bot.id, prompt="long task", status=RunStatus.running, owner=""))
    with store._lock:                     # a real claim carries a live lease; that is what "working" needs
        store._db.execute("UPDATE runs SET lease_owner = 'supervisor', lease_expires_at = ? WHERE id = ?",
                          (iso(utcnow() + timedelta(minutes=5)), run.id))
        store._db.commit()
    working = client.get("/usage", headers=BROWSER).text
    assert "/stop-all" in working and "1 working</a>" in working
    assert "Stop all runs now" in working


def test_the_server_header_ignores_a_live_row_without_lease_evidence(client):
    """A live status alone is not working: a pre-lease row with no evidence must not offer Stop all."""
    store = client.app.state.store
    bot = store.create_bot(Bot(name="ghost-bot"))
    store.create_run(Run(bot_id=bot.id, prompt="ghost", status=RunStatus.cancelling, owner=""))
    text = client.get("/usage", headers=BROWSER).text
    assert "/stop-all" not in text and '<a class="app-top-work"' not in text


def test_parked_work_does_not_show_the_global_stop(client):
    """Approvals waiting for a person are not execution capacity; the SPA header counts them separately too."""
    store = client.app.state.store
    bot = store.create_bot(Bot(name="parked-bot"))
    store.create_run(Run(bot_id=bot.id, prompt="needs approval",
                         status=RunStatus.waiting_approval, owner=""))
    text = client.get("/models", headers=BROWSER).text
    assert "/stop-all" not in text and '<a class="app-top-work"' not in text


@pytest.mark.parametrize("path", ["/models", "/usage", "/legacy/connections", "/bots/delete"])
def test_server_pages_keep_their_plain_forms_usable(client, path):
    """With `Referrer-Policy: no-referrer` Chromium posts `Origin: null` and the same-origin guard
    refuses every form on the page (a 403 on /models/set-default). Same-origin referrers are visible
    only to this server, so server pages opt back in, as the first-run page already did."""
    text = client.get(path, headers=BROWSER).text
    assert '<meta name="referrer" content="same-origin">' in text, path
