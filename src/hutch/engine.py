"""Run orchestration: dispatch, execution, caps, transcripts, stopping.

The engine owns what frameworks don't: per-bot single-instance locks, global
concurrency, wall-clock/step/token caps with a hard kill, append-only
transcripts (SQLite + JSONL on disk), and approval expiry (fail-closed).
"""

from __future__ import annotations

import json
import threading
import time
import traceback
from typing import Optional

from .approvals import ApprovalGate, expire_stale_approvals
from .config import hutchConfig
from .models import (
    Bot,
    Event,
    EventType,
    Run,
    RunStatus,
    Task,
    iso,
    utcnow,
)
from .runtime import RunAborted, get_runtime
from .safety import PolicyEngine
from .scheduler import Scheduler
from .store import Store
from .tools import ToolContext, build_tools

DEFAULT_MAX_CONCURRENT = 2


class Engine:
    def __init__(self, config: hutchConfig, store: Store, max_concurrent: int = DEFAULT_MAX_CONCURRENT):
        self.config = config
        self.store = store
        self.scheduler = Scheduler(store)
        self.max_concurrent = max_concurrent
        self._threads: dict[str, threading.Thread] = {}
        self._cancels: dict[str, threading.Event] = {}
        self._gates: dict[str, ApprovalGate] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------- dispatch

    def submit(self, bot: Bot, prompt: str, kind: str = "on_demand",
               missed_windows: int = 0) -> Run:
        """Create a queued run; the dispatcher (or run_blocking) executes it."""
        run = Run(bot_id=bot.id, prompt=prompt, missed_windows=missed_windows)
        self.store.create_run(run)
        self.store.enqueue_task(Task(bot_id=bot.id, kind=kind, prompt=prompt))
        # attach the task to this run so it is marked done when the run finishes
        task = self.store.next_task(bot.id)
        if task and task.prompt == prompt and task.kind == kind:
            run.task_id = task.id
            self.store.update_run(run)
            self.store.finish_task(task.id)
        return run

    def dispatch_pending(self) -> int:
        """Start pending runs while capacity allows. Returns number started."""
        started = 0
        with self._lock:
            self._reap_threads()
            started_bots: set[str] = set()
            for run in self.store.active_runs():
                if run.status is not RunStatus.pending or run.id in self._threads:
                    continue
                if len(self._threads) >= self.max_concurrent:
                    break
                bot = self.store.get_bot(run.bot_id)
                if bot is None:
                    run.status, run.exit_reason = RunStatus.failed, "bot deleted"
                    run.finished_at = iso(utcnow())
                    self.store.update_run(run)
                    continue
                # Per-bot single-instance lock. started_bots closes the race where
                # two pending runs of one bot pass the store-status check together.
                if bot.id in started_bots:
                    continue
                if any(
                    r.id != run.id and r.status in (RunStatus.running, RunStatus.waiting_approval)
                    for r in self.store.active_runs() if r.bot_id == bot.id
                ):
                    continue
                self._start_worker(bot, run)
                started_bots.add(bot.id)
                started += 1
        return started

    def _start_worker(self, bot: Bot, run: Run) -> None:
        cancel = threading.Event()
        self._cancels[run.id] = cancel
        t = threading.Thread(target=self._execute, args=(bot, run, cancel),
                             name=f"hutch-run-{run.id}", daemon=True)
        self._threads[run.id] = t
        t.start()

    def run_blocking(self, bot: Bot, prompt: str, missed_windows: int = 0) -> Run:
        """Create + execute a run in the calling thread (CLI `hutch run`)."""
        run = self.submit(bot, prompt, missed_windows=missed_windows)
        self._execute(bot, run, threading.Event())
        return run

    # -------------------------------------------------------------- stopping

    def stop_run(self, run_id: str) -> bool:
        run = self.store.get_run(run_id)
        if run is None:
            return False
        cancel = self._cancels.get(run_id)
        if cancel:
            cancel.set()
        gate = self._gates.get(run_id)
        if gate:
            gate.cancel_requested = True
        if run.status is RunStatus.pending:
            run.status, run.exit_reason = RunStatus.stopped, "stopped before start"
            run.finished_at = iso(utcnow())
            self.store.update_run(run)
        return True

    def stop_all(self) -> int:
        n = 0
        for run in self.store.active_runs():
            if self.stop_run(run.id):
                n += 1
        return n

    # ------------------------------------------------------------ execution

    def _execute(self, bot: Bot, run: Run, cancel: threading.Event) -> None:
        run_dir = self.config.run_dir(bot.name, run.id)
        workspace = run_dir / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        transcript = run_dir / "transcript.jsonl"

        def emit(ev: Event) -> None:
            try:
                self.store.append_event(ev)
                with transcript.open("a", encoding="utf-8") as fh:  # append-only
                    fh.write(json.dumps({"id": ev.id, "ts": ev.ts, "type": ev.type.value, "data": ev.data},
                                        ensure_ascii=False) + "\n")
            except Exception:
                pass  # transcript writes must never kill a run

        run.status = RunStatus.running
        run.started_at = iso(utcnow())
        run.workspace = str(workspace)
        self.store.update_run(run)
        if run.missed_windows:
            emit(Event(run_id=run.id, type=EventType.log,
                       data={"note": f"catch-up run: {run.missed_windows} missed schedule window(s) coalesced"}))
        emit(Event(run_id=run.id, type=EventType.status, data={"status": "running"}))

        policy = PolicyEngine()
        gate = ApprovalGate(self.store, bot, run, policy, emit)
        self._gates[run.id] = gate
        ctx = ToolContext(bot=bot, run=run, store=self.store, policy=policy, gate=gate,
                          config=self.config, workspace=workspace, emit=emit)
        tools = build_tools(bot.tools, ctx)
        runtime = get_runtime(bot)
        deadline = time.monotonic() + bot.limits.timeout_seconds
        emit(Event(run_id=run.id, type=EventType.log,
                   data={"runtime": runtime.kind, "model": bot.model,
                         "tools": sorted(tools), "limits": bot.limits.model_dump()}))

        outcome_status, outcome_reason, error = RunStatus.succeeded, "completed", ""
        result: dict[str, object] = {}

        def stop() -> bool:
            return cancel.is_set() or time.monotonic() > deadline

        def work() -> None:
            try:
                result["final"] = runtime.execute(run, ctx, tools, stop)
            except RunAborted as exc:
                result["aborted"] = exc
            except Exception as exc:  # engine/runtime bug — keep the run, lose nothing
                result["crashed"] = exc
                result["traceback"] = traceback.format_exc(limit=6)

        worker = threading.Thread(target=work, daemon=True, name=f"hutch-agent-{run.id}")
        worker.start()
        worker.join(timeout=max(1.0, deadline - time.monotonic() + 5))

        if worker.is_alive():
            cancel.set()
            gate.cancel_requested = True
            outcome_status, outcome_reason = RunStatus.failed, "timeout"
            error = f"run exceeded {bot.limits.timeout_seconds}s wall clock and was killed"
            emit(Event(run_id=run.id, type=EventType.error, data={"error": error}))
        elif "aborted" in result:
            exc: RunAborted = result["aborted"]  # type: ignore[assignment]
            error = exc.detail or exc.reason
            outcome_reason = exc.reason
            outcome_status = RunStatus.stopped if exc.reason == "stopped" else RunStatus.failed
            emit(Event(run_id=run.id, type=EventType.error,
                       data={"error": f"run aborted ({exc.reason}): {error}"}))
        elif "crashed" in result:
            outcome_status, outcome_reason = RunStatus.failed, "error"
            error = f"{result['crashed']}\n{result.get('traceback', '')}"
            emit(Event(run_id=run.id, type=EventType.error, data={"error": str(result['crashed'])}))
        else:
            final = str(result.get("final", ""))
            emit(Event(run_id=run.id, type=EventType.log,
                       data={"final_chars": len(final), "steps": run.steps, "tokens": run.tokens}))

        for finisher in ctx.on_finish:
            try:
                finisher()
            except Exception:
                pass

        run.status = outcome_status
        run.exit_reason = outcome_reason
        run.error = error[:2_000]
        run.finished_at = iso(utcnow())
        self.store.update_run(run)
        self._gates.pop(run.id, None)
        self._cancels.pop(run.id, None)
        emit(Event(run_id=run.id, type=EventType.status,
                   data={"status": outcome_status.value, "reason": outcome_reason}))

    # ------------------------------------------------------------- tick/loop

    def tick(self) -> list[Run]:
        """One daemon beat: expire approvals, dispatch due schedules, drain queue."""
        expire_stale_approvals(self.store, self.config.default_approval_ttl_seconds)
        created: list[Run] = []
        for bot, missed in self.scheduler.due():
            run = self.submit(bot, bot_prompt_for_schedule(bot), kind="scheduled",
                              missed_windows=missed)
            self.scheduler.mark_dispatched(bot)
            created.append(run)
            note = {"scheduled_run": run.id, "missed_windows": missed}
            self.store.kv_set(f"schedule:{bot.id}:last_dispatch", json.dumps(note))
        self.dispatch_pending()
        return created

    def run_daemon(self, interval: float = 20.0, on_tick=None) -> None:
        """Foreground daemon loop (Ctrl-C to stop)."""
        import signal
        stopping = threading.Event()

        def _sig(_sig, _frm):
            stopping.set()

        try:
            signal.signal(signal.SIGINT, _sig)
            signal.signal(signal.SIGTERM, _sig)
        except ValueError:  # not on main thread (tests)
            pass
        while not stopping.is_set():
            try:
                runs = self.tick()
                if on_tick:
                    on_tick(runs)
            except Exception:
                traceback.print_exc()
            stopping.wait(interval)

    def _reap_threads(self) -> None:
        for run_id in list(self._threads):
            t = self._threads[run_id]
            if not t.is_alive():
                self._threads.pop(run_id, None)

    @property
    def active_count(self) -> int:
        with self._lock:
            self._reap_threads()
            return len(self._threads)


def bot_prompt_for_schedule(bot: Bot) -> str:
    """Prompt used for scheduled runs — stable and self-describing."""
    when = utcnow().strftime("%Y-%m-%d %H:%M UTC")
    return (
        f"[scheduled run — {when}]\n{bot.description or bot.name}: "
        f"{bot.instructions or 'execute your standing task and write a report to the workspace.'}"
    )
