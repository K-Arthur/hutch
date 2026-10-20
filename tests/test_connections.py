"""Connections (CN): subscription plans and custom endpoints with their own keys, headers, billing and allowance."""

from __future__ import annotations

import json
import os
import re
import stat
import time
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from hutch.cli import app as cli_app
from hutch.connections import ConnectionBook, WINDOWS
from hutch.models import Bot, Escalation, Limits, Run, iso, utcnow
from hutch.providers.connection import check_connection
from hutch.runtime import RunAborted
from hutch.runtime.builtin import reset_connection_cache
from hutch.runtime.ladder import reset_provider_cache
from hutch.server.app import create_app
from tests.fakes import FakeAnthropic, FakeOllama, FakeOpenAI, agent_script
from tests.test_runtime_builtin import build, kinds, run_it, runtime

runner = CliRunner()


@pytest.fixture(autouse=True)
def _fresh():
    reset_provider_cache()
    reset_connection_cache()


@pytest.fixture()
def oai():
    s = FakeOpenAI()
    yield s
    s.close()


@pytest.fixture()
def book(config):
    return ConnectionBook(config.state_dir)


def add_go(book, oai, monkeypatch, key="go-secret", **extra):
    monkeypatch.setenv("OPENCODE_API_KEY", key)
    c = book.add("opencode-go", base_url=oai.url + "/v1", **extra)
    return c


def ack(book, store, name):
    book.acknowledge(store, name)


# ============================================================ the researched facts stay pinned

def test_templates_carry_the_endpoints_and_requirements_found_in_the_vendor_docs():
    t = ConnectionBook.__new__(ConnectionBook)  # templates only; no state dir needed
    from hutch.connections import load_templates
    tpl = load_templates()
    go = tpl["opencode-go"]
    assert go["base_url"] == "https://opencode.ai/zen/go/v1" and go["billing"] == "subscription"
    assert go["session_header"] == "x-opencode-session" and go["terms"]["requires_ack"]
    assert go["get_key_url"] == "https://opencode.ai/auth"
    assert "copy" in go["signin_guidance"] and "not an OAuth session login" in go["signin_guidance"]
    assert "never reads OpenCode's auth.json" in go["signin_guidance"]
    assert "monitored" in go["terms"]["notice"] and "UNATTENDED" in go["terms"]["notice"]
    for region in ("sgp", "cn", "ams"):
        x = tpl[f"xiaomi-token-plan-{region}"]
        assert x["base_url"] == f"https://token-plan-{region}.xiaomimimo.com/v1"
        assert x["anthropic_base_url"] == f"https://token-plan-{region}.xiaomimimo.com/anthropic"
        assert x["api_key_env"] == "XIAOMI_TOKEN_PLAN_API_KEY" and x["billing"] == "subscription"
    assert tpl["xiaomi"]["base_url"] == "https://api.xiaomimimo.com/v1" and tpl["xiaomi"]["billing"] == "per_token"
    openrouter = tpl["openrouter"]
    assert openrouter["base_url"] == "https://openrouter.ai/api/v1"
    assert openrouter["api_key_env"] == "OPENROUTER_API_KEY" and openrouter["billing"] == "per_token"
    assert openrouter["get_key_url"] == "https://openrouter.ai/settings/keys"
    assert openrouter["protocol"] == "openai-chat" and not openrouter["terms"]["requires_ack"]
    assert {"custom-openai", "custom-anthropic"} <= set(tpl)
    del t


def test_every_template_builds_into_a_valid_connection(book):
    for name in book.templates():
        c = book.add(name, name=f"t-{name}", base_url="https://example.test/v1" if name.startswith("custom") else None)
        assert c.protocol in ("openai-chat", "anthropic") and c.user_agent.startswith("hutch/")


# ============================================================ book: add / update / validate

def test_add_persists_and_reloads(config):
    b1 = ConnectionBook(config.state_dir)
    b1.add("opencode-go", quota={"window": "5h", "tokens": 100_000})
    b2 = ConnectionBook(config.state_dir)
    c = b2.get("opencode-go")
    assert c and c.quota.tokens == 100_000 and c.quota.window == "5h" and c.session_header == "x-opencode-session"
    assert json.loads((config.state_dir / "connections.json").read_text())["connections"]["opencode-go"]["template"] == "opencode-go"


def test_account_policy_groups_connections_and_keeps_strictest_limits(book):
    first = book.add("custom-openai", name="route-one", base_url="https://one.example.test/v1",
                     account_id="vendor-billing", account_daily_cost_cap_usd=4.0,
                     quota={"window": "day", "tokens": 2000})
    second = book.add("custom-openai", name="route-two", base_url="https://two.example.test/v1",
                      account_id="vendor-billing", account_daily_cost_cap_usd=2.0,
                      quota={"window": "week", "tokens": 5000})
    assert first.account_id == second.account_id == "vendor-billing"
    assert book.account_policy("vendor-billing") == (2.0, [(2000, 86400.0), (5000, 604800.0)])
    with pytest.raises(ValueError, match="quota window"):
        book.add("custom-openai", name="bad-window", base_url="https://bad.example.test/v1",
                 quota={"window": "fortnight", "tokens": 1})


def test_bad_names_reserved_names_duplicates_and_unknown_templates_are_refused(book):
    with pytest.raises(ValueError, match="slug"):
        book.add("opencode-go", name="Bad Name!")
    with pytest.raises(ValueError, match="built-in provider"):
        book.add("opencode-go", name="ollama")
    with pytest.raises(ValueError, match="unknown template"):
        book.add("telepathy")
    book.add("opencode-go")
    with pytest.raises(ValueError, match="already exists"):
        book.add("opencode-go")


def test_unsupported_protocols_are_rejected_with_a_clear_message(book):
    with pytest.raises(ValueError, match="not supported yet"):
        book.add("custom-openai", name="resp", base_url="https://x.test/v1", protocol="openai-responses")
    book.add("opencode-go")
    with pytest.raises(ValueError, match="not supported yet"):
        book.set_model_protocol("opencode-go", "grok-4.5", "openai-responses")


def test_per_model_protocol_switches_endpoint(book):
    book.add("xiaomi-token-plan-sgp", name="mimo")
    assert book.get("mimo").endpoint_for("mimo-v2.6-pro") == ("openai-chat", "https://token-plan-sgp.xiaomimimo.com/v1")
    book.set_model_protocol("mimo", "mimo-v2.6-pro", "anthropic")
    assert book.get("mimo").endpoint_for("mimo-v2.6-pro") == ("anthropic", "https://token-plan-sgp.xiaomimimo.com/anthropic")
    assert book.get("mimo").endpoint_for("mimo-v2.6-flash")[0] == "openai-chat"


def test_set_quota_validates_the_window(book):
    book.add("opencode-go")
    with pytest.raises(ValueError, match="window"):
        book.set_quota("opencode-go", "fortnight", 10)
    assert book.set_quota("opencode-go", "week", 5000).quota.seconds == WINDOWS["week"]


def test_a_corrupt_connections_file_is_reported_not_fatal(config):
    config.ensure()
    (config.state_dir / "connections.json").write_text("{nope")
    b = ConnectionBook(config.state_dir)
    assert b.errors and b.configured() == {}


# ============================================================ keys (CN-2)

def test_env_key_wins_over_the_file_and_the_file_is_private(book, config, monkeypatch):
    book.add("opencode-go")
    monkeypatch.delenv("OPENCODE_API_KEY", raising=False)
    assert book.key("opencode-go") is None and book.key_source("opencode-go") == "missing"
    book.set_key("opencode-go", "  file-key  ")
    f = book.key_file("opencode-go")
    assert book.key("opencode-go") == "file-key" and "key file" in book.key_source("opencode-go")
    assert stat.S_IMODE(f.stat().st_mode) == 0o600 and stat.S_IMODE(f.parent.stat().st_mode) == 0o700
    monkeypatch.setenv("OPENCODE_API_KEY", "env-key")
    assert book.key("opencode-go") == "env-key" and "environment variable" in book.key_source("opencode-go")
    book.remove("opencode-go")
    assert not f.exists(), "removing a connection removes its stored key"


def test_the_key_is_never_written_to_the_database_the_connections_file_or_the_api(config, monkeypatch):
    monkeypatch.setenv("HUTCH_ALLOWED_HOSTS", "testserver")
    secret = "sk-SUPER-SECRET-12345"
    with TestClient(create_app()) as c:
        html = c.get("/legacy/connections").text
        tok = re.search(r'<meta name="csrf" content="([^"]+)"', html).group(1)
        c.post("/connections/add", data={"csrf": tok, "template": "opencode-go", "name": ""})
        c.post("/connections/opencode-go/key", data={"csrf": tok, "key": secret})
        for url in ("/legacy/connections", "/", "/bots", "/api/bots", "/api/stats", "/api/runs"):
            assert secret not in c.get(url).text, url
        assert "present" in c.get("/legacy/connections").text
    assert secret not in (config.state_dir / "connections.json").read_text()
    assert secret not in (config.state_dir / "hutch.db").read_bytes().decode("latin-1")
    assert secret in book_key_file(config).read_text()      # it IS in the 0600 file, and only there


def book_key_file(config):
    return ConnectionBook(config.state_dir).key_file("opencode-go")


# ============================================================ terms (CN-6)

def test_ack_status_lifecycle_including_a_changed_notice(book, store):
    book.add("opencode-go")
    book.add("xiaomi", name="payg")
    assert book.ack_status(store, "opencode-go") == "required" and book.ack_status(store, "payg") == "not_needed"
    book.acknowledge(store, "opencode-go")
    assert book.ack_status(store, "opencode-go") == "ok"
    book.update("opencode-go", terms={"notice": "A NEW, stricter notice.", "requires_ack": True})
    assert book.ack_status(store, "opencode-go") == "stale"


def test_a_run_cannot_start_on_an_unacknowledged_plan_and_says_how_to_fix_it(store, config, tmp_path, oai, book, monkeypatch):
    add_go(book, oai, monkeypatch)
    ctx, run, emitted, tools = build(store, config, tmp_path, model="opencode-go/glm-5.3", tools=("remember",))
    with pytest.raises(RunAborted) as e:
        run_it(runtime(), run, ctx, tools)
    assert "terms of" in e.value.detail and "hutch connections ack opencode-go" in e.value.detail
    assert not oai.requests, "nothing may be sent to a plan whose terms were not acknowledged"


def test_acknowledging_lets_the_run_proceed(store, config, tmp_path, oai, book, monkeypatch):
    add_go(book, oai, monkeypatch)
    ack(book, store, "opencode-go")
    oai.script = lambda b: {"content": "done", "prompt_tokens": 100, "completion_tokens": 10}
    ctx, run, emitted, tools = build(store, config, tmp_path, model="opencode-go/glm-5.3", tools=("remember",))
    assert run_it(runtime(), run, ctx, tools) == "done"


def test_an_unacknowledged_plan_falls_back_to_a_local_model_instead_of_failing(store, config, tmp_path, oai, book, monkeypatch):
    add_go(book, oai, monkeypatch)
    ollama = FakeOllama({"fake:8b": {}})
    try:
        ollama.script = agent_script([{"content": "local answer"}])
        from tests.test_runtime_builtin import factory
        ctx, run, emitted, tools = build(store, config, tmp_path, model="opencode-go/glm-5.3", tools=("remember",),
                                         fallbacks=["ollama/fake:8b"])
        assert run_it(runtime(provider_factory=factory(ollama=ollama)), run, ctx, tools) == "local answer"
        assert "terms" in kinds(emitted, "fallback")[0]["reason"]
    finally:
        ollama.close()


# ============================================================ headers, keys, protocols (CN-3, CN-4)

def test_requests_carry_the_connections_own_key_user_agent_and_a_per_run_session_id(store, config, tmp_path, oai, book, monkeypatch):
    add_go(book, oai, monkeypatch, key="opencode-key-A")
    ack(book, store, "opencode-go")
    oai.script = lambda b: {"content": "ok"}
    ctx, run, emitted, tools = build(store, config, tmp_path, model="opencode-go/zhipuai/glm-5.3", tools=("remember",))
    run_it(runtime(), run, ctx, tools)
    h = oai.of("/v1/chat/completions")[0]["headers"]
    assert h["authorization"] == "Bearer opencode-key-A"
    assert h["user-agent"].startswith("hutch/") and "python" not in h["user-agent"].lower()
    assert h["x-opencode-session"] == run.id                      # stable per run, as the plan requires
    assert oai.of("/v1/chat/completions")[0]["body"]["model"] == "zhipuai/glm-5.3"   # model ids may contain '/'


def test_opencode_session_id_is_stable_for_a_conversation(store, config, tmp_path, oai, book, monkeypatch):
    add_go(book, oai, monkeypatch, key="opencode-key-A")
    ack(book, store, "opencode-go")
    oai.script = lambda b: {"content": "ok"}
    ctx, run, emitted, tools = build(store, config, tmp_path, model="opencode-go/glm-5.3",
                                     tools=("remember",), conversation_id="conversation-go-fixture")
    run_it(runtime(), run, ctx, tools)
    h = oai.of("/v1/chat/completions")[0]["headers"]
    assert run.id != run.conversation_id
    assert h["x-opencode-session"] == "conversation-go-fixture"


def test_two_connections_with_different_keys_coexist(store, config, tmp_path, book, monkeypatch):
    a, b = FakeOpenAI(), FakeOpenAI()
    try:
        monkeypatch.setenv("OPENCODE_API_KEY", "KEY-FOR-A")
        monkeypatch.setenv("OTHER_KEY", "KEY-FOR-B")
        book.add("opencode-go", base_url=a.url + "/v1")
        book.add("custom-openai", name="gateway", base_url=b.url + "/v1", api_key_env="OTHER_KEY")
        ack(book, store, "opencode-go")
        a.script = lambda x: {"content": "from a"}
        b.script = lambda x: {"content": "from b"}
        ctx, run, emitted, tools = build(store, config, tmp_path, model="opencode-go/m", tools=("remember",))
        assert run_it(runtime(), run, ctx, tools) == "from a"
        # a second bot (build() names its bot "rt-bot", so make this one by hand)
        bot2 = Bot(name="b2", model="gateway/other-model", tools=["remember"], selfcheck=False)
        store.create_bot(bot2)
        run2 = Run(bot_id=bot2.id, prompt="x")
        store.create_run(run2)
        from hutch.approvals import ApprovalGate
        from hutch.safety import PolicyEngine
        from hutch.tools import build_tools
        from hutch.tools.base import ToolContext
        gate = ApprovalGate(store, bot2, run2, PolicyEngine(), lambda ev: store.append_event(ev))
        ctx2 = ToolContext(bot=bot2, run=run2, store=store, policy=gate.policy, gate=gate, config=config,
                           workspace=tmp_path / "ws", emit=lambda ev: store.append_event(ev))
        assert run_it(runtime(), run2, ctx2, build_tools(bot2.tools, ctx2)) == "from b"
        assert a.of("/v1/chat/completions")[0]["headers"]["authorization"] == "Bearer KEY-FOR-A"
        assert b.of("/v1/chat/completions")[0]["headers"]["authorization"] == "Bearer KEY-FOR-B"
        assert "x-opencode-session" not in b.of("/v1/chat/completions")[0]["headers"]
    finally:
        a.close()
        b.close()


def test_a_model_set_to_the_anthropic_protocol_goes_to_the_messages_endpoint(store, config, tmp_path, book, monkeypatch):
    anth = FakeAnthropic()
    try:
        monkeypatch.setenv("XIAOMI_TOKEN_PLAN_API_KEY", "tp-abc123")
        book.add("xiaomi-token-plan-sgp", name="mimo", base_url="http://127.0.0.1:9/v1", anthropic_base_url=anth.url)
        book.set_model_protocol("mimo", "mimo-v2.6-pro", "anthropic")
        ack(book, store, "mimo")
        anth.script = lambda b: {"content": "via anthropic protocol", "input_tokens": 30, "output_tokens": 7}
        ctx, run, emitted, tools = build(store, config, tmp_path, model="mimo/mimo-v2.6-pro", tools=("remember",))
        assert run_it(runtime(), run, ctx, tools) == "via anthropic protocol"
        sent = anth.of("/v1/messages")[0]
        assert sent["headers"]["x-api-key"] == "tp-abc123" and sent["headers"]["user-agent"].startswith("hutch/")
        assert run.tokens == 37
    finally:
        anth.close()


def test_a_missing_key_fails_fast_with_both_ways_to_supply_it(store, config, tmp_path, oai, book, monkeypatch):
    monkeypatch.delenv("OPENCODE_API_KEY", raising=False)
    book.add("opencode-go", base_url=oai.url + "/v1")
    ack(book, store, "opencode-go")
    ctx, run, emitted, tools = build(store, config, tmp_path, model="opencode-go/m", tools=("remember",))
    with pytest.raises(RunAborted) as e:
        run_it(runtime(), run, ctx, tools)
    assert "OPENCODE_API_KEY" in e.value.detail and "set-key" in e.value.detail and not oai.requests


# ============================================================ billing (CN-4)

def test_subscription_calls_cost_nothing_per_call_but_are_recorded_in_the_ledger(store, config, tmp_path, oai, book, monkeypatch):
    add_go(book, oai, monkeypatch)
    ack(book, store, "opencode-go")
    oai.script = lambda b: {"content": "ok", "prompt_tokens": 5000, "completion_tokens": 400}
    # a $ cap is fine on a flat plan: nothing is priced per token, so nothing can exceed it
    ctx, run, emitted, tools = build(store, config, tmp_path, model="opencode-go/m", tools=("remember",),
                                     limits=Limits(max_cost_usd=1.0))
    run_it(runtime(), run, ctx, tools)
    assert run.cost_usd == 0.0 and run.tokens == 5400
    assert store.usage_tokens_since("opencode-go", 3600) == 5400
    row = store.usage_summary("provider")[0]
    assert row["key"] == "opencode-go" and row["prompt"] == 5000 and row["completion"] == 400 and row["cost"] == 0.0


def test_a_per_token_connection_needs_a_price_before_a_cost_cap_can_be_enforced(store, config, tmp_path, oai, book, monkeypatch):
    monkeypatch.setenv("XIAOMI_API_KEY", "sk-x")
    book.add("xiaomi", base_url=oai.url + "/v1")
    oai.script = lambda b: {"content": "ok"}
    ctx, run, emitted, tools = build(store, config, tmp_path, model="xiaomi/mimo-v2.6-pro", tools=("remember",),
                                     limits=Limits(max_cost_usd=1.0))
    with pytest.raises(RunAborted) as e:
        run_it(runtime(), run, ctx, tools)
    assert "no price" in e.value.detail and not oai.requests


def test_a_price_row_in_the_user_file_makes_a_per_token_connection_billable(store, config, tmp_path, oai, book, monkeypatch):
    monkeypatch.setenv("XIAOMI_API_KEY", "sk-x")
    book.add("xiaomi", base_url=oai.url + "/v1")
    (config.state_dir / "prices.json").write_text(json.dumps({"models": {"xiaomi/mimo-v2.6-pro": {
        "input": 1.0, "output": 3.0, "verified_on": "2026-10-07", "source": "my invoice"}}}))
    oai.script = lambda b: {"content": "ok", "prompt_tokens": 1_000_000, "completion_tokens": 100_000}
    ctx, run, emitted, tools = build(store, config, tmp_path, model="xiaomi/mimo-v2.6-pro", tools=("remember",),
                                     limits=Limits(max_cost_usd=100.0))
    run_it(runtime(), run, ctx, tools)
    assert run.cost_usd == pytest.approx(1.0 + 0.3)


# ============================================================ allowance (CN-5)

def seed_usage(store, bot_id, provider, tokens, age_seconds=0):
    store.add_usage("run_seed", bot_id, provider, "m", tokens, 0)
    if age_seconds:
        with store._lock:
            store._db.execute("UPDATE usage SET ts = ? WHERE id = (SELECT MAX(id) FROM usage)",
                              (iso(utcnow() - timedelta(seconds=age_seconds)),))
            store._db.commit()


def test_the_allowance_stops_a_run_before_the_vendor_would(store, config, tmp_path, oai, book, monkeypatch):
    add_go(book, oai, monkeypatch)
    book.set_quota("opencode-go", "5h", 100_000)
    ack(book, store, "opencode-go")
    ctx, run, emitted, tools = build(store, config, tmp_path, model="opencode-go/m", tools=("remember",))
    seed_usage(store, ctx.bot.id, "opencode-go", 100_000)
    with pytest.raises(RunAborted) as e:
        run_it(runtime(), run, ctx, tools)
    assert e.value.reason == "cost_cap" and "allowance" in e.value.detail and "spent" in e.value.detail
    assert not oai.requests


def test_a_call_that_could_pass_the_allowance_is_refused_before_it_is_made(store, config, tmp_path, oai, book, monkeypatch):
    add_go(book, oai, monkeypatch)
    book.set_quota("opencode-go", "month", 30_000)
    ack(book, store, "opencode-go")
    ctx, run, emitted, tools = build(store, config, tmp_path, model="opencode-go/m", tools=("remember",))
    seed_usage(store, ctx.bot.id, "opencode-go", 20_000)       # 10k left; one call may need ~16k reserved for the reply
    with pytest.raises(RunAborted) as e:
        run_it(runtime(), run, ctx, tools)
    assert "could pass the 30,000-token allowance" in e.value.detail and not oai.requests


def test_usage_outside_the_window_does_not_count(store, config, tmp_path, oai, book, monkeypatch):
    add_go(book, oai, monkeypatch)
    book.set_quota("opencode-go", "5h", 1_000_000)
    ack(book, store, "opencode-go")
    oai.script = lambda b: {"content": "ok", "prompt_tokens": 50, "completion_tokens": 5}
    ctx, run, emitted, tools = build(store, config, tmp_path, model="opencode-go/m", tools=("remember",),
                                     limits=Limits(daily_token_cap=2_000_000))
    seed_usage(store, ctx.bot.id, "opencode-go", 999_999, age_seconds=6 * 3600)    # six hours ago: outside 5h
    assert run_it(runtime(), run, ctx, tools) == "ok"


def test_a_warning_is_logged_once_when_the_allowance_passes_its_threshold(store, config, tmp_path, oai, book, monkeypatch):
    add_go(book, oai, monkeypatch)
    book.set_quota("opencode-go", "month", 1_000_000)
    ack(book, store, "opencode-go")
    oai.script = lambda b: {"tool_calls": [{"name": "recall", "arguments": {"query": str(time.time())}}],
                            "prompt_tokens": 100, "completion_tokens": 10} if len(oai.requests) < 3 else {"content": "done"}
    ctx, run, emitted, tools = build(store, config, tmp_path, model="opencode-go/m", tools=("recall",),
                                     limits=Limits(daily_token_cap=2_000_000))
    seed_usage(store, ctx.bot.id, "opencode-go", 850_000)
    run_it(runtime(), run, ctx, tools)
    warns = kinds(emitted, "quota")
    assert len(warns) == 1 and "850" in warns[0]["note"] and warns[0]["limit"] == 1_000_000


# ============================================================ check / test without spending tokens

def test_testing_a_connection_authenticates_against_the_model_list_and_spends_nothing(book, oai, monkeypatch):
    add_go(book, oai, monkeypatch, key="good-key")
    oai.require_key = "good-key"
    res = check_connection(book, "opencode-go")
    assert res.ok and res.models == ["fake-model"]
    assert [r["path"] for r in oai.requests] == ["/v1/models"], "no chat call may be made by a plain test"
    assert oai.requests[0]["headers"]["authorization"] == "Bearer good-key"


def test_testing_with_a_wrong_key_reports_it(book, oai, monkeypatch):
    add_go(book, oai, monkeypatch, key="wrong")
    oai.require_key = "right"
    res = check_connection(book, "opencode-go")
    assert not res.ok and "key was rejected" in res.detail


def test_unreserved_chat_connection_probe_is_refused_without_provider_request(book, oai, monkeypatch):
    add_go(book, oai, monkeypatch)
    monkeypatch.setenv("HUTCH_STATE_DIR", str(book.state_dir))
    help_result = runner.invoke(cli_app, ["connections", "test", "--help"])
    assert "--chat" not in help_result.output

    result = runner.invoke(cli_app, ["connections", "test", "opencode-go", "--chat", "glm-5.3"])

    message = " ".join(result.output.split())
    assert result.exit_code == 2
    assert "shared usage reservations" in message
    assert "normal bot run" in message
    assert oai.requests == []


def test_anthropic_protocol_connections_are_not_pretend_verified(book, monkeypatch):
    monkeypatch.setenv("CUSTOM_API_KEY", "k")
    book.add("custom-anthropic", name="anth", base_url="http://127.0.0.1:9")
    res = check_connection(book, "anth")
    assert res.ok and "not verified" in res.detail


def test_check_without_a_key_names_the_env_var(book, monkeypatch):
    monkeypatch.delenv("OPENCODE_API_KEY", raising=False)
    book.add("opencode-go")
    assert "OPENCODE_API_KEY" in check_connection(book, "opencode-go").detail


def test_anthropic_first_party_catalog_uses_the_documented_model_api(book, monkeypatch):
    from hutch.providers.claude import ClaudeProvider

    book.add("anthropic-api")
    book.set_key("anthropic-api", "fixture-anthropic-key")
    calls = []

    class Page:
        def __init__(self, data, has_more=False, last_id=None):
            self.data = data
            self.has_more = has_more
            self.last_id = last_id

    class Models:
        def list(self, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                return Page([type("Model", (), {"id": "claude-active"})()], True, "cursor-1")
            return Page([type("Model", (), {"id": "claude-legacy"})()])

    client = type("AnthropicClient", (), {"models": Models()})()
    monkeypatch.setattr(ClaudeProvider, "_c", lambda self: client)

    result = check_connection(book, "anthropic-api")

    assert result.ok and result.models == ["claude-active", "claude-legacy"]
    assert calls == [{"limit": 1000}, {"limit": 1000, "after_id": "cursor-1"}]


def test_connection_api_accepts_a_key_once_and_reports_model_discovery(book, config, oai, monkeypatch):
    monkeypatch.setenv("HUTCH_ALLOWED_HOSTS", "testserver")
    monkeypatch.setenv("CUSTOM_API_KEY", "the-old-environment-key")
    oai.require_key = "the-key-pasted-in-hutch"
    oai.models = [{"id": "account-model-one"}, {"id": "account-model-two"}]

    with TestClient(create_app()) as client:
        response = client.post("/api/connections", json={
            "template": "custom-openai", "name": "connected-provider", "base_url": f"{oai.url}/v1",
            "api_key": "the-key-pasted-in-hutch",
        })

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["added"] == "connected-provider"
    assert payload["discovery"]["ok"] is True
    assert payload["discovery"]["model_count"] == 2
    assert "the-key-pasted-in-hutch" not in response.text
    assert "the-old-environment-key" not in response.text
    stored = ConnectionBook(config.state_dir)
    assert stored.key("connected-provider") == "the-key-pasted-in-hutch"
    assert stored.get("connected-provider").api_key_env == "CUSTOM_API_KEY"
    assert stored.get("connected-provider").prefer_stored_key is True
    assert [request["headers"]["authorization"] for request in oai.requests] == [
        "Bearer the-key-pasted-in-hutch"]
    stored.clear_key("connected-provider")
    assert stored.key("connected-provider") == "the-old-environment-key"
    assert stored.get("connected-provider").prefer_stored_key is False


def test_connection_api_rejects_an_empty_or_oversized_pasted_key_without_echo(config, monkeypatch):
    monkeypatch.setenv("HUTCH_ALLOWED_HOSTS", "testserver")
    oversized_key = "s" * 4097
    with TestClient(create_app()) as client:
        empty = client.post("/api/connections", json={"template": "openrouter", "api_key": "  "})
        too_long = client.post("/api/connections", json={"template": "openrouter", "api_key": oversized_key})

    assert empty.status_code == 422
    assert too_long.status_code == 413
    assert oversized_key not in too_long.text
    assert ConnectionBook(config.state_dir).get("openrouter") is None


# ============================================================ usage summary (feeds UI-11)

def test_usage_summary_groups_by_day_bot_provider_and_model(store):
    store.add_usage("r1", "botA", "opencode-go", "glm", 1000, 100)
    store.add_usage("r2", "botA", "anthropic", "claude-opus-5-5", 2000, 200, cached_tokens=1500, cost_usd=0.05)
    store.add_usage("r3", "botB", "anthropic", "claude-opus-5-5", 500, 50, cost_usd=0.01)
    by_provider = {r["key"]: r for r in store.usage_summary("provider")}
    assert by_provider["anthropic"]["calls"] == 2 and by_provider["anthropic"]["cost"] == pytest.approx(0.06)
    assert by_provider["anthropic"]["cached"] == 1500 and by_provider["opencode-go"]["prompt"] == 1000
    assert {r["key"] for r in store.usage_summary("bot")} == {"botA", "botB"}
    assert store.usage_summary("model")[0]["key"] == "anthropic/claude-opus-5-5"
    assert store.usage_summary("day")[0]["key"] == utcnow().date().isoformat()
    with pytest.raises(ValueError):
        store.usage_summary("planet")


# ============================================================ CLI

def test_cli_add_list_ack_set_key_test_and_remove(config, store, oai, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(config.state_dir))
    monkeypatch.delenv("OPENCODE_API_KEY", raising=False)
    out = runner.invoke(cli_app, ["connections", "templates"]).output
    assert "opencode-go" in out and "xiaomi-token-plan-sgp" in out
    r = runner.invoke(cli_app, ["connections", "add", "opencode-go", "--base-url", oai.url + "/v1",
                                "--allowance-tokens", "500000", "--allowance-window", "week",
                                "--account-id", "team-provider", "--account-daily-cap-usd", "20"])
    assert r.exit_code == 0 and "hutch connections ack opencode-go" in r.output
    book = ConnectionBook(config.state_dir)
    book.add("custom-openai", name="team-route", base_url="https://team.example.test/v1",
             account_id="team-provider")
    store.add_usage("seed-cli-usage", "bot-cli", "team-route", "model", 300, 200,
                    account_id="team-provider")
    listing = runner.invoke(cli_app, ["connections", "list"]).output
    assert "ACK REQUIRED" in listing and "missing" in listing
    normalized_listing = " ".join(listing.split())
    assert "500 / 500,000 tokens (week window; includes shared-account pending holds)" in normalized_listing
    assert "account: team-provider" in listing and "$20.00" in listing
    book.remove("team-route")
    cap = runner.invoke(cli_app, ["connections", "set-account-cap", "opencode-go", "24",
                                  "--account-id", "team-provider"])
    assert cap.exit_code == 0 and "$24.00" in cap.output
    secret = "cli-secret-key-777"
    r = runner.invoke(cli_app, ["connections", "set-key", "opencode-go"], input=secret + "\n")
    assert r.exit_code == 0 and secret not in r.output and "0600" in r.output
    r = runner.invoke(cli_app, ["connections", "ack", "opencode-go"], input="n\n")
    assert r.exit_code == 1 and "monitored" in r.output          # the notice is shown; declining acknowledges nothing
    assert runner.invoke(cli_app, ["connections", "ack", "opencode-go", "--yes"]).exit_code == 0
    assert "acknowledged" in runner.invoke(cli_app, ["connections", "list"]).output
    t = runner.invoke(cli_app, ["connections", "test", "opencode-go"])
    assert t.exit_code == 0 and "authenticated" in t.output and "opencode-go/fake-model" in t.output
    assert runner.invoke(cli_app, ["connections", "set-protocol", "opencode-go", "m", "anthropic"]).exit_code == 0
    assert runner.invoke(cli_app, ["connections", "set-protocol", "opencode-go", "m", "openai-responses"]).exit_code == 1
    assert runner.invoke(cli_app, ["connections", "remove", "opencode-go", "--yes"]).exit_code == 0
    assert "no connections yet" in runner.invoke(cli_app, ["connections", "list"]).output


# ============================================================ dashboard

def test_dashboard_connection_flow_add_key_ack_allowance_remove(config, monkeypatch):
    monkeypatch.setenv("HUTCH_ALLOWED_HOSTS", "testserver")
    monkeypatch.delenv("OPENCODE_API_KEY", raising=False)
    with TestClient(create_app()) as c:
        tok = re.search(r'<meta name="csrf" content="([^"]+)"', c.get("/legacy/connections").text).group(1)
        post = lambda path, **d: c.post(path, data={"csrf": tok, **d}, follow_redirects=True)
        assert "OpenCode Go" in post("/connections/add", template="opencode-go", name="").text
        page = c.get("/legacy/connections").text
        assert "acknowledgement required" in page and "missing" in page and "monitored for abuse" in page
        # the box must be ticked: a bare POST does not acknowledge
        post("/connections/opencode-go/ack")
        assert "acknowledgement required" in c.get("/legacy/connections").text
        post("/connections/opencode-go/ack", agree="1")
        assert "acknowledgement required" not in c.get("/legacy/connections").text
        post("/connections/opencode-go/key", key="k-123")
        page = post("/connections/opencode-go/allowance", tokens="40000", window="5h").text
        assert "40k" in page and "5h window" in page
        page = post("/connections/opencode-go/account-cap", daily_usd="12.50").text
        assert "$12.50" in page and "Shared daily currency cap" in page
        assert "$0.0000 measured + $0.0000 held of the shared $12.50" in page and "measured" in page and "held" in page
        page = post("/connections/opencode-go/account-cap", daily_usd="NaN").text
        assert "finite non-negative" in page
        # bad input is refused politely
        assert "window must be one of" in post("/connections/opencode-go/allowance", tokens="5", window="fortnight").text
        assert "unknown template" in post("/connections/add", template="telepathy", name="").text
        post("/connections/opencode-go/remove")
        assert "No connections yet" in c.get("/legacy/connections").text
        assert c.post("/connections/ghost/key", data={"csrf": tok, "key": "x"}).status_code == 404


def test_connection_post_without_csrf_is_refused(config, monkeypatch):
    monkeypatch.setenv("HUTCH_ALLOWED_HOSTS", "testserver")
    with TestClient(create_app()) as c:
        assert c.post("/connections/add", data={"template": "opencode-go"}).status_code == 403
