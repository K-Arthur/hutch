"""Tests for readiness states (local facts only, no network)."""

from __future__ import annotations

import pytest

from hutch.connections import ConnectionBook
from hutch.providers.readiness import (
    STATES,
    account_readiness,
    provider_readiness,
    readiness_json,
    route_readiness,
)


@pytest.fixture()
def book(tmp_path, monkeypatch):
    for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    return ConnectionBook(tmp_path / "state")


def test_account_without_a_key_needs_authentication(book):
    book.add("openai-api", "openai-personal", title="Personal")
    state = account_readiness(book, "openai-personal")
    assert state.state == "needs_authentication"
    assert "OPENAI_API_KEY" in (state.next_action + state.detail)
    assert state.state in STATES


def test_account_with_a_key_is_available_but_not_capability_verified(book):
    book.add("openai-api", "openai-personal", title="Personal")
    book.set_key("openai-personal", "sk-unit-test-placeholder")
    state = account_readiness(book, "openai-personal")
    assert state.state == "available"
    assert state.ready
    route = route_readiness(book, "openai-personal/gpt-4o")
    assert route.state == "capability_unverified"
    assert route.scope == "model"


def test_empty_or_unknown_specs_need_configuration(book):
    assert route_readiness(book, "").state == "needs_configuration"
    assert route_readiness(book, "not-a-provider/model").state == "needs_configuration"


def test_ambient_key_route_is_never_called_available(book, monkeypatch):
    assert route_readiness(book, "openai/gpt-4o").state == "needs_authentication"
    monkeypatch.setenv("OPENAI_API_KEY", "env-unit-test-placeholder")
    route = route_readiness(book, "openai/gpt-4o")
    assert route.state == "capability_unverified"


def test_blocked_and_deferred_providers_are_explained(book):
    assert route_readiness(book, "github-copilot/some-model").state == "blocked_by_policy"
    assert route_readiness(book, "fal/some-model").state == "needs_configuration"


def test_local_route_states_depend_on_probe_result(book):
    assert route_readiness(book, "ollama/llama3").state == "capability_unverified"
    unreachable = {"ollama": {"reachable": False}}
    assert route_readiness(book, "ollama/llama3", local_services=unreachable).state == "endpoint_unavailable"
    reachable = {"ollama": {"reachable": True, "models": ["llama3"]}}
    assert route_readiness(book, "ollama/llama3", local_services=reachable).state == "capability_unverified"


def test_provider_readiness_groups_accounts(book):
    book.add("openai-api", "openai-personal")
    book.add("openai-api", "openai-work")
    summary = provider_readiness(book, "openai")
    assert summary["provider"] == "openai"
    assert len(summary["accounts"]) == 2
    assert all(account["state"] == "needs_authentication" for account in summary["accounts"])
    body = readiness_json(account_readiness(book, "openai-personal"))
    assert set(body) == {"state", "subject", "scope", "detail", "next_action", "ready"}
