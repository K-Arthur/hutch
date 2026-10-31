"""The governed search_web tool: account selection, approval, output and the ledger.

NO NETWORK: the adapter runs through ``httpx.MockTransport``; the real policy engine, gate
recorder, media-free run ledger and SQLite store run against a temporary state directory.
"""

from __future__ import annotations

import json

import httpx
import pytest

from hutch.connections import load_templates
from hutch.integrations.catalog import OFFLINE_WITHHELD_TOOLS
from hutch.providers.search import route_from_template
from hutch.tools import ALL_TOOL_NAMES, GROUPS, expand_tools
from hutch.tools.search import SearchWebTool
from tests.support.audio import (add_xiaomi, install_fake_transport, make_ctx,
                                 no_xiaomi_env)
from tests.test_search_support import OBSERVED_SEARCH_RESPONSE, no_usage, observed, template

# ---------------------------------------------------------------- tool path


def test_the_tool_is_registered_in_its_own_group():
    assert "search_web" in ALL_TOOL_NAMES
    assert GROUPS["search"] == ["search_web"]
    assert expand_tools(["search"]) == ["search_web"]
    assert "search_web" in OFFLINE_WITHHELD_TOOLS


def test_with_no_search_connection_the_tool_refuses_and_points_at_the_local_alternative(
        store, config, tmp_path, monkeypatch):
    no_xiaomi_env(monkeypatch)
    ctx, gate = make_ctx(store, config, tmp_path)
    result = SearchWebTool().run({"query": "weather"}, ctx)
    assert not result.ok
    assert "no configured connection offers provider-native search" in result.output
    assert "live_search" in result.output
    assert gate.calls == []


def test_a_connection_without_a_key_fails_before_the_request(store, config, tmp_path, monkeypatch):
    no_xiaomi_env(monkeypatch)
    add_xiaomi(config, key=None)
    ctx, gate = make_ctx(store, config, tmp_path)
    result = SearchWebTool().run({"query": "weather"}, ctx)
    assert not result.ok
    assert "XIAOMI_TOKEN_PLAN_API_KEY" in result.output
    assert gate.calls == []


def test_the_approval_names_the_destination_the_caps_and_the_billing_route(
        store, config, tmp_path, monkeypatch):
    no_xiaomi_env(monkeypatch)
    add_xiaomi(config)
    install_fake_transport(monkeypatch, lambda request: httpx.Response(
        200, json=OBSERVED_SEARCH_RESPONSE))
    ctx, gate = make_ctx(store, config, tmp_path)

    result = SearchWebTool().run({"query": "Wuhan weather tomorrow"}, ctx)

    assert result.ok, result.output
    call = gate.calls[0]
    assert call["tool"] == "web_search"
    assert call["decision"].outward is True
    detail = call["detail"]
    assert detail["connection"] == "mimo"
    assert detail["provider"] == "xiaomi"
    assert detail["endpoint"] == "https://token-plan-sgp.xiaomimimo.com/v1"
    assert detail["model"] == "mimo-v2.6-flash"
    assert detail["billing"] == "subscription"
    assert detail["force_search"] is True
    assert detail["max_keyword"] == 2
    assert "bills per search round" in detail["note"]


def test_the_answer_sources_and_usage_reach_the_model_and_the_ledger(
        store, config, tmp_path, monkeypatch):
    no_xiaomi_env(monkeypatch)
    add_xiaomi(config)
    install_fake_transport(monkeypatch, lambda request: httpx.Response(
        200, json=OBSERVED_SEARCH_RESPONSE))
    ctx, gate = make_ctx(store, config, tmp_path)

    result = SearchWebTool().run({"query": "Wuhan weather tomorrow"}, ctx)

    assert result.ok, result.output
    assert result.data["citation_count"] == 2
    assert result.data["search_calls"] == 3
    assert result.data["searched"] is True
    assert result.data["citations"][0]["url"].startswith("https://www.weather.com.cn/")
    assert "[S1]" in result.output and "[S2]" in result.output
    assert "untrusted data" in result.output
    assert "3 billed search call(s)" in result.output

    row = tuple(store._db.execute(
        "SELECT provider, model, prompt_tokens, completion_tokens, kind, account_id "
        "FROM usage WHERE run_id = ?", (ctx.run.id,)).fetchone())
    assert row == ("xiaomi", "mimo-v2.6-flash", 1476, 60, "search", "mimo")
    assert (ctx.run.prompt_tokens, ctx.run.completion_tokens) == (1476, 60)


def test_an_ungrounded_reply_is_labelled_in_the_output_not_smoothed_over(
        store, config, tmp_path, monkeypatch):
    no_xiaomi_env(monkeypatch)
    add_xiaomi(config)
    body = no_usage(observed())
    body["choices"][0]["message"]["annotations"] = None
    install_fake_transport(monkeypatch, lambda request: httpx.Response(200, json=body))
    ctx, gate = make_ctx(store, config, tmp_path)

    result = SearchWebTool().run({"query": "weather"}, ctx)

    assert result.ok, result.output
    assert result.data["searched"] is False
    assert "does not present this as grounded" in result.output


def test_the_recorded_arguments_carry_the_query_length_not_the_query(
        store, config, tmp_path, monkeypatch):
    no_xiaomi_env(monkeypatch)
    ctx, _gate = make_ctx(store, config, tmp_path)
    recorded = SearchWebTool().recorded_arguments(
        {"query": "a private question about my health", "connection": "mimo"}, ctx)
    assert recorded == {"query_chars": 34, "connection": "mimo"}
    assert "private" not in json.dumps(recorded)


def test_the_approval_gate_denial_stops_the_spend(store, config, tmp_path, monkeypatch):
    no_xiaomi_env(monkeypatch)
    add_xiaomi(config)
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, json=OBSERVED_SEARCH_RESPONSE)

    install_fake_transport(monkeypatch, handler)
    ctx, _gate = make_ctx(store, config, tmp_path)

    def deny(*args, **kwargs):
        raise PermissionError("the operator declined the search")

    ctx.gate.decide = deny
    result = SearchWebTool().run({"query": "weather"}, ctx)
    assert not result.ok and "declined" in result.output
    assert calls == []


def test_the_providers_own_param_field_reaches_the_message():
    """Observed live on 2026-10-31: the message was generic and ``param`` held the cause."""
    from hutch.providers.search import WebSearchClient

    route = route_from_template(template())
    response = httpx.Response(
        400,
        json={"error": {"code": "400", "message": "Param Incorrect", "type": "",
                         "param": "web search tool found in the request body, but "
                                  "webSearchEnabled is false"}},
        request=httpx.Request("POST", "https://unit.test/v1/chat/completions"))
    client = WebSearchClient(base_url="http://unit.test/v1", api_key="k", route=route)
    message = client._error_from_response(response)
    assert "webSearchEnabled is false" in message
    assert "has not activated the provider's web-search plugin" in message
    assert "not a Hutch setting" in message


def test_a_provider_error_is_reported_without_a_retry(store, config, tmp_path, monkeypatch):
    no_xiaomi_env(monkeypatch)
    add_xiaomi(config)
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        return httpx.Response(403, json={"error": {
            "message": "web search plugin is not activated for this account"}})

    install_fake_transport(monkeypatch, handler)
    ctx, _gate = make_ctx(store, config, tmp_path)

    result = SearchWebTool().run({"query": "weather"}, ctx)
    assert not result.ok
    assert "plugin is not activated" in result.output.lower()
    assert "did not retry" in result.output
    assert len(requests) == 1


def test_rehearsal_describes_the_search_and_sends_nothing(store, config, tmp_path, monkeypatch):
    no_xiaomi_env(monkeypatch)
    add_xiaomi(config)

    def handler(request):  # pragma: no cover - must never run
        raise AssertionError("rehearsal must not reach the network")

    install_fake_transport(monkeypatch, handler)
    ctx, _gate = make_ctx(store, config, tmp_path)
    ctx.dry_run = True
    result = SearchWebTool().run({"query": "weather"}, ctx)
    assert result.ok and "[rehearsal]" in result.output
    assert "mimo-v2.6-flash" in result.output


def test_the_bundled_xiaomi_templates_declare_the_documented_search_route():
    templates = load_templates()
    for name in ("xiaomi-token-plan-sgp", "xiaomi-token-plan-cn",
                 "xiaomi-token-plan-ams", "xiaomi"):
        route = route_from_template(templates[name])
        assert route is not None, name
        assert route.model == "mimo-v2.6-flash"
        assert route.force_search is True
        assert route.source.endswith("/text-generation/tool-calling/web-search.md")
