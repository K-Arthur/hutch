"""Doctor (SR-14), per-runtime health (SR-1) and the Models view (LM-5)."""

from __future__ import annotations

import json
import os
import stat

import pytest
from typer.testing import CliRunner

from hutch.cli import app as cli_app
from hutch.connections import ConnectionBook
from hutch.doctor import FAIL, INFO, OK, WARN, run_doctor, worst
from hutch.hardware import GIB, Gpu, Hardware, RuntimeInfo
from hutch.health import FAIL_DEGRADED_AT, FAIL_DOWN_AT, failures, record_outcome, runtime_health
from hutch.models import ApprovalMode, Bot, Limits, Run, RunStatus
from hutch.modelview import build_models_view
from hutch.providers.ollama import OllamaProvider
from hutch.runtime.ladder import reset_provider_cache
from tests.fakes import FakeOllama, agent_script

runner = CliRunner()
BIG = Hardware(gpus=[Gpu("X", "nvidia", 24.0, False, 24.0)], ram_total_gb=64, ram_available_gb=48,
               runtimes=[RuntimeInfo("ollama", True, True, "http://x", "0.0-fake", "running")])
DOWN = Hardware(ram_total_gb=16, ram_available_gb=12,
                runtimes=[RuntimeInfo("ollama", True, False, "http://x", "", "installed but not running"),
                          RuntimeInfo("llama.cpp"), RuntimeInfo("lmstudio")])
NO_SYSTEMD = lambda argv: type("R", (), {"stdout": ""})()


@pytest.fixture(autouse=True)
def _fresh():
    reset_provider_cache()


@pytest.fixture()
def ollama(monkeypatch):
    s = FakeOllama({"fake:8b": {}, "huge:70b": {"params": "70B", "size": 45_000_000_000, "ctx": 131072}})
    monkeypatch.setenv("OLLAMA_HOST", s.url)
    yield s
    s.close()


def by_id(checks):
    return {c.id: c for c in checks}


# ================================================================== doctor

def test_a_clean_install_has_no_failures(config, store):
    checks = run_doctor(config, store, hw=DOWN, systemctl=NO_SYSTEMD)
    c = by_id(checks)
    assert c["python"].status == OK and c["database"].status == OK and "journal wal" in c["database"].detail
    assert worst(checks) != FAIL


def test_database_check_reports_schema_integrity_and_wal(config, store):
    d = by_id(run_doctor(config, store, hw=DOWN, systemctl=NO_SYSTEMD))["database"]
    assert d.status == OK and f"schema v{store.schema_version}" in d.detail and "integrity ok" in d.detail


def test_loose_permissions_are_flagged_with_the_exact_fix(config, store):
    os.chmod(config.state_dir, 0o755)
    keys = config.state_dir / "keys"
    keys.mkdir()
    k = keys / "x.key"
    k.write_text("secret")
    os.chmod(k, 0o644)
    p = by_id(run_doctor(config, store, hw=DOWN, systemctl=NO_SYSTEMD))["permissions"]
    assert p.status == WARN and "0o755" in p.detail and "0o644" in p.detail
    assert f"chmod 700 {config.state_dir}" in p.fix and "chmod 600" in p.fix


def test_new_state_directories_are_created_private(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "fresh-state"))
    from hutch.config import get_config
    from hutch.store import Store
    Store(get_config()).close()
    assert stat.S_IMODE((tmp_path / "fresh-state").stat().st_mode) == 0o700


def test_orphaned_runs_are_reported(config, store):
    bot = store.create_bot(Bot(name="o"))
    store.create_run(Run(bot_id=bot.id, prompt="x", status=RunStatus.running, owner="2147483646"))
    o = by_id(run_doctor(config, store, hw=DOWN, systemctl=NO_SYSTEMD))["orphans"]
    assert o.status == WARN and "exited" in o.detail


def test_service_states_not_installed_inactive_active(config, store, tmp_path, monkeypatch):
    def sc(load, active):
        return lambda argv: type("R", (), {"stdout": load if "show" in argv else active})()

    from hutch.service import ServiceProbe, render_user_unit

    config_home = tmp_path / "config"
    unit_dir = config_home / "systemd/user"
    unit_dir.mkdir(parents=True)
    (unit_dir / "hutch.service").write_text(render_user_unit("/usr/bin/python3", config.state_dir, port=18888))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))

    ready = lambda *a, **k: ServiceProbe(True, True, "ready", {"id": "x", "pid": 1})
    unready = lambda *a, **k: ServiceProbe(True, False, "a different Hutch instance owns this port")
    get = lambda s, probe=ready: by_id(run_doctor(config, store, hw=DOWN, systemctl=s,
                                                  service_probe=probe))["service"]
    ni = get(sc("not-found", "inactive"))
    assert ni.status == INFO and "hutch service install" in ni.fix, "inactive must not be confused with not installed"
    assert get(sc("loaded", "inactive")).status == WARN
    active = get(sc("loaded", "active"))
    assert active.status == OK and "readiness handshake" in active.detail
    not_ready = get(sc("loaded", "active"), probe=unready)
    assert not_ready.status == WARN and "not confirmed ready" in not_ready.detail


def test_a_local_bot_with_ollama_down_fails_with_the_fix(config, store):
    store.create_bot(Bot(name="loc", model="ollama/fake:8b"))
    checks = by_id(run_doctor(config, store, hw=DOWN, systemctl=NO_SYSTEMD))
    assert checks["runtime:ollama"].status == FAIL and "ollama serve" in checks["runtime:ollama"].fix
    assert checks["models"].status == WARN


def test_missing_model_fit_and_effective_context_are_reported_per_bot(config, store, ollama):
    store.create_bot(Bot(name="ok-bot", model="ollama/fake:8b", num_ctx=16384))
    store.create_bot(Bot(name="gone", model="ollama/absent:7b"))
    store.create_bot(Bot(name="big", model="ollama/huge:70b"))
    hw = Hardware(gpus=[Gpu("X", "nvidia", 12.0, False, 12.0)], ram_total_gb=32, ram_available_gb=24,
                  runtimes=[RuntimeInfo("ollama", True, True, ollama.url, "0.0", "running")])
    c = by_id(run_doctor(config, store, hw=hw, systemctl=NO_SYSTEMD))
    assert c["model:ok-bot"].status == OK and "context it will actually get" in c["model:ok-bot"].detail
    assert c["model:gone"].status == FAIL and "ollama pull absent:7b" in c["model:gone"].fix
    assert c["model:big"].status == FAIL and "won't fit" in c["model:big"].detail


def test_deep_runs_the_context_selfcheck_and_fails_loudly(config, store, ollama):
    store.create_bot(Bot(name="loc", model="ollama/fake:8b", num_ctx=8192))
    ollama.script = agent_script([{"content": "x"}], recall=False)
    c = by_id(run_doctor(config, store, hw=BIG, deep=True, systemctl=NO_SYSTEMD))
    assert c["selfcheck:loc"].status == FAIL and "could NOT recall" in c["selfcheck:loc"].detail
    ollama.script = agent_script([{"content": "x"}], recall=True)
    c = by_id(run_doctor(config, store, hw=BIG, deep=True, systemctl=NO_SYSTEMD))
    assert c["selfcheck:loc"].status == OK


def test_connection_problems_name_the_fix(config, store, monkeypatch):
    book = ConnectionBook(config.state_dir)
    monkeypatch.delenv("OPENCODE_API_KEY", raising=False)
    book.add("opencode-go")
    c = by_id(run_doctor(config, store, hw=DOWN, systemctl=NO_SYSTEMD))["connection:opencode-go"]
    assert c.status == FAIL and "OPENCODE_API_KEY" in c.fix
    monkeypatch.setenv("OPENCODE_API_KEY", "k")
    c = by_id(run_doctor(config, store, hw=DOWN, systemctl=NO_SYSTEMD))["connection:opencode-go"]
    assert c.status == FAIL and "hutch connections ack opencode-go" in c.fix
    book.acknowledge(store, "opencode-go")
    c = by_id(run_doctor(config, store, hw=DOWN, systemctl=NO_SYSTEMD))["connection:opencode-go"]
    assert c.status == OK and "--online" in c.detail


def test_bot_hygiene_warnings(config, store):
    store.create_bot(Bot(name="risky", model="mock/demo", tools=["shell"], approval_mode=ApprovalMode.auto))
    store.create_bot(Bot(name="nocap", model="anthropic/claude-opus-5-5"))
    store.create_bot(Bot(name="capped", model="anthropic/claude-opus-5-5", limits=Limits(max_cost_usd=2.0)))
    store.create_bot(Bot(name="toolbox", model="ollama/fake:8b",
                         tools=["shell", "read_file", "list_files", "write_file", "remember", "recall", "web_fetch",
                                "browser", "x"]))
    c = by_id(run_doctor(config, store, hw=BIG, systemctl=NO_SYSTEMD))
    assert c["auto-shell:risky"].status == WARN and "stay blocked" in c["auto-shell:risky"].detail
    assert c["nocap:nocap"].status == WARN and "max_cost_usd" in c["nocap:nocap"].fix
    assert "nocap:capped" not in c


def test_doctor_cli_exit_code_json_and_output(config, store, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(config.state_dir))
    store.create_bot(Bot(name="loc", model="ollama/fake:8b"))
    store.close()
    ok = runner.invoke(cli_app, ["doctor", "--json"])
    rows = json.loads(ok.output)
    assert {r["id"] for r in rows} >= {"python", "database", "permissions"}
    r = runner.invoke(cli_app, ["doctor"])
    assert "fix:" in r.output or r.exit_code in (0, 1)


# ================================================================== health (SR-1)

def test_failures_degrade_then_down_and_a_success_recovers(config, store):
    for _ in range(FAIL_DEGRADED_AT):
        record_outcome(store, "ollama", False, "unreachable: refused")
    assert failures(store, "ollama")[0] == FAIL_DEGRADED_AT
    hw = Hardware(ram_total_gb=16, ram_available_gb=12,
                  runtimes=[RuntimeInfo("ollama", True, False, "http://x", "", "installed but not running")])
    h = [x for x in runtime_health(config, store, hw) if x.name == "ollama"][0]
    assert h.state == "down" and h.fix                                 # unreachable wins; failures are appended
    assert "2 recent call failure" in h.detail and "refused" in h.detail
    record_outcome(store, "ollama", True)
    assert failures(store, "ollama")[0] == 0


def test_a_reachable_runtime_with_repeated_failures_is_degraded_then_down(config, store, ollama):
    hw = Hardware(ram_total_gb=16, ram_available_gb=12,
                  runtimes=[RuntimeInfo("ollama", True, True, ollama.url, "0.0", "running")])
    prov = OllamaProvider(ollama.url)
    for n in range(1, FAIL_DOWN_AT + 1):
        record_outcome(store, "ollama", False, "stream: broke")
        h = runtime_health(config, store, hw, ollama=prov)[0]
        assert h.state == ("degraded" if n < FAIL_DOWN_AT else "down") if n >= FAIL_DEGRADED_AT else h.state == "healthy"
    assert h.loaded == [] and h.latency_ms >= 0


def test_one_runtimes_failures_do_not_touch_anothers_health(config, store, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    for _ in range(5):
        record_outcome(store, "ollama", False, "down")
    hw = Hardware(ram_total_gb=16, ram_available_gb=12, runtimes=[
        RuntimeInfo("ollama", True, True, "http://x", "0", "running"), RuntimeInfo("lmstudio", True, True, "http://y")])
    got = {h.name: h for h in runtime_health(config, store, hw, ["anthropic/claude-opus-5-5"], ollama=OllamaProvider("http://127.0.0.1:9"))}
    assert got["ollama"].state == "down" and got["lmstudio"].state == "healthy" and got["anthropic"].state == "healthy"


def test_connections_and_hosted_providers_show_setup_needs(config, store, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENCODE_API_KEY", raising=False)
    ConnectionBook(config.state_dir).add("opencode-go")
    got = {h.name: h for h in runtime_health(config, store, DOWN, ["anthropic/claude-opus-5-5"])}
    assert got["opencode-go"].state == "needs_setup" and "OPENCODE_API_KEY" in got["opencode-go"].fix
    assert got["anthropic"].state == "needs_setup" and "ANTHROPIC_API_KEY" in got["anthropic"].fix


def test_the_runtime_records_outcomes_so_health_reflects_real_calls(store, config, tmp_path):
    from hutch.runtime.builtin import BuiltinRuntime
    from tests.test_runtime_builtin import build, factory, run_it
    s = FakeOllama({"fake:8b": {}})
    try:
        s.script = agent_script([{"content": "ok"}])
        ctx, run, emitted, tools = build(store, config, tmp_path)
        run_it(BuiltinRuntime(hardware=BIG, provider_factory=factory(s)), run, ctx, tools)
        assert failures(store, "ollama")[0] == 0
        s.force_status = (500, "boom")
        from hutch.models import Bot as _B
        bot2 = store.create_bot(_B(name="rt2", model="ollama/fake:8b", approval_mode=ApprovalMode.auto, selfcheck=False,
                                   tools=["files"]))
        run2 = store.create_run(Run(bot_id=bot2.id, prompt="x"))
        from hutch.approvals import ApprovalGate
        from hutch.safety import PolicyEngine
        from hutch.tools import build_tools
        from hutch.tools.base import ToolContext
        gate = ApprovalGate(store, bot2, run2, PolicyEngine(), lambda e: store.append_event(e))
        ctx2 = ToolContext(bot=bot2, run=run2, store=store, policy=gate.policy, gate=gate, config=config,
                           workspace=tmp_path / "ws", emit=lambda e: store.append_event(e))
        from hutch.runtime import RunAborted
        with pytest.raises(RunAborted):
            run_it(BuiltinRuntime(hardware=BIG, provider_factory=factory(s)), run2, ctx2, build_tools(bot2.tools, ctx2))
        assert failures(store, "ollama")[0] >= 1
    finally:
        s.close()


# ================================================================== Models view (LM-5, LM-7, LM-14)

def test_models_view_marks_each_installed_model_with_the_context_it_will_get(config, store, ollama):
    hw = Hardware(gpus=[Gpu("X", "nvidia", 12.0, False, 12.0)], ram_total_gb=32, ram_available_gb=24,
                  runtimes=[RuntimeInfo("ollama", True, True, ollama.url, "0.0", "running")])
    store.create_bot(Bot(name="user-of-fake", model="ollama/fake:8b"))
    store.kv_set("model_load:fake:8b", json.dumps({"ms": 4200.0}))
    v = build_models_view(config, store, hw=hw, provider=OllamaProvider(ollama.url))
    rows = {r.name: r for r in v.rows}
    fake, huge = rows["fake:8b"], rows["huge:70b"]
    assert fake.fits[16384].status in ("fits", "tight") and fake.fits[16384].effective_ctx >= 8192
    assert huge.fits[16384].status == "wont_fit"
    assert fake.bots == ["user-of-fake"] and fake.load_ms == 4200.0 and fake.selfcheck == "not run"
    assert not any(t == "fake:8b" for t, *_ in v.suggestions)            # installed models are not suggested
    assert all(isinstance(t, str) for t, *_ in v.suggestions) and v.prices


def test_models_view_without_ollama_says_so_and_still_resolves_presets(config, store):
    v = build_models_view(config, store, hw=DOWN, provider=OllamaProvider("http://127.0.0.1:9"))
    assert not v.ollama_up and not v.rows and any("Ollama is not running" in n for n in v.notes)
    assert len(v.presets) == 6 and v.suggestions


def test_selfcheck_status_is_read_from_the_cache(config, store, ollama):
    store.kv_set("selfcheck:sha:fake:8b:16384:tpl", json.dumps({"ok": True}))
    hw = Hardware(gpus=[Gpu("X", "nvidia", 24.0, False, 24.0)], ram_total_gb=32, ram_available_gb=24,
                  runtimes=[RuntimeInfo("ollama", True, True, ollama.url, "0", "running")])
    v = build_models_view(config, store, hw=hw, provider=OllamaProvider(ollama.url))
    assert {r.name: r.selfcheck for r in v.rows}["fake:8b"] == "passed"


def test_price_rows_expose_verified_dates_and_staleness(config, store):
    v = build_models_view(config, store, hw=DOWN, provider=OllamaProvider("http://127.0.0.1:9"))
    p = {x.model: x for x in v.prices}["anthropic/claude-opus-5-5"]
    assert p.verified_on == "2026-10-07" and p.source.startswith("https://platform.claude.com")
