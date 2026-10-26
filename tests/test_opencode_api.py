from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from hutch.runtime.opencode_server import OpenCodeModel, OpenCodeServer, OpenCodeServerError
from hutch.server.app import create_app


class FakeServer:
    def __init__(self, *_args, **_kwargs):
        self.keys: list[tuple[str, str]] = []
        self.oauth: list[tuple[str, str]] = []

    def start(self):
        return None

    def close(self):
        return None

    def info(self):
        return {"version": "2.1.2"}

    def integrations(self):
        return [{
            "id": "openai", "name": "OpenAI",
            "methods": [{"id": "", "type": "key", "label": "API key"}],
            "connections": [],
        }]

    def models(self, _workspace=None):
        return [OpenCodeModel("openai", "gpt-test", "GPT Test", context=128_000, output=16_000)]

    def connect_key(self, integration_id, key, *, label=""):
        self.keys.append((integration_id, key))

    def start_oauth(self, integration_id, method_id):
        self.oauth.append((integration_id, method_id))
        return {"attemptID": "att_1", "url": "https://example.test/auth", "instructions": "Sign in",
                "mode": "auto", "time": {"created": 1, "expires": 2}}


def test_opencode_v1_is_rejected_before_starting_a_server(tmp_path, monkeypatch):
    class Result:
        returncode = 0
        stdout = "1.18.0"
        stderr = ""

    monkeypatch.setattr("hutch.runtime.opencode_server.subprocess.run", lambda *a, **k: Result())
    server = OpenCodeServer(tmp_path / "state")
    with pytest.raises(OpenCodeServerError, match="OpenCode V2"):
        server.start()
    assert server.process is None


def test_version_check_uses_the_same_private_profile_as_the_server(tmp_path, monkeypatch):
    seen = {}
    def version(command, **kwargs):
        seen.update(kwargs)
        return type("Result", (), {"returncode": 0, "stdout": "opencode v1.18.0", "stderr": ""})()
    monkeypatch.setattr("hutch.runtime.opencode_server.subprocess.run", version)
    with pytest.raises(OpenCodeServerError, match="OpenCode V2"):
        OpenCodeServer(tmp_path / "private-state").start()
    assert str(tmp_path / "private-state") in seen["env"]["HOME"]
    assert seen["cwd"] == seen["env"]["HOME"]
    assert "OPENROUTER_API_KEY" not in seen["env"]


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("HUTCH_ALLOWED_HOSTS", "testserver")
    fake = FakeServer()
    monkeypatch.setattr("hutch.runtime.opencode_server.OpenCodeServer", lambda *a, **k: fake)
    with TestClient(create_app()) as c:
        c.fake_opencode = fake
        yield c


def test_opencode_status_is_truthful_and_never_returns_a_secret(client):
    response = client.get("/api/v1/opencode/status")
    assert response.status_code == 200
    body = response.json()
    assert body["version"] == "2.1.2"
    assert body["models"][0]["spec"] == "opencode/openai/gpt-test"
    assert body["ready"] is True
    assert body["authenticated"] is False  # the fixture has a model but no saved account
    assert "password" not in response.text.lower()
    assert "api_key" not in response.text.lower()


def test_opencode_key_connection_is_write_only(client):
    response = client.post("/api/v1/opencode/connect/key", json={
        "integration_id": "openai", "key": "sk-secret-never-echoed", "label": "Work",
    })
    assert response.status_code == 200
    assert client.fake_opencode.keys == [("openai", "sk-secret-never-echoed")]
    assert "sk-secret-never-echoed" not in response.text


def test_opencode_oauth_start_returns_only_the_attempt_descriptor(client):
    response = client.post("/api/v1/opencode/oauth/start", json={
        "integration_id": "openai", "method_id": "browser",
    })
    assert response.status_code == 200
    assert response.json()["attempt"]["attemptID"] == "att_1"
    assert client.fake_opencode.oauth == [("openai", "browser")]


def test_local_login_routes_transfer_only_selected_key(client, tmp_path, monkeypatch):
    import json
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    auth = tmp_path / "opencode" / "auth.json"
    auth.parent.mkdir()
    auth.write_text(json.dumps({"openai": {"type": "api", "key": "selected-only"},
                                "other": {"type": "api", "key": "never-import"}}))
    auth.chmod(0o600)
    response = client.get("/api/v1/opencode/local-logins")
    assert response.status_code == 200
    assert "selected-only" not in response.text and "never-import" not in response.text
    response = client.post("/api/v1/opencode/connect/local", json={"provider_id": "openai"})
    assert response.status_code == 200
    assert client.fake_opencode.keys == [("openai", "selected-only")]
    assert "selected-only" not in response.text
    assert client.post("/api/v1/opencode/connect/local", json={"provider_id": "../auth"}).status_code == 422
