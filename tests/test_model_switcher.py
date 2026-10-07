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
                       "huge:70b": {"params": "70B", "size": 45_000_000_000, "ctx": 131072}})
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
    bot = mkbot(env)
    assert validate_override(env.config, env.store, bot, "") == ""
    assert validate_override(env.config, env.store, bot, "ollama/anything:1b") == "ollama/anything:1b"
