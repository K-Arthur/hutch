"""One title format: `<View> — Hutch`, on every server page and in the SPA document.

The view name is the destination's nav label where the page is a destination
(docs/realignment/product-spine.md, section 3), so a title cannot drift from the
sidebar. The SPA sets its own title per route; tests/e2e/test_page_titles.py
covers that in a browser.
"""

from __future__ import annotations

import html
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hutch.models import Bot
from hutch.server.app import create_app
from hutch.server.nav import FOOT, MORE, PRIMARY
from tests.fakes import FakeOllama

INDEX = Path(__file__).resolve().parent.parent / "src" / "hutch" / "server" / "static" / "index.html"
TITLE = re.compile(r"^(?P<view>[^<>—]+) — Hutch$")
BROWSER = {"accept": "text/html"}  # the error handler renders HTML only for browsers


def _title(text: str) -> str:
    match = re.search(r"<title>(.*?)</title>", text, re.S)
    assert match, "page has no <title>"
    return html.unescape(" ".join(match.group(1).split()))


def _label(key: str) -> str:
    for group in (PRIMARY, MORE, FOOT):
        for item_key, _href, label, _icon in group:
            if item_key == key:
                return label
    raise AssertionError(key)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    ollama = FakeOllama({})
    monkeypatch.setenv("OLLAMA_HOST", ollama.url)
    from hutch.runtime.ladder import reset_provider_cache
    reset_provider_cache()
    try:
        with TestClient(create_app()) as test_client:
            test_client.app.state.store.create_bot(Bot(name="title-bot", display_name="Title Bot"))
            yield test_client
    finally:
        ollama.close()


# Pages that are sidebar destinations: the title's view is the nav label.
DESTINATIONS = {"/models": "models", "/usage": "usage"}
# Pages inside a destination or outside the sidebar: any single view name is fine.
OTHER_PAGES = ("/bots/delete", "/bots/title-bot", "/bots/title-bot/delete", "/onboarding", "/login", "/pair",
               "/no-such-page")


@pytest.mark.parametrize("path,key", sorted(DESTINATIONS.items()))
def test_destination_pages_title_matches_the_nav_label(client, path, key):
    response = client.get(path, headers=BROWSER)
    assert response.status_code == 200, path
    title = _title(response.text)
    match = TITLE.match(title)
    assert match, f"{path}: {title!r} is not '<View> — Hutch'"
    assert match.group("view") == _label(key), (path, title)


@pytest.mark.parametrize("path", OTHER_PAGES)
def test_every_other_server_page_uses_the_same_format(client, path):
    response = client.get(path, headers=BROWSER)
    assert response.status_code in (200, 404), (path, response.status_code)
    title = _title(response.text)
    assert TITLE.match(title), f"{path}: {title!r} is not '<View> — Hutch'"
    assert title.lower() != "hutch — hutch", path


def test_the_spa_document_title_uses_the_format_before_scripts_run():
    title = _title(INDEX.read_text(encoding="utf-8"))
    assert TITLE.match(title), f"{title!r} is not '<View> — Hutch'"
