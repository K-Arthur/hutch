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


def test_use_route_saves_the_default_through_the_existing_validated_endpoint(client):
    token = _csrf(client)
    response = client.post("/models/set-default", data={"csrf": token, "model": "mock/demo"}, follow_redirects=False)
    assert response.status_code == 303
    saved = json.loads(client.app.state.store.kv_get("workspace:model-defaults"))
    assert saved["model"] == "mock/demo"
    after = client.get("/models", headers=BROWSER).text
    assert "mock/demo" in after and "No model routes saved yet" not in after


def test_use_route_refuses_a_route_that_does_not_validate(client, monkeypatch):
    from hutch import modelchoices

    def refuse(config, store, bot, spec, *args, **kwargs):
        raise modelchoices.ModelNotUsable("not available", fix="connect it first")

    monkeypatch.setattr(modelchoices, "validate_override", refuse)
    token = _csrf(client)
    response = client.post("/models/set-default", data={"csrf": token, "model": "opencode/free/fake"}, follow_redirects=False)
    assert response.status_code == 303
    assert client.app.state.store.kv_get("workspace:model-defaults") is None, "nothing is saved for an unusable route"
