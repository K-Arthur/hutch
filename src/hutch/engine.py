"""Run orchestration: dispatch, execution, caps, transcripts, stopping.

The engine owns what frameworks don't: per-bot single-instance locks, global
concurrency, wall-clock/step/token caps with a hard kill, append-only
transcripts (SQLite + JSONL on disk), approval expiry (fail-closed), and a
scheduler loop that *sleeps until something is due* (PF-5) instead of polling.

Stop (UI-2) is independent of the model loop: it sets the cancel flag, aborts
in-flight model I/O through cancel hooks, unblocks approval waits, and kills
every child process group the run started.
"""

from __future__ import annotations

import json
import os
import threading
import time
import traceback
from datetime import datetime, timedelta
from typing import Callable, Optional

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

#: The scheduler loop sleeps exactly until the next due run or incoming event. This cap is only a
#: safety net: CLOCK_MONOTONIC does not advance while a laptop is suspended, so an unbounded sleep
#: could oversleep a due window after resume. One wake per five minutes is ~zero CPU.
MAX_SLEEP_SECONDS = 300.0

#: how long a cancelled worker gets to unwind before the supervisor abandons it
CANCEL_GRACE_SECONDS = 3.0


class Engine:
    def __init__(self, config: hutchConfig, store: Store, max_concurrent: int | None = None):
        self.config = config
        self.store = store
        self.bus = store.bus
        self.scheduler = Scheduler(store)
        self.max_concurrent = max_concurrent or int(os.environ.get("HUTCH_MAX_CONCURRENT", DEFAULT_MAX_CONCURRENT))
        self._threads: dict[str, threading.Thread] = {}
        self._cancels: dict[str, threading.Event] = {}
        self._gates: dict[str, ApprovalGate] = {}
        self._ctxs: dict[str, ToolContext] = {}
        self._lock = threading.Lock()
        #: local models are scheduled resources (LM-6): batch by loaded model, gate by free slots
        from .hardware import probe
        from .slots import ModelSlots
        self.slots = ModelSlots(store, tier=probe(with_runtimes=False).tier, loaded=_ollama_loaded)
        #: optional hook so a model-slot scheduler (LM-6) can veto/reorder dispatch
        self.slot_filter: Optional[Callable[[list[Run], list[Run]], list[Run]]] = self.slots.filter
        self.slot_reason: Optional[Callable[[Run], object]] = self.slots.reason

    # ------------------------------------------------------------- dispatch

    def submit(self, bot: Bot, prompt: str, kind: str = "on_demand", missed_windows: int = 0,
               origin: str = "manual", plan_id: Optional[str] = None,
               plan_task_id: Optional[str] = None, rehearsal: bool = False, model: str = "") -> Run:
        """Create a queued run; the dispatcher (or run_blocking) executes it.

        ``model`` runs this one run on a different model than the bot's own (the chat switcher)."""
        run = Run(bot_id=bot.id, prompt=prompt, missed_windows=missed_windows, origin=origin,
                  plan_id=plan_id, plan_task_id=plan_task_id, rehearsal=rehearsal, model_override=model)
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
            active = self.store.active_runs()
            pending = sorted((r for r in active if r.status is RunStatus.pending),
                             key=lambda r: r.created_at)
            if self.slot_filter:
                pending = self.slot_filter(pending, active)
            live_bots = {r.bot_id for r in active
                         if r.status in (RunStatus.running, RunStatus.waiting_approval,
                                         RunStatus.loading_model, RunStatus.waiting_human)}
            for run in pending:
                if run.id in self._threads:
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
                if bot.id in started_bots or bot.id in live_bots:
                    continue
                self._start_worker(bot, run)
                started_bots.add(bot.id)
                started += 1
        return started

    def _start_worker(self, bot: Bot, run: Run) -> None:
        if run.model_override:
            bot = bot.model_copy(update={"model": run.model_override})    # this run only; the stored bot is unchanged
        cancel = threading.Event()
        self._cancels[run.id] = cancel
        t = threading.Thread(target=self._execute, args=(bot, run, cancel),
                             name=f"hutch-run-{run.id}", daemon=True)
        self._threads[run.id] = t
        t.start()

    def run_blocking(self, bot: Bot, prompt: str, missed_windows: int = 0,
                     origin: str = "manual:cli", rehearsal: bool = False) -> Run:
        """Create + execute a run in the calling thread (CLI `hutch run`)."""
        run = self.submit(bot, prompt, missed_windows=missed_windows, origin=origin, rehearsal=rehearsal)
        self._execute(bot, run, threading.Event())
        return self.store.get_run(run.id) or run

    # -------------------------------------------------------------- stopping

    def stop_run(self, run_id: str) -> bool:
        """Stop one run: cancel flag, abort model I/O, unblock approvals, kill child processes."""
        run = self.store.get_run(run_id)
        if run is None:
            return False
        cancel = self._cancels.get(run_id)
        if cancel:
            cancel.set()
        gate = self._gates.get(run_id)
        if gate:
            gate.cancel_requested = True
            self.bus.notify(f"approval:wake:{run_id}")
        ctx = self._ctxs.get(run_id)
        if ctx:
            for hook in list(ctx.cancel_hooks):
                try:
                    hook()
                except Exception:
                    pass
            threading.Thread(target=ctx.procs.kill_all, name=f"hutch-kill-{run_id}", daemon=True).start()
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
                with transcript.open("a", encoding="utf-8") as fh:  # append-only mirror
                    fh.write(json.dumps({"seq": ev.seq, "ts": ev.ts, "type": ev.type.value,
                                         "data": ev.data, "hash": ev.hash}, ensure_ascii=False) + "\n")
            except Exception:
                pass  # transcript writes must never kill a run

        run.status = RunStatus.running
        run.started_at = iso(utcnow())
        run.workspace = str(workspace)
        run.owner = str(os.getpid())
        self.store.update_run(run)
        if run.missed_windows:
            emit(Event(run_id=run.id, type=EventType.log,
                       data={"note": f"catch-up run: {run.missed_windows} missed schedule window(s) coalesced"}))
        emit(Event(run_id=run.id, type=EventType.status, data={"status": "running", "origin": run.origin}))

        policy = PolicyEngine(bot.risk_tier, bot.command_rules)
        gate = ApprovalGate(self.store, bot, run, policy, emit)
        self._gates[run.id] = gate
        ctx = ToolContext(bot=bot, run=run, store=self.store, policy=policy, gate=gate,
                          config=self.config, workspace=workspace, emit=emit,
                          dry_run=run.rehearsal)
        self._ctxs[run.id] = ctx
        tools = build_tools(bot.tools, ctx)
        runtime = get_runtime(bot)
        deadline = time.monotonic() + bot.limits.timeout_seconds
        emit(Event(run_id=run.id, type=EventType.log,
                   data={"runtime": runtime.kind, "model": bot.model,
                         "tools": sorted(tools), "limits": bot.limits.model_dump(),
                         **({"rehearsal": True} if run.rehearsal else {})}))

        outcome_status, outcome_reason, error = RunStatus.succeeded, "completed", ""
        result: dict[str, object] = {}
        done = threading.Event()

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
            finally:
                done.set()

        worker = threading.Thread(target=work, daemon=True, name=f"hutch-agent-{run.id}")
        worker.start()

        # Supervise: wake on completion, or when the deadline/cancel needs action. No fixed poll tick
        # beyond a half-second re-check of the cancel flag while a run is actually active.
        cancelled_at: Optional[float] = None
        while not done.wait(timeout=0.5):
            now = time.monotonic()
            if cancel.is_set() and cancelled_at is None:
                cancelled_at = now
            if now > deadline and cancelled_at is None:
                cancel.set()
                cancelled_at = now
                gate.cancel_requested = True
                self.bus.notify(f"approval:wake:{run.id}")
                for hook in list(ctx.cancel_hooks):
                    try:
                        hook()
                    except Exception:
                        pass
                threading.Thread(target=ctx.procs.kill_all, daemon=True).start()
            if cancelled_at is not None and now - cancelled_at > CANCEL_GRACE_SECONDS:
                break  # worker did not unwind in time: abandon the thread, record the outcome

        if not done.is_set():
            if time.monotonic() > deadline:
                outcome_status, outcome_reason = RunStatus.failed, "timeout"
                error = f"run exceeded {bot.limits.timeout_seconds}s wall clock and was killed"
            else:
                outcome_status, outcome_reason = RunStatus.stopped, "stopped"
                error = "stopped by user (the agent loop did not unwind; child processes were killed)"
            emit(Event(run_id=run.id, type=EventType.error, data={"error": error}))
        elif "aborted" in result:
            exc: RunAborted = result["aborted"]  # type: ignore[assignment]
            error = exc.detail or exc.reason
            outcome_reason = exc.reason
            outcome_status = RunStatus.stopped if exc.reason == "stopped" else RunStatus.failed
            if time.monotonic() > deadline and exc.reason == "stopped":
                outcome_status, outcome_reason = RunStatus.failed, "timeout"
                error = f"run exceeded {bot.limits.timeout_seconds}s wall clock and was killed"
            emit(Event(run_id=run.id, type=EventType.error,
                       data={"error": f"run aborted ({outcome_reason}): {error}"}))
        elif "crashed" in result:
            outcome_status, outcome_reason = RunStatus.failed, "error"
            error = f"{result['crashed']}\n{result.get('traceback', '')}"
            emit(Event(run_id=run.id, type=EventType.error, data={"error": str(result['crashed'])}))
        elif cancel.is_set():
            # Stop (or the deadline) arrived while the runtime was finishing: its last tool may have been
            # killed mid-command, so reporting success would be a lie. Stop always wins.
            if time.monotonic() > deadline:
                outcome_status, outcome_reason = RunStatus.failed, "timeout"
                error = f"run exceeded {bot.limits.timeout_seconds}s wall clock and was killed"
            else:
                outcome_status, outcome_reason = RunStatus.stopped, "stopped"
                error = "stopped by user"
            emit(Event(run_id=run.id, type=EventType.error,
                       data={"error": f"run {outcome_reason}: {error}"}))
        else:
            final = str(result.get("final", ""))
            emit(Event(run_id=run.id, type=EventType.log,
                       data={"final_chars": len(final), "steps": run.steps, "tokens": run.tokens}))

        ctx.procs.kill_all(grace=0.5)  # nothing a run started may outlive it
        for finisher in ctx.on_finish:
            try:
                finisher()
            except Exception:
                pass

        run.status = outcome_status
        run.exit_reason = outcome_reason
        run.error = error[:2_000]
        run.finished_at = iso(utcnow())
        emit(Event(run_id=run.id, type=EventType.status,
                   data={"status": outcome_status.value, "reason": outcome_reason}))
        self.store.flush_events()
        self.store.update_run(run)
        self._gates.pop(run.id, None)
        self._cancels.pop(run.id, None)
        self._ctxs.pop(run.id, None)

    # ------------------------------------------------------------- tick/loop

    # ------------------------------------------------------------- recovery

    @staticmethod
    def _pid_alive(pid: str) -> bool:
        try:
            os.kill(int(pid), 0)
        except (ValueError, ProcessLookupError):
            return False
        except PermissionError:
            return True
        try:  # a zombie is not alive for our purposes
            return open(f"/proc/{int(pid)}/stat").read().rsplit(") ", 1)[1][0] != "Z"
        except (OSError, IndexError):
            return True

    def recover_orphans(self) -> list[Run]:
        """Runs whose owning process died (crash, kill -9, power loss) must not stay 'running' forever.

        An orphan would show in "Running now" indefinitely and, via the per-bot single-instance lock, block
        that bot from ever running again. A run owned by a *live* process (another `hutch run`, or this one)
        is never touched.
        """
        recovered: list[Run] = []
        for run in self.store.active_runs():
            if run.status is RunStatus.pending or not run.owner:
                continue
            if run.id in self._threads or self._pid_alive(run.owner):
                continue
            run.status, run.exit_reason = RunStatus.failed, "interrupted"
            run.error = f"the process running this job (pid {run.owner}) exited before it finished"
            run.finished_at = iso(utcnow())
            self.store.append_event(Event(run_id=run.id, type=EventType.error, data={"error": run.error}))
            self.store.append_event(Event(run_id=run.id, type=EventType.status,
                                          data={"status": "failed", "reason": "interrupted"}))
            self.store.flush_events()
            self.store.update_run(run)
            for req in self.store.pending_approvals():
                if req.run_id == run.id:
                    from .models import ApprovalStatus
                    req.status, req.resolved_at, req.decided_by = ApprovalStatus.expired, iso(utcnow()), "interrupted"
                    self.store.update_approval(req)
            recovered.append(run)
        return recovered

    def shutdown(self, timeout: float = 5.0) -> None:
        """Graceful stop for `hutch serve` / the daemon: stop every run and let workers record their
        outcome *before* the database closes. Anything that does not unwind in time is left to
        ``recover_orphans`` on the next start."""
        self.stop_all()
        deadline = time.monotonic() + timeout
        for t in list(self._threads.values()):
            t.join(timeout=max(0.0, deadline - time.monotonic()))
        self.store.flush_events()

    def tick(self) -> list[Run]:
        """One beat: expire approvals, dispatch due schedules, drain the queue."""
        self.recover_orphans()
        expire_stale_approvals(self.store, self.config.default_approval_ttl_seconds)
        created: list[Run] = []
        for bot, missed in self.scheduler.due():
            run = self.submit(bot, bot_prompt_for_schedule(bot), kind="scheduled",
                              missed_windows=missed, origin="schedule")
            self.scheduler.mark_dispatched(bot)
            created.append(run)
            note = {"scheduled_run": run.id, "missed_windows": missed}
            self.store.kv_set(f"schedule:{bot.id}:last_dispatch", json.dumps(note))
        self.dispatch_pending()
        return created

    def next_wakeup(self, now: datetime | None = None) -> float:
        """Seconds until the earliest thing that needs the loop: a due schedule or an approval expiry.

        Queued runs are *not* a timer concern: a run finishing frees capacity and notifies the bus.
        """
        now = now or utcnow()
        best = MAX_SLEEP_SECONDS
        for bot in self.store.list_bots():
            if bot.paused or not bot.schedule:
                continue
            nxt = self.scheduler.next_fire(bot, now)
            if nxt is not None:
                best = min(best, (nxt - now).total_seconds())
        for req in self.store.pending_approvals():
            try:
                exp = (datetime.fromisoformat(req.expires_at) if req.expires_at
                       else datetime.fromisoformat(req.created_at) + timedelta(seconds=req.ttl_seconds))
            except ValueError:
                continue
            best = min(best, (exp - now).total_seconds())
        return max(0.05, best)

    def run_loop(self, stop: threading.Event, on_tick: Callable[[list[Run]], None] | None = None) -> None:
        """Dispatch loop: tick, then sleep until the next due time or a bus event (PF-5)."""
        while not stop.is_set():
            seen = {"work": self.bus.version("work")}  # read BEFORE working: no lost wake-ups
            try:
                runs = self.tick()
                if on_tick:
                    on_tick(runs)
                timeout = self.next_wakeup()
            except Exception:
                traceback.print_exc()
                timeout = 5.0
            self.bus.wait_any(seen, timeout=timeout)

    def start_background(self) -> tuple[threading.Thread, threading.Event]:
        """Run the loop on a thread (used by `hutch serve`). Returns (thread, stop_event)."""
        stop = threading.Event()
        t = threading.Thread(target=self.run_loop, args=(stop,), name="hutch-scheduler", daemon=True)
        t.start()
        return t, stop

    def run_daemon(self, on_tick=None) -> None:
        """Foreground daemon loop (Ctrl-C to stop)."""
        import signal
        stopping = threading.Event()

        def _sig(_sig, _frm):
            stopping.set()
            self.bus.notify("work", remote=False)

        try:
            signal.signal(signal.SIGINT, _sig)
            signal.signal(signal.SIGTERM, _sig)
        except ValueError:  # not on main thread (tests)
            pass
        self.run_loop(stopping, on_tick)

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


def _ollama_loaded() -> set[str]:
    """Models Ollama currently has resident, as ``ollama/<name>`` (1 s timeout: dispatch must never stall on it)."""
    from .runtime.ladder import get_provider
    prov = get_provider("ollama", None)
    return {f"ollama/{m.get('name') or m.get('model')}" for m in prov.ps(timeout=1.0)}


def bot_prompt_for_schedule(bot: Bot) -> str:
    """Prompt used for scheduled runs — stable and self-describing."""
    when = utcnow().strftime("%Y-%m-%d %H:%M UTC")
    return (
        f"[scheduled run — {when}]\n{bot.description or bot.name}: "
        f"{bot.instructions or 'execute your standing task and write a report to the workspace.'}"
    )
