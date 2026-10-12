"""Computer-use readiness: what this host can actually do, one independent capability at a time.

Every probe is read-only and harmless: it reads environment variables, looks for sockets and libraries, and reads D-Bus
*properties* of services that are already running. Nothing here captures the screen, sends input, opens a portal session,
or triggers a consent dialog, so a probe can never act on a person's desktop. Where a capability can only be proven by a
consent-gated action, the state is ``needs_consent`` (not ``ready``): package presence is not capability, and a successful
capture says nothing about input (they are separate portals and separate grants).

Every result names the evidence it rests on and the human step that would change it.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

READY, DEGRADED, NEEDS_CONSENT, UNAVAILABLE, UNKNOWN = "ready", "degraded", "needs_consent", "unavailable", "unknown"

Runner = Callable[[list[str]], tuple[int, str]]


@dataclass
class Capability:
    id: str
    title: str
    state: str
    detail: str
    fix: str = ""
    evidence: str = ""

    def public(self) -> dict[str, Any]:
        return asdict(self)


def _default_runner(argv: list[str]) -> tuple[int, str]:
    try:
        done = subprocess.run(argv, capture_output=True, text=True, timeout=4, check=False)
        return done.returncode, (done.stdout or "") + (done.stderr or "")
    except (OSError, subprocess.SubprocessError):
        return 127, ""


class _Host:
    """The facts a probe may read, injectable so every branch is testable without the real desktop."""

    def __init__(self, env: Optional[Mapping[str, str]] = None, run: Optional[Runner] = None,
                 which: Optional[Callable[[str], Optional[str]]] = None,
                 exists: Optional[Callable[[str], bool]] = None, libraries: Optional[Callable[[], str]] = None,
                 has_module: Optional[Callable[[str], bool]] = None):
        self.env = dict(os.environ if env is None else env)
        self.run = run or _default_runner
        self.which = which or shutil.which
        self.exists = exists or (lambda p: Path(p).exists())
        self._libraries = libraries
        self.has_module = has_module or (lambda name: importlib.util.find_spec(name) is not None)
        self._bus_names: Optional[set[str]] = None
        self._lib_text: Optional[str] = None

    @property
    def runtime_dir(self) -> str:
        return self.env.get("XDG_RUNTIME_DIR", "")

    def bus_names(self) -> set[str]:
        if self._bus_names is None:
            code, out = self.run(["busctl", "--user", "list", "--no-pager"]) if self.which("busctl") else (127, "")
            names: set[str] = set()
            if code == 0:
                for line in out.splitlines()[1:]:
                    parts = line.split()
                    if parts and not parts[0].startswith(":"):
                        names.add(parts[0])
            self._bus_names = names
        return self._bus_names

    def library(self, stem: str) -> bool:
        if self._lib_text is None:
            if self._libraries is not None:
                self._lib_text = self._libraries()
            else:
                code, out = self.run(["ldconfig", "-p"]) if self.which("ldconfig") else (127, "")
                self._lib_text = out if code == 0 else ""
        return any(line.strip().startswith(stem) for line in self._lib_text.splitlines())

    def portal_property(self, interface: str, prop: str) -> Optional[str]:
        if not self.which("busctl"):
            return None
        code, out = self.run(["busctl", "--user", "get-property", "org.freedesktop.portal.Desktop",
                              "/org/freedesktop/portal/desktop", f"org.freedesktop.portal.{interface}", prop])
        if code != 0:
            return None
        parts = out.strip().split()
        return parts[-1] if parts else None


# ------------------------------------------------------------------ probes


def _session(h: _Host) -> Capability:
    kind = h.env.get("XDG_SESSION_TYPE", "").lower()
    wayland = h.env.get("WAYLAND_DISPLAY", "")
    x11 = h.env.get("DISPLAY", "")
    desktop = h.env.get("XDG_CURRENT_DESKTOP", "") or "unknown desktop"
    wayland_socket = bool(wayland and h.runtime_dir and h.exists(os.path.join(h.runtime_dir, wayland)))
    if wayland and (wayland_socket or kind == "wayland"):
        extra = (f" XWayland is also available ({x11}); X11-only tools see only X11 windows, never native Wayland ones."
                 if x11 else "")
        return Capability("session", "Display session", READY,
                          f"Native Wayland session ({wayland}) on {desktop}.{extra}",
                          evidence=f"XDG_SESSION_TYPE={kind or '?'} WAYLAND_DISPLAY={wayland} socket={wayland_socket}")
    if x11 and kind != "wayland":
        return Capability("session", "Display session", DEGRADED,
                          f"X11 session ({x11}) on {desktop}. X11 gives any client broad capture and input access; it "
                          "is not app-scoped.", "Prefer an isolated display (Xvfb/virtual compositor) for automation.",
                          evidence=f"DISPLAY={x11}")
    if x11:
        return Capability("session", "Display session", DEGRADED,
                          f"Only XWayland ({x11}) is reachable from this process; native Wayland windows are not.",
                          "Run Hutch inside the graphical session so WAYLAND_DISPLAY and XDG_RUNTIME_DIR are set.",
                          evidence=f"DISPLAY={x11} WAYLAND_DISPLAY unset")
    return Capability("session", "Display session", UNAVAILABLE, "No graphical session is reachable from this process.",
                      "Start Hutch from the desktop session (or set up an isolated virtual display).",
                      evidence="no WAYLAND_DISPLAY or DISPLAY")


def _compositor(h: _Host) -> Capability:
    names = h.bus_names()
    found = ""
    if "org.kde.KWin" in names:
        found = "KWin (KDE Plasma)"
    elif any(n.startswith("org.gnome.Mutter") for n in names) or "org.gnome.Shell" in names:
        found = "Mutter (GNOME Shell)"
    elif h.env.get("SWAYSOCK"):
        found = "sway"
    elif h.env.get("HYPRLAND_INSTANCE_SIGNATURE"):
        found = "Hyprland"
    if not found:
        return Capability("compositor", "Compositor", UNKNOWN,
                          "The compositor could not be identified from the session bus or environment.",
                          "Hutch will not guess. Existing-desktop portal control is not implemented; isolated sessions require KWin.",
                          evidence="no org.kde.KWin / org.gnome.Mutter / SWAYSOCK / HYPRLAND_INSTANCE_SIGNATURE")
    return Capability("compositor", "Compositor", READY, f"{found}.", evidence="session bus names / environment")


def _portal(h: _Host) -> Capability:
    names = h.bus_names()
    if "org.freedesktop.portal.Desktop" not in names:
        return Capability("portal", "Desktop portal service", UNAVAILABLE,
                          "xdg-desktop-portal is not running on the session bus.",
                          "Install and start xdg-desktop-portal and your desktop's backend "
                          "(for KDE: xdg-desktop-portal-kde).", evidence="org.freedesktop.portal.Desktop absent")
    backends = sorted(n.rsplit(".", 1)[-1] for n in names if n.startswith("org.freedesktop.impl.portal.desktop."))
    if not backends:
        return Capability("portal", "Desktop portal service", DEGRADED,
                          "xdg-desktop-portal is running but no desktop backend was found, so capture and input will "
                          "have nothing to answer them.", "Install your desktop's portal backend.",
                          evidence="no org.freedesktop.impl.portal.desktop.*")
    return Capability("portal", "Desktop portal service", READY, f"Running with backend(s): {', '.join(backends)}.",
                      evidence="org.freedesktop.portal.Desktop + impl.portal.desktop.*")


def _screencast(h: _Host) -> Capability:
    version = h.portal_property("ScreenCast", "version")
    if version is None:
        return Capability("screencast", "Screen capture (ScreenCast portal)", UNAVAILABLE,
                          "The ScreenCast portal interface is not available.",
                          "Install a portal backend that implements ScreenCast.",
                          evidence="busctl get-property ScreenCast version failed")
    sources = h.portal_property("ScreenCast", "AvailableSourceTypes") or "?"
    mask = int(sources) if sources.isdigit() else 0
    kinds = [name for bit, name in ((1, "monitor"), (2, "window"), (4, "virtual")) if mask & bit]
    return Capability("screencast", "Screen capture (ScreenCast portal)", NEEDS_CONSENT,
                      f"Host interface v{version}; source types: {', '.join(kinds) or 'unknown'}. A portal client needs "
                      "an OS share grant. Hutch's existing-desktop portal adapter is not implemented.",
                      "Use the reviewed isolated KWin mode; this discovery does not test capture.",
                      evidence=f"ScreenCast version={version} AvailableSourceTypes={sources}")


def _remotedesktop(h: _Host) -> Capability:
    version = h.portal_property("RemoteDesktop", "version")
    if version is None:
        return Capability("remotedesktop", "Input injection (RemoteDesktop portal)", UNAVAILABLE,
                          "The host RemoteDesktop interface is absent. Hutch uses private KWin EIS for its isolated mode.",
                          "Existing-desktop portal control is not implemented.",
                          evidence="busctl get-property RemoteDesktop version failed")
    devices = h.portal_property("RemoteDesktop", "AvailableDeviceTypes") or "?"
    mask = int(devices) if devices.isdigit() else 0
    kinds = [name for bit, name in ((1, "keyboard"), (2, "pointer"), (4, "touchscreen")) if mask & bit]
    eis = "ConnectToEIS available" if version.isdigit() and int(version) >= 2 else "no ConnectToEIS (portal v1)"
    return Capability("remotedesktop", "Input injection (RemoteDesktop portal)", NEEDS_CONSENT,
                      f"Interface v{version} ({eis}); devices: {', '.join(kinds) or 'unknown'}. Input is seat-wide: "
                      "approving it is not scoped to one window. Capture and input are separate grants.",
                      "Host discovery only: Hutch has no existing-desktop portal input adapter.",
                      evidence=f"RemoteDesktop version={version} AvailableDeviceTypes={devices}")


def _pipewire(h: _Host) -> Capability:
    socket_path = os.path.join(h.runtime_dir, "pipewire-0") if h.runtime_dir else ""
    has_socket = bool(socket_path and h.exists(socket_path))
    has_lib = h.library("libpipewire-0.3.so")
    if has_socket and has_lib:
        return Capability("pipewire", "PipeWire", READY, "Daemon socket present and libpipewire installed.",
                          evidence=f"{socket_path} + libpipewire-0.3")
    if has_socket:
        return Capability("pipewire", "PipeWire", DEGRADED, "The daemon is running but libpipewire was not found.",
                          "Install libpipewire so a capture stream can be opened.", evidence=socket_path)
    return Capability("pipewire", "PipeWire", UNAVAILABLE,
                      "No PipeWire socket; portal screen capture cannot deliver frames.",
                      "Install and start pipewire and wireplumber.", evidence="no pipewire-0 socket")


def _libei(h: _Host) -> Capability:
    sockets = []
    if h.runtime_dir:
        try:
            sockets = [n for n in os.listdir(h.runtime_dir) if "eis" in n and not n.endswith(".lock")]
        except OSError:
            sockets = []
    if h.library("libei.so"):
        extra = f" A compositor EIS socket is present ({sockets[0]})." if sockets else ""
        return Capability("libei", "libei (emulated input)", READY,
                          "libei is installed. Hutch obtains EIS from its private KWin session; input still needs a delivered-action test." + extra,
                          evidence="ldconfig libei.so")
    return Capability("libei", "libei (emulated input)", UNAVAILABLE, "libei is not installed.",
                      "Install libei for the isolated KWin EIS input adapter.",
                      evidence="ldconfig libei.so absent")


def _accessibility(h: _Host) -> Capability:
    bus = "org.a11y.Bus" in h.bus_names()
    bindings = h.has_module("gi")
    if bus and bindings:
        return Capability("accessibility", "Accessibility tree (AT-SPI)", DEGRADED,
                          "The host accessibility bus and bindings are present. Hutch has no native AT-SPI action adapter, "
                          "and does not mount the host accessibility bus into its isolated apps.",
                          evidence="org.a11y.Bus + import gi")
    if bus:
        return Capability("accessibility", "Accessibility tree (AT-SPI)", DEGRADED,
                          "The accessibility bus is running, but this Python environment has no GObject bindings (gi).",
                          "Install python-gobject (and gir1.2-atspi / at-spi2-core typelibs) for Hutch's interpreter, "
                          "or run the accessibility adapter out of process.", evidence="org.a11y.Bus; import gi failed")
    return Capability("accessibility", "Accessibility tree (AT-SPI)", UNAVAILABLE,
                      "The accessibility bus is not running; applications may not expose their UI tree.",
                      "Enable assistive technologies in the desktop settings (or start at-spi-bus-launcher).",
                      evidence="org.a11y.Bus absent")


def _clipboard(h: _Host) -> Capability:
    tools = [t for t in ("wl-copy", "wl-paste", "xclip", "xsel") if h.which(t)]
    if tools:
        return Capability("clipboard", "Clipboard", UNAVAILABLE,
                          f"Host tools found: {', '.join(tools)}. Hutch does not expose clipboard read/write or mount "
                          "the personal clipboard into its private session.", evidence="PATH lookup; adapter absent")
    return Capability("clipboard", "Clipboard", UNAVAILABLE, "No clipboard command-line tool found.",
                      "Clipboard transfer is unsupported; use reviewed workspace files.",
                      evidence="PATH lookup")


def _input_tools(h: _Host) -> Capability:
    tools = [t for t in ("wtype", "ydotool", "xdotool", "dotool") if h.which(t)]
    if not tools:
        return Capability("input_tools", "Third-party input tools", UNKNOWN,
                          "None installed. Hutch uses the private KWin EIS channel after session review, "
                          "never a privileged input daemon.",
                          evidence="PATH lookup")
    return Capability("input_tools", "Third-party input tools", UNKNOWN,
                      f"Found: {', '.join(tools)}. Hutch does not use these; some (ydotool) need an elevated input "
                      "daemon that bypasses compositor consent, and xdotool reaches only X11 windows.",
                      evidence="PATH lookup")


def _isolated_compositor(h: _Host) -> Capability:
    required = ("kwin_wayland", "dbus-daemon", "busctl", "spectacle", "bwrap", "systemd-run", "prlimit")
    missing = [tool for tool in required if not h.which(tool)]
    if not missing and h.library("libei.so"):
        return Capability("isolated_compositor", "Isolated KWin prerequisites", NEEDS_CONSENT,
                          "KWin virtual/capture/containment tools and libei are present. Package presence is not a "
                          "capture or input test; a reviewed run checks its private display and EIS separately.",
                          "Enable computer applications and review a new session. A PyGObject interpreter, usable user "
                          "namespaces and the user service manager are also required.", evidence="PATH lookup + libei")
    return Capability("isolated_compositor", "Isolated test compositor", UNAVAILABLE,
                      "Supported isolated KWin prerequisites are missing: " + ", ".join(missing or ["libei"]),
                      "Use the supported KWin setup. Installed weston, cage or sway cannot use Hutch's KWin adapter.",
                      evidence="PATH lookup + libei")


def _browser_engine(h: _Host, deep: bool) -> Capability:
    if not h.has_module("playwright"):
        return Capability("browser_engine", "Browser engine", UNAVAILABLE, "Playwright is not installed.",
                          'pip install "hutch[browser]" && playwright install chromium', evidence="import playwright failed")
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            exe = p.chromium.executable_path
        present = bool(exe) and h.exists(exe)
    except Exception as exc:
        return Capability("browser_engine", "Browser engine", UNKNOWN, f"Could not inspect Playwright ({exc}).",
                          evidence="sync_playwright() failed")
    if not present:
        return Capability("browser_engine", "Browser engine", UNAVAILABLE,
                          "Playwright is installed but its Chromium build is not.", "playwright install chromium",
                          evidence=str(exe))
    if not deep:
        return Capability("browser_engine", "Browser engine", READY,
                          "Playwright and its Chromium build are installed (launch not exercised; use --deep).",
                          evidence=str(exe))
    started = time.monotonic()
    try:
        import tempfile
        from playwright.sync_api import sync_playwright
        with tempfile.TemporaryDirectory(prefix="hutch-doctor-") as profile, sync_playwright() as p:
            context = p.chromium.launch_persistent_context(profile, headless=True)
            page = context.new_page()
            page.goto("about:blank")
            context.close()
    except Exception as exc:
        return Capability("browser_engine", "Browser engine", DEGRADED,
                          f"Installed, but a headless launch failed: {str(exc)[:200]}",
                          "Check browser dependencies (shared libraries, sandbox permissions).", evidence=str(exe))
    return Capability("browser_engine", "Browser engine", READY,
                      f"Headless launch in a throwaway profile worked in {time.monotonic() - started:.1f}s.",
                      evidence=str(exe))


def _remote_takeover() -> Capability:
    return Capability("human_takeover", "Human step control", DEGRADED,
                      "Bounded human frames and step input are available for owned Chromium and private KWin sessions. "
                      "Per-assistant computer access defaults off; paired viewing needs Monitor, input needs Review and "
                      "an explicit controller lease. Physical phones and live remote networks remain unverified.",
                      "Enable Computer access in assistant settings, then start a new supported run. Use the existing "
                      "private HTTPS/passkey deployment; this feature opens no listener.", evidence="local Chromium/KWin input tests; viewport emulation")


def probe_computer_use(*, deep: bool = False, env: Optional[Mapping[str, str]] = None, run: Optional[Runner] = None,
                       which: Optional[Callable[[str], Optional[str]]] = None,
                       exists: Optional[Callable[[str], bool]] = None, libraries: Optional[Callable[[], str]] = None,
                       has_module: Optional[Callable[[str], bool]] = None) -> list[Capability]:
    """Probe every capability independently. A failing probe never hides another."""
    host = _Host(env, run, which, exists, libraries, has_module)
    probes: list[Callable[[], Capability]] = [
        lambda: _session(host), lambda: _compositor(host), lambda: _portal(host), lambda: _screencast(host),
        lambda: _remotedesktop(host), lambda: _pipewire(host), lambda: _libei(host), lambda: _accessibility(host),
        lambda: _clipboard(host), lambda: _input_tools(host), lambda: _isolated_compositor(host),
        lambda: _browser_engine(host, deep), _remote_takeover,
    ]
    results: list[Capability] = []
    for probe in probes:
        try:
            results.append(probe())
        except Exception as exc:                            # a probe must never raise into the doctor
            results.append(Capability("probe_error", "Probe failed", UNKNOWN, f"{type(exc).__name__}: {exc}"))
    return results


def summary(results: list[Capability]) -> dict[str, Any]:
    """What a person should read first, without implying capability the probes could not establish."""
    by_id = {c.id: c for c in results}

    def state(cap: str) -> str:
        return by_id[cap].state if cap in by_id else UNKNOWN

    return {
        "browser": state("browser_engine"),
        "native_desktop": state("isolated_compositor") if state("isolated_compositor") == NEEDS_CONSENT else UNAVAILABLE,
        "existing_desktop": UNAVAILABLE,
        "note": ("Hutch implements isolated KWin sessions. Portal discovery describes host interfaces, not an implemented "
                 "existing-desktop adapter. Session review, capture and delivered input are separate checks."),
    }


def main(argv: Optional[list[str]] = None) -> int:  # pragma: no cover - convenience for `python -m`
    import json
    results = probe_computer_use(deep="--deep" in (argv or sys.argv[1:]))
    print(json.dumps({"capabilities": [c.public() for c in results], "summary": summary(results)}, indent=2))
    return 0
