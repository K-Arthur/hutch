"""Installing, testing and granting a connector through the real HTTP API.

The connector under test is the real fixtures/mcp_stdio_server.py, launched through Hutch's
sandbox by the real transport, so this exercises the same path a user's local server takes.
"""

from __future__ import annotations

import shutil
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
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    app = create_app()
    with TestClient(app, base_url="http://127.0.0.1:18787", follow_redirects=False) as client:
        yield client, app.state.store


def _bot(store, name: str) -> str:
    """Create an assistant directly: the bot API additionally requires a configured model route."""
    return store.create_bot(Bot(name=name, model="mock/demo", tools=[])).id


@pytest.fixture
def package():
    """A reviewed server package on disk, the way a real local connector is installed.

    The mount screen refuses /tmp and the state directory, so this uses the repository's
    documented scratch root under the user's home and removes it afterwards.
    """
    root = Path.home() / ".hutch-tmp"
    root.mkdir(exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix="mcp-api-", dir=root))
    shutil.copyfile(FIXTURE, directory / "server.py")
    try:
        yield directory
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def _definition(package: Path) -> dict:
    """A definition whose executable lives in a reviewed read-only package, not the workspace."""
    return {"transport": "mcp_stdio", "command": "/usr/bin/python3",
            "args": [str(package / "server.py")], "read_only_paths": [str(package)]}


def test_an_empty_connector_list_is_reported_honestly(api):
    client, _store = api
    body = client.get("/api/v1/integrations").json()
    assert body["connectors"] == []
    assert "never run a tool" in body["detail"]


def test_configuring_a_connector_does_not_authorize_anything(api, package):
    client, _store = api
    response = client.post("/api/v1/integrations", json={
        "integration_id": "acme", "title": "Acme", "definition": _definition(package)})
    assert response.status_code == 200, response.text
    detail = client.get("/api/v1/integrations/acme").json()
    assert detail["state"] == "installed" and detail["enabled"] is False
    assert detail["catalog"] == [] and detail["grants"] == []


def test_a_connector_id_that_is_not_a_slug_is_refused(api, package):
    client, _store = api
    response = client.post("/api/v1/integrations", json={
        "integration_id": "Acme Corp!", "title": "Acme", "definition": _definition(package)})
    assert response.status_code == 400


def test_a_credential_in_a_command_line_is_refused_with_a_reason(api):
    client, _store = api
    response = client.post("/api/v1/integrations", json={
        "integration_id": "acme", "title": "Acme",
        "definition": {"transport": "mcp_stdio", "command": "/usr/bin/python3",
                       "args": ["--api-key=secret"]}})
    assert response.status_code == 409
    assert "credential" in response.json()["detail"]


def test_an_unknown_connector_is_a_404(api):
    client, _store = api
    assert client.get("/api/v1/integrations/missing").status_code == 404
    assert client.delete("/api/v1/integrations/missing").status_code == 404


@needs_sandbox
def test_testing_reads_the_catalog_and_grants_are_per_assistant(api, package):
    client, store = api
    created = client.post("/api/v1/integrations", json={
        "integration_id": "acme", "title": "Acme", "definition": _definition(package)}).json()

    tested = client.post("/api/v1/integrations/acme/test")
    assert tested.status_code == 200, tested.text
    body = tested.json()
    assert body["tool_count"] == 4
    assert {t["server_tool_name"] for t in body["catalog"]} == {
        "read_workspace", "write_workspace", "inspect_process", "wait_for_cancel"}

    detail = client.get("/api/v1/integrations/acme").json()
    assert detail["state"] == "capabilities_discovered"

    bot_id = _bot(store, "reader-bot")
    granted = client.post("/api/v1/integrations/acme/grants", json={
        "bot": bot_id, "tools": ["read_workspace"],
        "operation_classes": {"read_workspace": "read"}, "revision": created["revision"]})
    assert granted.status_code == 200, granted.text

    after = client.get("/api/v1/integrations/acme").json()
    assert after["enabled"] is True and after["state"] == "operation_authorized"
    assert [g["server_tool_name"] for g in after["grants"]] == ["read_workspace"]

    revoked = client.delete(f"/api/v1/integrations/acme/grants/{bot_id}")
    assert revoked.status_code == 200
    assert revoked.json()["remaining_grants"] == 0
    assert client.get("/api/v1/integrations/acme").json()["grants"] == []


@needs_sandbox
def test_a_grant_for_a_tool_outside_the_catalog_is_refused(api, package):
    client, store = api
    created = client.post("/api/v1/integrations", json={
        "integration_id": "acme", "title": "Acme", "definition": _definition(package)}).json()
    assert client.post("/api/v1/integrations/acme/test").status_code == 200
    response = client.post("/api/v1/integrations/acme/grants", json={
        "bot": _bot(store, "reader-bot"), "tools": ["rm_rf"], "revision": created["revision"]})
    assert response.status_code == 409
    assert "not in the reviewed catalog" in response.json()["detail"]


@needs_sandbox
def test_removing_a_connector_removes_its_grants(api, package):
    client, store = api
    created = client.post("/api/v1/integrations", json={
        "integration_id": "acme", "title": "Acme", "definition": _definition(package)}).json()
    assert client.post("/api/v1/integrations/acme/test").status_code == 200
    client.post("/api/v1/integrations/acme/grants", json={
        "bot": _bot(store, "reader-bot"), "tools": ["read_workspace"], "revision": created["revision"]})
    assert client.delete("/api/v1/integrations/acme").status_code == 200
    assert client.get("/api/v1/integrations").json()["connectors"] == []
    assert client.get("/api/v1/integrations/acme").status_code == 404
