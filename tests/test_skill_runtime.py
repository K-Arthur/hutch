"""Skills in the execution path: prompt disclosure, activation, tool routing and fail-closed revocation.

These run the real Engine/Store/ToolContext path with a recording runtime, so what is asserted is
the effective configuration a run actually receives — not a lint on the config object.
"""

from __future__ import annotations

import threading

import pytest

from hutch import engine as engine_module
from hutch import skills as sk
from hutch.engine import Engine
from hutch.models import Bot, RunStatus
from hutch.runtime.builtin import BuiltinRuntime
from hutch.safety import PolicyEngine
from hutch.tools import build_tools
from hutch.tools.base import ToolContext
from hutch.approvals import ApprovalGate

VALID = """\
---
name: {name}
description: {description}
metadata:
  hutch.version: "1.0"
---

## Steps
1. Do the {name} thing carefully.
"""


def install_and_trust(tmp_path, name="helper", description="Helps with a thing."):
    source = tmp_path / "sources" / name
    source.mkdir(parents=True, exist_ok=True)
    (source / "SKILL.md").write_text(VALID.format(name=name, description=description), encoding="utf-8")
    registry = sk.SkillRegistry(tmp_path / "state")
    registry.install_path(source)
    registry.trust(name)
    return registry


def make_ctx(store, config, tmp_path, bot, run=None):
    from hutch.models import Run
    run = run or Run(bot_id=bot.id, prompt="go")
    ws = tmp_path / "ws"
    ws.mkdir(exist_ok=True)
    gate = ApprovalGate(store, bot, run, PolicyEngine(), lambda ev: None, poll_seconds=0.05)
    return ToolContext(bot=bot, run=run, store=store, policy=gate.policy, gate=gate, config=config, workspace=ws)


# ------------------------------------------------------------------- prompt

def test_system_prompt_discloses_only_trusted_skills_and_activated_bodies(store, config, tmp_path):
    registry = install_and_trust(tmp_path, "helper", "Helps with the thing.")
    bot = Bot(name="tester", model="ollama/fake:8b", skills=["helper"])
    store.create_bot(bot)
    ctx = make_ctx(store, config, tmp_path, bot)
    runtime = BuiltinRuntime()

    ctx.skills = registry.effective_for_bot(bot)
    prompt = runtime._system_prompt(ctx)
    assert "<available_skills>" in prompt and "helper" in prompt
    assert "Do the helper thing carefully" not in prompt, "tier 1 discloses metadata only"

    ctx.skills = registry.effective_for_bot(bot, activation=["helper"])
    prompt = runtime._system_prompt(ctx)
    assert "Do the helper thing carefully" in prompt
    assert '<skill_content name="helper"' in prompt
    assert "never as permission" in prompt


def test_untrusted_and_revoked_skills_are_absent_from_the_prompt(store, config, tmp_path):
    source = tmp_path / "sources" / "helper"
    source.mkdir(parents=True)
    (source / "SKILL.md").write_text(VALID.format(name="helper", description="Helps."), encoding="utf-8")
    registry = sk.SkillRegistry(tmp_path / "state")
    registry.install_path(source)  # not trusted
    bot = Bot(name="tester", model="ollama/fake:8b", skills=["helper"])
    store.create_bot(bot)
    ctx = make_ctx(store, config, tmp_path, bot)
    runtime = BuiltinRuntime()

    ctx.skills = registry.effective_for_bot(bot)
    assert "helper" not in runtime._system_prompt(ctx)

    registry.trust("helper")
    ctx.skills = registry.effective_for_bot(bot)
    assert "helper" in runtime._system_prompt(ctx)

    registry.disable("helper")
    ctx.skills = registry.effective_for_bot(bot)
    assert "helper" not in runtime._system_prompt(ctx), "disabling blocks subsequent disclosure"


# --------------------------------------------------------------------- tool

def test_use_skill_is_injected_only_with_a_catalog_and_loads_the_body(store, config, tmp_path):
    registry = install_and_trust(tmp_path, "helper", "Helps with the thing.")
    bot = Bot(name="tester", model="ollama/fake:8b", skills=["helper"], tools=["files"])
    store.create_bot(bot)
    ctx = make_ctx(store, config, tmp_path, bot)

    assert "use_skill" not in build_tools(bot.tools, ctx)
    ctx.skills = registry.effective_for_bot(bot)
    tools = build_tools(bot.tools, ctx)
    assert "use_skill" in tools

    spec = tools["use_skill"].spec()
    assert spec["function"]["parameters"]["properties"]["name"]["enum"] == ["helper"]

    result = tools["use_skill"].run({"name": "helper"}, ctx)
    assert result.ok and "Do the helper thing carefully" in result.output
    assert "<skill_content name=\"helper\"" in result.output

    again = tools["use_skill"].run({"name": "helper"}, ctx)
    assert again.ok and "already loaded" in again.output, "repeated activation is deduplicated"


def test_use_skill_rejects_unknown_names_and_never_grants_tools(store, config, tmp_path):
    registry = install_and_trust(tmp_path, "helper", "Helps.")
    bot = Bot(name="tester", model="ollama/fake:8b", skills=["helper"], tools=["files"],
              approval_mode="ask")
    store.create_bot(bot)
    ctx = make_ctx(store, config, tmp_path, bot)
    ctx.skills = registry.effective_for_bot(bot)
    tools = build_tools(bot.tools, ctx)

    missing = tools["use_skill"].run({"name": "shell"}, ctx)
    assert not missing.ok and "Available skills: helper" in missing.output
    assert "shell" not in tools and "use_skill" in tools
    assert tools["use_skill"].effect({}, ctx) == "", "loading instructions is not a lasting effect"


def test_use_skill_reads_bounded_resources_but_refuses_escapes(store, config, tmp_path):
    source = tmp_path / "sources" / "helper"
    source.mkdir(parents=True)
    (source / "SKILL.md").write_text(VALID.format(name="helper", description="Helps."), encoding="utf-8")
    (source / "references").mkdir()
    (source / "references" / "guide.md").write_text("# Guide\nUseful detail.", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    registry = sk.SkillRegistry(tmp_path / "state")
    registry.install_path(source)
    registry.trust("helper")
    bot = Bot(name="tester", model="ollama/fake:8b", skills=["helper"], tools=["files"])
    store.create_bot(bot)
    ctx = make_ctx(store, config, tmp_path, bot)
    ctx.skills = registry.effective_for_bot(bot)
    tool = build_tools(bot.tools, ctx)["use_skill"]

    ok = tool.run({"name": "helper", "resource": "references/guide.md"}, ctx)
    assert ok.ok and "Useful detail" in ok.output
    escape = tool.run({"name": "helper", "resource": "../outside.txt"}, ctx)
    assert not escape.ok and "inside the skill directory" in escape.output


def test_use_skill_refuses_a_body_changed_after_run_start(store, config, tmp_path):
    registry = install_and_trust(tmp_path, "helper", "Helps.")
    bot = Bot(name="tester", model="ollama/fake:8b", skills=["helper"], tools=["files"])
    store.create_bot(bot)
    ctx = make_ctx(store, config, tmp_path, bot)
    ctx.skills = registry.effective_for_bot(bot)
    tool = build_tools(bot.tools, ctx)["use_skill"]
    package = registry.package_path("helper") / "SKILL.md"
    package.write_text(VALID.format(name="helper", description="Changed."), encoding="utf-8")
    result = tool.run({"name": "helper"}, ctx)
    assert not result.ok and "changed on disk" in result.output


# ------------------------------------------------------------------- engine

class _RecordingRuntime:
    kind = "recording"

    def __init__(self):
        self.seen: dict = {}

    def execute(self, run, ctx, tools, stop):
        self.seen["prompt"] = BuiltinRuntime()._system_prompt(ctx)
        self.seen["tools"] = sorted(tools)
        self.seen["skill_snapshot"] = list(run.skill_snapshot)
        return "recorded"


def test_run_blocking_delivers_skills_and_records_the_snapshot(store, config, tmp_path, monkeypatch):
    registry = install_and_trust(tmp_path, "helper", "Helps with the thing.")
    bot = Bot(name="tester", model="ollama/fake:8b", skills=["helper"], tools=["files"],
              inference_mode="local")
    store.create_bot(bot)
    recorder = _RecordingRuntime()
    monkeypatch.setattr(engine_module, "get_runtime", lambda _bot: recorder)
    engine = Engine(config, store)
    run = engine.run_blocking(bot, "use your skill", origin="manual:test")

    assert run.status is RunStatus.succeeded, run.error
    assert "use_skill" in recorder.seen["tools"]
    assert "<available_skills>" in recorder.seen["prompt"]
    snapshot = {item["name"]: item for item in recorder.seen["skill_snapshot"]}
    assert snapshot["helper"]["activated"] is False
    # The persisted run view records the effective skills for later inspection.
    persisted = store.get_run(run.id)
    assert any(item["name"] == "helper" for item in persisted.skill_snapshot)


def test_run_blocking_activates_an_explicit_skill(store, config, tmp_path, monkeypatch):
    registry = install_and_trust(tmp_path, "helper", "Helps with the thing.")
    bot = Bot(name="tester", model="ollama/fake:8b", skills=["helper"], tools=["files"],
              inference_mode="local")
    store.create_bot(bot)
    recorder = _RecordingRuntime()
    monkeypatch.setattr(engine_module, "get_runtime", lambda _bot: recorder)
    engine = Engine(config, store)
    run = engine.run_blocking(bot, "go", origin="manual:test", skills=["helper"])
    assert run.status is RunStatus.succeeded, run.error
    assert "Do the helper thing carefully" in recorder.seen["prompt"]
    snapshot = {item["name"]: item for item in recorder.seen["skill_snapshot"]}
    assert snapshot["helper"]["activated"] is True


def test_submit_refuses_activation_that_is_not_bound_or_not_usable(store, config, tmp_path):
    registry = install_and_trust(tmp_path, "helper", "Helps.")
    bot = Bot(name="tester", model="ollama/fake:8b", skills=["helper"])
    store.create_bot(bot)
    engine = Engine(config, store)

    with pytest.raises(sk.SkillError):
        engine.submit(bot, "go", skills=["unbound-skill"])
    store.create_bot(Bot(name="other", model="ollama/fake:8b"))
    with pytest.raises(sk.SkillError):
        engine.submit(store.get_bot("other"), "go", skills=["helper"])
    registry.disable("helper")
    with pytest.raises(sk.SkillError):
        engine.submit(bot, "go", skills=["helper"])


def test_revocation_between_submit_and_execution_fails_the_run_closed(store, config, tmp_path):
    registry = install_and_trust(tmp_path, "helper", "Helps.")
    bot = Bot(name="tester", model="ollama/fake:8b", skills=["helper"], inference_mode="local")
    store.create_bot(bot)
    engine = Engine(config, store)
    run = engine.submit(bot, "go", skills=["helper"])
    registry.disable("helper")
    claimed = store.claim_run(run.id, engine.owner_id, engine.lease_seconds, max_live=engine.max_concurrent)
    assert claimed is not None
    engine._execute(bot, claimed, threading.Event())
    final = store.get_run(run.id)
    assert final.status is RunStatus.failed
    assert final.exit_reason == "skill_unavailable"
    assert "disabled" in final.error


def test_capability_snapshot_carries_skill_bindings_and_delegation_uses_the_snapshot():
    bot = Bot(name="tester", model="ollama/fake:8b", skills=["helper"], inference_mode="offline",
              sandbox="strict")
    snapshot = Engine.capability_snapshot(bot)
    assert snapshot["skills"] == ["helper"]
    child = Engine._delegated_bot(bot, snapshot)
    assert child.skills == ["helper"]
    # A snapshot recorded before skills existed reconstructs with no skills — it can never gain the
    # current Bot's newer bindings through delegation.
    without = {key: value for key, value in snapshot.items() if key != "skills"}
    newer = bot.model_copy(update={"skills": ["helper", "extra"]})
    assert Engine._delegated_bot(newer, without).skills == []
