"""Host readiness probing: independent capabilities, explicit consent states, and read-only behaviour."""

from __future__ import annotations

import json

import pytest

from hutch.computer.doctor import (DEGRADED, NEEDS_CONSENT, READY, UNAVAILABLE, UNKNOWN, probe_computer_use, summary)

KDE_BUS = """NAME                                   PID PROCESS         USER    CONNECTION
:1.4                                  1 systemd         me      :1.4
org.freedesktop.portal.Desktop      100 xdg-desktop-por me      :1.9
org.freedesktop.impl.portal.desktop.kde 101 portal-kde  me      :1.10
org.kde.KWin                        200 kwin_wayland    me      :1.12
org.a11y.Bus                        300 at-spi-bus-lau  me      :1.13
"""
LIBS = "\tlibpipewire-0.3.so.0 (libc6,x86-64) => /usr/lib/libpipewire-0.3.so.0\n\tlibei.so.1 (libc6) => /usr/lib/libei.so.1\n"


def fake_run(props=None, bus=KDE_BUS, log=None):
    props = {"ScreenCast.version": "u 5", "ScreenCast.AvailableSourceTypes": "u 3",
             "RemoteDesktop.version": "u 2", "RemoteDesktop.AvailableDeviceTypes": "u 3"} if props is None else props

    def run(argv):
        if log is not None:
            log.append(list(argv))
        if argv[:3] == ["busctl", "--user", "list"]:
            return 0, bus
        if argv[:3] == ["busctl", "--user", "get-property"]:
            interface = argv[5].rsplit(".", 1)[-1]
            key = f"{interface}.{argv[6]}"
            return (0, f"u {props[key].split()[-1]}\n") if key in props else (1, "")
        if argv[:2] == ["ldconfig", "-p"]:
            return 0, LIBS
        return 127, ""
    return run


def probe(env=None, *, props=None, bus=KDE_BUS, tools=("busctl", "ldconfig", "wl-copy", "kwin_wayland"), modules=(),
          paths=("/run/user/1000/wayland-0", "/run/user/1000/pipewire-0"), log=None):
    environment = {"XDG_SESSION_TYPE": "wayland", "WAYLAND_DISPLAY": "wayland-0", "DISPLAY": ":0",
                   "XDG_RUNTIME_DIR": "/run/user/1000", "XDG_CURRENT_DESKTOP": "KDE"} if env is None else env
    results = probe_computer_use(
        env=environment, run=fake_run(props, bus, log), which=lambda t: f"/usr/bin/{t}" if t in tools else None,
        exists=lambda p: p in paths or str(p).endswith("chrome"), libraries=lambda: LIBS,
        has_module=lambda m: m in modules)
    return {c.id: c for c in results}


def test_kde_wayland_reports_each_capability_independently():
    got = probe(modules=("playwright",))
    assert got["session"].state == READY and "XWayland" in got["session"].detail
    assert got["compositor"].detail.startswith("KWin")
    assert got["portal"].state == READY
    assert got["screencast"].state == NEEDS_CONSENT and "monitor, window" in got["screencast"].detail
    assert got["remotedesktop"].state == NEEDS_CONSENT and "ConnectToEIS" in got["remotedesktop"].detail
    assert "separate grants" in got["remotedesktop"].detail
    assert got["pipewire"].state == READY and got["libei"].state == READY
    assert got["accessibility"].state == DEGRADED and "gi" in got["accessibility"].detail
    assert got["accessibility"].fix, "a degraded capability must say what to do"


def test_capture_without_input_is_not_reported_as_control():
    props = {"ScreenCast.version": "u 5", "ScreenCast.AvailableSourceTypes": "u 3"}      # no RemoteDesktop portal
    got = probe(props=props)
    assert got["screencast"].state == NEEDS_CONSENT
    assert got["remotedesktop"].state == UNAVAILABLE
    assert summary(list(got.values()))["native_desktop"] == "unavailable"


def test_xwayland_only_is_not_native_wayland():
    env = {"XDG_SESSION_TYPE": "wayland", "DISPLAY": ":0", "XDG_RUNTIME_DIR": "/run/user/1000"}
    got = probe(env)
    assert got["session"].state == DEGRADED and "native Wayland windows are not" in got["session"].detail


def test_plain_x11_is_degraded_and_headless_is_unavailable():
    assert probe({"XDG_SESSION_TYPE": "x11", "DISPLAY": ":1"})["session"].state == DEGRADED
    none = probe({})
    assert none["session"].state == UNAVAILABLE and "isolated" in none["session"].fix.lower()


def test_missing_portal_service_and_backend():
    assert probe(bus="NAME PID\n:1.1 1 x\n")["portal"].state == UNAVAILABLE
    only_frontend = "NAME PID\norg.freedesktop.portal.Desktop 1 x u :1.2\n"
    assert probe(bus=only_frontend)["portal"].state == DEGRADED


def test_accessibility_ready_only_with_bus_and_bindings():
    assert probe(modules=("gi",))["accessibility"].state == READY
    no_bus = "NAME PID\norg.freedesktop.portal.Desktop 1 x u :1.2\n"
    assert probe(bus=no_bus, modules=("gi",))["accessibility"].state == UNAVAILABLE


def test_probing_runs_only_read_only_commands():
    """No capture, input, portal session or dialog may be triggered by a probe."""
    log: list[list[str]] = []
    probe(log=log, modules=("playwright",))
    allowed_prefixes = (["busctl", "--user", "list"], ["busctl", "--user", "get-property"], ["ldconfig", "-p"])
    for argv in log:
        assert any(argv[:len(prefix)] == prefix for prefix in allowed_prefixes), argv
    flat = " ".join(" ".join(argv) for argv in log).lower()
    for forbidden in ("createsession", "start", "notify", "screenshot", "xdotool", "ydotool", "wtype", "spectacle"):
        assert forbidden not in flat


def test_a_crashing_probe_is_reported_not_raised():
    def boom(argv):
        raise RuntimeError("bus exploded")
    results = probe_computer_use(env={"XDG_RUNTIME_DIR": "/x"}, run=boom, which=lambda t: "/usr/bin/" + t,
                                 exists=lambda p: False, libraries=lambda: "", has_module=lambda m: False)
    assert len(results) >= 10, "one failing probe must not hide the others"
    errors = [c for c in results if c.id == "probe_error"]
    assert errors and all("bus exploded" in c.detail for c in errors)
    assert {c.id for c in results} >= {"session", "pipewire", "libei", "clipboard"}   # probes that need no bus still ran


def test_cli_prints_json(tmp_path, monkeypatch):
    from typer.testing import CliRunner
    from hutch.cli import app
    monkeypatch.setenv("HUTCH_STATE_DIR", str(tmp_path / "state"))
    result = CliRunner().invoke(app, ["computer", "doctor", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert {c["id"] for c in payload["capabilities"]} >= {"session", "portal", "screencast", "remotedesktop",
                                                           "accessibility", "browser_engine"}
    assert payload["summary"]["note"]


def test_api_exposes_the_same_probe(config):
    from fastapi.testclient import TestClient
    from hutch.server.app import create_app
    client = TestClient(create_app())
    response = client.get("/api/v1/computer/readiness")
    assert response.status_code == 200
    body = response.json()
    assert body["capabilities"] and all({"id", "state", "detail"} <= set(c) for c in body["capabilities"])
    assert body["summary"]["native_desktop"] in ("needs_consent", "unavailable")
