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

import json
import os
import socket
import sqlite3
import threading
import time
import traceback
import uuid
from pathlib import Path
from datetime import datetime, timedelta
from typing import Callable, Optional

from .approvals import ApprovalGate, expire_stale_approvals
from .config import hutchConfig
from .lifecycle import LIVE, IllegalTransition, LeaseLost
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
                 lease_seconds: float | None = None):
        self.config = config
        self.store = store
        self.bus = store.bus
        self.scheduler = Scheduler(store)
        self.max_concurrent = max_concurrent or int(os.environ.get("HUTCH_MAX_CONCURRENT", DEFAULT_MAX_CONCURRENT))
        #: who this engine is, as written into every lease it takes (host:pid:nonce: unique even after a pid is reused)
        self.owner_id = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:6]}"
        self.lease_seconds = float(lease_seconds or os.environ.get("HUTCH_LEASE_SECONDS", DEFAULT_LEASE_SECONDS))
        self._hb: Optional[threading.Thread] = None
        self._hb_stop = threading.Event()
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
        """Admit work: a queued run and its task, created together in one transaction.

        ``model`` runs this one run on a different model than the bot's own (the chat switcher)."""
        run = Run(bot_id=bot.id, prompt=prompt, missed_windows=missed_windows, origin=origin,
                  plan_id=plan_id, plan_task_id=plan_task_id, rehearsal=rehearsal, model_override=model)
        return self.store.submit_run(run, Task(bot_id=bot.id, kind=kind, prompt=prompt))

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
                self._start_worker(bot, claimed)
                started += 1
        return started

    def _start_worker(self, bot: Bot, run: Run) -> None:
        if run.model_override:
            bot = bot.model_copy(update={"model": run.model_override})    # this run only; the stored bot is unchanged
        cancel = threading.Event()
        self._cancels[run.id] = cancel
        self._ensure_heartbeat()
        t = threading.Thread(target=self._execute, args=(bot, run, cancel),
                             name=f"hutch-run-{run.id}", daemon=True)
        self._threads[run.id] = t
        t.start()

    def run_blocking(self, bot: Bot, prompt: str, missed_windows: int = 0,
                     origin: str = "manual:cli", rehearsal: bool = False) -> Run:
        """Create + execute a run in the calling thread. Goes through the same claim as everything else, so it cannot start
        beside another live run of the same bot (it used to bypass that rule)."""
        run = self.submit(bot, prompt, missed_windows=missed_windows, origin=origin, rehearsal=rehearsal)
        claimed = self.store.claim_run(run.id, self.owner_id, self.lease_seconds)
        if claimed is None:
            self.store.request_cancel(run.id)
            raise BotBusy(f"'{bot.name}' already has a live run; stop it or wait for it to finish")
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
        threading.Thread(target=ctx.procs.kill_all, name=f"hutch-kill-{run_id}", daemon=True).start()

    # -------------------------------------------------------------- stopping

    def stop_run(self, run_id: str) -> bool:
        """Stop one run. The intent is recorded in the database, so it works from any process; if this process owns the run it
        also takes the fast path: cancel flag, abort model I/O, unblock approvals, kill child process groups."""
        run = self.store.request_cancel(run_id)
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
        workdir_error = check_workdir_at_run(bot.workdir, self.config.state_dir)
        if bot.workdir:
            workspace = Path(bot.workdir).resolve()                # the user's own folder: never created, never replaced
        else:
            workspace = run_dir / "workspace"
            workspace.mkdir(parents=True, exist_ok=True)
        run_dir.mkdir(parents=True, exist_ok=True)
        transcript = run_dir / "transcript.jsonl"
        closed = threading.Event()          # set once the run is over: a late worker's events and tool calls are dropped
        degraded: list[str] = []            # audit writes that failed: shown, never silent

        def mirror(ev: Event) -> None:
            """Append-only JSONL mirror. The store calls this for every event, in sequence order, whether it arrived through the
            batched path or an atomic status transition; a failure is collected by the store and reported, not swallowed."""
            with transcript.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"seq": ev.seq, "ts": ev.ts, "type": ev.type.value,
                                     "data": ev.data, "hash": ev.hash}, ensure_ascii=False) + "\n")

        def emit(ev: Event) -> None:
            if closed.is_set():
                return                      # a worker that outlived its run must not extend the transcript
            try:
                self.store.append_event(ev)
            except Exception as exc:
                degraded.append(f"{type(exc).__name__}: {exc}")     # recorded on the run's final event, not swallowed


        # The first step of a run's life. A stop that arrived between the claim and now is noticed here: the run is then
        # 'cancelling' and not allowed to start.
        self.store.attach_sink(run.id, mirror)
        try:
            run = self.store.transition_run(
                run.id, RunStatus.running, fence=run.fence, event={"origin": run.origin},
                fields={"started_at": iso(utcnow()), "workspace": str(workspace), "owner": str(os.getpid())})
        except (IllegalTransition, LeaseLost, KeyError):
            self._finish_unstarted(run)
            self.store.detach_sink(run.id)
            return
        if run.missed_windows:
            emit(Event(run_id=run.id, type=EventType.log,
                       data={"note": f"catch-up run: {run.missed_windows} missed schedule window(s) coalesced"}))

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

        worker = threading.Thread(target=work, daemon=True, name=f"hutch-agent-{run.id}")
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
            threading.Thread(target=ctx.procs.kill_all, daemon=True).start()

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
            if cancelled_at is not None and now - cancelled_at > CANCEL_GRACE_SECONDS:
                break  # worker did not unwind in time: abandon the thread, record the outcome (it is fenced from here on)

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

        ctx.procs.kill_all(grace=0.5)  # nothing a run started may outlive it
        for finisher in ctx.on_finish:
            try:
                finisher()
            except Exception:
                pass

        # An action that began but never recorded how it ended means we cannot say what happened: that is its own outcome,
        # never "failed", and it is never replayed (ADR-0003).
        doubt = self.store.actions_in_doubt(run.id)
        if doubt and outcome_status is not RunStatus.succeeded:
            self.store.mark_actions_unknown(run.id)
            outcome_status = RunStatus.outcome_unknown
            error = (error + "\n" if error else "") + "may have happened: " + "; ".join(d["summary"] or d["tool"] for d in doubt)

        closed.set()                    # from here on this worker's events and tool calls are dropped
        ctx.closed = True
        gate.cancel_requested = True
        data: dict[str, object] = {"reason": outcome_reason}
        degraded.extend(self.store.sink_errors(run.id))      # an unwritable transcript is reported on the final event
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
                                          event=data)
            except (LeaseLost, IllegalTransition, KeyError):
                pass                    # recovery already decided this run's outcome; the owner does not overwrite it
            self.store.flush_events()
        except sqlite3.ProgrammingError:
            return                      # the database was closed under us (shutdown); the lease lapses and recovery decides
        self.store.detach_sink(run.id)
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
        leases existed - when the pid it records is dead. Recovery moves the run to a terminal state **and bumps its fence**, so
        a worker that was only suspended can no longer write to it. A run is never resumed in the middle (ADR-0003): if an action
        began and never recorded its receipt the outcome is `outcome_unknown`, otherwise `failed/interrupted`.
        """
        from .models import ApprovalStatus
        recovered: list[Run] = []
        self.store.release_expired_claims()
        candidates = [r for r in self.store.expired_runs() if r.id not in self._threads]
        candidates += [r for r in self.store.legacy_live_runs()
                       if r.owner and r.id not in self._threads and not self._pid_alive(r.owner)]
        for run in candidates:
            doubt = self.store.actions_in_doubt(run.id)
            if doubt:
                self.store.mark_actions_unknown(run.id)
                to, reason = RunStatus.outcome_unknown, "interrupted"
                error = (f"the process running this job exited while an action was in flight; it may have happened: "
                         + "; ".join(d["summary"] or d["tool"] for d in doubt))
            elif run.status is RunStatus.cancelling or run.cancel_requested:
                to, reason, error = RunStatus.stopped, "stopped", "stopped (its process had already exited)"
            else:
                to, reason = RunStatus.failed, "interrupted"
                owner = run.owner or run.lease_owner
                error = f"the process running this job ({owner}) exited before it finished"
            try:
                done_run = self.store.transition_run(
                    run.id, to, exit_reason=reason, error=error, bump_fence=True,
                    event={"reason": reason, "recovered_by": self.owner_id, "error": error})
            except (IllegalTransition, LeaseLost, KeyError):
                continue                # the owner finished it between our read and our write
            self.store.flush_events()
            for req in self.store.pending_approvals():
                if req.run_id == run.id:
                    req.status, req.resolved_at, req.decided_by = ApprovalStatus.expired, iso(utcnow()), "interrupted"
                    self.store.update_approval(req)
            recovered.append(done_run)
        return recovered

    def shutdown(self, timeout: float = 5.0) -> None:
        """Graceful stop for `hutch serve` / the daemon: stop every run and let workers record their
        outcome *before* the database closes. Anything that does not unwind in time is left to
        ``recover_orphans`` (its lease lapses and another process, or the next start, finishes it)."""
        self.stop_all()
        deadline = time.monotonic() + timeout
        for t in list(self._threads.values()):
            t.join(timeout=max(0.0, deadline - time.monotonic()))
        self._hb_stop.set()
        self.store.flush_events()

    def scheduler_claims(self) -> list[Run]:
        """Claim every due schedule occurrence and create its run. Safe to call from several processes: each occurrence is won
        by exactly one (``Store.submit_scheduled``), and the run is created in the same transaction as the claim."""
        created: list[Run] = []
        for due in self.scheduler.due_claims():
            run = Run(bot_id=due.bot.id, prompt=bot_prompt_for_schedule(due.bot), missed_windows=due.missed, origin="schedule")
            task = Task(bot_id=due.bot.id, kind="scheduled", prompt=run.prompt)
            now = utcnow()
            won = self.store.submit_scheduled(
                run, task, occurrence=iso(due.occurrence), expected_marker=due.marker, new_marker=iso(now),
                claimed_by=self.owner_id, note={"scheduled_run": run.id, "missed_windows": due.missed})
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
        lapse = self.store.next_lease_expiry(exclude_owner=self.owner_id)      # someone else's run whose owner may be gone
        if lapse is not None:
            try:
                best = min(best, (datetime.fromisoformat(lapse) - now).total_seconds() + 1.0)
            except ValueError:
                pass
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
