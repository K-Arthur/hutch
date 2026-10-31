"""Bring up the accessibility bus inside Hutch's disposable desktop session.

An isolated session has its own minimal D-Bus bus with nothing auto-activated, so the at-spi stack has to be started
explicitly: the bus launcher owns ``org.a11y.Bus`` on the session bus and creates the accessibility bus, and the registry
daemon is then started on *that* bus. Applications inside the session are told the address directly
(``AT_SPI_BUS_ADDRESS``); they never resolve the personal desktop's bus.

Two failure modes are expected and handled as refusals, not as silent degradation to guessing:
* the distribution puts the launcher/registry outside ``PATH`` (Arch: ``/usr/lib``), so several paths are tried;
* a long ``TMPDIR`` can exhaust the Unix socket pathname limit, which makes the launcher fall back to an unusable
  abstract address. The caller keeps running with pixel control and reports the reason.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path
from typing import Callable, Mapping, Optional

_LAUNCHER_NAMES = ("at-spi-bus-launcher",)
_REGISTRY_NAMES = ("at-spi2-registryd",)
_EXTRA_DIRS = ("/usr/lib", "/usr/libexec", "/usr/lib/at-spi2-core", "/usr/libexec/at-spi2-core")
START_SECONDS = 10.0
POLL_SECONDS = 0.2


class BusUnavailable(Exception):
    """The private accessibility bus could not be started; the message is safe to show to a person."""


def _locate(names: tuple[str, ...], which: Optional[Callable[[str], Optional[str]]] = None,
            exists: Optional[Callable[[str], bool]] = None) -> Optional[str]:
    """A binary by name, falling back to the distribution directories it may live in outside ``PATH``."""
    which = which or shutil.which
    exists = exists or (lambda path: Path(path).is_file())
    for name in names:
        found = which(name)
        if found:
            return found
    for directory in _EXTRA_DIRS:
        for name in names:
            candidate = str(Path(directory) / name)
            if exists(candidate):
                return candidate
    return None


def availability(which: Optional[Callable[[str], Optional[str]]] = None,
                 exists: Optional[Callable[[str], bool]] = None) -> tuple[bool, str]:
    """Whether the host has the binaries; package presence is not a capture or input test."""
    if _locate(_LAUNCHER_NAMES, which, exists) is None:
        return False, "at-spi-bus-launcher is not installed"
    if _locate(_REGISTRY_NAMES, which, exists) is None:
        return False, "at-spi2-registryd is not installed (install at-spi2-core)"
    return True, ""


class AccessibilityBus:
    """Starts and owns the private accessibility bus for one session."""

    def __init__(self, runtime: Path, env: Mapping[str, str],
                 spawn: Callable[..., subprocess.Popen], *, seconds: float = START_SECONDS):
        self._runtime = Path(runtime)
        self._env = dict(env)
        self._spawn = spawn
        self._seconds = seconds
        self._launcher: Optional[str] = None
        self._registry: Optional[str] = None
        self._process = None

    # ------------------------------------------------------------- helpers

    def _busctl(self, *args: str, address: str = "") -> subprocess.CompletedProcess:
        command = ["busctl", "--user", *(["--address", address] if address else []), *args]
        return subprocess.run(command, env=self._env, capture_output=True, text=True, timeout=8, check=False)

    def _address(self) -> str:
        done = self._busctl("call", "org.a11y.Bus", "/org/a11y/bus", "org.a11y.Bus", "GetAddress")
        if done.returncode != 0 or '"' not in done.stdout:
            return ""
        address = done.stdout.split('"')[1]
        if not address.startswith("unix:path="):
            # An abstract or empty address here means the socket path did not fit; say so rather than guessing.
            raise BusUnavailable("the accessibility bus address is unusable in this session (its socket path is too long)"
                                 if not address else f"unexpected accessibility bus address: {address[:60]}")
        return address

    def _inside_runtime(self, address: str) -> bool:
        try:
            path = Path(address.split("=", 1)[1]).resolve(strict=False)
            path.relative_to(self._runtime.resolve(strict=False))
            return True
        except (OSError, ValueError, IndexError):
            return False

    def _wait(self, predicate, message: str) -> None:
        end = time.monotonic() + self._seconds
        while time.monotonic() < end:
            if predicate():
                return
            time.sleep(POLL_SECONDS)
        raise BusUnavailable(message)

    # ---------------------------------------------------------------- start

    def start(self) -> str:
        """Return the private accessibility bus address. Raises ``BusUnavailable``."""
        self._launcher = _locate(_LAUNCHER_NAMES)
        self._registry = _locate(_REGISTRY_NAMES)
        if self._launcher is None:
            raise BusUnavailable("at-spi-bus-launcher is not installed")
        if self._registry is None:
            raise BusUnavailable("at-spi2-registryd is not installed (install at-spi2-core)")
        try:
            self._process = self._spawn([self._launcher, "--launch-immediately"], "a11y-bus",
                                        {"AT_SPI_BUS_TYPE": "session"})
        except OSError as exc:
            raise BusUnavailable(f"the accessibility bus launcher could not start: {exc}") from None
        try:
            self._wait(lambda: self._busctl("status", "org.a11y.Bus").returncode == 0,
                       "the accessibility bus launcher did not register on the private session bus")
            address = self._address()
            if not address:
                self._wait(lambda: bool(self._address()), "the accessibility bus did not report an address")
                address = self._address()
            if not self._inside_runtime(address):
                raise BusUnavailable("the accessibility bus is not inside this session's private runtime directory")
            # Accessibility is opt-in for toolkits; the flag is per-bus state, not a host setting.
            self._busctl("set-property", "org.a11y.Bus", "/org/a11y/bus", "org.a11y.Status", "IsEnabled", "b", "true")
            # The registry resolves org.a11y.Bus from the SESSION bus and then serves the accessibility bus.
            self._spawn([self._registry], "a11y-registry", {"AT_SPI_BUS_TYPE": "session"})
            self._wait(lambda: self._busctl("status", "org.a11y.atspi.Registry", address=address).returncode == 0,
                       "the accessibility registry did not start")
            return address
        except Exception:
            self.stop()
            raise

    @property
    def socket_path(self) -> str:
        """The bus socket, for the containment mount. Empty when the bus is not up."""
        return ""

    def stop(self) -> None:
        process, self._process = self._process, None
        if process is not None and process.poll() is None:
            try:
                process.terminate()
            except OSError:
                pass
