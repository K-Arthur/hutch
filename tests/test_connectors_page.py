"""The Connectors page: server-rendered install, review, grant and revoke.

These drive the real forms over HTTP with CSRF, the way a browser without JavaScript would, and
assert the page states what actually happened. The connector they install is the real fixture
launched through Hutch's sandbox.
"""

from __future__ import annotations

import re
import shutil
from urllib.parse import urlencode
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hutch.models import Bot
from hutch.server.app import create_app

FIXTURE = Path(__file__).parent / "fixtures" / "mcp_stdio_server.py"

needs_sandbox = pytest.mark.skipif(
    not shutil.which("bwrap") or not shutil.which("systemd-run") or not Path("/usr/bin/python3").is_file(),
    reason="the contained stdio transport needs bubblewrap, systemd-run and the system Python")


@pytest.fixture
def ui(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    app = create_app()
    with TestClient(app, base_url="http://127.0.0.1:18787", follow_redirects=True) as client:
        client.get("/connectors")                       # establishes the CSRF cookie
        token = client.cookies.get("hutch_csrf")
        yield client, token, app.state.store


@pytest.fixture
def package():
    root = Path.home() / ".hutch-tmp"
    root.mkdir(exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix="mcp-ui-", dir=root))
    shutil.copyfile(FIXTURE, directory / "server.py")
    try:
        yield directory
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def _add(client, token, package):
    return client.post("/connectors/add", data={
        "csrf": token, "integration_id": "acme", "title": "Acme", "transport": "mcp_stdio",
        "command": "/usr/bin/python3", "args": str(package / "server.py"),
        "read_only_paths": str(package), "env": ""})


def test_the_page_states_the_three_separate_acts(ui):
    client, _token, _store = ui
    body = client.get("/connectors").text
    assert "Installing a connector authorizes nothing" in body
    assert "no inherited environment" in body
    # The empty state points at the neighbouring, different concept rather than duplicating it.
    assert "provider accounts, which are a different thing" in body


def test_installing_from_the_page_does_not_authorize(ui, package):
    client, token, _store = ui
    response = _add(client, token, package)
    assert response.status_code == 200
    body = response.text
    assert "Connector saved" in body
    assert "installed" in body
    assert "No tool list yet" in body


def test_a_refused_definition_is_shown_as_a_sentence(ui, package):
    client, token, _store = ui
    response = client.post("/connectors/add", data={
        "csrf": token, "integration_id": "acme", "title": "Acme", "transport": "mcp_stdio",
        "command": "/usr/bin/python3", "args": "--api-key=secret", "read_only_paths": "", "env": ""})
    assert "credential" in response.text


def test_a_form_without_csrf_is_refused(ui, package):
    client, _token, _store = ui
    response = client.post("/connectors/add", data={
        "integration_id": "acme", "title": "Acme", "transport": "mcp_stdio", "command": "/usr/bin/python3"})
    assert response.status_code == 403


@needs_sandbox
def test_the_full_page_journey(ui, package):
    client, token, store = ui
    bot = store.create_bot(Bot(name="reader-bot", model="mock/demo", tools=[]))

    _add(client, token, package)
    tested = client.post("/connectors/acme/test", data={"csrf": token})
    assert "Read 4 tools" in tested.text
    assert "acme__read_workspace" in tested.text or "read_workspace" in tested.text

    granted = _form(client, "/connectors/acme/grant", [
        ("csrf", token), ("bot", bot.id), ("tools", "read_workspace"),
        ("class_read_workspace", "read"), ("revision", _revision(tested.text))])
    assert "Access granted" in granted.text
    assert "reader-bot" in granted.text

    revoked = client.post("/connectors/acme/revoke", data={"csrf": token, "bot": bot.id})
    assert "Access revoked" in revoked.text
    assert not store.integration_tool_granted(bot.id, "acme", "read_workspace")

    removed = client.post("/connectors/acme/remove", data={"csrf": token})
    assert "Connector removed" in removed.text
    assert "No connectors are installed" in removed.text


@needs_sandbox
def test_granting_without_choosing_a_tool_is_refused_with_a_reason(ui, package):
    client, token, store = ui
    bot = store.create_bot(Bot(name="reader-bot", model="mock/demo", tools=[]))
    _add(client, token, package)
    tested = client.post("/connectors/acme/test", data={"csrf": token})
    response = _form(client, "/connectors/acme/grant", [
        ("csrf", token), ("bot", bot.id), ("revision", _revision(tested.text))])
    assert "Choose an assistant and at least one tool" in response.text


def _form(client, path: str, pairs: list[tuple[str, str]]):
    """Post a real urlencoded form, including repeated fields such as tools."""
    return client.post(path, content=urlencode(pairs).encode(),
                       headers={"content-type": "application/x-www-form-urlencoded"})


def _revision(body: str) -> str:
    match = re.search(r'name="revision" value="([0-9a-f]{64})"', body)
    assert match, "the page did not render a reviewable revision"
    return match.group(1)
