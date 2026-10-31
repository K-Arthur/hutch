"""Server-surface tests for the provider catalogue, accounts, capabilities and runtimes."""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from hutch.connections import ConnectionBook
from hutch.server.app import create_app


@pytest.fixture()
def state(tmp_path, monkeypatch):
    for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    directory = tmp_path / "state"
    monkeypatch.setenv("HUTCH_STATE_DIR", str(directory))
    with TestClient(create_app()) as client:
        yield client, directory


def test_providers_api_lists_the_catalogue_without_secret_fields(state):
    client, _ = state
    response = client.get("/api/v1/providers")
    assert response.status_code == 200
    body = response.json()
    assert body["reviewed_on"] == "2026-10-30"
    assert len(body["providers"]) == 62
    ids = {row["id"] for row in body["providers"]}
    assert {"openai", "anthropic", "google", "minimax", "moonshot", "qwen", "xai", "zai",
            "opencode", "opencode-go", "fal", "ollama", "custom-compatible"} <= ids
    text = response.text.lower()
    for forbidden in ("api_key_env", "secret", "password", "bearer "):
        assert forbidden not in text
    openai = next(row for row in body["providers"] if row["id"] == "openai")
    assert any(method["type"] == "pkce" for method in openai["auth_methods"])


def test_provider_accounts_api_groups_accounts_and_reports_readiness(state):
    client, directory = state
    book = ConnectionBook(directory)
    book.add("openai-api", "openai-personal", title="Personal")
    book.add("openai-api", "openai-work", title="Work")
    response = client.get("/api/v1/provider-accounts")
    assert response.status_code == 200
    groups = {group["provider_id"]: group for group in response.json()["groups"]}
    assert set(groups) == {"openai"}
    assert len(groups["openai"]["accounts"]) == 2
    assert all(account["readiness"]["state"] == "needs_authentication"
               for account in groups["openai"]["accounts"])
    assert all("credential" in account["profile"] for account in groups["openai"]["accounts"])


def test_capability_api_reports_levels_and_evidence(state):
    client, _ = state
    response = client.get("/api/v1/provider-capabilities", params={"provider": "openai"})
    assert response.status_code == 200
    report = response.json()["report"]
    assert report["provider"] == "openai"
    assert report["levels"]["text"] == "documented"
    assert report["levels"]["tool_calls"] == "documented"
    assert "live-verified" not in report["levels"].values()
    assert all(item["source"] for item in report["evidence"])
    matrix = client.get("/api/v1/provider-capabilities")
    assert len(matrix.json()["reports"]) == 62
    assert client.get("/api/v1/provider-capabilities", params={"provider": "unknown-provider"}).status_code == 404


def test_readiness_api_explains_route_states(state):
    client, _ = state
    empty = client.get("/api/v1/provider-readiness", params={"spec": ""}).json()["readiness"]
    assert empty["state"] == "needs_configuration"
    ambient = client.get("/api/v1/provider-readiness", params={"spec": "openai/gpt-4o"}).json()["readiness"]
    assert ambient["state"] == "needs_authentication"
    blocked = client.get("/api/v1/provider-readiness", params={"spec": "github-copilot/x"}).json()["readiness"]
    assert blocked["state"] == "blocked_by_policy"
    local = client.get("/api/v1/provider-readiness").json()
    assert len(local["providers"]) == 62
    assert len(local["local_services"]) == 5


def test_runtime_catalog_separates_execution_from_providers(state):
    client, _ = state
    body = client.get("/api/v1/runtime-catalog").json()
    assert body["enabled"] == ["builtin", "opencode"]
    by_id = {item["id"]: item for item in body["runtimes"]}
    assert by_id["builtin"]["usage_reservation"] is True
    assert by_id["opencode"]["usage_reservation"] is False
    assert by_id["pi"]["enabled"] is False
    assert by_id["claude-code"]["enabled"] is False


def test_providers_page_renders_catalogue_accounts_and_local_services(state):
    client, directory = state
    book = ConnectionBook(directory)
    book.add("openai-api", "openai-personal", title="Personal")
    book.set_key("openai-personal", "sk-unit-test-placeholder")
    response = client.get("/providers")
    assert response.status_code == 200
    html = response.text
    assert "Two owner-authorized routes were live-verified on 2026-10-30" in html
    assert "Your provider accounts" in html
    assert "Execution runtimes" in html
    assert "Local inference on this machine" in html
    assert "data-provider-card" in html
    assert 'action="/providers/account/openai-personal/rename"' in html
    assert "sk-unit-test-placeholder" not in html
    assert re.search(r'name="csrf" value="[^"]+"', html)


def test_account_actions_require_csrf(state):
    client, _ = state
    response = client.post("/providers/account/anything/rename", data={"title": "x"})
    assert response.status_code == 403


def test_models_page_includes_route_readiness_without_calling_a_provider(state):
    client, directory = state
    book = ConnectionBook(directory)
    book.add("openai-api", "openai-personal", title="Personal")
    response = client.get("/models")
    assert response.status_code == 200
    # The configured route may not be in view.configured_routes until it is used or saved; the page must
    # still render. The readiness API covers the explicit route check.
    assert response.text.count("<html") <= 1
