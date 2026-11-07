"""Per-assistant data-sharing confirmation for non-local model routes (EC-28).

A local route needs no confirmation. A cloud-tagged model served through a
loopback runtime, a hosted provider and a server on the local network each need
one, and the confirmation is consumed by the change that follows.
"""

from __future__ import annotations

import json
import re
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from hutch.models import ApprovalMode, Bot
from hutch.modelchoices import reset_cache
from hutch.route_sharing import consume_ack, disclosure_for, record_ack
from hutch.runtime.ladder import reset_provider_cache
from hutch.server.app import create_app
from tests.fakes import FakeOllama


class Store:
    def __init__(self):
        self.kv: dict[str, str] = {}

    def kv_get(self, key, default=None):
        return self.kv.get(key, default)

    def kv_set(self, key, value):
        self.kv[key] = value


def _bot(**kw):
    return SimpleNamespace(id="bot-1", name="scout", display_name="Scout", base_url="", **kw)


def _config(tmp_path):
    return SimpleNamespace(state_dir=tmp_path)


def test_a_local_route_needs_no_confirmation(tmp_path, monkeypatch):
    monkeypatch.setattr("hutch.providers.locality.fetch_ollama_rows",
                        lambda *args, **kwargs: [{"name": "qwen3:0.6b"}])
    assert disclosure_for(_bot(), "ollama/qwen3:0.6b", _config(tmp_path)) is None


def test_a_renamed_cloud_copy_is_cloud_routed_even_without_a_cloud_tag(tmp_path, monkeypatch):
    monkeypatch.setattr("hutch.providers.locality.fetch_ollama_rows",
                        lambda *args, **kwargs: [{"name": "my-local-copy:latest", "remote_host": "ollama.com"}])
    disclosure = disclosure_for(_bot(), "ollama/my-local-copy:latest", _config(tmp_path))
    assert disclosure is not None
    assert disclosure.locality == "cloud_via_local"
    assert "forwards them to a cloud service" in disclosure.body


def test_a_hosted_provider_needs_a_confirmation(tmp_path):
    disclosure = disclosure_for(_bot(), "openai/gpt-5", _config(tmp_path))
    assert disclosure is not None and disclosure.locality == "cloud"
    assert "Data leaves this computer" in disclosure.body


def test_a_private_https_connection_is_network_not_cloud(tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    (state / "connections.json").write_text(json.dumps({"connections": {"lanbox": {
        "template": "custom-openai", "title": "LAN box", "account_id": "lanbox",
        "base_url": "https://192.168.1.50:8443/v1"}}}))
    disclosure = disclosure_for(_bot(), "lanbox/qwen3-4b", _config(state))
    assert disclosure is not None and disclosure.locality == "network"
    assert "another machine on your network" in disclosure.body


def test_a_loopback_gateway_connection_needs_no_confirmation(tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    (state / "connections.json").write_text(json.dumps({"connections": {"gateway": {
        "template": "custom-openai", "title": "Gateway", "account_id": "gateway",
        "base_url": "http://127.0.0.1:4000/v1"}}}))
    assert disclosure_for(_bot(), "gateway/local-model", _config(state)) is None


def test_a_confirmation_is_consumed_once(tmp_path, monkeypatch):
    monkeypatch.setattr("hutch.providers.locality.fetch_ollama_rows",
                        lambda *args, **kwargs: [{"name": "cloud:70b-cloud"}])
    disclosure = disclosure_for(_bot(), "ollama/cloud:70b-cloud", _config(tmp_path))
    store = Store()
    record_ack(store, "bot-1", disclosure.spec, "default", disclosure)
    assert consume_ack(store, "bot-1", disclosure.spec, "default", disclosure) is True
    assert consume_ack(store, "bot-1", disclosure.spec, "default", disclosure) is False


def test_a_confirmation_for_another_route_is_not_consumed(tmp_path, monkeypatch):
    monkeypatch.setattr("hutch.providers.locality.fetch_ollama_rows",
                        lambda *args, **kwargs: [{"name": "cloud:70b-cloud"}])
    disclosure = disclosure_for(_bot(), "ollama/cloud:70b-cloud", _config(tmp_path))
    store = Store()
    record_ack(store, "bot-1", disclosure.spec, "default", disclosure)
    assert consume_ack(store, "bot-1", "ollama/other:3b", "default", disclosure) is False
    assert consume_ack(store, "bot-1", disclosure.spec, "default", disclosure) is True


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    for key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENCODE_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    fake = FakeOllama({"local:3b": {}, "cloud:70b-cloud": {}})
    monkeypatch.setenv("OLLAMA_HOST", fake.url)
    reset_provider_cache()
    reset_cache()
    with TestClient(create_app()) as client:
        client.fake = fake
        yield client
    fake.close()


def _bot_row(env):
    return env.app.state.store.create_bot(
        Bot(name="scout", display_name="Scout", model="ollama/local:3b", tools=[],
            selfcheck=False, approval_mode=ApprovalMode.auto))


def _csrf(client):
    html = client.get("/models").text
    return re.search(r'name="csrf" content="([^"]+)"', html).group(1)


def test_the_read_endpoint_says_which_routes_need_a_confirmation(env):
    _bot_row(env)
    cloud = env.get("/api/bots/scout/model-sharing", params={"model": "ollama/cloud:70b-cloud"})
    assert cloud.status_code == 200 and cloud.json()["required"] is True
    assert cloud.json()["disclosure"]["locality"] == "cloud_via_local"
    local = env.get("/api/bots/scout/model-sharing", params={"model": "ollama/local:3b"})
    assert local.status_code == 200 and local.json()["required"] is False


def test_switching_to_a_cloud_model_needs_one_recorded_confirmation(env):
    bot = _bot_row(env)
    refused = env.patch(f"/api/bots/{bot.name}", json={"model": "ollama/cloud:70b-cloud"})
    assert refused.status_code == 409
    assert "confirm the data-sharing notice" in refused.json()["detail"]

    token = _csrf(env)
    ack = env.post(f"/api/bots/{bot.name}/model-sharing",
                   json={"model": "ollama/cloud:70b-cloud", "scope": "default"},
                   headers={"x-csrf-token": token})
    assert ack.status_code == 200 and ack.json()["recorded"] is True
    saved = env.patch(f"/api/bots/{bot.name}", json={"model": "ollama/cloud:70b-cloud"})
    assert saved.status_code == 200 and saved.json()["model"] == "ollama/cloud:70b-cloud"

    # The confirmation was consumed: switching away and back asks again.
    assert env.patch(f"/api/bots/{bot.name}", json={"model": "ollama/local:3b"}).status_code == 200
    again = env.patch(f"/api/bots/{bot.name}", json={"model": "ollama/cloud:70b-cloud"})
    assert again.status_code == 409


def test_the_confirmation_endpoint_requires_the_page_token(env):
    bot = _bot_row(env)
    refused = env.post(f"/api/bots/{bot.name}/model-sharing",
                       json={"model": "ollama/cloud:70b-cloud", "scope": "default"},
                       headers={"x-csrf-token": "not-the-cookie"})
    assert refused.status_code == 403


def test_a_one_message_override_also_needs_a_confirmation(env):
    bot = _bot_row(env)
    refused = env.post(f"/api/bots/{bot.name}/run",
                       json={"prompt": "hi", "model": "ollama/cloud:70b-cloud"})
    assert refused.status_code == 409
    token = _csrf(env)
    ack = env.post(f"/api/bots/{bot.name}/model-sharing",
                   json={"model": "ollama/cloud:70b-cloud", "scope": "override"},
                   headers={"x-csrf-token": token})
    assert ack.status_code == 200 and ack.json()["recorded"] is True
    accepted = env.post(f"/api/bots/{bot.name}/run",
                        json={"prompt": "hi", "model": "ollama/cloud:70b-cloud"})
    assert accepted.status_code == 201
    # Drain the run so the fixture's shutdown is quiet.
    for _ in range(200):
        run = env.app.state.store.get_run(accepted.json()["id"])
        if run is None or run.status.value not in ("pending", "running", "loading_model"):
            break
        import time
        time.sleep(0.05)
