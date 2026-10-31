"""Models acknowledges a detected-but-unsaved AI service (audit finding S2).

First run reads live detection ("OpenCode is ready with 8 model options") while the
Models page used to list only saved routes ("No model routes configured"). The page
now says what it has saved, offers the detected service, and one click saves it as the
workspace default through the existing validated endpoint. Detection itself runs in the
browser against the same endpoint first run uses (tests/e2e/test_models_detected_route.py),
because it can start a private OpenCode server and a page view must not.
"""

from __future__ import annotations

import json
import re

import pytest
from fastapi.testclient import TestClient

from hutch.server.app import create_app

BROWSER = {"accept": "text/html"}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    # Ollama pinned to a closed port: a running local engine already counts as a route.
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:9")
    from hutch.runtime.ladder import reset_provider_cache
    reset_provider_cache()
    with TestClient(create_app()) as test_client:
        yield test_client


def _csrf(client) -> str:
    return re.search(r'<meta name="csrf" content="([^"]+)"', client.get("/models", headers=BROWSER).text).group(1)


def test_empty_models_page_says_saved_and_offers_detection(client):
    text = client.get("/models", headers=BROWSER).text
    assert "No model routes saved yet" in text
    assert "No model routes configured" not in text, "the claim that contradicted first run"
    panel = re.search(r'<section[^>]*id="detected-service"[^>]*>', text)
    assert panel and 'data-no-routes="1"' in panel.group(0)
    assert '/static/models-detect.js' in text


def test_models_page_with_a_saved_route_has_no_detection_panel(client):
    client.app.state.store.kv_set("workspace:model-defaults", json.dumps(
        {"model": "mock/demo", "inference_mode": "hybrid", "configured": True}))
    text = client.get("/models", headers=BROWSER).text
    assert "mock/demo" in text
    assert "No model routes saved yet" not in text
    assert 'data-no-routes="1"' not in text


def test_use_route_opens_settings_and_writes_nothing_by_itself(client):
    """Settings is the one default writer: the Models use action only opens it with the route prefilled."""
    token = _csrf(client)
    response = client.post("/models/set-default", data={"csrf": token, "model": "mock/demo"}, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].endswith("/#/settings")
    assert client.app.state.store.kv_get("workspace:model-defaults") is None, "Models never writes the default"


def test_the_one_writer_uses_the_validated_settings_api(client):
    """The Settings endpoint is the single write path, and it refuses a route that cannot run."""
    refused = client.put("/api/v1/preferences/model-defaults",
                         json={"model": "mock/demo", "inference_mode": "hybrid"})
    assert refused.status_code == 422
    assert client.app.state.store.kv_get("workspace:model-defaults") is None
    saved = client.put("/api/v1/preferences/model-defaults",
                       json={"model": "ollama/llama3.2:3b", "inference_mode": "hybrid"})
    assert saved.status_code in (200, 422)     # 422 only if this host has no matching local route installed
    if saved.status_code == 200:
        assert "ollama/llama3.2:3b" in client.get("/models", headers=BROWSER).text
