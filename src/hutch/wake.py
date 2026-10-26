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
import stat
import tempfile
import threading
import time
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Optional


def datagram_transport_available() -> bool:
    # Windows exposes AF_UNIX but not Unix datagram sockets. Existing waiters
    # retain their safety timeout when this best-effort accelerator is absent.
    return os.name != "nt" and hasattr(socket, "AF_UNIX")


class Bus:
    """Versioned in-process topics. Cheap enough to notify on every state change."""

    def __init__(self) -> None:
        self._cv = threading.Condition()
        self._ver: dict[str, int] = defaultdict(int)
        self._hub: Optional["WakeHub"] = None
        self._subs: dict[str, list] = defaultdict(list)

    def attach_hub(self, hub: "WakeHub") -> None:
        self._hub = hub

    def version(self, topic: str) -> int:
        with self._cv:
            return self._ver[topic]

    def subscribe(self, topics: Iterable[str], callback) -> "callable":
        """Call ``callback()`` (from the notifying thread) whenever any topic moves.

        Lets an asyncio server wait on ``loop.call_soon_threadsafe(event.set)`` instead of parking
        a thread per open SSE stream. Returns an unsubscribe function.
        """
        topics = tuple(topics)
        with self._cv:
            for t in topics:
                self._subs[t].append(callback)

        def unsubscribe() -> None:
            with self._cv:
                for t in topics:
                    try:
                        self._subs[t].remove(callback)
                    except ValueError:
                        pass
        return unsubscribe

    def notify(self, *topics: str, remote: bool = True) -> None:
        with self._cv:
            for t in topics:
                self._ver[t] += 1
            self._cv.notify_all()
            callbacks = [cb for t in topics for cb in self._subs.get(t, ())]
        for cb in callbacks:
            try:
                cb()
            except Exception:
                pass
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
    configured = os.environ.get("HUTCH_WAKE_DIR")
    if configured:
        d = Path(configured)
        try:
            info = d.lstat()
        except OSError as exc:
            raise RuntimeError(f"configured Hutch wake directory is unavailable: {exc}") from exc
        if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
            raise RuntimeError("configured Hutch wake path must be a real directory")
        if hasattr(os, "getuid") and info.st_uid != os.getuid():
            raise RuntimeError("configured Hutch wake directory is not owned by this user")
        if info.st_mode & 0o077:
            raise RuntimeError("configured Hutch wake directory must be private to this user")
        return d
    tag = hashlib.sha1(str(state_dir.resolve()).encode()).hexdigest()[:8]
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    uid = os.getuid() if hasattr(os, "getuid") else 0
    base = Path(runtime) if runtime and os.access(runtime, os.W_OK) else Path(tempfile.gettempdir())
    parent = base / f"hutch-{uid}"
    d = parent / tag

    def open_owned_directory(path: Path, *, create: bool = False) -> int:
        if create:
            try:
                path.mkdir(mode=0o700)
            except FileExistsError:
                pass
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(path, flags)
        except OSError as exc:
            raise RuntimeError(f"Hutch wake path must be a real directory: {path}") from exc
        info = os.fstat(fd)
        if not stat.S_ISDIR(info.st_mode) or (hasattr(os, "getuid") and info.st_uid != uid):
            os.close(fd)
            raise RuntimeError(f"Hutch wake directory is not owned by this user: {path}")
        return fd

    # Validate the shared/runtime base without changing its mode. /tmp is
    # intentionally shared and sticky; XDG_RUNTIME_DIR is expected to be private.
    try:
        base_info = base.lstat()
    except OSError as exc:
        raise RuntimeError(f"Hutch wake base directory is unavailable: {exc}") from exc
    if not stat.S_ISDIR(base_info.st_mode) or stat.S_ISLNK(base_info.st_mode):
        raise RuntimeError("Hutch wake base must be a real directory")
    if runtime and base == Path(runtime):
        if (hasattr(os, "getuid") and base_info.st_uid != uid) or base_info.st_mode & 0o022:
            base = Path(tempfile.gettempdir())
            base_info = base.lstat()
            if not stat.S_ISDIR(base_info.st_mode) or stat.S_ISLNK(base_info.st_mode):
                raise RuntimeError("Hutch temporary wake base must be a real directory")
            parent, d = base / f"hutch-{uid}", base / f"hutch-{uid}" / tag

    parent_fd = open_owned_directory(parent, create=True)
    try:
        os.fchmod(parent_fd, 0o700)
        leaf_fd = open_owned_directory(d, create=True)
        try:
            # A legacy directory created by this user may be tightened safely.
            os.fchmod(leaf_fd, 0o700)
        finally:
            os.close(leaf_fd)
    finally:
        os.close(parent_fd)
    return d


class WakeHub:
    """Per-process datagram socket + a way to nudge every other listener on this state dir."""

    def __init__(self, state_dir: Path, bus: Bus) -> None:
        self.bus = bus
        self.dir = _sock_dir(state_dir) if datagram_transport_available() else None
        self.path = self.dir / f"{os.getpid()}-{id(self) & 0xffff:x}.sock" if self.dir else None
        self._sock: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._peers_checked = 0.0
        self._has_peers = False

    # ------------------------------------------------------------ listening

    def listen(self) -> bool:
        if self.path is None:
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
        if self.path is not None:
            try:
                self.path.unlink(missing_ok=True)
            except OSError:
                pass

    # -------------------------------------------------------------- pinging

    def _peers(self) -> list[Path]:
        if self.dir is None:
            return []
        try:
            return [p for p in self.dir.glob("*.sock") if p != self.path]
        except OSError:
            return []

    def ping(self, topics: Iterable[str]) -> None:
        """Nudge other processes, promptly for approval and human-review decisions.

        Low-priority notifications throttle peer discovery when no listener is
        known. A decision can arrive just after a worker begins listening, so
        review topics always refresh that discovery instead of waiting for the
        waiter's safety poll.
        """
        if self.dir is None:
            return
        topics = tuple(topics)
        now = time.monotonic()
        urgent = any(topic.startswith(("approval:", "human:")) for topic in topics)
        if not urgent and not self._has_peers and now - self._peers_checked < 1.0:
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
