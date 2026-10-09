"""Run orchestration: dispatch, execution, caps, transcripts, stopping.

The engine owns what frameworks don't: per-bot single-instance locks, global
concurrency, wall-clock/step/token caps with a hard kill, append-only
transcripts (SQLite + JSONL on disk), approval expiry (fail-closed), and a
scheduler loop that *sleeps until something is due* (PF-5) instead of polling.

Ownership is a database fact, not process memory (ADR-0001): a run is *claimed* by one atomic statement that also enforces the
per-bot single-instance rule across processes, the owner keeps a lease alive with a heartbeat, every write the owner makes
carries a fence, and a run whose lease lapses is recovered by whichever process notices first. So `hutch serve`, `hutch daemon`
and `hutch run` can all run at once without double-dispatching, and a worker that lost its run cannot write to it.

Stop (UI-2) is an *intent* in the database (``Store.request_cancel``): any process can record it and the owner acts on it.
In the owning process it also takes the fast path: set the cancel flag, abort in-flight model I/O through cancel hooks, unblock
approval waits, and kill every child process group the run started.
"""

from __future__ import annotations

import os
import signal
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import traceback
import uuid
from pathlib import Path
from datetime import datetime, timedelta
from typing import Callable, Optional

from . import procguard, sandbox
from .approvals import ApprovalGate, expire_stale_approvals
from .config import hutchConfig
from .lifecycle import LIVE, TERMINAL as TERMINAL_STATUSES, IllegalTransition, LeaseLost
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
from .workdir import check_workdir_at_run
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

#: how long a claim stays valid without a heartbeat. The owner renews it every third of this; a run whose owner stops
#: renewing (crash, kill -9, power loss, a suspended laptop) is recovered by the next process that ticks.
DEFAULT_LEASE_SECONDS = 30.0


class BotBusy(Exception):
    """The bot already has a live run (in this or another process), so a second one cannot start."""


class Engine:
    def __init__(self, config: hutchConfig, store: Store, max_concurrent: int | None = None,
                 lease_seconds: float | None = None, executor: str | None = None, owner_id: str | None = None,
                 light: bool = False):
        self.config = config
        self.store = store
        self.bus = store.bus
        self.scheduler = Scheduler(store)
        self.max_concurrent = max_concurrent or int(os.environ.get("HUTCH_MAX_CONCURRENT", DEFAULT_MAX_CONCURRENT))
        #: who this engine is, as written into every lease it takes (host:pid:nonce: unique even after a pid is reused)
        self.owner_id = owner_id or f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:6]}"
        self.lease_seconds = float(lease_seconds or os.environ.get("HUTCH_LEASE_SECONDS", DEFAULT_LEASE_SECONDS))
        #: "thread": explicit in-process compatibility/tests.
        #: "process": production default; every run is its own OS process in its own session.
        self.executor = (executor or os.environ.get("HUTCH_EXECUTOR") or "thread").lower()
        if self.executor not in ("thread", "process"):
            raise ValueError("executor must be 'thread' or 'process'")
        if self.executor == "process" and not procguard.pidfd_available():
            raise RuntimeError("process execution requires Linux /proc boot identity and pidfd signalling support")
        self._procs: dict[str, "subprocess.Popen"] = {}
        self._offline_brokers: dict[str, object] = {}
        self._hb: Optional[threading.Thread] = None
        self._hb_stop = threading.Event()
        self._threads: dict[str, threading.Thread] = {}
        self._cancels: dict[str, threading.Event] = {}
        self._gates: dict[str, ApprovalGate] = {}
        self._ctxs: dict[str, ToolContext] = {}
        self._background_thread: Optional[threading.Thread] = None
        self._background_stop: Optional[threading.Event] = None
        self._is_supervisor = False
        self._lock = threading.Lock()
        #: local models are scheduled resources (LM-6): batch by loaded model, gate by free slots. A worker process runs ONE
        #: run it was handed, so it does not need (or pay for) the dispatch machinery.
        self.slot_filter: Optional[Callable[[list[Run], list[Run]], list[Run]]] = None
        self.slot_reason: Optional[Callable[[Run], object]] = None
        if not light:
            from .hardware import probe
            from .slots import ModelSlots
            self.slots = ModelSlots(store, tier=probe(with_runtimes=False).tier, loaded=_ollama_loaded)
            #: optional hook so a model-slot scheduler (LM-6) can veto/reorder dispatch
            self.slot_filter = self.slots.filter
            self.slot_reason = self.slots.reason
        self.store.register_shutdown(self.shutdown)

    # ------------------------------------------------------------- dispatch

    def submit(self, bot: Bot, prompt: str, kind: str = "on_demand", missed_windows: int = 0,
               origin: str = "manual", plan_id: Optional[str] = None,
               plan_task_id: Optional[str] = None, rehearsal: bool = False, model: str = "") -> Run:
        """Admit work: a queued run and its task, created together in one transaction.

        ``model`` runs this one run on a different model than the bot's own (the chat switcher)."""
        run = Run(bot_id=bot.id, prompt=prompt, missed_windows=missed_windows, origin=origin,
                  plan_id=plan_id, plan_task_id=plan_task_id, rehearsal=rehearsal, model_override=model)
        return self.store.submit_run(run, Task(bot_id=bot.id, kind=kind, prompt=prompt))

    def submit_idempotent(self, bot: Bot, prompt: str, *, idem_key: str, request_hash: str,
                          rehearsal: bool = False, model: str = "") -> tuple[Run, bool]:
        """Submit one versioned manual request with durable retry semantics."""
        run = Run(bot_id=bot.id, prompt=prompt, origin="manual:api:v1",
                  rehearsal=rehearsal, model_override=model)
        task = Task(bot_id=bot.id, kind="on_demand", prompt=prompt)
        return self.store.submit_run_idempotent(run, task, idem_key=idem_key, request_hash=request_hash)

    def dispatch_pending(self) -> int:
        """Claim and start pending runs while capacity allows. Returns number started.

        Several processes may call this at once; ``Store.claim_run`` is what makes each run (and each bot) belong to exactly one."""
        started = 0
        with self._lock:
            self._reap_threads()
            self.store.release_expired_claims()
            active = self.store.active_runs()
            pending = sorted((r for r in active if r.status is RunStatus.pending and not r.lease_owner),
                             key=lambda r: r.created_at)
            if self.slot_filter:
                pending = self.slot_filter(pending, active)
            for run in pending:
                if run.id in self._threads:
                    continue
                if len(self._threads) >= self.max_concurrent:
                    break
                bot = self.store.get_bot(run.bot_id)
                if bot is None:
                    try:
                        self.store.transition_run(run.id, RunStatus.failed, exit_reason="bot deleted", error="bot deleted",
                                                  event={"reason": "bot deleted"})
                    except (IllegalTransition, LeaseLost, KeyError):
                        pass
                    continue
                claimed = self.store.claim_run(run.id, self.owner_id, self.lease_seconds, max_live=self.max_concurrent)
                if claimed is None:
                    continue          # another process took it, this bot is busy elsewhere, or the global cap is reached
                if self._start_worker(bot, claimed):
                    started += 1
        return started

    def _start_worker(self, bot: Bot, run: Run) -> bool:
        try:
            target = bot.model_copy(update={"model": run.model_override}) if run.model_override else bot
            get_runtime(target)
        except RuntimeError as exc:
            self._fail_unavailable_runtime(run, str(exc))
            return False
        offline = bot.inference_mode.value == "offline"
        if offline:
            from .providers.registry import validate_offline_bot
            try:
                validate_offline_bot(bot, model_override=run.model_override, refresh_host=True)
                if self.executor != "process":
                    raise ValueError("Strict offline runs require the supervised process executor")
            except ValueError as exc:
                self._fail_offline_start(run, str(exc))
                return False
        if self.executor == "process":
            try:
                self._start_process(run, bot=bot)
            except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
                broker = self._offline_brokers.pop(run.id, None)
                if broker is not None:
                    broker.close()
                if not offline:
                    raise
                self._fail_offline_start(run, f"could not start the isolated worker: {exc}")
                return False
            return True
        if run.model_override:
            bot = bot.model_copy(update={"model": run.model_override})    # this run only; the stored bot is unchanged
        cancel = threading.Event()
        self._cancels[run.id] = cancel
        self._ensure_heartbeat()
        t = threading.Thread(target=self._execute, args=(bot, run, cancel),
                             name=f"hutch-run-{run.id}", daemon=True)
        self._threads[run.id] = t
        t.start()
        return True

    def _fail_offline_start(self, run: Run, reason: str) -> None:
        try:
            self.store.transition_run(
                run.id, RunStatus.failed, fence=run.fence, exit_reason="offline_unavailable", error=reason,
                event={"reason": "offline_unavailable", "error": reason}, cancel_wins=True)
        except (IllegalTransition, LeaseLost, KeyError):
            pass

    def _fail_unavailable_runtime(self, run: Run, reason: str) -> None:
        """Do not start legacy mock or unconfigured bots; preserve the actionable failure on the run."""
        try:
            self.store.transition_run(
                run.id, RunStatus.failed, fence=run.fence, exit_reason="model_unavailable", error=reason,
                event={"reason": "model_unavailable", "error": reason}, cancel_wins=True)
        except (IllegalTransition, LeaseLost, KeyError):
            pass

    # ------------------------------------------------------ process executor

    def _start_process(self, run: Run, *, bot: Bot | None = None) -> None:
        """Start the run in its own process and session, and watch it. The supervisor's only jobs are to start it, to escalate a
        stop that is ignored, and to recover the run at once if the worker dies without finishing it."""
        log_dir = self.config.run_dir(self._bot_name(run), run.id)
        log_dir.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ, HUTCH_STATE_DIR=str(self.config.state_dir), HUTCH_LEASE_SECONDS=str(self.lease_seconds))
        argv = [sys.executable, "-m", "hutch.worker", run.id, "--owner", self.owner_id, "--fence", str(run.fence)]
        if bot is not None and bot.inference_mode.value == "offline":
            from .offline import OfflineBrokerSet
            from .providers.registry import offline_endpoints_for_bot
            brokers = OfflineBrokerSet(offline_endpoints_for_bot(bot, model_override=run.model_override))
            brokers.start()
            self._offline_brokers[run.id] = brokers
            argv = sandbox.offline_worker_argv(argv, env, str(self.config.state_dir), self.lease_seconds,
                                               brokers.directory)
        with open(log_dir / "worker.log", "ab") as log:
            proc = subprocess.Popen(argv, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
        identity = procguard.identity(proc.pid)
        if identity is not None:
            self.store.add_proc(run.id, proc.pid, proc.pid, identity.starttime, "worker", procguard.boot_id())
        self._procs[run.id] = proc
        try:
            self.store.set_pgid(run.id, run.fence, proc.pid)
        except LeaseLost:
            # The child validates the claim again before execution. Always watch
            # and reap the process we started, even if the claim expired at spawn.
            self._signal_group(proc, signal.SIGTERM)
        self._ensure_heartbeat()
        t = threading.Thread(target=self._watch_process, args=(run, proc), name=f"hutch-watch-{run.id}", daemon=True)
        self._threads[run.id] = t
        t.start()

    def _bot_name(self, run: Run) -> str:
        bot = self.store.get_bot(run.bot_id)
        return bot.name if bot else run.bot_id

    def _watch_process(self, run: Run, proc: "subprocess.Popen") -> None:
        """Wait for the worker. If a stop was requested and the worker has not unwound within the grace, TERM then KILL its whole
        process group. When it exits, make sure the run is not left half-owned: a worker that died without finishing is recovered
        immediately (fence bumped, outcome decided by its receipts) instead of waiting for the lease to lapse."""
        cancel_seen: Optional[float] = None
        sent_term = False
        while True:
            try:
                proc.wait(timeout=0.5)
                break
            except subprocess.TimeoutExpired:
                pass
            cur = self.store.get_run(run.id)
            if cur is None:
                continue
            if cur.status in TERMINAL_STATUSES:
                # the run is finished but the process lingers (a hung child, a stuck finalizer): give it a moment, then end it
                cancel_seen = cancel_seen or time.monotonic()
            elif cur.cancel_requested or cur.status is RunStatus.cancelling:
                cancel_seen = cancel_seen or time.monotonic()
            if cancel_seen is not None:
                waited = time.monotonic() - cancel_seen
                if waited > CANCEL_GRACE_SECONDS + 2.0 and not sent_term:
                    sent_term = True
                    self._signal_group(proc, signal.SIGTERM)
                elif waited > CANCEL_GRACE_SECONDS + 5.0:
                    self._signal_group(proc, signal.SIGKILL)
        cur = self.store.get_run(run.id)
        if cur is not None and cur.status not in TERMINAL_STATUSES:
            self._recover_one(cur, extra_error=f"worker exited with code {proc.returncode} before the run finished",
                              owner_exited=True)
        elif cur is not None:
            left = self._end_recorded_processes(cur)
            if not left:
                self.store.close_procs(run.id)
        self._procs.pop(run.id, None)
        broker = self._offline_brokers.pop(run.id, None)
        if broker is not None:
            broker.close()

    @staticmethod
    def _signal_group(proc: "subprocess.Popen", sig: int) -> None:
        try:
            # The direct child is held unreaped by Popen; never signal a numeric PGID that may have been reused.
            proc.send_signal(sig)
        except (ProcessLookupError, OSError):
            pass

    def run_blocking(self, bot: Bot, prompt: str, missed_windows: int = 0,
                     origin: str = "manual:cli", rehearsal: bool = False) -> Run:
        """Create + execute a run in the calling thread. Goes through the same claim as everything else, so it cannot start
        beside another live run of the same bot (it used to bypass that rule)."""
        if bot.inference_mode.value == "offline":
            raise ValueError("Strict offline needs a supervised process worker; use `hutch run`, `hutch serve` or `hutch daemon`")
        run = self.submit(bot, prompt, missed_windows=missed_windows, origin=origin, rehearsal=rehearsal)
        claimed = self.store.claim_run(run.id, self.owner_id, self.lease_seconds, max_live=self.max_concurrent)
        if claimed is None:
            self.store.request_cancel(run.id)
            same_bot = any(r.bot_id == bot.id and r.id != run.id for r in self.store.active_runs())
            if same_bot:
                raise BotBusy(f"'{bot.name}' already has a live run; stop it or wait for it to finish")
            raise BotBusy(f"the global limit of {self.max_concurrent} concurrent runs is full; wait for a slot")
        self._ensure_heartbeat()
        self._execute(bot, claimed, threading.Event())
        return self.store.get_run(run.id) or run

    # ---------------------------------------------------------- heartbeat

    def _ensure_heartbeat(self) -> None:
        if self._hb is not None and self._hb.is_alive():
            return
        self._hb_stop = threading.Event()
        self._hb = threading.Thread(target=self._heartbeat_loop, args=(self._hb_stop,), name="hutch-heartbeat", daemon=True)
        self._hb.start()

    def _heartbeat_loop(self, stop: threading.Event) -> None:
        """Keep every lease this engine holds alive. If the process stalls (suspend, swap storm) the leases lapse and another
        process recovers the runs; the stalled workers are then fenced out of them when they wake."""
        interval = max(0.1, self.lease_seconds / 3.0)
        while not stop.wait(interval):
            try:
                renewed = set(self.store.renew_leases(self.owner_id, self.lease_seconds))
            except Exception:
                continue
            for run_id in [r for r in list(self._ctxs) if r not in renewed]:
                self._lost(run_id)

    def _lost(self, run_id: str) -> None:
        """A run this engine is still executing is no longer ours (another process recovered it while we were stalled).
        Stop it now: nothing more may start, what it started is killed, and its writes are already fenced."""
        ctx = self._ctxs.get(run_id)
        if ctx is None:
            return
        ctx.closed = True
        cancel = self._cancels.get(run_id)
        if cancel:
            cancel.set()
        gate = self._gates.get(run_id)
        if gate:
            gate.cancel_requested = True
            self.bus.notify(f"approval:wake:{run_id}")
        for hook in list(ctx.cancel_hooks):
            try:
                hook()
            except Exception:
                pass
        ctx.procs.request_cleanup()

    # -------------------------------------------------------------- stopping

    def stop_run(self, run_id: str, *, idem_key: Optional[str] = None,
                 request_hash: Optional[str] = None) -> bool:
        """Stop a run and its persisted descendants, signaling every process this supervisor owns."""
        runs = self.store.request_cancel_tree(run_id, idem_key=idem_key, request_hash=request_hash)
        if runs is None:
            return False
        for run in runs:
            if run.status in TERMINAL_STATUSES:
                continue
            cancel = self._cancels.get(run.id)
            if cancel:
                cancel.set()
            gate = self._gates.get(run.id)
            if gate:
                gate.cancel_requested = True
                self.bus.notify(f"approval:wake:{run.id}")
            ctx = self._ctxs.get(run.id)
            if ctx:
                for hook in list(ctx.cancel_hooks):
                    try:
                        hook()
                    except Exception:
                        pass
                ctx.procs.request_cleanup()
            proc = self._procs.get(run.id)
            if proc is not None and proc.poll() is None:
                self._signal_group(proc, signal.SIGTERM)  # its supervisor escalates if cooperative cleanup stalls
        return True

    def stop_owned(self) -> int:
        """Stop only the runs THIS engine is executing (what a shutting-down dashboard or daemon must do). ``stop_all`` is the
        explicit emergency stop for every active run in the database, whoever owns it."""
        n = 0
        for run_id in list(self._threads):
            if self.stop_run(run_id):
                n += 1
        return n

    def stop_all(self) -> int:
        n = 0
        for run in self.store.active_runs():
            if self.stop_run(run.id):
                n += 1
        return n

    # ------------------------------------------------------------ execution

    def _execute(self, bot: Bot, run: Run, cancel: threading.Event) -> None:
        try:
            runtime = get_runtime(bot)
        except RuntimeError as exc:
            self._fail_unavailable_runtime(run, str(exc))
            return
        run_dir = self.config.run_dir(bot.name, run.id)
        workdir_error = check_workdir_at_run(bot.workdir, self.config.state_dir)
        try:
            if bot.workdir:
                workspace = Path(bot.workdir).resolve()             # the user's own folder: never created, never replaced
            elif bot.workspace_mode == "managed":
                workspace = self.config.ensure_managed_workspace(bot.id)
            else:
                workspace = run_dir / "workspace"
                workspace.mkdir(parents=True, exist_ok=True)
        except (OSError, ValueError) as exc:
            workspace = run_dir / "workspace"
            workdir_error = f"Could not prepare the managed workspace: {exc}"
        run_dir.mkdir(parents=True, exist_ok=True)
        closed = threading.Event()          # set once the run is over: a late worker's events and tool calls are dropped
        degraded: list[str] = []            # audit writes that failed: shown, never silent

        def emit(ev: Event) -> None:
            if closed.is_set():
                return                      # a worker that outlived its run must not extend the transcript
            try:
                ev.owner_fence = run.fence
                self.store.append_event(ev)
            except Exception as exc:
                degraded.append(f"{type(exc).__name__}: {exc}")     # recorded on the run's final event, not swallowed


        # The first step of a run's life. A stop that arrived between the claim and now is noticed here: the run is then
        # 'cancelling' and not allowed to start.
        try:
            run = self.store.transition_run(
                run.id, RunStatus.running, fence=run.fence, event={"origin": run.origin},
                fields={"started_at": iso(utcnow()), "workspace": str(workspace), "owner": str(os.getpid())})
        except (IllegalTransition, LeaseLost, KeyError):
            self._finish_unstarted(run)
            return
        if run.missed_windows:
            emit(Event(run_id=run.id, type=EventType.log,
                       data={"note": f"catch-up run: {run.missed_windows} missed schedule window(s) coalesced"}))

        policy = PolicyEngine(bot.risk_tier, bot.command_rules)
        gate = ApprovalGate(self.store, bot, run, policy, emit)
        self._gates[run.id] = gate
        ctx = ToolContext(bot=bot, run=run, store=self.store, policy=policy, gate=gate,
                          config=self.config, workspace=workspace, emit=emit,
                          headless=not bot.local_browser_handoff, dry_run=run.rehearsal)
        self._ctxs[run.id] = ctx
        # remember every process this run starts, so a supervisor that did not spawn it can still end it after a crash
        ctx.procs.on_register = lambda pid, pgid, st, kind, boot: self.store.add_proc(run.id, pid, pgid, st, kind, boot)
        tools = build_tools(bot.tools, ctx)
        deadline = time.monotonic() + bot.limits.timeout_seconds
        emit(Event(run_id=run.id, type=EventType.log,
                   data={"runtime": runtime.kind, "model": bot.model,
                         "inference_mode": bot.inference_mode.value,
                         "browser_handoff": "local_desktop" if bot.local_browser_handoff else "headless",
                         "tools": sorted(tools), "limits": bot.limits.model_dump(),
                         **({"containment": sandbox.describe(bot)} if "shell" in tools else {}),
                         **({"rehearsal": True} if run.rehearsal else {})}))

        outcome_status, outcome_reason, error = RunStatus.succeeded, "completed", ""
        result: dict[str, object] = {}
        done = threading.Event()

        def stop() -> bool:
            return cancel.is_set() or time.monotonic() > deadline

        def work() -> None:
            try:
                if workdir_error:
                    raise RunAborted("error", workdir_error)
                result["final"] = runtime.execute(run, ctx, tools, stop)
            except RunAborted as exc:
                result["aborted"] = exc
            except LeaseLost as exc:       # recovery took this run away from us: stop touching it
                result["lost"] = exc
            except Exception as exc:  # engine/runtime bug — keep the run, lose nothing
                result["crashed"] = exc
                result["traceback"] = traceback.format_exc(limit=6)
            finally:
                done.set()

        worker = threading.Thread(target=work, daemon=False, name=f"hutch-agent-{run.id}")
        worker.start()

        def begin_cancel() -> None:
            """Wake everything the run is blocked on and start killing what it started."""
            cancel.set()
            gate.cancel_requested = True
            self.bus.notify(f"approval:wake:{run.id}")
            for hook in list(ctx.cancel_hooks):
                try:
                    hook()
                except Exception:
                    pass
            ctx.procs.request_cleanup()

        # Supervise: wake on completion, or when the deadline/cancel needs action. The cancel flag lives in the database (a stop
        # from another process lands there), so it is re-read every half second while the run is actually active.
        cancelled_at: Optional[float] = None
        timed_out = False
        while not done.wait(timeout=0.5):
            now = time.monotonic()
            if cancelled_at is None and cancel.is_set():
                cancelled_at = now                                  # stop_run already ran the hooks in this process
            elif cancelled_at is None and self.store.is_cancel_requested(run.id):
                cancelled_at = now
                begin_cancel()
            elif cancelled_at is None and now > deadline:
                timed_out = True
                cancelled_at = now
                try:
                    self.store.transition_run(run.id, RunStatus.cancelling, fence=run.fence,
                                              event={"reason": "timeout"})
                except (IllegalTransition, LeaseLost, KeyError):
                    pass
                begin_cancel()
            # Python cannot safely kill a thread. Keep this run in `cancelling` until
            # its runtime thread exits; in process mode the outer supervisor can kill
            # the worker process after its grace period.

        worker.join()   # done is set in the finally block; join its last instructions before finalizing

        timed_out = timed_out or time.monotonic() > deadline
        timeout_msg = f"run exceeded {bot.limits.timeout_seconds}s wall clock and was killed"
        if not done.is_set():
            if timed_out:
                outcome_status, outcome_reason, error = RunStatus.failed, "timeout", timeout_msg
            else:
                outcome_status, outcome_reason = RunStatus.stopped, "stopped"
                error = "stopped by user (the agent loop did not unwind; child processes were killed)"
            emit(Event(run_id=run.id, type=EventType.error, data={"error": error}))
        elif "lost" in result:
            outcome_status, outcome_reason, error = RunStatus.failed, "interrupted", str(result["lost"])
        elif "aborted" in result:
            exc: RunAborted = result["aborted"]  # type: ignore[assignment]
            error = exc.detail or exc.reason
            outcome_reason = exc.reason
            outcome_status = RunStatus.stopped if exc.reason == "stopped" else RunStatus.failed
            if timed_out and exc.reason == "stopped":
                outcome_status, outcome_reason, error = RunStatus.failed, "timeout", timeout_msg
            emit(Event(run_id=run.id, type=EventType.error,
                       data={"error": f"run aborted ({outcome_reason}): {error}"}))
        elif "crashed" in result:
            outcome_status, outcome_reason = RunStatus.failed, "error"
            error = f"{result['crashed']}\n{result.get('traceback', '')}"
            emit(Event(run_id=run.id, type=EventType.error, data={"error": str(result['crashed'])}))
        elif cancel.is_set() or self.store.is_cancel_requested(run.id):
            # Stop (or the deadline) arrived while the runtime was finishing: its last tool may have been
            # killed mid-command, so reporting success would be a lie. Stop always wins.
            if timed_out:
                outcome_status, outcome_reason, error = RunStatus.failed, "timeout", timeout_msg
            else:
                outcome_status, outcome_reason, error = RunStatus.stopped, "stopped", "stopped by user"
            emit(Event(run_id=run.id, type=EventType.error,
                       data={"error": f"run {outcome_reason}: {error}"}))
        else:
            final = str(result.get("final", ""))
            emit(Event(run_id=run.id, type=EventType.log,
                       data={"final_chars": len(final), "steps": run.steps, "tokens": run.tokens}))

        for finisher in ctx.on_finish:
            try:
                finisher()
            except Exception:
                pass
        ctx.procs.finish(grace=0.5)  # owned cleanup finishes before status becomes terminal
        if ctx.procs.survivors:
            # Never turn a run terminal while an owned process is still live. A later supervisor retries cleanup.
            left = procguard.describe(ctx.procs.survivors)
            reason = f"cleanup incomplete: still running: {left}"
            try:
                current = self.store.get_run(run.id)
                if current is not None and current.status not in (RunStatus.cancelling, RunStatus.recovering):
                    current = self.store.transition_run(
                        run.id, RunStatus.recovering, fence=run.fence,
                        event={"reason": "cleanup_incomplete", "pids": [p.pid for p in ctx.procs.survivors]},
                        fields={"reason": reason})
                elif current is not None:
                    current.reason = reason
                    self.store.update_run(current)
                if current is not None:
                    self.store.defer_recovery(current, reason)
                self.store.append_event(Event(run_id=run.id, type=EventType.error,
                                              data={"error": reason, "kind": "cleanup_incomplete",
                                                    "pids": [p.pid for p in ctx.procs.survivors]}))
            except (LeaseLost, IllegalTransition, KeyError):
                pass
            closed.set()
            ctx.closed = True
            gate.cancel_requested = True
            try:
                self.store.flush_events()
            finally:
                self._gates.pop(run.id, None)
                self._cancels.pop(run.id, None)
                self._ctxs.pop(run.id, None)
            return
        self.store.close_procs(run.id, keep_pid=os.getpid())

        # An action that began but never recorded how it ended means we cannot say what happened: that is its own outcome,
        # never "failed", and it is never replayed (ADR-0003).
        doubt = self.store.actions_in_doubt(run.id)
        if doubt:
            outcome_status = RunStatus.outcome_unknown
            error = (error + "\n" if error else "") + "may have happened: " + "; ".join(d["summary"] or d["tool"] for d in doubt)

        closed.set()                    # from here on this worker's events and tool calls are dropped
        ctx.closed = True
        gate.cancel_requested = True
        data: dict[str, object] = {"reason": outcome_reason}
        degraded.extend(self.store.sink_errors(run.id))      # observer failures remain visible; mirror delivery has its own ledger
        if degraded:
            data["audit_degraded"] = len(degraded)
            data["audit_error"] = degraded[0][:200]
        try:
            try:
                self.store.update_run(run)  # final accounting (a stale owner is refused here, harmlessly)
            except LeaseLost:
                pass
            try:
                self.store.transition_run(run.id, outcome_status, fence=run.fence, exit_reason=outcome_reason, error=error,
                                          event=data, cancel_wins=True)
            except (LeaseLost, IllegalTransition, KeyError):
                pass                    # recovery already decided this run's outcome; the owner does not overwrite it
            self.store.flush_events()
        except sqlite3.ProgrammingError:
            return                      # the database was closed under us (shutdown); the lease lapses and recovery decides
        self._gates.pop(run.id, None)
        self._cancels.pop(run.id, None)
        self._ctxs.pop(run.id, None)

    def _finish_unstarted(self, run: Run) -> None:
        """A run that was claimed but never started because a stop (or recovery) got there first."""
        try:
            self.store.transition_run(run.id, RunStatus.stopped, fence=run.fence, exit_reason="stopped",
                                      error="stopped before it started", event={"reason": "stopped before start"})
        except (IllegalTransition, LeaseLost, KeyError):
            pass

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
        """Runs whose owner is gone (crash, kill -9, power loss, a long suspend) must not stay 'running' forever.

        An orphan would show in "Running now" indefinitely and, via the per-bot single-instance rule, block that bot from ever
        running again. A run is an orphan when its **lease has lapsed** (the owner stopped heartbeating), or - for rows from before
        leases existed - when the pid it records is dead. Recovery first acquires the expired ownership and bumps its fence in
        one transaction, then verifies process cleanup, and only then decides the outcome. A run is never resumed in the middle
        (ADR-0003): if an action began and never recorded its receipt the outcome is `outcome_unknown`.
        """
        recovered: list[Run] = []
        self.store.release_expired_claims()
        candidates = [r for r in self.store.expired_runs() if r.id not in self._threads]
        candidates += [r for r in self.store.legacy_live_runs()
                       if r.owner and r.id not in self._threads and not self._pid_alive(r.owner)]
        if candidates:
            self._ensure_heartbeat()
        for run in candidates:
            done_run = self._recover_one(run, owner_exited=run.lease_expires_at is None)
            if done_run is not None:
                recovered.append(done_run)
        return recovered

    def _recover_one(self, run: Run, extra_error: str = "", *, owner_exited: bool = False) -> Optional[Run]:
        """Fence an orphan, end its recorded processes, and decide its outcome only after cleanup is verified."""
        owned = self.store.claim_recovery(run, self.owner_id, self.lease_seconds, owner_exited=owner_exited)
        if owned is None:
            return None                    # lease renewed, another supervisor won, or the run changed
        left = self._end_recorded_processes(owned)
        if left:
            detail = f"cleanup incomplete: still running or unverified: {procguard.describe(left)}"
            self.store.defer_recovery(owned, detail)
            self.store.append_event(Event(run_id=run.id, type=EventType.error,
                                          data={"error": detail, "kind": "cleanup_incomplete",
                                                "pids": [p.pid for p in left]}))
            self.store.flush_events()
            return None                    # stopping/recovering remains visible; another supervisor retries after the lease
        doubt = self.store.actions_in_doubt(run.id)
        if doubt:
            to, reason = RunStatus.outcome_unknown, "interrupted"
            error = (f"the process running this job exited while an action was in flight; it may have happened: "
                     + "; ".join(d["summary"] or d["tool"] for d in doubt))
        elif owned.status is RunStatus.cancelling or owned.cancel_requested:
            to, reason, error = RunStatus.stopped, "stopped", "stopped after owned processes were verified gone"
        else:
            to, reason = RunStatus.failed, "interrupted"
            owner = run.owner or run.lease_owner
            error = f"the process running this job ({owner}) exited before it finished"
        if extra_error:
            error += "\n" + extra_error
        try:
            done_run = self.store.transition_run(
                run.id, to, fence=owned.fence, exit_reason=reason, error=error,
                event={"reason": reason, "recovered_by": self.owner_id, "error": error},
                cancel_wins=(to is RunStatus.failed))
        except (IllegalTransition, LeaseLost, KeyError):
            return None                 # a newer owner or state change won before the final decision
        self.store.close_procs(run.id)
        self.store.flush_events()
        return done_run

    def _end_recorded_processes(self, run: Run) -> list:
        """End only processes whose boot and start identity were persisted; unverifiable survivors block terminal status."""
        procs = self.store.live_procs(run.id)
        left = procguard.end_recorded(procs, term_grace=1.0, kill_grace=2.0)
        recorded = {int(p["pgid"]) for p in procs}
        if run.pgid and run.pgid not in recorded:
            left.extend(procguard.unverified_group(run.pgid))
        return left

    def shutdown(self, timeout: float = 5.0) -> None:
        """Graceful stop for `hutch serve` / the daemon: stop every run and let workers record their
        outcome *before* the database closes. Anything that does not unwind in time is left to
        ``recover_orphans`` (its lease lapses and another process, or the next start, finishes it)."""
        deadline = time.monotonic() + timeout
        if self._background_stop is not None:
            self._background_stop.set()
            self.bus.notify("work", remote=False)
        if self._background_thread is not None:
            self._background_thread.join(timeout=max(0.0, deadline - time.monotonic()))
        self.stop_owned()
        for t in list(self._threads.values()):
            t.join(timeout=max(0.0, deadline - time.monotonic()))
        pending = [t for t in self._threads.values() if t.is_alive()]
        if pending:
            # Give process workers a hard stop after the grace period. Their watchers
            # recover the lease and finish the transcript before returning.
            for proc in list(self._procs.values()):
                if proc.poll() is None:
                    self._signal_group(proc, signal.SIGKILL)
            force_deadline = time.monotonic() + 2.0
            for t in pending:
                t.join(timeout=max(0.0, force_deadline - time.monotonic()))
            pending = [t for t in self._threads.values() if t.is_alive()]
        if pending or (self._background_thread is not None and self._background_thread.is_alive()):
            names = ", ".join(t.name for t in pending) or "hutch-scheduler"
            raise RuntimeError(f"cannot close Hutch state while owned threads are still running: {names}")
        self._hb_stop.set()
        if self._hb is not None:
            self._hb.join(timeout=max(0.0, deadline - time.monotonic()))
            if self._hb.is_alive():
                raise RuntimeError("cannot close Hutch state while the lease heartbeat is still running")
        self.store.release_supervisor(self.owner_id)
        self.store.flush_events()

    def scheduler_claims(self) -> list[Run]:
        """Claim every due schedule occurrence and create its run. Safe to call from several processes: each occurrence is won
        by exactly one (``Store.submit_scheduled``), and the run is created in the same transaction as the claim."""
        created: list[Run] = []
        for due in self.scheduler.due_claims():
            run = Run(bot_id=due.bot.id, prompt=bot_prompt_for_schedule(due.bot, due.schedule),
                      missed_windows=due.missed, origin="schedule", schedule_id=due.schedule.id)
            task = Task(bot_id=due.bot.id, kind="scheduled", prompt=run.prompt)
            now = utcnow()
            won = self.store.submit_scheduled(
                run, task, occurrence=iso(due.occurrence), expected_marker=due.marker, new_marker=iso(now),
                claimed_by=self.owner_id, schedule_id=due.schedule.id,
                note={"scheduled_run": run.id, "schedule_id": due.schedule.id,
                      "missed_windows": due.missed})
            if won is not None:
                created.append(won)
        return created

    def tick(self) -> list[Run]:
        """One beat: recover orphans, expire approvals, claim due schedules, drain the queue."""
        self.recover_orphans()
        expire_stale_approvals(self.store, self.config.default_approval_ttl_seconds)
        created = self.scheduler_claims()
        self.dispatch_pending()
        return created

    def next_wakeup(self, now: datetime | None = None) -> float:
        """Seconds until the earliest thing that needs the loop: a due schedule or an approval expiry.

        Queued runs are *not* a timer concern: a run finishing frees capacity and notifies the bus.
        """
        now = now or utcnow()
        best = MAX_SLEEP_SECONDS
        for bot in self.store.list_bots():
            if bot.paused:
                continue
            for schedule in bot.schedules or ([bot.schedule] if bot.schedule else []):
                nxt = self.scheduler.next_fire(bot, now, schedule)
                if nxt is not None:
                    best = min(best, (nxt - now).total_seconds())
        for req in self.store.pending_approvals():
            try:
                exp = (datetime.fromisoformat(req.expires_at) if req.expires_at
                       else datetime.fromisoformat(req.created_at) + timedelta(seconds=req.ttl_seconds))
            except ValueError:
                continue
            best = min(best, (exp - now).total_seconds())
        lapse = self.store.next_lease_expiry(exclude_owner=self.owner_id)      # someone else's run whose owner may be gone
        if lapse is not None:
            try:
                best = min(best, (datetime.fromisoformat(lapse) - now).total_seconds() + 1.0)
            except ValueError:
                pass
        return max(0.05, best)

    def run_loop(self, stop: threading.Event, on_tick: Callable[[list[Run]], None] | None = None) -> None:
        """One leased supervisor owns recovery/scheduling; other web workers only wait for commands and lease expiry."""
        try:
            while not stop.is_set():
                seen = {"work": self.bus.version("work")}  # read BEFORE working: no lost wake-ups
                try:
                    self._is_supervisor = self.store.claim_supervisor(self.owner_id, self.lease_seconds)
                    if self._is_supervisor:
                        runs = self.tick()
                        if on_tick:
                            on_tick(runs)
                        timeout = min(self.next_wakeup(), max(0.1, self.lease_seconds / 3))
                    else:
                        timeout = min(MAX_SLEEP_SECONDS, max(0.1, self.lease_seconds / 3))
                except Exception:
                    traceback.print_exc()
                    timeout = min(5.0, max(0.1, self.lease_seconds / 3))
                self.bus.wait_any(seen, timeout=timeout)
        finally:
            self._is_supervisor = False
            self.store.release_supervisor(self.owner_id)

    def start_background(self) -> tuple[threading.Thread, threading.Event]:
        """Run the loop on a thread (used by `hutch serve`). Returns (thread, stop_event)."""
        stop = threading.Event()
        t = threading.Thread(target=self.run_loop, args=(stop,), name="hutch-scheduler", daemon=True)
        self._background_thread, self._background_stop = t, stop
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


def bot_prompt_for_schedule(bot: Bot, schedule=None) -> str:
    """Prompt used for scheduled runs — stable and self-describing."""
    when = utcnow().strftime("%Y-%m-%d %H:%M UTC")
    schedule = schedule or bot.schedule
    task = schedule.prompt.strip() if schedule else ""
    task = task or bot.instructions or "execute your standing task and write a report to the workspace."
    return (
        f"[scheduled run — {when}]\n{bot.description or bot.name}: "
        f"{task}"
    )
