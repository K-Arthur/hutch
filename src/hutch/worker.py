"""One run, in its own OS process (ADR-0001 / ADR-0004).

    python -m hutch.worker <run_id> --owner <lease_owner> --fence <n>

The supervisor (``Engine`` with ``executor="process"``) claims a run in the database and starts this process in a new session,
so the worker and everything it starts form one process group that can be ended as a unit. The worker verifies the claim, keeps the
lease alive with its own heartbeat, runs the same ``Engine._execute`` as the in-process executor, and exits when the run is terminal.

It deliberately does not depend on its supervisor: if the supervisor dies the worker finishes (or is stopped through the database),
and the next supervisor adopts it. SIGTERM is a cooperative stop: it records the cancel intent and the run unwinds; a worker that does
not react is SIGKILLed by the supervisor after a grace period.
"""

from __future__ import annotations

import argparse
import os
import signal
import sys
import threading

from .config import get_config
from .engine import Engine
from .lifecycle import LIVE, LeaseLost
from .models import RunStatus
from .store import Store

EXIT_OK, EXIT_NOT_OURS, EXIT_MISSING = 0, 3, 4


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="hutch.worker")
    ap.add_argument("run_id")
    ap.add_argument("--owner", required=True, help="the lease owner string the supervisor claimed the run with")
    ap.add_argument("--fence", required=True, type=int)
    args = ap.parse_args(argv)

    config = get_config()
    store = Store(config)
    stop_requested = threading.Event()
    signal_finished = threading.Event()
    signal_worker: threading.Thread | None = None
    parent_watch: threading.Thread | None = None
    try:
        run = store.get_run(args.run_id)
        if run is None:
            print(f"hutch.worker: no such run {args.run_id}", file=sys.stderr)
            return EXIT_MISSING
        if run.lease_owner != args.owner or run.fence != args.fence or run.status is not RunStatus.pending:
            # somebody else owns it, or it already moved: acting on it would be acting without authority
            print(f"hutch.worker: {args.run_id} is not claimed by {args.owner} at fence {args.fence} "
                  f"(status {run.status.value}, owner {run.lease_owner!r}, fence {run.fence})", file=sys.stderr)
            return EXIT_NOT_OURS
        bot = store.get_bot(run.bot_id)
        if bot is None:
            engine = Engine(config, store, owner_id=args.owner, light=True)
            engine._finish_unstarted(run)
            return EXIT_MISSING
        if run.parent_run_id is not None:
            engine = Engine(config, store, owner_id=args.owner, light=True)
            snapshot = store.run_capability_snapshot(run.id)
            try:
                if snapshot is None:
                    raise ValueError("delegated run has no inherited capability snapshot")
                bot = Engine._delegated_bot(bot, snapshot)
            except ValueError as exc:
                engine._fail_unavailable_child_executor(run, str(exc))
                latest = store.get_run(run.id)
                if latest is None or latest.status not in LIVE:
                    return EXIT_OK
                print(f"hutch.worker: {args.run_id} could not enforce delegated capabilities: {exc}", file=sys.stderr)
                return EXIT_NOT_OURS
        elif run.model_override:
            bot = bot.model_copy(update={"model": run.model_override})

        engine = engine if run.parent_run_id is not None else Engine(config, store, owner_id=args.owner, light=True)
        try:
            store.set_pgid(run.id, run.fence, os.getpgrp())
        except LeaseLost:
            print(f"hutch.worker: {args.run_id} claim expired before execution", file=sys.stderr)
            return EXIT_NOT_OURS
        def on_term(_sig, _frm) -> None:
            stop_requested.set()                    # a signal handler only records; a thread does the work

        signal.signal(signal.SIGTERM, on_term)
        signal.signal(signal.SIGINT, on_term)

        def watch_signal() -> None:
            stop_requested.wait()
            if not signal_finished.is_set():
                engine.stop_run(run.id)             # database intent + in-process fast path (hooks, kill children)

        signal_worker = threading.Thread(target=watch_signal, name="hutch-worker-signal", daemon=False)
        signal_worker.start()
        if run.parent_run_id is not None:
            def watch_parent() -> None:
                # A child must not outlive the parent worker that is awaiting it. This
                # also covers a hard parent crash, where no in-process cancel hook runs.
                while not signal_finished.wait(0.25):
                    parent = store.get_run(run.parent_run_id)
                    if (parent is None or parent.status is not RunStatus.running or parent.cancel_requested):
                        engine.stop_run(run.id)
                        return

            parent_watch = threading.Thread(target=watch_parent, name="hutch-child-parent-watch", daemon=False)
            parent_watch.start()
        engine._ensure_heartbeat()
        engine._execute(bot, run, threading.Event())
        engine._hb_stop.set()
        store.flush_events()
        final = store.get_run(run.id)
        return EXIT_OK if final is None or final.status not in LIVE else 1
    finally:
        # A completed run no longer needs signal-to-database translation. Wake the
        # listener on normal completion too; an in-flight stop must finish before
        # persistence closes. Late handlers merely set this already-consumed event.
        signal_finished.set()
        stop_requested.set()
        if signal_worker is not None:
            signal_worker.join()
        if parent_watch is not None:
            parent_watch.join()
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
