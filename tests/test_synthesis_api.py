"""Server routes for synthesis artifacts and the Workspace connection."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from hutch.server.app import create_app
from hutch.synthesis.model import SynthesisManifest, SourceCoverage, SourceRecord, new_id
from hutch.synthesis.storage import SynthesisStorage


@pytest.fixture()
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    app = create_app()
    with TestClient(app) as client:
        yield client, app.state.store, app.state.config


def _manifest(store) -> str:
    source = SourceRecord(kind="thread", identity="https://social.example/t/1",
                          coverage=SourceCoverage(state="complete", expected_units=1,
                                                  accessible_units=1))
    manifest = SynthesisManifest(sources=[source], coverage_summary="1 of 1 accessible")
    store.save_synthesis_manifest(manifest.model_dump(mode="json"), reason="api test")
    return manifest.id


def _artifact(store, config, manifest_id: str, *, kind="transcript", name="episode.vtt",
              data=b"WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nAda: hello\n"):
    storage = SynthesisStorage(config)
    artifact_id = new_id("art")
    staged = storage.stage_bytes(kind, name, data)
    version = 1
    rel = storage.version_rel_path(manifest_id, kind, version, staged.sha256, staged.storage_name)
    storage.commit(staged, manifest_id, version, insert_row=lambda: store.record_synthesis_artifact(
        artifact_id=artifact_id, manifest_id=manifest_id, kind=kind, version=version,
        status="validated", storage_path=rel, storage_name=staged.storage_name,
        mime=staged.mime, bytes_=staged.bytes, sha256=staged.sha256,
        meta={"test": True}))
    return artifact_id, data, rel


def test_synthesis_artifact_download_is_hash_verified_and_rangeable(api, tmp_path):
    client, store, config = api
    manifest_id = _manifest(store)
    artifact_id, data, rel = _artifact(store, config, manifest_id)

    response = client.get(f"/api/v1/synthesis/artifacts/{artifact_id}/content")
    assert response.status_code == 200
    assert response.content == data
    assert response.headers["x-hutch-artifact-verified"] == "sha256"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "attachment" in response.headers["content-disposition"]
    assert response.headers["etag"].strip('"') == __import__("hashlib").sha256(data).hexdigest()

    ranged = client.get(f"/api/v1/synthesis/artifacts/{artifact_id}/content",
                        headers={"Range": "bytes=0-5"})
    assert ranged.status_code == 206
    assert ranged.content == data[:6]
    assert ranged.headers["content-range"] == f"bytes 0-5/{len(data)}"

    manifest = client.get(f"/api/v1/synthesis/manifests/{manifest_id}")
    assert manifest.status_code == 200
    body = manifest.json()
    assert body["revision"] == 1
    assert [a["id"] for a in body["artifacts"]] == [artifact_id]
    assert body["artifacts"][0]["sha256"] == __import__("hashlib").sha256(data).hexdigest()

    assert client.get("/api/v1/synthesis/artifacts/art_missing/content").status_code == 404
    assert client.get("/api/v1/synthesis/manifests/syn_missing").status_code == 404


def test_tampered_artifact_bytes_are_refused_not_served(api):
    client, store, config = api
    manifest_id = _manifest(store)
    artifact_id, data, rel = _artifact(store, config, manifest_id)
    target = config.synthesis_dir / rel
    os.chmod(target, 0o600)
    target.write_bytes(b"WEBVTT\ntampered\n")
    response = client.get(f"/api/v1/synthesis/artifacts/{artifact_id}/content")
    assert response.status_code == 409
    assert "no longer match" in response.json()["detail"]


def test_workspace_connection_surface_and_callback_redirect(api, monkeypatch):
    client, store, config = api
    listing = client.get("/api/v1/connections/google-workspace")
    assert listing.status_code == 200
    body = listing.json()
    assert body["accounts"] == []
    assert "drive.file" in body["detail"]
    assert body["callback_path"].endswith("/google-workspace/callback")

    # Sign-in and the callback are loopback-only, like the other Google connections.
    monkeypatch.delenv("HUTCH_GOOGLE_OAUTH_CLIENT_ID", raising=False)
    with TestClient(create_app(), base_url="http://127.0.0.1:18787",
                    follow_redirects=False) as loop:
        sign_in = loop.post("/api/v1/connections/google-workspace/sign-in",
                            json={"label": "Test account"})
        assert sign_in.status_code == 409
        assert "client id" in sign_in.json()["detail"].lower()

        # The callback redirects honestly instead of raising; the query is consumed by
        # the security middleware so codes never sit in access logs.
        callback = loop.get("/api/v1/connections/google-workspace/callback?state=abc&code=def")
        assert callback.status_code == 303
        assert "google_workspace_result=error" in callback.headers["location"]
        assert callback.headers["cache-control"] == "no-store"


def test_google_file_service_updates_are_versioned_and_revision_bound(api):
    from hutch.gsuite.client import FILE_SCOPE, _atomic_private_json
    client, store, config = api
    account_id = "gws_0123456789abcdef01234567"
    _atomic_private_json(config.state_dir / "google-workspace-accounts.json", {
        account_id: {"label": "Files", "scopes": [FILE_SCOPE], "services": ["drive"], "revision": 0}})
    path = f"/api/v1/connections/google-workspace/accounts/{account_id}/services/docs"
    body = {"contract_version": 1, "enabled": True, "expected_revision": 0}
    assert client.put(path, json={**body, "contract_version": 2}).status_code == 422
    response = client.put(path, json=body)
    assert response.status_code == 200
    assert response.json()["account"]["services"] == ["drive", "docs"]
    assert client.put(path, json=body).status_code == 409
    listing = client.get("/api/v1/connections/google-workspace").json()
    assert listing["service_contract_version"] == 1
    assert listing["accounts"][0]["revision"] == 1
    assert all(row["scopes"] == [FILE_SCOPE] for row in listing["service_profiles"].values())
    assert not store.list_google_calendar_grants()
