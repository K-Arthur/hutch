"""Wake-ups instead of polling (PF-5).

Two layers:

* ``Bus`` — in-process, versioned topics on one Condition. A waiter records the
  version it has seen, does its work, and then sleeps until the version moves or
  a timeout fires. Reading the version *before* working closes the lost-wakeup race.
* ``WakeHub`` — cross-process nudges over per-process Unix datagram sockets, so
  ``hutch approvals approve`` in one terminal wakes a run waiting in ``hutch serve``
  in another. Several listeners can coexist (``serve`` + ``daemon``); a FIFO could
  not do that because readers would compete for each message.

Both are best-effort accelerators. Every waiter that matters also has a long
safety timeout, so a lost datagram delays work, never loses it.
"""

from __future__ import annotations

import hashlib
import os
import socket
import tempfile
import threading
import time
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Optional


class Bus:
    """Versioned in-process topics. Cheap enough to notify on every state change."""

    def __init__(self) -> None:
        self._cv = threading.Condition()
        self._ver: dict[str, int] = defaultdict(int)
        self._hub: Optional["WakeHub"] = None

    def attach_hub(self, hub: "WakeHub") -> None:
        self._hub = hub

    def version(self, topic: str) -> int:
        with self._cv:
            return self._ver[topic]

    def notify(self, *topics: str, remote: bool = True) -> None:
        with self._cv:
            for t in topics:
                self._ver[t] += 1
            self._cv.notify_all()
        if remote and self._hub is not None:
            self._hub.ping(topics)

    def wait(self, topic: str, since: int, timeout: Optional[float]) -> int:
        """Block until ``topic`` moves past ``since`` or ``timeout`` elapses. Returns the version."""
        with self._cv:
            self._cv.wait_for(lambda: self._ver[topic] != since, timeout=timeout)
            return self._ver[topic]

    def wait_any(self, seen: dict[str, int], timeout: Optional[float]) -> bool:
        """True if any topic in ``seen`` has moved; updates ``seen`` in place."""
        with self._cv:
            moved = self._cv.wait_for(
                lambda: any(self._ver[t] != v for t, v in seen.items()), timeout=timeout)
            for t in seen:
                seen[t] = self._ver[t]
            return bool(moved)


def _sock_dir(state_dir: Path) -> Path:
    """Short path (AF_UNIX limits paths to ~104 bytes) unique to one state directory."""
    tag = hashlib.sha1(str(state_dir.resolve()).encode()).hexdigest()[:8]
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    base = Path(runtime) if runtime and os.access(runtime, os.W_OK) else Path(tempfile.gettempdir())
    d = base / f"hutch-{os.getuid() if hasattr(os, 'getuid') else 0}" / tag
    d.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(d, 0o700)
    except OSError:
        pass
    return d


class WakeHub:
    """Per-process datagram socket + a way to nudge every other listener on this state dir."""

    def __init__(self, state_dir: Path, bus: Bus) -> None:
        self.bus = bus
        self.dir = _sock_dir(state_dir)
        self.path = self.dir / f"{os.getpid()}-{id(self) & 0xffff:x}.sock"
        self._sock: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._peers_checked = 0.0
        self._has_peers = False

    # ------------------------------------------------------------ listening

    def listen(self) -> bool:
        if not hasattr(socket, "AF_UNIX"):
            return False
        try:
            self.path.unlink(missing_ok=True)
            s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
            s.bind(str(self.path))
            s.settimeout(1.0)
        except OSError:
            return False
        self._sock = s
        self._thread = threading.Thread(target=self._loop, name="hutch-wake", daemon=True)
        self._thread.start()
        return True

    def _loop(self) -> None:
        assert self._sock is not None
        while not self._stop.is_set():
            try:
                data = self._sock.recv(4096)
            except socket.timeout:
                continue
            except OSError:
                return
            topics = [t for t in data.decode("utf-8", "replace").split("\n") if t]
            if topics:
                self.bus.notify(*topics, remote=False)

    def close(self) -> None:
        self._stop.set()
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
        try:
            self.path.unlink(missing_ok=True)
        except OSError:
            pass

    # -------------------------------------------------------------- pinging

    def _peers(self) -> list[Path]:
        try:
            return [p for p in self.dir.glob("*.sock") if p != self.path]
        except OSError:
            return []

    def ping(self, topics: Iterable[str]) -> None:
        """Nudge other processes. Costs one directory listing per second when nobody listens."""
        now = time.monotonic()
        if not self._has_peers and now - self._peers_checked < 1.0:
            return
        self._peers_checked = now
        peers = self._peers()
        self._has_peers = bool(peers)
        if not peers or not hasattr(socket, "AF_UNIX"):
            return
        payload = "\n".join(topics).encode()
        s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        s.setblocking(False)
        try:
            for p in peers:
                try:
                    s.sendto(payload, str(p))
                except (ConnectionRefusedError, FileNotFoundError):
                    try:
                        p.unlink(missing_ok=True)  # stale socket from a dead process
                    except OSError:
                        pass
                except OSError:
                    pass
        finally:
            s.close()
