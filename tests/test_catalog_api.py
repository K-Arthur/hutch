"""Catalog API: the bundled store, reviewed export/import, and explicit hash-pinned sources.

Owner configuration only; every route here is in the default-deny inventory for paired phones. Tests use the
real app with a scratch state directory and a local-folder source; no network is touched.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hutch.catalog import bundled
from hutch.models import Bot
from hutch.server.app import create_app

DATA = Path(__file__).resolve().parent.parent / "src" / "hutch" / "data" / "catalog"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:9")
    from hutch.runtime.ladder import reset_provider_cache
    reset_provider_cache()
    with TestClient(create_app()) as test_client:
        yield test_client


def test_the_bundled_catalog_lists_every_entry_with_its_permissions(client):
    body = client.get("/api/v1/catalog").json()
    entries = body["bundled"]["entries"]
    assert len(entries) == len(bundled().entries) == 8
    assert body["bundled"]["diagnostics"] == []
    for entry in entries:
        assert entry["publisher"] == "Hutch" and len(entry["content_hash"]) == 64
        assert "tools" in entry["permissions"] and entry["permissions"]["publisher"] == "Hutch"
    assert body["sources"]["revision"] == 0 and body["sources"]["sources"] == []


def test_export_draft_runs_the_checklist_and_writes_nothing(client):
    client.app.state.store.create_bot(Bot(name="release-notes", display_name="Release Notes",
                                          instructions="Summarize the changes.", tools=["files"]))
    ok = client.post("/api/v1/catalog/export-draft", json={"bot": "release-notes", "publisher": "Kev"})
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["manifest"]["id"] == "release-notes" and body["blocked"] == []
    assert body["checklist"] and body["omitted"]
    assert client.app.state.store.get_bot("release-notes").name == "release-notes"   # untouched

    client.app.state.store.create_bot(Bot(name="leaky", instructions="Use sk-abcdefghijklmnopqrstuvwx"))
    blocked = client.post("/api/v1/catalog/export-draft", json={"bot": "leaky"}).json()
    assert blocked["manifest"] is None and blocked["blocked"]
    assert client.post("/api/v1/catalog/export-draft", json={"bot": "nope"}).status_code == 404


def test_import_draft_returns_an_unsaved_configuration(client):
    manifest = json.loads((DATA / "day-planner.json").read_text(encoding="utf-8"))
    response = client.post("/api/v1/catalog/import-draft", json={"manifest": manifest})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["saved"] is False and body["configuration"]["name"] == "day-planner"
    assert body["configuration"]["tools"] == ["files", "memory"]
    assert body["entry"]["content_hash"] and body["permissions"]["tools"] == ["files", "memory"]
    broken = dict(manifest, surprise="field")
    assert client.post("/api/v1/catalog/import-draft", json={"manifest": broken}).status_code == 422


def test_a_local_source_is_fetched_previewed_and_trusted_explicitly(client, tmp_path):
    folder = tmp_path / "my-catalog"
    folder.mkdir()
    shutil.copy(DATA / "day-planner.json", folder / "day-planner.json")

    added = client.post("/api/v1/catalog/sources", json={"kind": "local", "location": str(folder),
                                                         "expected_revision": 0})
    assert added.status_code == 200, added.text
    body = added.json()
    source = body["sources"][0]
    assert source["kind"] == "local" and source["last_fetched_at"] == ""   # adding never fetches

    fetched = client.post(f"/api/v1/catalog/sources/{source['id']}/fetch",
                          json={"expected_revision": body["revision"]})
    assert fetched.status_code == 200, fetched.text
    revision = fetched.json()["revision"]
    preview = client.get(f"/api/v1/catalog/sources/{source['id']}/entries/day-planner").json()
    assert preview["state"] == "untrusted" and preview["inert"] is True
    trusted = client.post(f"/api/v1/catalog/sources/{source['id']}/entries/day-planner/trust",
                          json={"expected_hash": preview["content_hash"], "expected_revision": revision})
    assert trusted.status_code == 200, trusted.text
    revision = trusted.json()["revision"]
    assert client.get(f"/api/v1/catalog/sources/{source['id']}/entries/day-planner").json()["state"] == "trusted"
    listed = client.get("/api/v1/catalog").json()["sources"]["sources"][0]
    assert listed["entries"][0]["trusted"] is True

    removed = client.delete(f"/api/v1/catalog/sources/{source['id']}", params={"expected_revision": revision})
    assert removed.status_code == 200 and removed.json()["sources"] == []
    assert client.get("/api/v1/catalog").json()["sources"]["sources"] == []
