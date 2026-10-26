"""WorkspaceManager: one contained kernel process per conversation.

Containment substrate (extends the story in ``docs/safety.md``'s shell row —
this module is where it is implemented for Python):

* ``kernel_argv`` reuses :mod:`hutch.sandbox`'s strict profile — bubblewrap
  with ``--unshare-all`` (no network: a new empty network namespace, loopback
  down), a filesystem of read-only ``/usr`` + venv + hutch source and ONLY
  the conversation's workspace writable, a fresh ``/proc``, private ``/tmp``,
  then systemd-run's user scope for cgroup memory/task caps and prlimit for
  CPU/address-space/file limits — exactly the shell tool's tail.
* The environment is a fixed allowlist: shell.py's ``PATH``/``HOME``/``LANG``/
  ``TERM`` pattern plus exactly the entries this child needs — ``TMPDIR``
  (as ``shell_argv`` also sets), ``PYTHONPATH``/``PYTHONUNBUFFERED`` (the
  offline worker's pattern, so the kernel can import hutch and the venv's
  packages from read-only mounts), ``HUTCH_KERNEL=1`` (the containment
  marker) and ``HUTCH_WORKSPACE_GENERATION`` (so receipts carry the
  generation they ran in). Nothing ambient crosses: ``--clearenv``.
* Fail-closed: when strict containment is unavailable on this host there is
  NO execution and NO uncontained fallback — the same refusal
  ``tools/shell.py`` gives, surfaced as :class:`ContainmentUnavailable`.
* Every spawn is registered in the run's :class:`~hutch.tools.base.ProcRegistry`,
  so run teardown ends the kernel tree (verified teardown: ``survivors`` is
  measured, not assumed). A child that dies anyway — mid-cell or between
  runs — is reported honestly: status ``'lost'``, the store row moves to
  ``'expired'``, and the next execution starts a NEW generation rather than
  pretending the old in-memory state survived.
* One exec at a time per conversation. A concurrent caller gets ``'busy'``
  immediately; nothing is queued behind a runaway cell.
* ``interrupt()`` sends SIGINT and waits a bounded three seconds for the
  protocol ack. No ack means the receipt is marked ``'interrupt_unconfirmed'``
  — never a silent claim that a cell stopped — and a reset is offered.
* ``restart()`` terminates the child via ``ProcRegistry.terminate`` (verified
  teardown), transitions the store row to ``'terminated'`` under optimistic
  concurrency, upserts the next generation, and hands back a stale marker so
  consumers can mark prior outputs (their receipts carry the old
  ``environment_generation``; comparing generations is the consumer's job).
"""

from __future__ import annotations

import json
import os
import platform
import select
import signal
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from importlib.util import find_spec
from pathlib import Path
from typing import Any, Callable, Optional

from .. import sandbox
from ..store import RevisionConflict, Store
from . import protocol
from .protocol import (
    INTERRUPT_ACK_SECONDS,
    MAX_RESPONSE_LINE_CHARS,
    PARENT_RESPONSE_MARGIN_SECONDS,
)

#: What a spawn returns: ``(proc, env_fingerprint)`` — the proc must already
#: have sent its ``hello`` line (the default contained spawner waits for it,
#: bounded, and fails closed if it never arrives).
SpawnFn = Callable[[Path, int], "tuple[subprocess.Popen, dict[str, Any]]"]


class ContainmentUnavailable(RuntimeError):
    """Strict containment is unavailable: the workspace refuses to run
    (fail-closed, mirroring the shell tool's refusal — never unsandboxed)."""


def workspace_dir_for(state_dir: Path | str, conversation_id: str) -> Path:
    """The workspace directory convention: ``<state>/workspaces/<conversation_id>/``."""
    return Path(state_dir) / "workspaces" / conversation_id


def sysconfig_purelib() -> str:
    import sysconfig
    return sysconfig.get_paths().get("purelib", "")


def kernel_env(workspace: Path, generation: int) -> dict[str, str]:
    """The fixed environment allowlist passed through ``--clearenv``.

    The four variables shell.py allowlists, plus exactly the entries this
    child needs — every one named, nothing ambient (provider keys, proxies,
    XDG data, user service buses never cross the boundary).
    """
    source_root = Path(__file__).resolve().parents[2]   # .../src (this file is src/hutch/workspace/manager.py)
    python_path = [str(source_root)]
    package_dir = sysconfig_purelib()
    package_path = Path(package_dir).resolve() if package_dir else None
    # Match the canonical venv prefix mounted read-only by the sandbox. The
    # caller may have launched through a symlink that is absent inside it.
    if package_path and package_path.is_dir() and not package_path.is_relative_to("/usr"):
        python_path.append(str(package_path))
    return {
        "PATH": sandbox.DEFAULT_PATH,
        "HOME": str(workspace),
        "LANG": "C.UTF-8",
        "TERM": "dumb",
        "TMPDIR": "/tmp",                       # private tmpfs inside the sandbox
        "PYTHONPATH": os.pathsep.join(python_path),
        "PYTHONUNBUFFERED": "1",
        "HUTCH_KERNEL": "1",                    # containment marker for the kernel process
        "HUTCH_WORKSPACE_GENERATION": str(int(generation)),
    }


def env_fingerprint() -> dict[str, Any]:
    """What the contained interpreter offers, detected WITHOUT importing:
    stdlib always; pandas/matplotlib are optional extras only."""
    return {
        "python_version": platform.python_version(),
        "extras": {
            "pandas": find_spec("pandas") is not None,
            "matplotlib": find_spec("matplotlib") is not None,
        },
    }


def kernel_argv(workspace: Path, generation: int) -> list[str]:
    """The full argv that runs ``python -m hutch.workspace.kernel`` contained.

    Mirrors ``sandbox.shell_argv``: bubblewrap unsharing everything, the
    read-only system tree, the workspace as the only writable path, a fresh
    /proc, then systemd-run's user scope (cgroup memory/task caps) wrapping
    prlimit (CPU / address space / file size / open files / no core).
    """
    if os.environ.get("HUTCH_SANDBOX") == "off":
        raise ContainmentUnavailable(
            "HUTCH_SANDBOX=off turns containment off for everything; the Python workspace "
            "has no uncontained mode, so it refuses to run")
    status = sandbox.status()
    if not status.ok:
        raise ContainmentUnavailable(
            f"this host cannot provide strict containment: {status.reason}. "
            "Nothing was run (fail-closed, as with the shell tool).")
    policy = sandbox.Policy(workspace=workspace, network=False)
    ws = str(Path(workspace).resolve())
    argv = [sandbox.binary(), "--die-with-parent", "--new-session", "--unshare-all"]
    argv += ["--ro-bind", "/usr", "/usr", *sandbox._layout(), *sandbox._etc(False)]
    argv += ["--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp", "--tmpfs", "/run",
             "--bind", ws, ws]
    # The venv, its base interpreter and the hutch source are bound READ-ONLY
    # (the offline worker's pattern) so the kernel can import hutch and the
    # venv's packages without writable access to any of them.
    made_dirs: set[str] = {"-", "/usr"}

    def prepare(target: Path) -> None:
        for directory in reversed((target, *target.parents)):
            value = str(directory)
            if value not in made_dirs:
                argv.append("--dir")
                argv.append(value)
                made_dirs.add(value)

    source_root = Path(__file__).resolve().parents[2]   # .../src — bound read-only so `import hutch` works
    prefix = Path(sys.prefix).resolve()
    base_prefix = Path(sys.base_prefix)
    if prefix.exists() and not prefix.is_relative_to(Path("/usr")):
        prepare(prefix)
        argv += ["--ro-bind", str(prefix), str(prefix)]
    if base_prefix.exists() and base_prefix != Path("/usr") and \
            not base_prefix.is_relative_to(Path("/usr")):
        prepare(base_prefix)
        argv += ["--ro-bind", str(base_prefix), str(base_prefix)]
    if source_root.exists():
        prepare(source_root)
        argv += ["--ro-bind", str(source_root), str(source_root)]
    argv += ["--chdir", ws, "--clearenv"]
    for key, value in sorted(kernel_env(Path(ws), generation).items()):
        argv += ["--setenv", key, value]
    argv += ["--", str(Path(sys.executable).resolve()), "-m", "hutch.workspace.kernel",
             "--workspace", ws, "--generation", str(int(generation))]
    limits = [f"--cpu={policy.cpu_seconds}", f"--fsize={policy.fsize_mb * 1024 * 1024}",
              f"--nofile={policy.nofile}", f"--as={policy.memory_mb * 1024 * 1024}", "--core=0"]
    prlimit = shutil.which("prlimit")
    if not prlimit:
        raise ContainmentUnavailable("strict sandbox requires prlimit for CPU, memory, process and file limits")
    if os.environ.get("HUTCH_OFFLINE_RUN") == "1":
        # The outer offline worker scope already owns the cgroup caps.
        return [prlimit, *limits, "--", *argv]
    systemd_run = shutil.which("systemd-run")
    if not systemd_run:
        raise ContainmentUnavailable("strict sandbox requires systemd-run for the delegated cgroup")
    return [systemd_run, "--user", "--scope", "--quiet",
            f"--property=MemoryMax={policy.memory_mb}M", f"--property=TasksMax={policy.processes}",
            "--", prlimit, *limits, "--", *argv]


def _contained_spawn(workspace: Path, generation: int) -> tuple[subprocess.Popen, dict[str, Any]]:
    """The default spawner: build the strict argv, start the child in its own
    session, and wait (bounded) for the protocol hello. No hello means no
    session — the failure is loud, never a half-open channel."""
    argv = kernel_argv(workspace, generation)
    try:
        proc = subprocess.Popen(
            argv, cwd=workspace,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            start_new_session=True,       # own process group: teardown ends the tree
        )
    except OSError as exc:
        raise ContainmentUnavailable(f"could not start the contained kernel: {exc}") from None
    hello = _read_hello(proc, timeout=30.0)
    if hello is None:
        from ..tools.base import ProcRegistry
        registry = ProcRegistry()
        registry.register(proc, "workspace-kernel")
        survivors = registry.terminate(proc, grace=0.5)   # verified teardown of the failed start
        stderr_tail = _drain_now(proc.stderr, limit=2000)
        raise ContainmentUnavailable(
            "the contained kernel did not start (no protocol hello; "
            f"stderr: {stderr_tail or 'empty'}; survivors: {len(survivors)})")
    return proc, env_fingerprint()


def _read_hello(proc: subprocess.Popen, timeout: float) -> dict[str, Any] | None:
    """Bounded wait for the child's first protocol line (raw fd reads only:
    the buffered reader API is never used on the child's stdout)."""
    stdout = proc.stdout
    if stdout is None:
        return None
    fd = stdout.fileno()
    deadline = time.monotonic() + timeout
    buffer = bytearray()
    while time.monotonic() < deadline and proc.poll() is None:
        ready, _, _ = select.select([fd], [], [], 0.1)
        if not ready:
            continue
        try:
            chunk = os.read(fd, 65536)
        except OSError:
            return None
        if not chunk:
            return None
        buffer.extend(chunk)
        if b"\n" in buffer:
            raw, _, _ = bytes(buffer).partition(b"\n")
            try:
                return protocol.decode_message(raw.decode("utf-8", "replace"))
            except ValueError:
                return None
    return None


def _drain_now(stream: Any, limit: int = 4096) -> str:
    """Best-effort bounded drain of a pipe's buffered bytes (diagnostics)."""
    if stream is None:
        return ""
    data = bytearray()
    try:
        while len(data) < limit:
            chunk = stream.read1(4096) if hasattr(stream, "read1") else stream.read(4096)
            if not chunk:
                break
            data.extend(chunk)
    except (OSError, ValueError):
        pass
    return data.decode("utf-8", "replace")[:limit]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class _Inflight:
    """State of the one exec that may be running."""

    __slots__ = ("id", "receipt", "abort", "done", "unconfirmed")

    def __init__(self, request_id: str):
        self.id = request_id
        self.receipt: dict[str, Any] | None = None
        self.abort = threading.Event()
        self.done = threading.Event()
        self.unconfirmed = False


class WorkspaceManager:
    """Owns the conversation's kernel process, its store row, and the
    one-exec-at-a-time discipline."""

    def __init__(self, store: Store, conversation_id: str, workspace_dir: Path | str, *,
                 spawn: SpawnFn | None = None,
                 now: Callable[[], str] = _utc_now_iso):
        if not conversation_id or any(bad in conversation_id for bad in ("/", "\\", "..")) \
                or conversation_id.startswith("."):
            raise ValueError(f"conversation id is not usable as a workspace name: {conversation_id!r}")
        self._store = store
        self._conversation_id = conversation_id
        self._workspace_dir = Path(workspace_dir)
        self._spawn: SpawnFn = spawn or _contained_spawn
        self._now = now
        self._lock = threading.RLock()
        self._write_lock = threading.Lock()
        self._exec_gate = threading.Lock()    # held for the duration of one exec
        self._proc: Optional[subprocess.Popen] = None
        self._registry: Any = None            # ProcRegistry that owns the child's group record
        self._generation = self._stored_generation()
        self._reserved_generation: int | None = None
        self._ordinal = 0
        self._state = "stopped"               # stopped | ready | busy | lost
        self._inflight: _Inflight | None = None
        self._last_error = ""

    # ------------------------------------------------------------- introspection

    @property
    def conversation_id(self) -> str:
        return self._conversation_id

    @property
    def workspace_dir(self) -> Path:
        return self._workspace_dir

    def session_info(self) -> dict[str, Any]:
        with self._lock:
            proc = self._proc
            return {
                "conversation_id": self._conversation_id,
                "status": self._state,
                "generation": self._generation,
                "ordinal": self._ordinal,
                "workspace_dir": str(self._workspace_dir),
                "child_alive": bool(proc is not None and proc.poll() is None),
                "last_error": self._last_error,
                "store": self._store.get_workspace_session(self._conversation_id),
            }

    # ------------------------------------------------------------ store plumbing

    def _stored_generation(self) -> int:
        row = self._store.get_workspace_session(self._conversation_id)
        return int(row["generation"]) if row else 0

    def _mark_expired(self) -> None:
        """Record honestly that the current environment died (active -> expired)."""
        row = self._store.get_workspace_session(self._conversation_id)
        if not row or row["status"] != "active":
            return
        try:
            self._store.transition_workspace_session(
                self._conversation_id, "expired", expected_generation=int(row["generation"]))
        except (RevisionConflict, KeyError, ValueError):
            pass  # a concurrent writer already advanced the row; its generation stands

    def _upsert_active(self, generation: int) -> None:
        fingerprint = json.dumps(env_fingerprint(), separators=(",", ":"))
        self._store.upsert_workspace_session(
            self._conversation_id, generation, str(self._workspace_dir),
            status="active", env_fingerprint=fingerprint)

    # ------------------------------------------------------------------ lifecycle

    def _ensure_dir(self) -> None:
        ws = self._workspace_dir
        if ws.is_symlink() or (ws.exists() and not ws.is_dir()):
            raise ValueError(f"the workspace directory is not a private directory: {ws}")
        ws.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(ws, 0o700)

    def _reserve_generation(self) -> int:
        stored = self._stored_generation()
        if self._reserved_generation is not None and self._reserved_generation >= stored:
            generation = self._reserved_generation
        else:
            generation = max(stored, self._generation) + 1
        self._reserved_generation = None
        return generation

    def _ensure_started(self, procs: Any) -> subprocess.Popen:
        with self._lock:
            if self._proc is not None and self._proc.poll() is None:
                return self._proc
            if self._proc is not None:
                # The previous environment died (run teardown or a crash):
                # in-memory state is gone and the new process is a NEW
                # generation, so consumers can tell the outputs apart.
                self._mark_expired()
                self._last_error = self._last_error or \
                    "previous kernel process was gone; starting a new generation"
            self._ensure_dir()
            generation = self._reserve_generation()
            proc, fingerprint = self._spawn(self._workspace_dir, generation)
            if procs is not None:
                procs.register(proc, "workspace-kernel")
                self._registry = procs
            self._proc = proc
            self._generation = generation
            self._ordinal = 0
            self._state = "ready"
            self._upsert_active(generation)
            return proc

    def _signal_int(self, proc: subprocess.Popen) -> None:
        try:
            proc.send_signal(signal.SIGINT)
        except (ProcessLookupError, OSError, ValueError):
            pass

    def _terminate(self, grace: float = 0.5) -> list[Any]:
        """Verified teardown of the child through its registered group record."""
        with self._lock:
            proc, registry = self._proc, self._registry
            self._proc, self._registry = None, None
            if self._state != "lost":
                self._state = "stopped"
        if proc is None:
            return []
        if registry is not None:
            try:
                survivors = list(registry.terminate(proc, grace=grace))
                return survivors
            except Exception:
                pass
        self._signal_term(proc)
        try:
            proc.wait(timeout=grace)
        except subprocess.TimeoutExpired:
            try:
                proc.kill()
            except (ProcessLookupError, OSError):
                pass
        return []

    def _signal_term(self, proc: subprocess.Popen) -> None:
        try:
            proc.terminate()
        except (ProcessLookupError, OSError, ValueError):
            pass

    def restart(self, *, reason: str = "reset requested") -> dict[str, Any]:
        """Terminate the environment, bump the generation, mark prior outputs
        stale. The next execution starts the new generation's process.

        While a cell is running this refuses (``status: 'busy'``) instead of
        blocking or killing a cell nobody asked to stop; call ``interrupt()``
        first.
        """
        if not self._exec_gate.acquire(blocking=False):
            return {"ok": False, "status": "busy",
                    "error": {"type": "Busy",
                              "value": "a cell is still running; interrupt() it first, then reset"}}
        try:
            old_generation = self._generation
            survivors = self._terminate()
            stored = self._stored_generation()
            if old_generation > 0:
                try:
                    self._store.transition_workspace_session(
                        self._conversation_id, "terminated", expected_generation=old_generation)
                except (RevisionConflict, KeyError, ValueError):
                    pass  # a concurrent writer advanced the row; the upsert below still lands
            new_generation = max(old_generation, stored) + 1
            with self._lock:
                self._generation = new_generation
                self._reserved_generation = new_generation   # the next start() uses exactly this
                self._ordinal = 0
            self._upsert_active(new_generation)
            return {
                "ok": True,
                "generation": new_generation,
                "reason": reason,
                "survivors": len(survivors),
                "stale": {
                    "state": "stale",
                    "generation_ended": old_generation,
                    "generation_started": new_generation,
                },
            }
        finally:
            self._exec_gate.release()

    def interrupt(self) -> dict[str, Any]:
        """SIGINT the in-flight cell; wait a bounded three seconds for the
        protocol ack. Without an ack the receipt is marked
        ``interrupt_unconfirmed`` — never a silent claim of success."""
        with self._lock:
            inflight, proc = self._inflight, self._proc
        if inflight is None or proc is None:
            return {"status": "idle"}
        self._signal_int(proc)
        if inflight.done.wait(INTERRUPT_ACK_SECONDS):
            receipt = inflight.receipt or {}
            return {"status": receipt.get("status", "unknown"), "receipt": receipt}
        inflight.unconfirmed = True
        inflight.abort.set()
        inflight.done.wait(2.0)   # let the reader fabricate the honest receipt
        return {"status": "interrupt_unconfirmed", "receipt": inflight.receipt,
                "offer": "reset — the cell did not confirm it stopped"}

    # -------------------------------------------------------------------- execute

    def execute(self, code: str, timeout_ms: int, *, procs: Any = None) -> dict[str, Any]:
        """Run one cell. Returns a protocol-response dict whose ``status`` is
        one of: ``ok`` (receipt carries the cell outcome), ``busy`` (another
        cell is running; nothing queued), ``error`` (the request could not
        run — e.g. containment unavailable), ``timeout`` (terminated past
        every deadline), ``interrupt_unconfirmed`` (SIGINT not acknowledged),
        or ``lost`` (the kernel died mid-execution)."""
        request_id = protocol.new_request_id()
        if not code or not code.strip():
            return {"op": "exec", "id": request_id, "status": "error",
                    "error": {"type": "ValueError", "value": "code is required"}}
        if not self._exec_gate.acquire(blocking=False):
            return {"op": "exec", "id": request_id, "status": "busy",
                    "error": {"type": "Busy", "value": "another cell is already running in this "
                               "workspace; nothing was queued"}}
        try:
            return self._execute_locked(code, timeout_ms, request_id, procs)
        finally:
            self._exec_gate.release()

    def _execute_locked(self, code: str, timeout_ms: int, request_id: str, procs: Any) -> dict[str, Any]:
        try:
            proc = self._ensure_started(procs)
        except ContainmentUnavailable as exc:
            self._last_error = str(exc)
            return {"op": "exec", "id": request_id, "status": "error",
                    "error": {"type": "ContainmentUnavailable", "value": str(exc)}}
        except (OSError, ValueError) as exc:
            self._last_error = str(exc)
            return {"op": "exec", "id": request_id, "status": "error",
                    "error": {"type": type(exc).__name__, "value": str(exc)}}
        inflight = _Inflight(request_id)
        with self._lock:
            self._inflight = inflight
            self._state = "busy"
        started_at = self._now()
        timeout_seconds = max(0.05, min(float(timeout_ms), 300_000.0) / 1000.0)
        try:
            if not self._send(proc, {"op": "exec", "id": request_id, "code": code,
                                     "timeout_ms": int(timeout_ms)}):
                return self._lost_response(request_id, started_at, code,
                                           "the workspace kernel is not accepting work")
            response = self._read_response(proc, request_id, timeout_seconds, inflight, started_at, code)
            return self._postprocess(response, proc)
        finally:
            with self._lock:
                self._inflight = None
                if self._state in ("busy", "stopped"):
                    alive = self._proc is not None and self._proc.poll() is None
                    self._state = "ready" if alive else "lost"

    def _send(self, proc: subprocess.Popen, request: dict[str, Any]) -> bool:
        data = protocol.encode_message(request).encode("utf-8")
        try:
            stdin = proc.stdin
            if stdin is None:
                return False
            with self._write_lock:
                stdin.write(data)
                stdin.flush()
            return True
        except (BrokenPipeError, OSError, ValueError):
            return False

    def _read_response(self, proc: subprocess.Popen, request_id: str, timeout_seconds: float,
                       inflight: _Inflight, started_at: str, code: str) -> dict[str, Any]:
        soft_deadline = time.monotonic() + timeout_seconds + 1.5   # the child reports first, with tails
        ack_deadline = soft_deadline + INTERRUPT_ACK_SECONDS
        hard_deadline = ack_deadline + PARENT_RESPONSE_MARGIN_SECONDS
        stdout_fd = proc.stdout.fileno() if proc.stdout else -1
        stderr_fd = proc.stderr.fileno() if proc.stderr else -1
        line_buffer = bytearray()
        stderr_seen = 0
        sent_interrupt = False
        stale_counter = [0]     # persists across chunks: unmatched lines accumulate
        while True:
            now = time.monotonic()
            if inflight.abort.is_set():
                receipt = protocol.fabricate_receipt(
                    ordinal=self._next_ordinal(), generation=self._generation,
                    started_at=started_at, finished_at=self._now(),
                    status="interrupt_unconfirmed",
                    source_sha256=protocol.sha256_of_source(code),
                    note="interrupt requested; the kernel did not acknowledge within "
                         f"{INTERRUPT_ACK_SECONDS:.0f}s — whether the cell stopped is unconfirmed")
                self._finish_inflight(inflight, receipt)
                return {"op": "exec", "id": request_id, "status": "interrupt_unconfirmed",
                        "receipt": receipt,
                        "error": {"type": "InterruptUnconfirmed",
                                  "value": "the cell did not acknowledge the interrupt; "
                                           "use reset_workspace for a guaranteed stop"}}
            if now >= hard_deadline:
                survivors = self._terminate()
                self._mark_expired()
                self._last_error = ("cell exceeded every deadline and the kernel never "
                                    "reported; it was terminated")
                receipt = protocol.fabricate_receipt(
                    ordinal=self._next_ordinal(), generation=self._generation,
                    started_at=started_at, finished_at=self._now(), status="timeout",
                    source_sha256=protocol.sha256_of_source(code),
                    note="the kernel never reported the cell's outcome; it was terminated "
                         f"({len(survivors)} survivor(s) after verified teardown) and its "
                         "captured output was lost")
                return {"op": "exec", "id": request_id, "status": "timeout", "receipt": receipt,
                        "error": {"type": "TimeoutError",
                                  "value": "the cell outlived every deadline and was terminated; "
                                           "its output was lost with the process"}}
            if now >= soft_deadline and not sent_interrupt:
                sent_interrupt = True
                self._signal_int(proc)
            timeout = max(0.0, min(hard_deadline - now, 0.05))
            fds = [fd for fd in (stdout_fd, stderr_fd) if fd >= 0]
            readable, _, _ = select.select(fds, [], [], timeout)
            for fd in readable:
                try:
                    chunk = os.read(fd, 65536)
                except OSError:
                    chunk = b""
                if not chunk:
                    if fd == stdout_fd:
                        return self._lost_response(request_id, started_at, code,
                                                   "the workspace kernel exited mid-execution")
                    continue
                if fd == stdout_fd:
                    line_buffer.extend(chunk)
                    response = self._take_line(line_buffer, request_id, inflight,
                                               started_at, code, stale_counter)
                    if response is not None:
                        return response
                elif stderr_seen < 16384:
                    stderr_seen += len(chunk)

    def _take_line(self, line_buffer: bytearray, request_id: str, inflight: _Inflight,
                   started_at: str, code: str, stale_counter: list[int]) -> dict[str, Any] | None:
        """Extract and match one complete protocol line; None keeps waiting."""
        while b"\n" in line_buffer:
            raw, _, rest = bytes(line_buffer).partition(b"\n")
            del line_buffer[:]
            line_buffer.extend(rest)
            if len(raw) > MAX_RESPONSE_LINE_CHARS:
                self._terminate()
                self._mark_expired()
                self._last_error = "the kernel sent an oversized protocol line; it was terminated"
                receipt = protocol.fabricate_receipt(
                    ordinal=self._next_ordinal(), generation=self._generation,
                    started_at=started_at, finished_at=self._now(), status="error",
                    source_sha256=protocol.sha256_of_source(code),
                    note="the kernel exceeded the protocol line bound and was terminated")
                return {"op": "exec", "id": request_id, "status": "lost", "receipt": receipt,
                        "error": {"type": "ProtocolViolation",
                                  "value": "oversized protocol line from the kernel"}}
            try:
                message = protocol.decode_message(raw.decode("utf-8", "replace"))
            except ValueError:
                continue  # unparseable line from the child: skipped, never trusted
            if message.get("id") != request_id:
                stale_counter[0] += 1
                if stale_counter[0] > 16:
                    self._terminate()
                    self._mark_expired()
                    self._last_error = "protocol desync: too many unmatched responses"
                    return self._lost_response(request_id, started_at, code,
                                               "protocol desync with the workspace kernel")
                continue
            self._finish_inflight(inflight, message.get("receipt"))
            return message
        return None

    def _next_ordinal(self) -> int:
        with self._lock:
            self._ordinal += 1
            return self._ordinal

    def _finish_inflight(self, inflight: _Inflight, receipt: dict[str, Any] | None) -> None:
        inflight.receipt = receipt
        inflight.done.set()

    def _lost_response(self, request_id: str, started_at: str, code: str, why: str) -> dict[str, Any]:
        self._terminate()
        self._mark_expired()
        self._last_error = why
        with self._lock:
            self._state = "lost"
        receipt = protocol.fabricate_receipt(
            ordinal=self._next_ordinal(), generation=self._generation,
            started_at=started_at, finished_at=self._now(), status="error",
            source_sha256=protocol.sha256_of_source(code),
            note=why)
        return {"op": "exec", "id": request_id, "status": "lost", "receipt": receipt,
                "error": {"type": "WorkspaceLost", "value": why}}

    def _postprocess(self, response: dict[str, Any], proc: subprocess.Popen) -> dict[str, Any]:
        receipt = response.get("receipt")
        if isinstance(receipt, dict):
            # The manager's generation is authoritative (the child got its via argv).
            receipt["environment_generation"] = self._generation
            try:
                self._ordinal = max(self._ordinal, int(receipt.get("ordinal") or 0))
            except (TypeError, ValueError):
                pass
        with self._lock:
            if proc.poll() is not None:
                self._state = "lost"
        return response

    def close(self) -> None:
        """End the environment now (the run's ProcRegistry would anyway)."""
        self._terminate()


_MANAGERS: dict[tuple[int, str], WorkspaceManager] = {}
_MANAGERS_LOCK = threading.Lock()


def manager_for_conversation(store: Store, conversation_id: str, state_dir: Path | str, *,
                             spawn: SpawnFn | None = None) -> WorkspaceManager:
    """The per-conversation manager registry used by the tools and routes.

    Keyed per (store, conversation). Passing a custom ``spawn`` (tests, or an
    integrator with a different containment substrate) replaces that
    conversation's manager, terminating any child it still owned.
    """
    key = (id(store), conversation_id)
    with _MANAGERS_LOCK:
        manager = _MANAGERS.get(key)
        if manager is not None and spawn is not None:
            manager.close()
            manager = None
        if manager is None:
            manager = WorkspaceManager(store, conversation_id,
                                       workspace_dir_for(state_dir, conversation_id),
                                       spawn=spawn)
            _MANAGERS[key] = manager
        return manager
