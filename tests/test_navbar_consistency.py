"""One navigation model for both shells.

The SPA app shell (static/index.html) and every server-rendered page show the
same destinations in the same order. The server model lives in
hutch.server.nav; this test fails when the two drift (label, href, order) or
when a full page loses its active destination.
"""

from __future__ import annotations

import html
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hutch.models import Bot
from hutch.server.app import create_app
from hutch.server.nav import FOOT, MORE, PRIMARY, normalize
from tests.fakes import FakeOllama

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "src" / "hutch" / "server" / "static" / "index.html"
BASE = ROOT / "src" / "hutch" / "server" / "templates" / "base.html"


class _SidebarParser(HTMLParser):
    """Collect the SPA sidebar's anchors in DOM order (nav, More, footer)."""

    def __init__(self) -> None:
        super().__init__()
        self._nav = 0
        self._foot = 0
        self._details = 0
        self._svg = 0
        self._capture: dict[str, str] | None = None
        self.anchors: list[dict[str, str]] = []
        self.needs_you = ""

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = attrs.get("class", "").split()
        if tag == "nav" and "ws-nav" in classes:
            self._nav += 1
        elif tag == "footer" and "ws-foot" in classes:
            self._foot += 1
        elif self._nav and not self._foot and tag == "details":
            self._details += 1
        elif tag == "svg":
            self._svg += 1
        if tag in ("a", "button"):
            if tag == "a" and (self._nav or self._foot):
                self._capture = {"href": attrs.get("href", ""), "data_nav": attrs.get("data-nav", ""),
                                 "label": "", "group": "footer" if self._foot else ("more" if self._details else "primary")}
            elif tag == "button" and self._nav and attrs.get("id") == "needs-you-open":
                self._capture = {"href": "", "data_nav": "", "label": "", "group": "needs-you"}

    def handle_data(self, data):
        if self._capture is not None and not self._svg:
            self._capture["label"] += data

    def handle_endtag(self, tag):
        if tag == "svg" and self._svg:
            self._svg -= 1
        elif tag == "a" and self._capture is not None:
            self._finish()
        elif tag == "button" and self._capture is not None:
            self.needs_you = self._capture["label"].split()
            self.needs_you = " ".join(self.needs_you)
            self._capture = None
        elif tag == "details" and self._details:
            self._details -= 1
        elif tag == "nav" and self._nav:
            self._nav -= 1
        elif tag == "footer" and self._foot:
            self._foot -= 1

    def _finish(self) -> None:
        assert self._capture is not None
        entry = self._capture
        entry["label"] = " ".join(entry["label"].split())
        self.anchors.append(entry)
        self._capture = None


def spa_sidebar() -> _SidebarParser:
    parser = _SidebarParser()
    parser.feed(INDEX.read_text(encoding="utf-8"))
    return parser


def normalize_href(href: str) -> str:
    """The SPA document uses root hash links; server pages need absolute ones."""
    if href.startswith("#"):
        return "/" + href
    return href


def test_server_nav_rows_match_the_spa_sidebar():
    parser = spa_sidebar()
    spa_links = [row for row in parser.anchors if row["group"] != "needs-you"]
    expected = (
        [{"href": href, "data_nav": key, "label": label, "group": "primary"}
         for key, href, label, _icon in PRIMARY if key != "approvals"]
        + [{"href": href, "data_nav": key, "label": label, "group": "more"}
           for key, href, label, _icon in MORE]
        + [{"href": href, "data_nav": key, "label": label, "group": "footer"}
           for key, href, label, _icon in FOOT]
    )
    assert len(spa_links) == len(expected), "SPA sidebar and server nav differ in item count"
    for spa, server in zip(spa_links, expected):
        assert normalize_href(spa["href"]) == server["href"], (spa, server)
        assert spa["data_nav"] == server["data_nav"], (spa, server)
        assert spa["label"] == server["label"], (spa, server)
    needs_you = next(key for key, _href, _label, _icon in PRIMARY if key == "approvals")
    label = next(label for key, _href, label, _icon in PRIMARY if key == needs_you)
    assert re.sub(r"\d+$", "", parser.needs_you).strip() == label, (
        "the Needs you row keeps its label in both shells")


def test_both_shells_load_the_one_navigation_component():
    for path in (BASE, INDEX):
        text = path.read_text(encoding="utf-8")
        assert "/static/hutch-nav.css" in text, path
    assert "/static/hutch-shell.css" in BASE.read_text(encoding="utf-8")


def test_server_pages_render_one_sidebar_with_the_active_destination(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    ollama = FakeOllama({})
    monkeypatch.setenv("OLLAMA_HOST", ollama.url)
    from hutch.runtime.ladder import reset_provider_cache
    reset_provider_cache()
    try:
        with TestClient(create_app()) as client:
            client.app.state.store.create_bot(Bot(name="nav-test-bot"))
            cases = {
                "/models": "models",
                "/usage": "usage",
                "/bots/delete": "bots",
                "/bots/nav-test-bot": "bots",
                "/bots/nav-test-bot/delete": "bots",
                "/legacy/connections": "connections",
            }
            for path, expected_key in cases.items():
                response = client.get(path)
                assert response.status_code == 200, path
                text = response.text
                assert "topbar" not in text, path
                start = text.index('<aside class="workspace"')
                end = text.index("</aside>", start) + len("</aside>")
                sidebar = text[start:end]
                assert 'id="primary-nav"' in sidebar, path
                assert 'class="active"' not in sidebar, "aria-current is the one active signal"
                active = re.findall(r'<a [^>]*href="([^"]+)"[^>]*aria-current="page"', sidebar)
                assert active == [_href_for(expected_key)], (path, active)
                active_anchor = re.search(r'<a [^>]*aria-current="page"[^>]*>.*?</a>', sidebar, re.S)
                assert active_anchor, path
                assert _label_for(expected_key) in html.unescape(active_anchor.group(0)), path
                assert 'class="skip" href="#main"' in text, path
                assert 'id="main" class="container" tabindex="-1"' in text, path
    finally:
        ollama.close()


def _nav_item(key: str):
    for group in (PRIMARY, MORE, FOOT):
        for item_key, href, label, _icon in group:
            if item_key == key:
                return href, label
    raise AssertionError(key)


def _label_for(key: str) -> str:
    return _nav_item(key)[1]


def _href_for(key: str) -> str:
    return _nav_item(key)[0]


def test_history_is_one_destination_and_the_assistants_row_has_one_label():
    """Conversation history, Activity and Work history are merged (spine, decision 1)."""
    labels = [label for group in (PRIMARY, MORE, FOOT) for _key, _href, label, _icon in group]
    assert labels.count("Activity") == 1
    for retired in ("Conversation history", "Work history", "Manage assistants"):
        assert retired not in labels, retired
    assert "Assistants" in labels
    keys = [key for group in (PRIMARY, MORE, FOOT) for key, _href, _label, _icon in group]
    assert "activity" in keys
    for retired_key in ("chats", "overview", "runs"):
        assert retired_key not in keys, retired_key
    # The loop orders the destinations: result and repeat first, then configuration.
    more = [key for key, _href, _label, _icon in MORE]
    assert more[:2] == ["activity", "schedules"]
    assert more[-1] == "bots"


def test_command_palette_destinations_are_the_nav_labels():
    """The palette's "Go to" entries are the sidebar's destinations, named the same way."""
    text = (ROOT / "src" / "hutch" / "server" / "static" / "palette.js").read_text(encoding="utf-8")
    labels = set(re.findall(r'nav\("([^"]+)"', text))
    labels |= set(re.findall(r'kind: "Go to", label: "([^"]+)"', text))
    shortcuts = {label for label in labels if label.startswith("Activity: ")}
    destinations = labels - shortcuts
    expected = {label for group in (PRIMARY, MORE, FOOT) for _key, _href, label, _icon in group}
    assert destinations == expected, (sorted(destinations - expected), sorted(expected - destinations))
    assert shortcuts == {"Activity: History", "Activity: Conversations"}


def test_nested_and_destructive_routes_map_to_a_primary_destination():
    assert normalize("deletion") == "bots"
    assert normalize("bots") == "bots"
    assert normalize("models") == "models"
    assert normalize("") == ""
