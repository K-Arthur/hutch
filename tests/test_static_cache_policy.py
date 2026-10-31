"""A browser must revalidate the dashboard after an update (owner report: "the changes are not being recognized").

Static files and the page shell carried an ETag and Last-Modified but no Cache-Control, so a browser applied heuristic
freshness and could serve a script or the shell from cache for hours after Hutch changed. Local responses now say
`no-cache` (always revalidate; the ETag makes that a cheap 304); paired and remote requests keep `private, no-store`.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from hutch.server.app import create_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:9")
    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.mark.parametrize("path", ["/", "/static/app.js", "/static/studio.css", "/static/starter-route.js", "/api/health"])
def test_local_responses_must_be_revalidated(client, path):
    response = client.get(path)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache", path


def test_an_unchanged_script_is_a_cheap_not_modified(client):
    first = client.get("/static/app.js")
    assert first.headers.get("etag")
    again = client.get("/static/app.js", headers={"If-None-Match": first.headers["etag"]})
    assert again.status_code == 304 and again.headers["cache-control"] == "no-cache"
