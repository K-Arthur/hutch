"""The workspace kernel: the contained child interpreter behind ``run_python``.

Run as ``python -m hutch.workspace.kernel --workspace DIR --generation N``
inside the bubblewrap strict profile (see ``manager.kernel_argv`` for the
argv and the environment allowlist, ``HUTCH_KERNEL=1`` marks this process).
It speaks the JSON-line protocol v1 from :mod:`hutch.workspace.protocol`:

* one persistent namespace per process; each ``exec`` compiles the submitted
  code with ``compile()`` and runs it in that namespace's dict, in-memory
  state survives across cells *within* one environment generation and is gone
  the moment the process ends, which is exactly what the generation number in
  every receipt makes detectable (never silently lost);
* user output never touches the protocol channel: the real stdout fd is
  duplicated for protocol writes and fd 1 is re-pointed at stderr, then
  ``sys.stdout``/``sys.stderr`` are replaced with bounded capture buffers;
* a trailing expression becomes ``result_repr``; a dict/list of scalars
  additionally becomes a bounded table payload preview; a trailing
  ``matplotlib.figure.Figure`` is rendered to a PNG in the workspace only if
  matplotlib is importable (detected extra, never required, stdlib-first);
* ``emit_block(kind, payload, text_fallback="")`` is injected into the
  namespace and validates payloads against the output-block payload models
  in-child when ``hutch.outputblocks`` is importable (the read-only venv
  makes it importable); invalid emissions degrade to a visible text block,  a diagnostic is never swallowed (outputs-failures A.4);
* ``inspect_csv(path)`` is injected and is the same bounded CSV disclosure the
  upload report route serves (``hutch.workspace.csvprobe``), so the model's
  in-kernel view of a uploaded file cannot disagree with the UI's;
* files a cell newly created under the workspace are hashed and reported in
  the bounded ``produced_files`` list; ``hutch_workspace_pending_files()``
  exposes the same convention to the code itself;
* every exception becomes a receipt with a redacted traceback: frame paths
  outside the workspace become ``<redacted>`` and local variables are never
  included;
* a cell over its wall-clock deadline or its output budget is terminated
  honestly: status ``'timeout'``, bounded tails preserved. External
  interrupts (SIGINT from the parent, or an ``interrupt`` protocol message)
  are confirmed by a receipt with status ``'interrupted'``; the parent marks
  ``'interrupt_unconfirmed'`` when no ack arrives, this child never lets
  silence stand for success.

Interruption mechanics, stated plainly: the cell runs in the main thread; a
watchdog thread (deadline), the SIGINT handler, and the reader thread (for
``interrupt`` messages) all call ``_thread.interrupt_main()`` after setting
their flag, raising into the cell. An opt-in cooperative line-event tracer
(``enable_tracer``; used by tests, where real signal delivery is
unavailable) additionally makes flag-only interruption stop pure-Python
spin loops. Submitted-cell frames include opcode events: Python 3.11 may
otherwise emit no further line event for a one-line spin. This optional
diagnostic path is off in normal workers. A single C-level call that never returns cannot be interrupted,the parent's watchdog then terminates the process and reports an honest
fabricated receipt whose counters admit the output was lost.
"""

from __future__ import annotations

import argparse
import builtins
import io
import os
import signal
import sys
import threading
import time
import ast
from datetime import datetime, timezone
from typing import Any, Callable

from . import csvprobe as _csvprobe

from . import protocol
from .protocol import (
    OUTPUT_BUDGET_CHARS,
    RESULT_REPR_CHARS,
    STDOUT_TAIL_CHARS,
    STDERR_TAIL_CHARS,
    TABLE_PREVIEW_ROWS,
)

def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class _BudgetExceeded(KeyboardInterrupt):
    """Raised in the cell when its output budget is spent (reported as
    status 'timeout' , the ask pins that mapping, with tails preserved)."""


class _DeadlineBreached(KeyboardInterrupt):
    """Raised in the cell when its wall-clock deadline is spent."""


class _InterruptRequested(KeyboardInterrupt):
    """Raised in the cell when an external interrupt was requested."""


class _Capture(io.TextIOBase):
    """Bounded stdout/stderr capture: totals always true, tail ring-buffered.

    ``write`` raises :class:`_BudgetExceeded` once the shared budget is spent,
    which terminates the cell from inside its own output call.
    """

    def __init__(self, budget_state: dict[str, int]):
        self._state = budget_state
        self.total = 0
        self._tail = ""

    def writable(self) -> bool:  # pragma: no cover - io API
        return True

    def write(self, text: str) -> int:
        if not text:
            return 0
        self.total += len(text)
        self._state["used"] += len(text)
        if self._state["used"] > self._state["budget"]:
            raise _BudgetExceeded()
        keep = STDOUT_TAIL_CHARS + 1
        self._tail = (self._tail + text)[-keep:]
        return len(text)

    def flush(self) -> None:
        pass

    def tail(self, limit: int) -> str:
        return self._tail[-limit:]


class _Tracer:
    """Cooperative interruption when ``interrupt_main`` is unavailable/stubbed.

    Cell opcode events cover single-line loops without expanding tracing in
    imported modules. This is opt-in diagnostic behavior, not containment.
    """

    __slots__ = ("kernel",)

    def __init__(self, kernel: "Kernel"):
        self.kernel = kernel

    def __call__(self, frame, event, arg):
        if event == 'call' and frame.f_code.co_filename == '<cell>':
            frame.f_trace_opcodes = True
        if event not in ('line', 'opcode'):
            return self
        kernel = self.kernel
        if kernel._budget_spent:
            raise _BudgetExceeded()
        if kernel._deadline is not None and time.monotonic() > kernel._deadline:
            kernel._deadline_breached = True
            raise _DeadlineBreached()
        if kernel._interrupt_flag:
            raise _InterruptRequested()
        return self


class Kernel:
    """One contained session: protocol loop plus a persistent namespace.

    ``proto_write(str)`` and ``readline()`` are the protocol channel;
    ``interrupt_main`` defaults to ``_thread.interrupt_main`` and is
    injectable so tests can run a kernel without signal delivery. This trusted
    callback must be nonblocking, like the default signal dispatcher.
    """

    def __init__(self, *, workspace: str, generation: int,
                 proto_write: Callable[[str], None],
                 readline: Callable[[], str],
                 interrupt_main: Callable[[], None] | None = None,
                 now: Callable[[], str] = _utc_now_iso,
                 output_budget: int = OUTPUT_BUDGET_CHARS,
                 validate_blocks: bool = True,
                 enable_tracer: bool = False):
        self.workspace = workspace
        self.generation = max(1, int(generation))
        try:
            os.chdir(workspace)   # the kernel's world is the workspace (production also gets --chdir ws)
        except OSError:
            pass
        self._proto_write = proto_write
        self._readline = readline
        self._interrupt_main = interrupt_main or _thread_interrupt_main
        self._now = now
        self._budget = output_budget
        self._validate_blocks = validate_blocks
        # In production, interrupts land via signals/_thread.interrupt_main in
        # the main thread and the tracer is pure overhead; tests (which cannot
        # use signal delivery) enable it so flag-based interruption reaches
        # spinning cells deterministically.
        self._enable_tracer = enable_tracer

        self.namespace: dict[str, Any] = self._fresh_namespace()
        self.ordinal = 0
        self.last_receipt: dict[str, Any] | None = None
        # per-exec interrupt state (all mutated on the main thread except the
        # flags the reader/watchdog threads set before interrupting it)
        self._interrupt_flag = False
        self._deadline: float | None = None
        self._deadline_breached = False
        self._budget_spent = False
        self._inflight: dict[str, Any] | None = None
        self._lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._payload_blocks: list[dict[str, Any]] = []
        self._emitted_errors: list[str] = []
        self._pending_snapshot: dict[str, tuple[int, int, int]] = {}
        self._shutdown = threading.Event()
        self._deadline_lock = threading.Lock()
        self._queue: "list[dict[str, Any]]" = []
        self._queue_cv = threading.Condition()

    # ------------------------------------------------------------------ setup

    def _fresh_namespace(self) -> dict[str, Any]:
        ns: dict[str, Any] = {
            "__name__": "hutch_workspace_cell",
            "__builtins__": builtins,
        }
        ns["emit_block"] = self.emit_block
        ns["hutch_workspace_pending_files"] = self.hutch_workspace_pending_files
        ns["inspect_csv"] = _csvprobe.probe_csv_path
        return ns

    # ------------------------------------------------- injected cell helpers

    def emit_block(self, kind: str, payload: Any, text_fallback: str = "") -> bool:
        """Queue a typed output block from inside a cell. Returns True when
        the payload was accepted.

        The payload is validated against the same output-block models the
        parent applies (when ``hutch.outputblocks`` is importable, it is,
        via the read-only venv binding). A rejected payload degrades to a
        visible text block carrying the validation error: the diagnostic is
        data, never a console line (outputs-failures A.4).
        """
        if not isinstance(kind, str) or not kind:
            raise ValueError("emit_block: kind must be a non-empty string")
        fallback = text_fallback.strip() or _fallback_for(kind, payload)
        accepted = False
        problem = ""
        if self._validate_blocks:
            envelope = {
                "v": protocol.PROTOCOL_VERSION,
                "id": None,  # assigned by the parent; shape-checked here
                "kind": kind,
                "revision": 1,
                "availability": "ready",
                "text_fallback": fallback[:4000] or "emitted block",
                "provenance": {"run_id": "hutch-workspace", "tool": "run_python"},
                "payload": payload,
            }
            try:
                from hutch.outputblocks import parse_blocks
                blocks, errors = parse_blocks([envelope | {"id": _temp_block_id()}])
                accepted, problem = bool(blocks), (errors[0]["error"] if errors else "")
            except Exception as exc:  # outputblocks unusable in-child: queue raw, parent validates
                accepted, problem = True, f"block validation unavailable in child: {exc!r}"
        else:
            accepted = True
        if not accepted:
            self._emitted_errors.append(problem or f"{kind!r} payload rejected")
            self._payload_blocks.append({
                "kind": "text",
                "text_fallback": fallback,
                "payload": {"content": truncate_for_content(
                    f"emit_block({kind!r}) was rejected: {problem}")},
            })
            return False
        self._payload_blocks.append({"kind": kind, "text_fallback": fallback, "payload": payload})
        return True

    def hutch_workspace_pending_files(self) -> list[dict[str, Any]]:
        """The files this cell has produced so far (bounded, hash-included)."""
        after = protocol.snapshot_workspace(_path(self.workspace))
        return protocol.produced_files_between(self._pending_snapshot, after, _path(self.workspace))

    # ------------------------------------------------------------- protocol

    def hello(self) -> dict[str, Any]:
        return {"op": "hello", "status": "ok", "protocol": protocol.PROTOCOL_VERSION,
                "generation": self.generation, "pid": os.getpid(),
                "python_version": sys.version.split()[0]}

    def handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        """One non-interrupt request, executed synchronously. Shared by the
        serve loop, the busy path, and tests."""
        op = request.get("op")
        rid = request.get("id")
        if op == "exec":
            if self._inflight is not None:
                return {"op": op, "id": rid, "status": "busy"}
            return self._exec(request)
        if op == "ping":
            return {"op": "ping", "id": rid, "status": "ok",
                    "generation": self.generation, "ordinal": self.ordinal}
        if op == "reset_ns":
            if self._inflight is not None:
                return {"op": op, "id": rid, "status": "busy"}
            self.namespace = self._fresh_namespace()
            return {"op": "reset_ns", "id": rid, "status": "ok",
                    "generation": self.generation}
        return {"op": str(op), "id": rid, "status": "unknown_id"}

    def handle_interrupt(self, request: dict[str, Any]) -> dict[str, Any]:
        """The ``interrupt`` protocol op: request the in-flight cell to stop."""
        rid = request.get("id")
        inflight = self._inflight
        if inflight is None or (rid is not None and inflight.get("id") != rid):
            return {"op": "interrupt", "id": rid, "status": "unknown_id"}
        self._interrupt_flag = True
        try:
            self._interrupt_main()
        except RuntimeError:
            pass  # no main-thread hook in this context; the tracer still fires
        return {"op": "interrupt", "id": rid, "status": "ok"}

    def _write_message(self, message: dict[str, Any]) -> None:
        """Thread-safe, complete write of one protocol line (os.write may
        write partially once a line exceeds PIPE_BUF)."""
        data = protocol.encode_message(message).encode("utf-8")
        with self._write_lock:
            view = memoryview(data)
            while view:
                written = self._proto_write(view)
                if written <= 0:
                    raise OSError("protocol channel closed")
                view = view[written:]

    def serve(self) -> None:
        """Protocol loop: a reader thread feeds requests; the main thread
        executes them so interrupts (signal or message) land in the cell."""
        reader = threading.Thread(target=self._read_loop, name="hutch-kernel-reader", daemon=True)
        reader.start()
        self._write_message(self.hello())
        try:
            while True:
                request = None
                try:
                    with self._queue_cv:
                        while not self._queue and not self._shutdown.is_set():
                            self._queue_cv.wait(timeout=0.2)
                        if self._queue:
                            request = self._queue.pop(0)
                except KeyboardInterrupt:
                    # an interrupt aimed at a cell that just finished; the
                    # flag dies with it, the loop goes on
                    continue
                if request is None:
                    break   # shutdown and the queue is drained: the session is over
                response = self.handle_request(request)
                self._write_message(response)
        finally:
            self._shutdown.set()

    def _read_loop(self) -> None:
        try:
            while not self._shutdown.is_set():
                line = self._readline()
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    request = protocol.decode_message(line)
                except ValueError:
                    continue  # a malformed line is dropped, never answered (no echo of hostile input)
                if request.get("op") == "interrupt":
                    # handled on the reader thread: a busy cell must be
                    # interruptible without waiting for the queue
                    self._write_message(self.handle_interrupt(request))
                    continue
                with self._queue_cv:
                    self._queue.append(request)
                    self._queue_cv.notify_all()
        except OSError:
            pass  # stdin/stdout closed: the session is over
        finally:
            self._shutdown.set()
            with self._queue_cv:
                self._queue_cv.notify_all()

    # ------------------------------------------------------------------ exec

    def _exec(self, request: dict[str, Any]) -> dict[str, Any]:
        code = request.get("code")
        rid = request.get("id")
        if not isinstance(code, str) or not code.strip():
            return {"op": "exec", "id": rid, "status": "error",
                    "error": {"type": "ValueError", "value": "exec requires non-empty 'code' code",
                              "redacted_traceback": []}}
        try:
            timeout_ms = int(request.get("timeout_ms") or 0)
        except (TypeError, ValueError):
            timeout_ms = 0
        deadline_ms = max(0, timeout_ms)

        self.ordinal += 1
        ordinal = self.ordinal
        source_sha256 = protocol.sha256_of_source(code)
        started_at = self._now()
        self._pending_snapshot = protocol.snapshot_workspace(_path(self.workspace))
        self._payload_blocks = []
        self._emitted_errors = []
        budget_state = {"used": 0, "budget": self._budget}
        out_cap, err_cap = _Capture(budget_state), _Capture(budget_state)
        self._interrupt_flag = False
        self._deadline_breached = False
        self._budget_spent = False
        self._deadline = (time.monotonic() + deadline_ms / 1000.0) if deadline_ms else None

        receipt: dict[str, Any]
        blocks: list[dict[str, Any]] = []
        error: dict[str, Any] | None = None
        status = "ok"
        result_repr = ""
        table: dict[str, Any] | None = None

        self._inflight = {"id": rid, "ordinal": ordinal}
        active_cell = self._inflight
        watchdog_cancelled = threading.Event()
        watchdog = None
        real_stdout, real_stderr = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = out_cap, err_cap
        try:
            if deadline_ms:
                watchdog = threading.Thread(target=self._watchdog,
                                            args=(self._deadline, watchdog_cancelled, active_cell),
                                            name="hutch-kernel-watchdog", daemon=True)
                watchdog.start()
            if self._enable_tracer:
                sys.settrace(_Tracer(self))
            try:
                value = self._run_cell(code)
            finally:
                sys.settrace(None)
            result_repr = self._safe_repr(value)
            self._maybe_render_figure(value)
            table = protocol.table_preview_from_value(value)
        except KeyboardInterrupt as exc:
            status, error = self._classify_interrupt(exc, out_cap, err_cap)
        except BaseException as exc:  # noqa: BLE001 - the cell is untrusted code; report, never crash the loop
            status = "error"
            error = {"type": type(exc).__name__, "value": str(exc)[:2000],
                     "redacted_traceback": protocol.redacted_traceback(exc, self.workspace)}
        finally:
            # A previous cell's timer may not interrupt a later request. Fence
            # cancellation against deadline dispatch and stop its owned thread.
            with self._deadline_lock:
                watchdog_cancelled.set()
                self._deadline = None
                self._inflight = None
            if watchdog is not None:
                watchdog.join(timeout=.1)
            sys.stdout, sys.stderr = real_stdout, real_stderr

        produced = protocol.produced_files_between(
            self._pending_snapshot, protocol.snapshot_workspace(_path(self.workspace)),
            _path(self.workspace))
        if table is not None:
            blocks.append({"kind": "table", "payload": table,
                           "text_fallback": _table_fallback(table)})
        if self._emitted_errors:
            blocks.append({"kind": "text", "payload": {"content": truncate_for_content(
                "block emission problems in this cell: " + "; ".join(self._emitted_errors))},
                "text_fallback": "Some emitted blocks failed validation in this cell."})
        blocks.extend(self._payload_blocks)
        self._payload_blocks = []

        finished_at = self._now()
        receipt = {
            "ordinal": ordinal,
            "environment_generation": self.generation,
            "started_at": started_at,
            "finished_at": finished_at,
            "source_sha256": source_sha256,
            "status": status,
            "stdout_chars_total": out_cap.total,
            "stderr_chars_total": err_cap.total,
        }
        if status == "timeout":
            receipt["note"] = "cell terminated: output budget exceeded" if self._budget_spent \
                else f"cell terminated after its {deadline_ms}ms deadline"
        self.last_receipt = receipt
        response: dict[str, Any] = {
            # the exec REQUEST was handled; the cell's own outcome lives in
            # receipt.status ('ok'|'error'|'timeout'|'interrupted')
            "op": "exec", "id": rid, "status": "ok",
            "receipt": receipt,
            "stdout_tail": out_cap.tail(STDOUT_TAIL_CHARS),
            "stderr_tail": err_cap.tail(STDERR_TAIL_CHARS),
            "result_repr": protocol.truncate(result_repr, RESULT_REPR_CHARS),
            "blocks": blocks,
            "produced_files": produced,
        }
        if error is not None:
            response["error"] = error
        return response

    def _run_cell(self, code: str) -> Any:
        """Compile and run one cell; a trailing expression is evaluated so its
        value can be auto-emitted as ``result_repr``."""
        tree = ast.parse(code, "<cell>", "exec")
        body, last = tree.body, None
        if body and isinstance(body[-1], ast.Expr):
            last = body.pop()
        prefix = compile(ast.Module(body=body, type_ignores=[]), "<cell>", "exec") if body else None
        ns = self.namespace
        if prefix is not None:
            exec(prefix, ns)  # noqa: S102 - the contained cell IS the product; containment is bwrap, not this exec
        if last is not None:
            expression = compile(ast.Expression(last.value), "<cell>", "eval")
            return eval(expression, ns)  # noqa: S307 - same reasoning
        return None

    def _watchdog(self, end: float, cancelled: threading.Event, active_cell: dict) -> None:
        """Backstop for cells the line-event tracer cannot see (a single
        blocking C call): spend the deadline, then interrupt the main thread."""
        while not cancelled.wait(timeout=max(0.0, min(end - time.monotonic(), 0.05))):
            if self._shutdown.is_set():
                return
            if time.monotonic() >= end:
                with self._deadline_lock:
                    if cancelled.is_set() or self._inflight is not active_cell:
                        return
                    self._deadline_breached = True
                    try:
                        self._interrupt_main()
                    except RuntimeError:
                        pass
                return

    def _classify_interrupt(self, exc: BaseException, out: "_Capture", err: "_Capture") \
            -> tuple[str, dict[str, Any]]:
        if isinstance(exc, _BudgetExceeded) or self._budget_spent or out.total + err.total > self._budget:
            self._budget_spent = True
            return "timeout", {"type": "OutputBudgetExceeded",
                               "value": "the cell exceeded its output budget and was terminated",
                               "redacted_traceback": []}
        if isinstance(exc, _DeadlineBreached) or self._deadline_breached:
            return "timeout", {"type": "TimeoutError",
                               "value": "the cell exceeded its wall-clock deadline and was terminated",
                               "redacted_traceback": []}
        return "interrupted", {"type": "KeyboardInterrupt",
                               "value": "interrupted by request",
                               "redacted_traceback": []}

    def _safe_repr(self, value: Any) -> str:
        try:
            return repr(value)
        except BaseException as exc:  # a hostile __repr__ must not take the receipt down
            return f"<unrepresentable {type(value).__name__}: {type(exc).__name__}>"

    def _maybe_render_figure(self, value: Any) -> None:
        """A trailing matplotlib Figure becomes a PNG in the workspace, ONLY
        when matplotlib is importable (a detected extra, never required; the
        stdlib data path works with nothing installed). The PNG is picked up
        by the produced-files scan like any other file the cell wrote."""
        try:
            import matplotlib
            from matplotlib.figure import Figure
        except ImportError:
            return
        try:
            matplotlib.use("Agg", force=False)   # never reach for a display
        except Exception:
            pass
        if not isinstance(value, Figure):
            return
        base = _path(self.workspace) / f"figure-{self.ordinal}.png"
        path, n = base, 1
        while path.exists():
            path = _path(self.workspace) / f"figure-{self.ordinal}-{n}.png"
            n += 1
        try:
            value.savefig(str(path), format="png")
        except Exception as exc:  # a failed render is a visible note, never a crashed cell
            sys.stderr.write(f"figure render failed: {type(exc).__name__}: {exc}\n")


def _thread_interrupt_main() -> None:
    import _thread
    _thread.interrupt_main()


def _path(workspace: str) -> Path:
    from pathlib import Path
    return Path(workspace)


def _temp_block_id() -> str:
    """Placeholder id for the in-child shape check (the parent assigns the
    real id when it builds the envelope)."""
    return "blk_" + os.urandom(8).hex()


def truncate_for_content(text: str, limit: int = 20_000) -> str:
    return protocol.truncate(text, limit)


def _fallback_for(kind: str, payload: Any) -> str:
    if kind == "table" and isinstance(payload, dict):
        rows = len(payload.get("rows", []))
        return f"Table preview: {rows} of {payload.get('row_total', rows)} rows shown."
    if kind == "chart" and isinstance(payload, dict):
        return f"Chart ({payload.get('kind', 'line')}): {len(payload.get('series', []))} series."
    if kind == "text" and isinstance(payload, dict):
        return truncate_for_content(str(payload.get("content", "")), 300)
    return f"Emitted {kind} block from the Python workspace."


def _table_fallback(table: dict[str, Any]) -> str:
    rows = table.get("rows", [])
    total = table.get("row_total", len(rows))
    return f"Table preview: {len(rows)} of {total} rows shown."


def main(argv: list[str] | None = None) -> int:
    """Child entry: rewire stdio so user output can never corrupt the
    protocol channel, then serve until stdin closes."""
    parser = argparse.ArgumentParser(prog="python -m hutch.workspace.kernel")
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--generation", required=True, type=int)
    parser.add_argument("--output-budget", type=int, default=OUTPUT_BUDGET_CHARS)
    args = parser.parse_args(argv)

    proto_fd = os.dup(1)               # the protocol channel, saved
    os.dup2(2, 1)                      # fd 1 now lands on stderr: even C-level writes cannot corrupt the protocol
    kernel = Kernel(workspace=args.workspace, generation=args.generation,
                    proto_write=lambda data: os.write(proto_fd, data),
                    readline=sys.stdin.readline,
                    output_budget=max(1000, args.output_budget))
    # Python-level prints land in the capture buffers even between cells.
    sys.stdout = _Capture({"used": 0, "budget": max(1000, args.output_budget)})
    sys.stderr = _Capture({"used": 0, "budget": max(1000, args.output_budget)})
    signal.signal(signal.SIGINT, _make_sigint_handler(kernel))
    try:
        kernel.serve()
    finally:
        sys.stdout.flush()
    return 0


def _make_sigint_handler(kernel: Kernel) -> Callable[[int, Any], None]:
    def handler(signum: int, frame: Any) -> None:
        kernel._interrupt_flag = True
        try:
            kernel._interrupt_main()
        except (RuntimeError, ValueError):
            pass
    return handler


if __name__ == "__main__":  # pragma: no cover - exercised via the manager's spawn
    raise SystemExit(main())
