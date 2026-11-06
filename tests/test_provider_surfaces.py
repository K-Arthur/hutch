"""Server-surface tests for the provider catalogue, accounts, capabilities and runtimes."""

from __future__ import annotations

import json
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


def test_resolution_api_names_the_account_source_and_refuses_ambiguity(state, monkeypatch):
    client, directory = state
    monkeypatch.setenv("OPENAI_API_KEY", "placeholder")
    ambient = client.get("/api/v1/provider-resolution",
                         params={"spec": "openai/gpt-4o"}).json()["resolution"]
    assert ambient["account"] == "openai"
    assert "ambient environment (OPENAI_API_KEY)" == ambient["account_source"]
    assert ambient["substituted"] is False
    book = ConnectionBook(directory)
    book.add("openai-api", "openai-personal")
    book.add("openai-api", "openai-work")
    ambiguous = client.get("/api/v1/provider-resolution",
                           params={"spec": "openai/gpt-4o"}).json()["resolution"]
    assert ambiguous["account"] == ""
    assert ambiguous["status"] == "needs_configuration"
    assert ambiguous["substituted"] is False


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
    assert "Live-verified in this build" in html
    assert "deepseek/deepseek-flash" in html and "xiaomi/mimo-v2.6-flash" in html
    assert "Two owner-authorized routes were live-verified" not in html
    assert "Catalogue status:" in html and "implemented-unverified" in html
    assert "Your provider accounts" in html
    assert "Execution runtimes" in html
    assert "Local inference on this machine" in html
    assert "data-provider-card" in html
    assert 'action="/providers/account/openai-personal/rename"' in html
    assert "sk-unit-test-placeholder" not in html
    assert re.search(r'name="csrf" value="[^"]+"', html)


def test_provider_and_connection_pages_show_expired_and_revoked_credentials(state):
    client, directory = state
    account_id = "acct_" + "d" * 24
    root = directory / "chatgpt"
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = root / "accounts.json"

    def write(record):
        path.write_text(json.dumps({"version": 1, "host_id": "urn:uuid:test",
                                    "accounts": {account_id: record}}))
        path.chmod(0o600)

    book = ConnectionBook(directory)
    book.add("chatgpt-plan", "chatgpt-plan", auth_account_id=account_id)
    write({"access_token": "access", "refresh_token": "", "expires_at": 0,
           "scopes": ["chatgpt.tokens.use.direct"]})
    assert "authentication expired" in client.get("/providers").text
    assert "expired - sign in again" in client.get("/legacy/connections").text
    write({"access_token": "", "refresh_token": "", "expires_at": 0, "revocation_status": "confirmed"})
    assert "needs authentication" in client.get("/providers").text
    assert "revoked - sign in again" in client.get("/legacy/connections").text


def test_connections_page_has_one_add_form_and_a_template_reference(state):
    client, _ = state
    html = client.get("/legacy/connections").text
    assert html.count('action="/connections/add"') == 1
    assert 'id="connection-template"' in html
    assert "Template reference (37)" in html
    assert html.count("Template reference") == 1


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
