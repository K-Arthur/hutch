"""The Models page's install and remove routes, called the way the page calls them (they once raised NameError on every request).

A fake Ollama stands in for the runtime (the shape is the ndjson captured from Ollama 0.40.13). Every write needs the page's security
token in a header; nothing downloads unless a request asks for it.
"""

from __future__ import annotations

import re
import time

import pytest
from fastapi.testclient import TestClient

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
        yield client, runtime, {"x-csrf-token": token.group(1)} if token else {}
    runtime.close()


def _wait(client, job_id, states=("done", "failed", "cancelled")):
    for _ in range(100):
        job = client.get(f"/api/models/install/{job_id}").json()
        if job["state"] in states:
            return job
        time.sleep(0.05)
    return job


def test_a_write_without_the_page_token_is_refused_and_starts_nothing(env):
    client, runtime, _ = env
    refused = client.post("/api/models/install", json={"model": "qwen3:4b"})
    assert refused.status_code == 403
    assert "qwen3:4b" not in runtime.models and client.get("/api/models/install").json() == {"jobs": []}


def test_install_runs_to_done_and_the_model_is_in_the_runtime(env):
    client, runtime, headers = env
    started = client.post("/api/models/install", json={"model": "qwen3:4b"}, headers=headers)
    assert started.status_code == 200, started.text
    job = _wait(client, started.json()["id"])
    assert job["state"] == "done" and "qwen3:4b" in runtime.models
    assert [item["id"] for item in client.get("/api/models/install").json()["jobs"]] == [job["id"]]


@pytest.mark.parametrize("bad", ["", "../etc", "has space", "a" * 300, "x;rm -rf /"])
def test_a_bad_model_name_is_refused_before_anything_is_requested(env, bad):
    client, runtime, headers = env
    response = client.post("/api/models/install", json={"model": bad}, headers=headers)
    assert response.status_code == 422, (bad, response.text)
    assert not any(name not in ("fake:4b",) for name in runtime.models)


def test_the_plan_endpoint_reports_catalog_size_and_the_runtime_directory(env):
    client, _, _ = env
    plan = client.get("/api/models/install/plan", params={"model": "qwen3:4b"}).json()
    assert plan["model"] == "qwen3:4b"
    assert plan["size_source"] == "catalog" and plan["size_bytes"] > 0
    assert plan["model_dir"] and plan["model_dir_source"] in ("default", "OLLAMA_MODELS")
    assert plan["free_bytes"] is not None
    assert plan["blocked"] == ""
    assert plan["fit_label"]


def test_the_plan_endpoint_refuses_a_bad_name_before_a_download(env):
    client, runtime, _ = env
    response = client.get("/api/models/install/plan", params={"model": "has space"})
    assert response.status_code == 422
    assert "has space" not in runtime.models


def test_remove_deletes_an_installed_model_and_refuses_one_that_is_missing(env):
    client, runtime, headers = env
    assert client.post("/api/models/remove", json={"model": "fake:4b"}, headers=headers).status_code == 200
    assert "fake:4b" not in runtime.models
    assert client.post("/api/models/remove", json={"model": "fake:4b"}, headers=headers).status_code == 404
    assert client.post("/api/models/remove", json={"model": "fake:4b"}).status_code == 403


def test_an_unknown_job_is_a_clear_404(env):
    client, _, headers = env
    assert client.get("/api/models/install/nope").status_code == 404
    assert client.delete("/api/models/install/nope", headers=headers).status_code == 404
