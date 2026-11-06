"""Where-inference-happens labels for the Models page (Phase 7.2).

The server signal wins: a renamed cloud copy (my-local-copy) listed with
remote_host must not be grouped under "On this machine" just because its name
does not contain a cloud tag.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from hutch.models import Bot
from hutch.modelview import locality_for_route, privacy_label_for
from hutch.server.app import create_app


def test_the_server_signal_wins_over_the_name_for_a_renamed_cloud_copy():
    entry = {"name": "my-local-copy:latest", "remote_host": "ollama.com"}
    assert locality_for_route("ollama/my-local-copy:latest", True, entry=entry) == "cloud_via_local"
    assert "forwarded to a cloud service" in privacy_label_for("cloud_via_local")


def test_a_local_model_without_a_remote_signal_is_on_this_machine():
    entry = {"name": "qwen3:0.6b"}
    assert locality_for_route("ollama/qwen3:0.6b", True, entry=entry) == "machine"
    assert "stays on this machine" in privacy_label_for("machine")


def test_a_private_https_connection_is_on_your_network_and_a_public_one_is_hosted():
    assert locality_for_route("lanbox/qwen3-4b", False, "https://192.168.1.50:8443/v1") == "network"
    assert locality_for_route("openai/gpt-5", False, "https://api.openai.com/v1") == "cloud"
    assert "service you control" in privacy_label_for("network")


def test_an_ollama_route_is_not_ready_when_ollama_is_down(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("OLLAMA_HOST", "127.0.0.1:1")
    from hutch.runtime.ladder import reset_provider_cache
    reset_provider_cache()
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        client.app.state.store.create_bot(Bot(name="offline-bot", model="ollama/qwen3:0.6b", tools=[]))
        html = client.get("/models").text
    assert "offline-bot" in html
    assert "Ollama is not running, so this route cannot run" in html
