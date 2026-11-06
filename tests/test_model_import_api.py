"""The import route's HTTP contract: CSRF, validation, status codes and JSON shape."""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from hutch.providers.base import ProviderError
from hutch.providers.model_import import ImportResult
from hutch.server.app import create_app
from tests.fakes import FakeOllama


@pytest.fixture()
def env(tmp_path, monkeypatch):
    runtime = FakeOllama(models={"fake:4b": {}})
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("OLLAMA_HOST", runtime.url)
    from hutch.runtime.ladder import reset_provider_cache
    reset_provider_cache()
    with TestClient(create_app()) as client:
        page = client.get("/models")
        token = re.search(r'name="csrf" content="([^"]+)"', page.text)
        headers = {"x-csrf-token": token.group(1)} if token else {}
        yield client, runtime, headers, tmp_path
    runtime.close()


def test_import_requires_the_page_token(env):
    client, _, _, tmp_path = env
    path = tmp_path / "model.gguf"
    path.write_bytes(b"GGUF" + b"\0" * 80)
    response = client.post("/api/models/import", json={"name": "imported:1b", "path": str(path)})
    assert response.status_code == 403


def test_a_non_gguf_path_is_refused_before_the_runtime_is_called(env):
    client, runtime, headers, tmp_path = env
    path = tmp_path / "notes.txt"
    path.write_text("not a model", "utf-8")
    response = client.post("/api/models/import", json={"name": "imported:1b", "path": str(path)},
                           headers=headers)
    assert response.status_code == 422
    assert "gguf" in response.json()["detail"].lower()
    assert "imported:1b" not in runtime.models


def test_a_missing_file_is_a_clear_404(env):
    client, _, headers, tmp_path = env
    response = client.post("/api/models/import",
                           json={"name": "imported:1b", "path": str(tmp_path / "absent.gguf")},
                           headers=headers)
    assert response.status_code == 404
    assert "does not exist" in response.json()["detail"]


def test_a_successful_import_returns_the_result(env, monkeypatch):
    client, _, headers, _ = env
    result = ImportResult(model="imported:1b", path="/models/tiny.gguf", size_bytes=88,
                          sha256="a" * 64, digest="sha256:" + "a" * 64, license_text="MIT",
                          license_source="provided", capabilities=["tools"])
    monkeypatch.setattr("hutch.server.pages_models.import_local_model",
                        lambda *args, **kwargs: result)
    response = client.post("/api/models/import",
                           json={"name": "imported:1b", "path": "/models/tiny.gguf",
                                 "sha256": "a" * 64, "license": "MIT"}, headers=headers)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["model"] == "imported:1b" and payload["license_source"] == "provided"
    assert payload["capabilities"] == ["tools"]


def test_a_runtime_refusal_is_a_409(env, monkeypatch):
    client, _, headers, _ = env

    def refuse(*args, **kwargs):
        raise ProviderError("bad_request", "the runtime refused the import")

    monkeypatch.setattr("hutch.server.pages_models.import_local_model", refuse)
    response = client.post("/api/models/import",
                           json={"name": "imported:1b", "path": "/models/tiny.gguf"},
                           headers=headers)
    assert response.status_code == 409
    assert "refused" in response.json()["detail"]


def test_a_bad_name_is_a_422(env):
    client, _, headers, tmp_path = env
    path = tmp_path / "tiny.gguf"
    path.write_bytes(b"GGUF" + b"\0" * 80)
    response = client.post("/api/models/import", json={"name": "has space", "path": str(path)},
                           headers=headers)
    assert response.status_code == 422
