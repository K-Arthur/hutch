from __future__ import annotations

import stat
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from hutch import service
from hutch.cli import app


class FakeSystemd:
    def __init__(self, *, fail_on: tuple[str, ...] | None = None):
        self.calls: list[list[str]] = []
        self.fail_on = fail_on

    def __call__(self, argv, **kwargs):
        self.calls.append(list(argv))
        if self.fail_on and tuple(argv[-len(self.fail_on):]) == self.fail_on:
            return subprocess.CompletedProcess(argv, 1, "", "unit failed")
        if "show" in argv:
            return subprocess.CompletedProcess(argv, 0, "loaded\n", "")
        if argv[-1:] == ["hutch.service"] and "is-active" in argv:
            return subprocess.CompletedProcess(argv, 0, "active\n", "")
        return subprocess.CompletedProcess(argv, 0, "", "")


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


def test_install_writes_managed_unit_then_reloads_enables_and_starts(tmp_path):
    config_home = tmp_path / "config"
    state_dir = tmp_path / "state"
    runner = FakeSystemd()

    installed = service.install_user_service(
        state_dir, config_home=config_home, python_executable="/usr/bin/python3",
        systemctl_bin="/usr/bin/systemctl", systemctl_runner=runner,
    )

    assert installed.path == config_home / "systemd/user/hutch.service"
    assert installed.started is True
    assert installed.path.read_text().startswith(service.MANAGED_MARKER)
    assert stat.S_IMODE(installed.path.stat().st_mode) == 0o644
    assert runner.calls[0][-1:] == ["daemon-reload"]
    assert runner.calls[1][-3:] == ["enable", "--now", "hutch.service"]
    assert runner.calls[2][-2:] == ["is-active", "hutch.service"]
    assert not state_dir.exists(), "installing the service must not create or alter Hutch data"


def test_install_is_idempotent_but_refuses_to_overwrite_a_user_unit(tmp_path):
    config_home = tmp_path / "config"
    state_dir = tmp_path / "state"
    runner = FakeSystemd()
    kwargs = dict(config_home=config_home, python_executable="/usr/bin/python3",
                  systemctl_bin="/usr/bin/systemctl", systemctl_runner=runner)

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


def test_uninstall_stops_unit_and_removes_only_service_file(tmp_path):
    config_home = tmp_path / "config"
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    marker = state_dir / "preserve.txt"
    marker.write_text("user data")
    runner = FakeSystemd()
    installed = service.install_user_service(
        state_dir, config_home=config_home, systemctl_bin="/usr/bin/systemctl", systemctl_runner=runner,
    )

    removed = service.remove_user_service(config_home=config_home, systemctl_bin="/usr/bin/systemctl",
                                          systemctl_runner=runner)

    assert removed is True
    assert not installed.path.exists()
    assert marker.read_text() == "user data"
    assert runner.calls[-2][-3:] == ["disable", "--now", "hutch.service"]
    assert runner.calls[-1][-1:] == ["daemon-reload"]


def test_status_reports_the_active_service_port_without_claiming_http_readiness(tmp_path):
    service.install_user_service(tmp_path / "state", config_home=tmp_path / "config", port=18888,
                                 systemctl_bin="/usr/bin/systemctl", systemctl_runner=FakeSystemd())

    status = service.user_service_status(config_home=tmp_path / "config",
                                         systemctl_bin="/usr/bin/systemctl", systemctl_runner=FakeSystemd())

    assert status.active and status.installed and status.port == 18888


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


def test_service_cli_exposes_install_remove_and_status():
    result = CliRunner().invoke(app, ["service", "--help"])

    assert result.exit_code == 0
    assert all(word in result.output for word in ("install", "uninstall", "status"))
