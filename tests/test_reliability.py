"""Reliability harness (LM-11): scripted models of known quality must be told apart, honestly."""

from __future__ import annotations

import json
import re

import pytest
from typer.testing import CliRunner

from hutch.cli import app as cli_app
from hutch.doctor import INFO, OK, WARN, run_doctor
from hutch.hardware import GIB, Gpu, Hardware, RuntimeInfo
from hutch.models import ApprovalMode, Bot
from hutch.modelview import build_models_view
from hutch.providers.ollama import OllamaProvider
from hutch.reliability import Profile, probes, profile_key, profile_model
from hutch.runtime.ladder import reset_provider_cache
from tests.fakes import FakeOllama

runner = CliRunner()


def _last_user(body) -> str:
    return next((m["content"] for m in reversed(body["messages"]) if m["role"] == "user"), "")


def behaviour(kind: str):
    """Scripted models: good | sloppy (string-typed args) | chatty (never calls a tool) | wrong (wrong tool/args)."""
    state = {"n": 0}

    def script(body):
        full = body.get("_full_text", "")
        if "secret code word for this check is" in full:
            m = re.search(r"code word for this check is ([A-Z0-9-]+)", body.get("_seen_text", ""))
            return {"content": m.group(1) if m else "unknown"}
        state["n"] += 1
        text = _last_user(body)
        has_result = any(m["role"] == "tool" for m in body["messages"])
        if "2 + 2" in text:
            return {"content": "4" if kind != "chatty" else "Sure! Happy to help with that."}
        if has_result:
            return {"content": "The meeting is at 3pm on Thursday." if kind != "chatty" else "Glad to help."}
        if kind == "chatty":
            return {"content": "I would read the file for you if I could."}
        if "notes.txt" in text:
            return {"tool_calls": [{"name": "read_file", "arguments": {"path": "notes.txt" if kind != "wrong" else "other.txt"}}]}
        if "bananas" in text:
            args = {"name": "bananas", "quantity": 3, "urgent": True}
            if kind == "sloppy":
                args = {"name": "bananas", "quantity": "3", "urgent": "true"}
            if kind == "wrong":
                args = {"name": "apples", "quantity": 1, "urgent": False}
            return {"tool_calls": [{"name": "add_item", "arguments": args}]}
        if "reports" in text:
            return {"tool_calls": [{"name": "shell" if kind == "wrong" else "list_files",
                                    "arguments": {"command": "ls reports"} if kind == "wrong" else {"path": "reports"}}]}
        return {"content": "?"}
    return script


@pytest.fixture()
def fake():
    s = FakeOllama({"m:1b": {"params": "1B", "size": 500_000_000}})
    yield s
    s.close()


def run_profile(fake, kind, trials=3, **kw):
    fake.script = behaviour(kind)
    return profile_model(OllamaProvider(fake.url), "m:1b", num_ctx=4096, trials=trials, hardware="test box", **kw)


# ---------------------------------------------------------------- verdicts

def test_a_well_behaved_model_is_reliable_on_every_probe(fake):
    p = run_profile(fake, "good")
    assert p.verdict == "reliable", p.summary
    assert all(x.raw == x.trials and x.repaired == x.trials for x in p.probes), [(x.id, x.raw, x.repaired) for x in p.probes]
    assert [x.id for x in p.probes] == ["call_shape", "arg_types", "tool_choice", "restraint", "uses_result", "long_context"]
    assert p.model == "ollama/m:1b" and p.num_ctx == 4096 and p.hardware == "test box" and p.measured_at


def test_a_model_that_only_works_after_type_repair_is_labelled_so(fake):
    p = run_profile(fake, "sloppy")
    arg = p.probe("arg_types")
    assert arg.raw == 0 and arg.repaired == arg.trials, "'3' and 'true' are repaired before the tool runs"
    assert p.verdict == "usable_with_repair" and "argument repair" in p.summary


def test_a_model_that_never_calls_tools_is_unreliable_and_the_weakest_probe_is_named(fake):
    p = run_profile(fake, "chatty")
    assert p.verdict == "unreliable"
    assert p.probe("call_shape").repaired == 0 and "prose" in p.probe("call_shape").detail
    assert "weakest" in p.summary


def test_wrong_tool_and_wrong_arguments_are_failures_with_reasons(fake):
    p = run_profile(fake, "wrong")
    assert p.verdict == "unreliable"
    assert "other.txt" in p.probe("call_shape").detail or "wrong file" in p.probe("call_shape").detail
    assert "shell" in p.probe("tool_choice").detail
    assert "wrong item name" in p.probe("arg_types").detail


def test_three_models_are_told_apart_in_order(fake):
    """The harness's job: rank what the person actually has installed."""
    order = {"reliable": 0, "usable_with_repair": 1, "unreliable": 2}
    verdicts = {k: run_profile(fake, k, trials=2).verdict for k in ("sloppy", "good", "chatty")}
    assert sorted(verdicts, key=lambda k: order[verdicts[k]]) == ["good", "sloppy", "chatty"], verdicts


def test_a_failing_runtime_is_inconclusive_not_unreliable(fake):
    fake.force_status = (500, "boom")
    p = profile_model(OllamaProvider(fake.url), "m:1b", num_ctx=4096, trials=2, with_recall=False)
    assert p.verdict == "inconclusive", "a dead runtime says nothing about the model's quality"
    assert all(x.errors == x.trials for x in p.probes)


def test_recall_can_be_skipped_and_failure_is_reported(fake):
    p = run_profile(fake, "good", trials=1, with_recall=False)
    assert p.probe("long_context") is None
    fake.script = lambda body: {"content": "I do not know."} if "secret code word" in body.get("_full_text", "") else behaviour("good")(body)
    p = profile_model(OllamaProvider(fake.url), "m:1b", num_ctx=4096, trials=1)
    assert p.probe("long_context").repaired == 0 and "could not recall" in p.summary


def test_every_probe_has_a_distinct_id_and_a_tool_schema():
    ps = probes()
    assert len({p.id for p in ps}) == len(ps) == 5
    assert all(p.tools and p.messages for p in ps)


# ---------------------------------------------------------------- keys and storage

def test_profile_keys_distinguish_quant_runtime_template_digest_and_window():
    base = ("ollama/m", "Q4_K_M", "ollama", "tpl1", "sha:1", 8192)
    keys = {profile_key(*base)}
    for i, alt in enumerate(["Q8_0", "lmstudio", "tpl2", "sha:2", 16384]):
        args = list(base)
        args[[1, 2, 3, 4, 5][i]] = alt
        keys.add(profile_key(*args))
    assert len(keys) == 6


def test_profiles_round_trip_and_the_latest_wins(store, fake):
    a = run_profile(fake, "chatty", trials=1)
    store.save_profile(a)
    import time
    time.sleep(0.01)
    b = run_profile(fake, "good", trials=1)
    store.save_profile(b)
    got = store.latest_profile("ollama/m:1b")
    assert got.verdict == "reliable" and got.key == b.key == a.key
    assert len(store.list_profiles()) == 1, "re-measuring the same model/quant/template/window replaces the old row"
    other = profile_model(OllamaProvider(fake.url), "m:1b", num_ctx=8192, trials=1)
    store.save_profile(other)
    assert len(store.list_profiles()) == 2, "a different window is a different profile"
    assert Profile.from_json(a.to_json()).probes[0].title == a.probes[0].title
    assert store.latest_profile("ollama/nope") is None


def test_migration_four_creates_the_profile_table(store):
    with store._lock:
        cols = [r[1] for r in store._db.execute("PRAGMA table_info(model_profiles)")]
    assert {"key", "model", "runtime", "digest", "template_hash", "measured_at", "doc"} <= set(cols)


# ---------------------------------------------------------------- CLI, doctor, page

@pytest.fixture()
def env(tmp_path, monkeypatch, fake):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("OLLAMA_HOST", fake.url)
    reset_provider_cache()
    return fake


def test_bench_command_prints_the_table_verdict_and_saves(env, tmp_path):
    env.script = behaviour("sloppy")
    r = runner.invoke(cli_app, ["models", "bench", "m:1b", "--trials", "2", "--ctx", "4096"])
    assert r.exit_code == 0, r.output
    for needle in ("Gets argument types right", "works, leaning on argument repair", "unaided"):
        assert needle in r.output, needle
    from hutch.config import get_config
    from hutch.store import Store
    assert Store(get_config()).latest_profile("ollama/m:1b").verdict == "usable_with_repair"


def test_bench_command_fails_clearly_when_ollama_is_down(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:9")
    reset_provider_cache()
    r = runner.invoke(cli_app, ["models", "bench", "m:1b"])
    assert r.exit_code == 1 and "ollama serve" in r.output


def _hw(url):
    return Hardware(gpus=[Gpu("X", "nvidia", 24.0, False, 24.0)], ram_total_gb=32, ram_available_gb=24,
                    runtimes=[RuntimeInfo("ollama", True, True, url, "0", "running")])


def test_doctor_uses_the_profile(config, store, env):
    store.create_bot(Bot(name="t", model="ollama/m:1b", tools=["files"], approval_mode=ApprovalMode.auto, selfcheck=False))
    sc = lambda argv: type("R", (), {"stdout": ""})()
    c = {x.id: x for x in run_doctor(config, store, hw=_hw(env.url), systemctl=sc)}
    assert c["profile:t"].status == INFO and "hutch models bench m:1b" in c["profile:t"].fix
    store.save_profile(run_profile(env, "chatty", trials=1))
    c = {x.id: x for x in run_doctor(config, store, hw=_hw(env.url), systemctl=sc)}
    assert c["profile:t"].status == WARN and "escalation" in c["profile:t"].fix
    store.save_profile(run_profile(env, "good", trials=1))
    c = {x.id: x for x in run_doctor(config, store, hw=_hw(env.url), systemctl=sc)}
    assert c["profile:t"].status == OK


def test_models_view_carries_the_profile_and_flags_a_changed_model(config, store, env):
    store.save_profile(run_profile(env, "good", trials=1))
    v = build_models_view(config, store, hw=_hw(env.url), provider=OllamaProvider(env.url))
    row = {r.name: r for r in v.rows}["m:1b"]
    assert row.profile and row.profile.verdict == "reliable" and not row.profile_stale
    prof = store.latest_profile("ollama/m:1b")
    prof.template_hash = "someothertemplate"
    store.save_profile(prof)
    v = build_models_view(config, store, hw=_hw(env.url), provider=OllamaProvider(env.url))
    assert {r.name: r for r in v.rows}["m:1b"].profile_stale, "a changed template must not reuse an old measurement silently"
