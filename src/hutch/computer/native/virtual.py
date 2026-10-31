"""A disposable native Wayland desktop that Hutch owns (KWin ``--virtual``).

What this isolates, and what it does not. It gives automation its own *display, compositor, input and session bus*: a
private runtime dir, HOME and XDG dirs under a mode-0700 temp directory, a D-Bus session bus with a minimal config (so
nothing is auto-activated), and its own compositor socket. It never uses the user's session bus, Wayland socket, EIS socket
or input devices, so automated input cannot reach the personal desktop.

Applications launched through ``launch`` additionally use workspace-only mount and network/PID namespaces plus resource
limits. The private compositor and minimal bus remain trusted host processes, not a VM boundary. Do NOT add
``uinput``/``ydotool`` here: those are system-global and would reach the real input stack.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Mapping, Optional

_BUS_CONF = """<!DOCTYPE busconfig PUBLIC "-//freedesktop//DTD D-Bus Bus Configuration 1.0//EN"
 "http://www.freedesktop.org/standards/dbus/1.0/busconfig.dtd">
<busconfig>
  <type>session</type>
  <auth>EXTERNAL</auth>
  <listen>unix:path={bus}</listen>
  <policy context="default">
    <allow send_destination="*" eavesdrop="true"/>
    <allow eavesdrop="true"/>
    <allow own="*"/>
  </policy>
</busconfig>
"""


class DesktopUnavailable(Exception):
    pass


class ManagedDesktop:
    SOCKET = "hutch-virt-0"

    def __init__(self, width: int = 1280, height: int = 800):
        self.width, self.height = width, height
        self.root: Optional[Path] = None
        self.env: dict[str, str] = {}
        self._procs: list[subprocess.Popen] = []
        self._capture_lock = threading.Lock()
        self._captures: set[subprocess.Popen] = set()
        self._stopping = False
        self._apps: list[subprocess.Popen] = []
        self.a11y_address = ""
        self.a11y_reason = ""

    # ------------------------------------------------------------ lifecycle

    @staticmethod
    def available() -> tuple[bool, str]:
        for tool in ("kwin_wayland", "dbus-daemon", "busctl", "spectacle"):
            if shutil.which(tool) is None:
                return False, f"{tool} is not installed"
        return True, ""

    def __enter__(self) -> "ManagedDesktop":
        ok, why = self.available()
        if not ok:
            raise DesktopUnavailable(why)
        self.root = Path(tempfile.mkdtemp(prefix="hutch-virt-"))
        os.chmod(self.root, 0o700)
        run, home = self.root / "run", self.root / "home"
        run.mkdir(mode=0o700)
        home.mkdir(mode=0o700)
        bus = run / "bus"
        conf = self.root / "bus.conf"
        conf.write_text(_BUS_CONF.format(bus=bus))
        self.env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": os.environ.get("LANG", "C.UTF-8"),
            "XDG_RUNTIME_DIR": str(run), "HOME": str(home), "XDG_CONFIG_HOME": str(home / ".config"),
            "XDG_DATA_HOME": str(home / ".local/share"), "XDG_CACHE_HOME": str(home / ".cache"),
            "XDG_STATE_HOME": str(home / ".local/state"),
            "XDG_DATA_DIRS": os.environ.get("XDG_DATA_DIRS", "/usr/local/share:/usr/share"),
            "DBUS_SESSION_BUS_ADDRESS": f"unix:path={bus}", "WAYLAND_DISPLAY": self.SOCKET,
            "QT_QPA_PLATFORM": "wayland", "XDG_CURRENT_DESKTOP": "KDE", "XDG_SESSION_TYPE": "wayland",
            "HUTCH_ISOLATED_SESSION": "1", "KDE_FULL_SESSION": "true",
        }
        try:
            self._spawn(["dbus-daemon", "--nofork", "--nopidfile", f"--config-file={conf}"], "dbus")
            self._wait(lambda: bus.exists(), 5, "the private D-Bus session bus did not start")
            self._spawn(["kwin_wayland", "--virtual", "--socket", self.SOCKET, "--width", str(self.width),
                         "--height", str(self.height), "--no-lockscreen", "--no-global-shortcuts"], "kwin")
            self._wait(lambda: (run / self.SOCKET).exists(), 10, "the virtual compositor did not create its socket")
            self._wait(lambda: self._busctl("status", "org.kde.KWin") == 0, 10, "KWin did not register on the bus")
            self._start_accessibility()
        except Exception:
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, *_exc) -> None:
        with self._capture_lock:
            self._stopping = True
            for proc in self._captures:
                if proc.poll() is None:
                    try: os.killpg(proc.pid, signal.SIGKILL)
                    except OSError: pass
        for proc in reversed(self._procs):
            if proc.poll() is None:
                try:
                    os.killpg(proc.pid, signal.SIGTERM)
                except OSError:
                    pass
        deadline = time.monotonic() + 2.0
        for proc in self._procs:
            try:
                proc.wait(timeout=max(0.05, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except OSError:
                    pass
        self._procs.clear()
        if self.root is not None:
            shutil.rmtree(self.root, ignore_errors=True)
            self.root = None

    # -------------------------------------------------------------- helpers

    def _spawn(self, argv: list[str], name: str, extra_env: Optional[Mapping[str, str]] = None,
               cwd: Optional[str] = None) -> subprocess.Popen:
        log = open(self.root / f"{name}.log", "ab") if self.root else subprocess.DEVNULL
        try:
            proc = subprocess.Popen(argv, env={**self.env, **(extra_env or {})}, stdout=log, stderr=log,
                                    stdin=subprocess.DEVNULL, start_new_session=True, cwd=cwd)
        finally:
            if hasattr(log, "close"):
                log.close()
        self._procs.append(proc)
        return proc

    def _busctl(self, *args: str) -> int:
        return subprocess.run(["busctl", "--user", *args], env=self.env, capture_output=True, timeout=5).returncode

    @staticmethod
    def _wait(predicate, seconds: float, message: str) -> None:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(0.1)
        raise DesktopUnavailable(message)

    # ------------------------------------------------------------- the API

    def launch(self, argv: list[str], name: str = "app", cwd: Optional[str] = None) -> subprocess.Popen:
        """Start a contained application with only the workspace and this desktop's private sockets."""
        from ...sandbox import Policy, desktop_argv, status
        if self._stopping:
            raise DesktopUnavailable("the private desktop is stopping")
        self._apps = [proc for proc in self._apps if proc.poll() is None]
        if len(self._apps) >= 4:
            raise DesktopUnavailable("the private desktop already has its maximum of four application launchers")
        if not cwd:
            raise DesktopUnavailable("a workspace is required for native applications")
        readiness = status()
        if not readiness.ok:
            raise DesktopUnavailable(f"native app containment is unavailable: {readiness.reason}")
        command = desktop_argv(argv, Policy(workspace=Path(cwd)), self.env)
        command = self._with_accessibility_mount(command)
        # The resource-limit launcher talks to the host user service manager. Its child clears the environment and
        # binds only the PRIVATE bus; the app cannot request host systemd activation through this socket.
        launcher_env = {key: os.environ[key] for key in ("XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS") if key in os.environ}
        proc = self._spawn(command, name, extra_env=launcher_env, cwd=cwd)
        self._apps.append(proc)
        # Emergency stop may race the host launcher. Fence its new process too.
        with self._capture_lock:
            if self._stopping:
                try: os.killpg(proc.pid, signal.SIGKILL)
                except OSError: pass
                raise DesktopUnavailable("the private desktop stopped during launch")
        return proc

    def _with_accessibility_mount(self, command: list[str]) -> list[str]:
        """Add the one socket semantic control needs, before the environment is cleared.

        The containment builder stays generic: only this session knows which accessibility socket it owns, so only this
        session may hand it across. A malformed path fails closed rather than silently mounting nothing.
        """
        socket = self.a11y_socket
        if not socket:
            return command
        assert self.root is not None
        path = Path(socket)
        try:
            path.resolve(strict=False).relative_to(self.root.resolve(strict=False))
        except (OSError, ValueError):
            raise DesktopUnavailable("the accessibility socket is not inside this private session") from None
        if not path.is_socket():
            raise DesktopUnavailable("the accessibility socket is unavailable")
        try:
            index = command.index("--clearenv")
        except ValueError:  # pragma: no cover - desktop_argv always ends its mounts with --clearenv
            raise DesktopUnavailable("the containment command has no environment boundary") from None
        return [*command[:index], "--dir", str(path.parent), "--ro-bind", str(path), str(path),
                *command[index:]]

    def capture_png(self, timeout: float = 15.0) -> bytes:
        """A full-output screenshot of THIS compositor only (KWin ScreenShot2 via spectacle's authorization)."""
        assert self.root is not None
        out = self.root / f"capture-{time.monotonic_ns()}.png"
        from ..frames import MAX_FRAME_BYTES
        proc = None
        try:
            with self._capture_lock:
                if self._stopping:
                    raise DesktopUnavailable("the private desktop is stopping")
                proc = subprocess.Popen(["spectacle", "-b", "-f", "-n", "-o", str(out)], env=self.env,
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                self._captures.add(proc)
            try:
                code = proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait(timeout=3)
                raise DesktopUnavailable("private capture exceeded its deadline") from None
            if code != 0:
                raise DesktopUnavailable(f"private capture failed (exit {code})")
            handle = os.open(out, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(handle, "rb") as stream:
                if not 0 < os.fstat(stream.fileno()).st_size <= MAX_FRAME_BYTES:
                    raise DesktopUnavailable("private capture exceeds the 900 KB frame bound or is empty")
                return stream.read(MAX_FRAME_BYTES + 1)
        finally:
            if proc is not None:
                with self._capture_lock:
                    self._captures.discard(proc)
            out.unlink(missing_ok=True)

    # ------------------------------------------------------- accessibility

    def _start_accessibility(self) -> None:
        """Start the private accessibility bus. On failure the session still runs with pixel control, and says why."""
        from .a11y_bus import AccessibilityBus, BusUnavailable
        assert self.root is not None
        bus = AccessibilityBus(self.root / "run", self.env, self._spawn)
        try:
            address = bus.start()
        except BusUnavailable as exc:
            self.a11y_reason = str(exc)
            self.env.pop("AT_SPI_BUS_ADDRESS", None)
            return
        self.a11y_address = address
        # Toolkits only build their accessibility tree when asked: Qt and GTK both honour these in a private session.
        self.env.update({"AT_SPI_BUS_ADDRESS": address, "QT_LINUX_ACCESSIBILITY_ALWAYS_ON": "1",
                         "ACCESSIBILITY_ENABLED": "1"})

    @property
    def a11y_socket(self) -> str:
        """The private accessibility socket, for the single containment mount. Empty when unavailable."""
        if not self.a11y_address.startswith("unix:path="):
            return ""
        return self.a11y_address.split("=", 1)[1]

    def kill_all(self) -> None:
        """End the compositor, bus and every application at once (emergency stop of the whole environment)."""
        with self._capture_lock:
            self._stopping = True
            captures = tuple(self._captures)
        for proc in [*reversed(self._procs), *captures]:
            if proc.poll() is None:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except OSError:
                    pass

    def alive(self) -> bool:
        return bool(self._procs) and all(p.poll() is None for p in self._procs[:2])

    @property
    def home(self) -> Path:
        assert self.root is not None
        return self.root / "home"
