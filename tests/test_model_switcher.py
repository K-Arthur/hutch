"""The chat model switcher: the list, the per-message override and its validation."""

from __future__ import annotations

import re
import time

import pytest
from fastapi.testclient import TestClient

from hutch.connections import ConnectionBook
from hutch.models import ApprovalMode, Bot, RunStatus
from hutch.modelchoices import ModelNotUsable, model_choices, reset_cache, validate_override
from hutch.runtime.ladder import reset_provider_cache
from hutch.server.app import create_app
from tests.fakes import FakeOllama, agent_script


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENCODE_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    fake = FakeOllama({"fake:8b": {}, "other:3b": {}, "tiny:1b": {"params": "1B", "size": 500_000_000},
                       "huge:70b": {"params": "70B", "size": 45_000_000_000, "ctx": 131072},
                       "qwen3-coder:480b-cloud": {}, "glm-4.7:cloud": {}})
    monkeypatch.setenv("OLLAMA_HOST", fake.url)
    reset_provider_cache()
    reset_cache()
    with TestClient(create_app()) as c:
        c.fake = fake
        c.store = c.app.state.store
        c.config = c.app.state.config
        yield c
    fake.close()


def mkbot(env, name="chatty", model="mock/demo", **kw):
    kw.setdefault("tools", [])
    kw.setdefault("selfcheck", False)
    kw.setdefault("approval_mode", ApprovalMode.auto)
    return env.store.create_bot(Bot(name=name, model=model, **kw))


def wait_done(env, run_id, timeout=20.0):
    end = time.time() + timeout
    while time.time() < end:
        r = env.store.get_run(run_id)
        if r.status not in (RunStatus.pending, RunStatus.running, RunStatus.loading_model):
            return r
        time.sleep(0.05)
    raise AssertionError("run did not finish")


# ---------------------------------------------------------------------------- the list

def test_the_bots_own_model_is_first_and_marked_default(env):
    bot = mkbot(env, model="ollama/fake:8b")
    ch = model_choices(env.config, env.store, bot)
    assert ch[0].spec == "ollama/fake:8b" and ch[0].default and ch[0].group == "This bot"
    assert [c.spec for c in ch].count("ollama/fake:8b") == 1, "the default must not be listed twice"


def test_local_model_routes_filter_hosted_choices_and_cloud_tagged_ollama(env):
    bot = mkbot(env, model="ollama/fake:8b", inference_mode="local")
    specs = {c.spec for c in model_choices(env.config, env.store, bot)}
    assert "ollama/fake:8b" in specs
    assert not any(s.startswith(("openai/", "anthropic/")) for s in specs)
    assert "ollama/qwen3-coder:480b-cloud" not in specs
    assert "ollama/glm-4.7:cloud" not in specs


def test_ollama_cloud_models_are_marked_hosted_in_hybrid_model_picker(env):
    from hutch.estimate import RunEstimator

    bot = mkbot(env, model="ollama/fake:8b")
    by = {c.spec: c for c in model_choices(env.config, env.store, bot)}
    cloud = by["ollama/qwen3-coder:480b-cloud"]
    assert cloud.hosted and cloud.group == "Hosted" and cloud.state == "setup"
    assert "inference runs on ollama.com" in cloud.note
    assert any("cost caps refuse" in item for item in cloud.detail)
    assert RunEstimator(env.config, env.store, bot).for_model(cloud.spec).kind == "unpriced"


def test_local_model_route_rejects_hosted_message_override(env):
    bot = mkbot(env, model="ollama/fake:8b", inference_mode="local")
    with pytest.raises(ModelNotUsable, match="Local model routes"):
        validate_override(env.config, env.store, bot, "openai/gpt-4o-mini")
    with pytest.raises(ModelNotUsable, match="Local model routes"):
        validate_override(env.config, env.store, bot, "ollama/qwen3-coder:480b-cloud")
    from hutch.runtime.ladder import make_rung
    assert not make_rung("ollama/qwen3-coder:480b-cloud", "fallback").local


def test_legacy_bot_defaults_to_hybrid(env):
    bot = mkbot(env)
    assert bot.inference_mode.value == "hybrid"
    assert env.get("/api/bots/chatty").json()["inference_mode"] == "hybrid"


def test_test_harness_flag_cannot_make_a_retired_mock_model_look_runnable(env):
    bot = mkbot(env, model="mock/demo")
    own = model_choices(env.config, env.store, bot)[0]
    assert own.state == "setup" and "legacy test route" in own.note
    with pytest.raises(ModelNotUsable, match="test-only"):
        validate_override(env.config, env.store, bot, "mock/demo")


def test_api_requires_local_primary_when_local_mode_is_selected(env):
    created = env.post("/api/bots", json={"name": "local-bot", "model": "ollama/fake:8b",
                                          "inference_mode": "local", "tools": []})
    assert created.status_code == 201 and created.json()["inference_mode"] == "local"
    bad_create = env.post("/api/bots", json={"name": "hosted-bot", "model": "openai/gpt-4o-mini",
                                              "inference_mode": "local", "tools": []})
    assert bad_create.status_code == 422 and "not an allowed local model route" in bad_create.json()["detail"]
    bad_patch = env.patch("/api/bots/local-bot", json={"model": "anthropic/claude-opus-5-5"})
    assert bad_patch.status_code == 422
    bad_override = env.post("/api/bots/local-bot/run", json={"prompt": "hello",
                                                            "model": "ollama/qwen3-coder:480b-cloud"})
    assert bad_override.status_code == 409 and "Local model routes" in bad_override.json()["detail"]
    good_patch = env.patch("/api/bots/local-bot", json={"model": "ollama/another-local:3b"})
    assert good_patch.status_code == 200


def test_installed_local_models_say_whether_they_fit(env):
    bot = mkbot(env, model="ollama/fake:8b")
    by = {c.spec: c for c in model_choices(env.config, env.store, bot)}
    assert by["ollama/other:3b"].group == "On this machine"
    assert by["ollama/huge:70b"].state == "wont_fit" and "does not fit" in by["ollama/huge:70b"].note
    assert by["ollama/huge:70b"].fix


def test_hosted_models_need_their_key_and_say_what_they_cost(env, monkeypatch):
    bot = mkbot(env, model="ollama/fake:8b")
    by = {c.spec: c for c in model_choices(env.config, env.store, bot)}
    opus = by["anthropic/claude-opus-5-5"]
    assert opus.state == "setup" and "ANTHROPIC_API_KEY" in opus.note and opus.hosted
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    reset_cache()
    opus = {c.spec: c for c in model_choices(env.config, env.store, bot)}["anthropic/claude-opus-5-5"]
    assert opus.state == "ready" and "$4 in / $20 out" in opus.note and "sends this chat to anthropic" in opus.detail


def test_connection_models_known_from_bots_appear_with_their_state(env, monkeypatch):
    from hutch.providers.base import ProviderError

    class UnavailableModelList:
        def list_models(self):
            raise ProviderError("unreachable", "catalog temporarily unavailable")

    monkeypatch.setattr(
        "hutch.providers.connection.provider_for_connection",
        lambda *args, **kwargs: UnavailableModelList(),
    )
    ConnectionBook(env.config.state_dir).add("opencode-go")
    bot = mkbot(env, model="ollama/fake:8b")
    mkbot(env, name="user-of-plan", model="opencode-go/glm-5.3")
    ch = {c.spec: c for c in model_choices(env.config, env.store, bot)}
    plan = ch["opencode-go/glm-5.3"]
    assert plan.state == "setup" and "key" in plan.note and "OPENCODE_API_KEY" in plan.fix
    monkeypatch.setenv("OPENCODE_API_KEY", "k")
    ConnectionBook(env.config.state_dir).acknowledge(env.store, "opencode-go")
    reset_cache()
    plan = {c.spec: c for c in model_choices(env.config, env.store, bot)}["opencode-go/glm-5.3"]
    assert plan.state == "ready" and "flat-rate" in plan.note


def test_openrouter_model_catalog_is_fetched_only_on_request_and_searches_with_its_key(env, monkeypatch):
    from urllib.parse import parse_qs, urlsplit
    from hutch.providers import ChatRequest
    from hutch.providers.connection import provider_for_connection
    from tests.fakes import FakeOpenAI

    router = FakeOpenAI()
    router.require_key = "router-secret"
    router.models = [
        {"id": "anthropic/claude-sonnet-4", "name": "Claude Sonnet 4",
         "pricing": {"prompt": "0.000003", "completion": "0.000015"},
         "supported_parameters": ["tools", "temperature"]},
        {"id": "deepseek/deepseek-chat-v3", "name": "DeepSeek Chat V3",
         "pricing": {"prompt": "0.0000002", "completion": "0.0000008"},
         "supported_parameters": ["temperature"]},
    ]
    try:
        book = ConnectionBook(env.config.state_dir)
        book.add("openrouter", base_url=router.url + "/v1")
        book.set_key("openrouter", "router-secret")
        monkeypatch.setenv("OPENAI_API_KEY", "must-not-be-sent-to-openrouter")
        bot = mkbot(env, model="ollama/fake:8b")
        reset_cache()

        before = len(router.requests)
        model_choices(env.config, env.store, bot, discover_hosted_models=False)
        assert len(router.requests) == before, "loading a chat must not contact OpenRouter"

        choices = model_choices(env.config, env.store, bot, discover_hosted_models=True)
        by = {choice.spec: choice for choice in choices}
        sonnet = by["openrouter/anthropic/claude-sonnet-4"]
        assert sonnet.label == "Claude Sonnet 4" and sonnet.group == "OpenRouter"
        assert "catalog" in sonnet.note and "$3" in sonnet.note
        assert any("does not verify" in detail for detail in sonnet.detail)
        request = router.requests[-1]
        assert request["headers"]["authorization"] == "Bearer router-secret"
        assert "must-not-be-sent-to-openrouter" not in str(request)
        assert parse_qs(urlsplit(request["path"]).query)["sort"] == ["most-popular"]

        reset_cache()
        result = env.get("/api/bots/chatty/models?discover=1&q=deepseek").json()
        assert [row["spec"] for row in result["models"] if row["spec"].startswith("openrouter/")] == [
            "openrouter/deepseek/deepseek-chat-v3"]
        query_request = router.requests[-1]
        assert parse_qs(urlsplit(query_request["path"]).query)["q"] == ["deepseek"]
        assert query_request["headers"]["authorization"] == "Bearer router-secret"
        assert validate_override(env.config, env.store, bot,
                                 "openrouter/anthropic/claude-sonnet-4") == "openrouter/anthropic/claude-sonnet-4"
        assert "router-secret" not in env.get("/api/bots/chatty/models?discover=1").text

        result = provider_for_connection(book, "openrouter", "anthropic/claude-sonnet-4").chat(
            ChatRequest(model="anthropic/claude-sonnet-4", messages=[{"role": "user", "content": "hello"}],
                        max_tokens=23, stream=False))
        sent = router.of("/v1/chat/completions")[-1]
        assert result.content == "ok"
        assert sent["headers"]["authorization"] == "Bearer router-secret"
        assert sent["body"]["model"] == "anthropic/claude-sonnet-4"
        assert sent["body"]["max_completion_tokens"] == 23 and "max_tokens" not in sent["body"]
        assert "must-not-be-sent-to-openrouter" not in str(sent)
    finally:
        router.close()


def test_openai_compatible_connection_discovers_its_own_model_catalog(env, monkeypatch):
    from tests.fakes import FakeOpenAI

    provider = FakeOpenAI()
    provider.require_key = "account-scoped-key"
    provider.models = [{"id": "account-model-a"}, {"id": "account-model-b"}]
    try:
        monkeypatch.delenv("CUSTOM_API_KEY", raising=False)
        monkeypatch.setenv("OPENAI_API_KEY", "must-not-be-sent-to-custom-endpoint")
        book = ConnectionBook(env.config.state_dir)
        book.add("custom-openai", name="account", base_url=f"{provider.url}/v1")
        book.set_key("account", "account-scoped-key")
        bot = mkbot(env, model="ollama/fake:8b")
        reset_cache()

        before = len(provider.requests)
        model_choices(env.config, env.store, bot, discover_hosted_models=False)
        assert len(provider.requests) == before, "opening a chat must not contact provider catalogs"

        choices = model_choices(env.config, env.store, bot, discover_hosted_models=True)
        found = {choice.spec for choice in choices}
        assert {"account/account-model-a", "account/account-model-b"} <= found
        assert len(provider.of("/v1/models")) == 1
        request = provider.of("/v1/models")[0]
        assert request["headers"]["authorization"] == "Bearer account-scoped-key"
        assert "must-not-be-sent-to-custom-endpoint" not in str(request)
    finally:
        provider.close()


def test_model_catalog_cache_is_bounded_and_keeps_recent_entries():
    from hutch.modelchoices import _CACHE_MAX, _cache, _cached

    reset_cache()
    for index in range(_CACHE_MAX + 20):
        _cached(f"catalog-search-{index}", lambda index=index: index, ttl=60)
    assert len(_cache) == _CACHE_MAX
    assert "catalog-search-0" not in _cache
    assert _cached(f"catalog-search-{_CACHE_MAX + 19}", lambda: -1, ttl=60) == _CACHE_MAX + 19
    reset_cache()


@pytest.mark.parametrize("mode", ["local", "offline"])
def test_local_and_offline_model_picker_never_discovers_chatgpt_models(env, monkeypatch, mode):
    from hutch.chatgpt_auth import ChatGPTAuthBook
    account_id = "acct_" + "a" * 24
    ConnectionBook(env.config.state_dir).add_chatgpt_account(account_id)
    original_has_key = ConnectionBook.has_key

    def has_key(book, name):
        if book.get(name) and book.get(name).auth_type == "chatgpt-siws":
            return True
        return original_has_key(book, name)

    monkeypatch.setattr(ConnectionBook, "has_key", has_key)
    monkeypatch.setattr(ChatGPTAuthBook, "list_models",
                        lambda *_args, **_kwargs: pytest.fail("local route performed hosted model discovery"))
    bot = mkbot(env, name=f"{mode}-bot", model="ollama/fake:8b", inference_mode=mode)
    choices = model_choices(env.config, env.store, bot)
    assert not any(choice.spec.startswith("chatgpt-") for choice in choices)


def test_models_endpoint_returns_the_list_and_404s_for_unknown_bots(env):
    mkbot(env, model="ollama/fake:8b")
    r = env.get("/api/bots/chatty/models")
    assert r.status_code == 200 and r.json()["default"] == "ollama/fake:8b"
    assert any(m["spec"] == "ollama/other:3b" for m in r.json()["models"])
    assert env.get("/api/bots/nobody/models").status_code == 404


# ------------------------------------------------------------------------ the override

def test_a_message_can_run_on_another_model_without_changing_the_bot(env):
    bot = mkbot(env, model="mock/demo")
    env.fake.script = agent_script([{"content": "hello from the other model"}])
    r = env.post("/api/bots/chatty/run", json={"prompt": "hi", "model": "ollama/tiny:1b"})
    assert r.status_code == 201 and r.json()["model_override"] == "ollama/tiny:1b"
    run = wait_done(env, r.json()["id"])
    assert run.status is RunStatus.succeeded, run.error
    assert run.model_used == "ollama/tiny:1b"
    assert env.store.get_bot("chatty").model == "mock/demo", "the stored bot must be untouched"


def test_switching_does_not_bypass_the_fit_guard(env):
    """The override reaches the real runtime, so a model that cannot fit is refused before it can freeze the machine."""
    mkbot(env, model="mock/demo")
    r = env.post("/api/bots/chatty/run", json={"prompt": "hi", "model": "ollama/huge:70b"})
    assert r.status_code == 201
    run = wait_done(env, r.json()["id"])
    assert run.status is RunStatus.failed and "does not fit this machine" in run.error


def test_a_plain_run_and_a_run_of_the_default_model_record_no_override(env):
    bot = mkbot(env, model="mock/demo")
    a = env.post("/api/bots/chatty/run", json={"prompt": "x"}).json()
    b = env.post("/api/bots/chatty/run", json={"prompt": "y", "model": "mock/demo"}).json()
    assert a["model_override"] == "" and b["model_override"] == ""


def test_scheduled_and_cli_runs_ignore_overrides_by_construction(env):
    bot = mkbot(env)
    run = env.app.state.engine.submit(bot, "scheduled", origin="schedule")
    assert run.model_override == ""


@pytest.mark.parametrize("spec,status,needle", [
    ("qwen3", 422, "not a model spec"),
    ("ollama/", 422, "no model"),
    ("nonsense/model", 422, "not a provider or connection"),
    ("anthropic/claude-opus-5-5", 409, "ANTHROPIC_API_KEY"),
])
def test_an_unusable_model_is_refused_up_front_with_the_fix(env, spec, status, needle):
    mkbot(env)
    r = env.post("/api/bots/chatty/run", json={"prompt": "hi", "model": spec})
    assert r.status_code == status and needle in r.json()["detail"], r.text
    assert env.store.list_runs() == [] if hasattr(env.store, "list_runs") else True


def test_connection_without_key_or_terms_is_refused_with_the_command_to_run(env, monkeypatch):
    ConnectionBook(env.config.state_dir).add("opencode-go")
    mkbot(env)
    r = env.post("/api/bots/chatty/run", json={"prompt": "hi", "model": "opencode-go/glm-5.3"})
    assert r.status_code == 409 and "no API key" in r.json()["detail"] and "set-key" in r.json()["detail"]
    monkeypatch.setenv("OPENCODE_API_KEY", "k")
    r = env.post("/api/bots/chatty/run", json={"prompt": "hi", "model": "opencode-go/glm-5.3"})
    assert r.status_code == 409 and "terms" in r.json()["detail"] and "ack opencode-go" in r.json()["detail"]


def test_a_bot_on_another_runtime_cannot_be_overridden(env):
    from hutch.models import RuntimeKind
    mkbot(env, name="piper", runtime=RuntimeKind.pi)
    r = env.post("/api/bots/piper/run", json={"prompt": "hi", "model": "ollama/fake:8b"})
    assert r.status_code == 422 and "chooses its own model" in r.json()["detail"]


def test_validate_override_returns_empty_for_no_choice(env):
    bot = mkbot(env, model="ollama/fake:8b")
    assert validate_override(env.config, env.store, bot, "") == bot.model
    assert validate_override(env.config, env.store, bot, "ollama/anything:1b") == "ollama/anything:1b"
