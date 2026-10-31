"""Host-side client for the out-of-process AT-SPI worker (``native/a11y_worker.py``).

Semantic desktop control complements pixels; it does not replace them. A pointer action says *where* something is; an
accessibility action says *what* it is, which survives layout changes, needs no vision model and can be verified by reading
the widget back. Everything here is bounded and fail-closed:

* the worker may only attach to **this session's** accessibility bus. An address outside the private runtime directory is
  refused, so a misconfiguration can never enumerate the person's own desktop;
* every request has a deadline, and a worker that stops answering is killed rather than waited for;
* replies are re-validated host-side in ``a11y_tree`` instead of trusted because they came from our own process;
* ids from one snapshot never authorize an action on another: the caller must quote the latest ``snapshot_id``;
* password and protected text is never returned by the worker, and typed text is redacted by the tool's recorder.
"""

from __future__ import annotations

import json
import os
import select
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Mapping, Optional, Protocol

from .a11y_tree import (MAX_NODE_DEPTH, MAX_NODES, MAX_NODE_TEXT, AccessibilityError, Node, ElementSnapshot,
                        parse_snapshot)

__all__ = ["AccessibilityError", "AccessibilitySession", "AccessibilityUnavailable", "A11yWorker", "ElementSnapshot",
           "Node", "WorkerTransport", "find_atspi_python", "private_bus_address", "MAX_NODES", "MAX_NODE_DEPTH",
           "MAX_NODE_TEXT", "MAX_TEXT", "REQUEST_DEADLINE"]

REQUEST_DEADLINE = 12.0
#: One call may replace at most this much text; the tool's schema and the worker agree on the same bound.
MAX_TEXT = 2000


class AccessibilityUnavailable(Exception):
    """Semantic desktop control is not available in this session; the message is safe to show to a person."""


class WorkerTransport(Protocol):
    """The one call the client needs. Production uses ``A11yWorker``; tests inject a fake."""

    def request(self, payload: dict[str, Any], *, deadline: float = REQUEST_DEADLINE) -> dict[str, Any]: ...
    def close(self) -> None: ...


def find_atspi_python() -> Optional[str]:
    """An interpreter that can import Atspi (the EIS interpreter may differ). None if there is none."""
    for candidate in (os.environ.get("HUTCH_GI_PYTHON"), "/usr/bin/python3", sys.executable):
        if not candidate or not Path(candidate).exists():
            continue
        try:
            done = subprocess.run(
                [candidate, "-c", "import gi; gi.require_version('Atspi','2.0'); from gi.repository import Atspi"],
                capture_output=True, timeout=15, check=False)
        except (OSError, subprocess.SubprocessError):
            continue
        if done.returncode == 0:
            return candidate
    return None


def private_bus_address(env: Mapping[str, str]) -> str:
    """The session's own accessibility bus, or a refusal. Never returns a bus outside the private runtime dir."""
    address = str(env.get("AT_SPI_BUS_ADDRESS") or "")
    runtime = str(env.get("XDG_RUNTIME_DIR") or "")
    if not address.startswith("unix:path=") or not runtime:
        raise AccessibilityUnavailable("this session has no private accessibility bus")
    path = Path(address.split("=", 1)[1])
    try:
        path.resolve(strict=False).relative_to(Path(runtime).resolve(strict=False))
    except (OSError, ValueError):
        raise AccessibilityUnavailable(
            "the accessibility bus is not inside this session's private runtime directory") from None
    return address


class A11yWorker(WorkerTransport):
    """A running accessibility worker for one private session."""

    def __init__(self, process: subprocess.Popen, ready: Mapping[str, Any]):
        self._proc = process
        self.apps = int(ready.get("apps") or 0)

    @property
    def process(self) -> subprocess.Popen:
        return self._proc

    # ------------------------------------------------------------ lifecycle

    @classmethod
    def start_in_isolated_session(cls, env: Mapping[str, str], *, python: Optional[str] = None,
                                  deadline: float = 15.0) -> "A11yWorker":
        address = private_bus_address(env)
        interpreter = python or find_atspi_python()
        if interpreter is None:
            raise AccessibilityUnavailable("no Python with PyGObject and the Atspi typelib was found; install "
                                           "python-gobject with at-spi2-core or set HUTCH_GI_PYTHON")
        worker = Path(__file__).with_name("native") / "a11y_worker.py"
        full_env = {**dict(env), "AT_SPI_BUS_ADDRESS": address, "HUTCH_ISOLATED_SESSION": "1",
                    "PYTHONUNBUFFERED": "1"}
        try:
            process = subprocess.Popen([interpreter, "-u", str(worker)], stdin=subprocess.PIPE,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=full_env, text=True,
                                       start_new_session=True)
        except OSError as exc:
            raise AccessibilityUnavailable(f"the accessibility worker could not start: {exc}") from None
        line = cls._readline(process, deadline)
        if line is None:
            cls._kill(process)
            raise AccessibilityUnavailable("the accessibility worker did not report ready in time")
        try:
            ready = json.loads(line)
        except json.JSONDecodeError:
            cls._kill(process)
            raise AccessibilityUnavailable(
                f"the accessibility worker sent an unreadable status: {line[:120]!r}") from None
        if not ready.get("ready"):
            cls._kill(process)
            raise AccessibilityUnavailable(f"accessibility is unavailable: {ready.get('error', 'unknown reason')}")
        return cls(process, ready)

    @staticmethod
    def _readline(process: subprocess.Popen, timeout: float) -> Optional[str]:
        assert process.stdout is not None
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if process.poll() is not None and not select.select([process.stdout], [], [], 0)[0]:
                return None
            if select.select([process.stdout], [], [], 0.1)[0]:
                return process.stdout.readline().strip()
        return None

    @staticmethod
    def _kill(process: subprocess.Popen) -> None:
        try:
            process.kill()
        except OSError:
            pass
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            pass

    # ------------------------------------------------------------- requests

    def request(self, payload: dict[str, Any], *, deadline: float = REQUEST_DEADLINE) -> dict[str, Any]:
        if self._proc.poll() is not None:
            raise AccessibilityError("the accessibility worker stopped running")
        if self._proc.stdin is None or self._proc.stdout is None:
            raise AccessibilityError("the accessibility worker has no channel")
        try:
            self._proc.stdin.write(json.dumps(payload) + "\n")
            self._proc.stdin.flush()
        except (BrokenPipeError, OSError):
            raise AccessibilityError("the accessibility worker stopped answering") from None
        line = self._readline(self._proc, deadline)
        if line is None:
            # A worker that misses its deadline is a liability: kill it, and let the caller say the outcome is unknown.
            self._kill(self._proc)
            raise AccessibilityError("the accessibility worker stopped answering and was stopped")
        try:
            reply = json.loads(line)
        except json.JSONDecodeError:
            raise AccessibilityError(
                f"the accessibility worker sent an unreadable reply: {line[:120]!r}") from None
        if not isinstance(reply, dict):
            raise AccessibilityError("the accessibility worker sent a malformed reply")
        if not reply.get("ok"):
            error = reply.get("error")
            raise AccessibilityError((" ".join(error.split())[:300] if isinstance(error, str) else "")
                                     or "the accessibility request failed")
        return reply

    def close(self) -> None:
        try:
            if self._proc.stdin is not None:
                self._proc.stdin.close()
        except OSError:
            pass
        try:
            self._proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self._kill(self._proc)

    def kill(self) -> None:
        self._kill(self._proc)


class AccessibilitySession:
    """Semantic observation and action on one worker, with the latest-snapshot fence."""

    def __init__(self, transport: WorkerTransport, *, clock=time.monotonic):
        self._transport = transport
        self._clock = clock
        self._latest: Optional[ElementSnapshot] = None
        self._counter = 0

    # ---------------------------------------------------------- observation

    def elements(self, *, root: str = "", max_nodes: int = MAX_NODES) -> ElementSnapshot:
        payload: dict[str, Any] = {"op": "snapshot", "max_nodes": max(1, min(int(max_nodes), MAX_NODES))}
        if root:
            if self._latest is None:
                raise AccessibilityError("there is no tree to narrow yet; read the elements without a root first")
            if self._latest.by_id(root) is None:
                raise AccessibilityError(f"element {root} is not in the current snapshot; read the tree again")
            payload["root"] = root
        reply = self._transport.request(payload)
        if reply.get("subtree"):
            # A narrowed read keeps the current generation: the caller's ids still mean what they meant.
            assert self._latest is not None
            return parse_snapshot(reply, self._latest.snapshot_id)
        self._counter += 1
        snapshot = parse_snapshot(reply, f"a{self._counter:04d}")
        self._latest = snapshot
        return snapshot

    @property
    def latest(self) -> Optional[ElementSnapshot]:
        return self._latest

    # -------------------------------------------------------------- acting

    def require(self, snapshot_id: str, element_id: str) -> Node:
        """The element an action may target, or a refusal. Binds ids to the latest snapshot only."""
        if self._latest is None:
            raise AccessibilityError("there is no accessibility snapshot yet; read the elements first")
        if snapshot_id != self._latest.snapshot_id:
            raise AccessibilityError(
                f"snapshot {snapshot_id or '(none given)'} is not the latest tree ({self._latest.snapshot_id}); "
                f"read the elements again and use the new snapshot_id")
        node = self._latest.by_id(element_id)
        if node is None:
            raise AccessibilityError(f"element {element_id or '(none given)'} is not in the latest tree; "
                                     "read the elements again")
        return node

    def activate(self, node: Node) -> dict[str, Any]:
        return self._transport.request({"op": "activate", "element": node.id})

    def set_text(self, node: Node, text: str) -> dict[str, Any]:
        return self._transport.request({"op": "set_text", "element": node.id, "text": text})

    # ------------------------------------------------------------ lifecycle

    def close(self) -> None:
        self._transport.close()
