from __future__ import annotations

import json
import stat
import subprocess
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from typer.testing import CliRunner

from hutch import service
from hutch.cli import app
from hutch.instance import instance_id


class FakeSystemd:
    def __init__(self, *, fail_on: tuple[str, ...] | None = None, load_state: str = "loaded",
                 active_state: str = "active", main_pid: int | None = None):
        self.calls: list[list[str]] = []
        self.fail_on = fail_on
        self.load_state = load_state
        self.active_state = active_state
        self.main_pid = main_pid

    def __call__(self, argv, **kwargs):
        self.calls.append(list(argv))
        if self.fail_on and tuple(argv[-len(self.fail_on):]) == self.fail_on:
            return subprocess.CompletedProcess(argv, 1, "", "unit failed")
        if "show" in argv and "LoadState" in argv:
            return subprocess.CompletedProcess(argv, 0, f"{self.load_state}\n", "")
        if "show" in argv and "MainPID" in argv:
            return subprocess.CompletedProcess(argv, 0, f"{self.main_pid or 0}\n", "")
        if argv[-1:] == ["hutch.service"] and "is-active" in argv:
            return subprocess.CompletedProcess(argv, 0, f"{self.active_state}\n", "")
        return subprocess.CompletedProcess(argv, 0, "", "")


def ready_probe(port=8787, **kwargs):
    return service.ServiceProbe(True, True, "ready", {"id": instance_id(kwargs.get("state_dir") or "/tmp/x"),
                                                      "pid": kwargs.get("expected_pid") or 4242})


# ------------------------------------------------------------------- unit file

def test_service_unit_starts_only_the_local_dashboard_with_private_defaults(tmp_path):
    unit = service.render_user_unit("/opt/Hutch Env/bin/python", tmp_path / "state", port=18888)

    assert ('ExecStart="/opt/Hutch Env/bin/python" "-m" "hutch.cli" "serve" "--host" '
            '"127.0.0.1" "--port" "18888"') in unit
    assert f'Environment=HUTCH_STATE_DIR="{tmp_path / "state"}"' in unit
    assert "Environment=HUTCH_EXECUTOR=process" in unit
    assert "Restart=on-failure" in unit
    assert "NoNewPrivileges=yes" in unit
    assert "UMask=0077" in unit
    assert "--allow-remote" not in unit and "HUTCH_REMOTE_ENABLED" not in unit


def test_systemd_arguments_escape_specifiers_and_shell_metacharacters(tmp_path):
    unit = service.render_user_unit('/opt/100%/$HOME" Hutch/python', tmp_path / "a $ b", port=8787)

    assert '"/opt/100%%/$$HOME\\\" Hutch/python"' in unit
    state_value = str(tmp_path / "a $ b").replace("$", "$")
    assert f'Environment=HUTCH_STATE_DIR="{state_value}"' in unit


def test_service_unit_rejects_invalid_ports_and_multiline_paths(tmp_path):
    with pytest.raises(service.ServiceError, match="port must be"):
        service.render_user_unit("/usr/bin/python3", tmp_path, port=0)
    with pytest.raises(service.ServiceError, match="control characters"):
        service.render_user_unit("/usr/bin/python3\nExecStart=/tmp/evil", tmp_path)


# --------------------------------------------------------------------- install

def test_install_writes_managed_unit_then_reloads_enables_and_starts(tmp_path):
    config_home = tmp_path / "config"
    state_dir = tmp_path / "state"
    runner = FakeSystemd()

    installed = service.install_user_service(
        state_dir, config_home=config_home, python_executable="/usr/bin/python3",
        systemctl_bin="/usr/bin/systemctl", systemctl_runner=runner, probe=ready_probe,
    )

    assert installed.path == config_home / "systemd/user/hutch.service"
    assert installed.started is True and installed.ready is True
    assert installed.path.read_text().startswith(service.MANAGED_MARKER)
    assert stat.S_IMODE(installed.path.stat().st_mode) == 0o644
    assert runner.calls[0][-1:] == ["daemon-reload"]
    assert runner.calls[1][-3:] == ["enable", "--now", "hutch.service"]
    assert runner.calls[2][-2:] == ["is-active", "hutch.service"]
    assert not state_dir.exists(), "installing the service must not create or alter Hutch data"


def test_install_completes_only_after_the_readiness_handshake(tmp_path):
    state_dir = tmp_path / "state"
    seen: dict = {}

    def probe(port, *, state_dir=None, expected_pid=None, timeout=2.0):
        seen.update(port=port, state_dir=state_dir, expected_pid=expected_pid)
        return service.ServiceProbe(True, True, "ready", {"id": instance_id(state_dir), "pid": 4242})

    installed = service.install_user_service(
        state_dir, config_home=tmp_path / "config", python_executable="/usr/bin/python3", port=18899,
        systemctl_bin="/usr/bin/systemctl", systemctl_runner=FakeSystemd(main_pid=4242), probe=probe,
    )

    assert installed.ready is True
    assert seen["port"] == 18899
    assert seen["state_dir"] == state_dir.absolute()
    assert seen["expected_pid"] == 4242, "readiness must bind to the unit's main PID, not any listener"


def test_install_reports_active_but_not_ready_instead_of_claiming_success(tmp_path):
    def never_ready(port, **kwargs):
        return service.ServiceProbe(True, False, "port is answered by a different Hutch instance")

    with pytest.raises(service.ServiceError, match="readiness check did not confirm"):
        service.install_user_service(
            tmp_path / "state", config_home=tmp_path / "config", python_executable="/usr/bin/python3",
            systemctl_bin="/usr/bin/systemctl", systemctl_runner=FakeSystemd(), probe=never_ready,
            ready_timeout=0.0,
        )
    assert (tmp_path / "config/systemd/user/hutch.service").is_file(), "the unit is left in place, not rolled back"


def test_install_is_idempotent_but_refuses_to_overwrite_a_user_unit(tmp_path):
    config_home = tmp_path / "config"
    state_dir = tmp_path / "state"
    runner = FakeSystemd()
    kwargs = dict(config_home=config_home, python_executable="/usr/bin/python3",
                  systemctl_bin="/usr/bin/systemctl", systemctl_runner=runner, probe=ready_probe)

    first = service.install_user_service(state_dir, **kwargs)
    second = service.install_user_service(state_dir, **kwargs)
    assert second.path.read_text() == first.path.read_text()

    first.path.write_text("[Service]\nExecStart=/home/user/custom-command\n")
    with pytest.raises(service.ServiceError, match="already exists and is not an unchanged Hutch unit"):
        service.install_user_service(state_dir, **kwargs)
    assert first.path.read_text() == "[Service]\nExecStart=/home/user/custom-command\n"


def test_install_refuses_a_symlink_at_the_unit_path(tmp_path):
    config_home = tmp_path / "config"
    unit_dir = config_home / "systemd/user"
    unit_dir.mkdir(parents=True)
    target = tmp_path / "keep.txt"
    target.write_text("keep")
    (unit_dir / "hutch.service").symlink_to(target)

    with pytest.raises(service.ServiceError, match="symbolic link"):
        service.install_user_service(tmp_path / "state", config_home=config_home,
                                     systemctl_bin="/usr/bin/systemctl", systemctl_runner=FakeSystemd())
    assert target.read_text() == "keep"


def test_install_reports_activation_failure_without_claiming_it_started(tmp_path):
    runner = FakeSystemd(fail_on=("enable", "--now", "hutch.service"))

    with pytest.raises(service.ServiceError, match="unit file was written but could not be confirmed running"):
        service.install_user_service(tmp_path / "state", config_home=tmp_path / "config",
                                     systemctl_bin="/usr/bin/systemctl", systemctl_runner=runner)
    assert (tmp_path / "config/systemd/user/hutch.service").is_file()


# ---------------------------------------------------------------------- status

def test_status_reports_the_active_service_port_and_readiness_separately(tmp_path):
    service.install_user_service(tmp_path / "state", config_home=tmp_path / "config", port=18888,
                                 systemctl_bin="/usr/bin/systemctl", systemctl_runner=FakeSystemd(),
                                 probe=ready_probe)

    status = service.user_service_status(config_home=tmp_path / "config", state_dir=tmp_path / "state",
                                         systemctl_bin="/usr/bin/systemctl", systemctl_runner=FakeSystemd(),
                                         probe=True, probe_runner=ready_probe)

    assert status.active and status.installed and status.port == 18888
    assert status.ready is True


def test_status_distinguishes_inactive_failed_and_not_installed(tmp_path):
    def status_for(load_state, active_state):
        return service.user_service_status(config_home=tmp_path / "config",
                                           systemctl_bin="/usr/bin/systemctl",
                                           systemctl_runner=FakeSystemd(load_state=load_state,
                                                                        active_state=active_state))

    inactive = status_for("loaded", "inactive")
    assert inactive.installed and not inactive.active and inactive.state == "inactive"

    failed = status_for("loaded", "failed")
    assert failed.installed and not failed.active and failed.state == "failed"

    missing = status_for("not-found", "inactive")
    assert not missing.installed and not missing.active and missing.state == "not installed"


def test_status_never_claims_readiness_from_process_state_alone(tmp_path):
    service.install_user_service(tmp_path / "state", config_home=tmp_path / "config", port=18888,
                                 systemctl_bin="/usr/bin/systemctl", systemctl_runner=FakeSystemd(),
                                 probe=ready_probe)

    def unreachable(port, **kwargs):
        return service.ServiceProbe(False, False, "no Hutch answered on 127.0.0.1:18888")

    status = service.user_service_status(config_home=tmp_path / "config", state_dir=tmp_path / "state",
                                         systemctl_bin="/usr/bin/systemctl", systemctl_runner=FakeSystemd(),
                                         probe=True, probe_runner=unreachable)

    assert status.active is True and status.ready is False
    assert "no Hutch answered" in status.detail


def test_status_reports_linger_state_and_never_enables_it(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    runner = FakeSystemd()
    status = service.user_service_status(
        config_home=tmp_path / "config", systemctl_bin="/usr/bin/systemctl", systemctl_runner=runner)

    assert status.linger in ("enabled", "disabled", "unavailable", "unknown")
    assert not any("enable-linger" in " ".join(call) for call in runner.calls), \
        "reading status must never change login semantics"


# --------------------------------------------------------------------- restart

def test_restart_calls_systemd_restart_then_confirms_active(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    service.install_user_service(tmp_path / "state", config_home=tmp_path / "config",
                                 systemctl_bin="/usr/bin/systemctl", systemctl_runner=FakeSystemd(),
                                 probe=ready_probe)
    runner = FakeSystemd()

    service.restart_user_service(systemctl_bin="/usr/bin/systemctl", systemctl_runner=runner)

    assert runner.calls[0][-2:] == ["restart", "hutch.service"]
    assert runner.calls[1][-2:] == ["is-active", "hutch.service"]


def test_restart_refuses_when_the_unit_is_not_installed(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))

    with pytest.raises(service.ServiceError, match="not installed"):
        service.restart_user_service(systemctl_bin="/usr/bin/systemctl", systemctl_runner=FakeSystemd())


# --------------------------------------------------------------------- linger

def test_linger_state_parses_loginctl_output():
    def runner_yes(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 0, "Linger=yes\n", "")

    def runner_no(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 0, "Linger=no\n", "")

    def runner_fail(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 1, "", "no such user")

    if __import__("sys").platform != "linux":
        pytest.skip("linger is reported on Linux only")
    assert service.linger_state(loginctl_bin="/usr/bin/loginctl", systemctl_runner=runner_yes, user="x") == "enabled"
    assert service.linger_state(loginctl_bin="/usr/bin/loginctl", systemctl_runner=runner_no, user="x") == "disabled"
    assert service.linger_state(loginctl_bin="/usr/bin/loginctl", systemctl_runner=runner_fail, user="x") == "unavailable"


# ------------------------------------------------------------------ uninstall

def test_uninstall_stops_unit_and_removes_only_service_file(tmp_path):
    config_home = tmp_path / "config"
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    marker = state_dir / "preserve.txt"
    marker.write_text("user data")
    runner = FakeSystemd()
    installed = service.install_user_service(
        state_dir, config_home=config_home, systemctl_bin="/usr/bin/systemctl", systemctl_runner=runner,
        probe=ready_probe,
    )

    removed = service.remove_user_service(config_home=config_home, systemctl_bin="/usr/bin/systemctl",
                                          systemctl_runner=runner)

    assert removed is True
    assert not installed.path.exists()
    assert marker.read_text() == "user data"
    assert runner.calls[-2][-3:] == ["disable", "--now", "hutch.service"]
    assert runner.calls[-1][-1:] == ["daemon-reload"]


def test_uninstall_refuses_an_unmanaged_unit(tmp_path):
    unit_dir = tmp_path / "config/systemd/user"
    unit_dir.mkdir(parents=True)
    unit = unit_dir / "hutch.service"
    unit.write_text("[Service]\nExecStart=/home/user/custom-command\n")

    with pytest.raises(service.ServiceError, match="not marked as managed by Hutch"):
        service.remove_user_service(config_home=tmp_path / "config", systemctl_bin="/usr/bin/systemctl",
                                    systemctl_runner=FakeSystemd())
    assert unit.is_file()
    assert not Path(str(tmp_path / "state")).exists()


def test_service_cli_exposes_install_remove_status_and_restart():
    result = CliRunner().invoke(app, ["service", "--help"])

    assert result.exit_code == 0
    assert all(word in result.output for word in ("install", "uninstall", "status", "restart"))


# ------------------------------------------------------- real HTTP handshake

@pytest.fixture()
def live_engine(tmp_path, monkeypatch):
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    from hutch.server.app import create_app

    application = create_app()
    server = uvicorn.Server(uvicorn.Config(application, host="127.0.0.1", port=0, log_level="error",
                                           lifespan="on"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while not server.started and time.time() < deadline:
        time.sleep(0.02)
    port = server.servers[0].sockets[0].getsockname()[1]
    yield port, tmp_path / "state"
    server.should_exit = True
    thread.join(timeout=10)


def test_readiness_probe_accepts_the_real_engine_and_rejects_another_instance(live_engine):
    port, state_dir = live_engine

    good = service.readiness_probe(port, state_dir=state_dir, timeout=5.0)
    assert good.ready, good.detail
    assert good.instance and good.instance["id"] == instance_id(state_dir)

    wrong = service.readiness_probe(port, state_dir=state_dir / "somewhere-else", timeout=5.0)
    assert not wrong.ready
    assert "different Hutch instance" in wrong.detail


def test_readiness_probe_rejects_a_wrong_main_pid(live_engine):
    port, state_dir = live_engine

    wrong_pid = service.readiness_probe(port, state_dir=state_dir, expected_pid=999_999_999, timeout=5.0)
    assert not wrong_pid.ready
    assert "main PID" in wrong_pid.detail


def test_wait_for_ready_times_out_honestly_on_a_dead_port():
    result = service.wait_for_ready(1, state_dir="/tmp/nowhere", timeout=0.3, interval=0.05)

    assert not result.ready and not result.reachable
    assert "no Hutch answered" in result.detail


def test_health_exposes_instance_identity_and_scheduler_role(live_engine):
    import httpx

    port, state_dir = live_engine
    body = httpx.get(f"http://127.0.0.1:{port}/api/health", timeout=5).json()

    assert body["status"] == "ok"
    assert body["instance"]["id"] == instance_id(state_dir)
    assert body["instance"]["pid"] > 0
    assert body["scheduler"]["role"] in ("supervisor", "follower")
    assert "state_dir" not in json.dumps(body), "the public health body must not leak local paths"
