"""Durable multi-step jobs: bounded sequences of deterministic handlers and runs.

The storage layer is SQLite, but the *state machine* lives here:

* A job is admitted once per ``(kind, occurrence)`` and never re-admitted.
* Each step is a checkpoint. A step's attempt is claimed before any work starts,
  so a crash can never start the same attempt twice; a step that never produced
  a result is retried only under its own policy, and only when it recorded no
  external effect.
* Run-backed steps reconcile from the run's terminal state and receipts: a
  possible external effect becomes ``unknown`` and blocks the job for review,  it is never replayed automatically.
* Handler steps run on a small worker pool with their own internal bounds; only
  the supervisor loop applies results and writes the database. Handlers must be
  idempotent and effect-free: a handler that dies mid-run leaves no result, is
  sealed as interrupted by the next supervisor, and is retried only under its
  step policy (its inputs are reused, not recreated).

Definition revisions are recorded at admission. If the code's definition
changes while a job is in flight, the job blocks instead of being reinterpreted
against new step semantics.
"""
from __future__ import annotations

import concurrent.futures
import hashlib
import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from .lifecycle import TERMINAL
from .models import Run, Task, iso, utcnow


@dataclass(frozen=True)
class StepSpec:
    """One node of a job definition."""

    key: str
    kind: str                       # "handler" | "run"
    deps: tuple[str, ...] = ()
    retries: int = 0                # extra attempts for an interrupted, effect-free step
    prompt: str = ""                # run steps: static instruction text


@dataclass(frozen=True)
class JobSpec:
    kind: str
    revision: int
    steps: tuple[StepSpec, ...]


@dataclass
class HandlerContext:
    job_id: str
    state_dir: Path
    work_dir: Path

    def ensure_work_dir(self) -> Path:
        path = self.work_dir
        path.mkdir(parents=True, exist_ok=True)
        return path


#: job definitions by kind. Additive; changing a step's meaning requires a new revision.
DEFINITIONS: dict[str, JobSpec] = {}

#: handler implementations, registered by pipelines.py
HANDLERS: dict[str, Callable[[dict, dict, HandlerContext], tuple[dict, str]]] = {}

#: run-step prompt builders, registered by pipelines.py
PROMPT_BUILDERS: dict[str, Callable[[dict, dict, HandlerContext], str]] = {}

#: per-step result appliers that must run on the supervisor loop thread (they may write
#: the database); a handler never touches SQLite itself. Returns an error string or "".
APPLIERS: dict[str, Callable[[object, dict, dict], str]] = {}


def register_applier(name: str, fn: Callable[[object, dict, dict], str]) -> None:
    APPLIERS[name] = fn


def register_job(spec: JobSpec) -> JobSpec:
    DEFINITIONS[spec.kind] = spec
    return spec


def register_handler(name: str, fn: Callable[[dict, dict, HandlerContext], tuple[dict, str]]) -> None:
    HANDLERS[name] = fn


def register_prompt_builder(name: str, fn: Callable[[dict, dict, HandlerContext], str]) -> None:
    PROMPT_BUILDERS[name] = fn


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _hash(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


class JobRunner:
    """Advances jobs from the elected supervisor loop; never blocks it on work."""

    def __init__(self, engine) -> None:
        self.engine = engine
        self.store = engine.store
        self.config = engine.config
        self._pool = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="hutch-job")
        self._inflight: dict[concurrent.futures.Future, tuple[dict, StepSpec, int, str]] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ loop

    def pending(self) -> bool:
        return bool(self._inflight)

    def pump(self) -> None:
        if not getattr(self.engine, "_is_supervisor", False):
            return
        self._collect()
        for job in self.store.running_jobs(limit=4):
            try:
                self._advance(job)
            except Exception as exc:  # a definition bug must not take down the daemon
                self.store.update_job_status(job["id"], "blocked",
                                             f"advance failed: {type(exc).__name__}: {exc}")

    def shutdown(self) -> None:
        with self._lock:
            futures = list(self._inflight)
        for future in futures:
            future.cancel()
        self._pool.shutdown(wait=False, cancel_futures=True)

    # ------------------------------------------------------------- advancement

    def _work_dir(self, job_id: str) -> Path:
        return Path(self.config.state_dir) / "jobs" / job_id

    def _advance(self, job: dict) -> None:
        spec = DEFINITIONS.get(job["kind"])
        if spec is None:
            self.store.update_job_status(job["id"], "blocked", f"unknown job kind: {job['kind']}")
            return
        if int(job["definition_revision"]) != int(spec.revision):
            self.store.update_job_status(
                job["id"], "blocked",
                "the job definition changed since this job was admitted; review it instead of reinterpreting it")
            return
        steps = self.store.job_steps(job["id"])
        by_key: dict[str, list[dict]] = {}
        for step in steps:
            by_key.setdefault(step["step_key"], []).append(step)

        # 1. reconcile run-backed steps whose run is terminal, and orphaned handler steps
        inflight = {(entry[0]["id"], entry[1].key, entry[2]) for entry in self._inflight.values()}
        for step in steps:
            if step["status"] == "running" and step["run_id"]:
                run = self.store.get_run(step["run_id"])
                if run is None:
                    self.store.finish_job_step(job["id"], step["step_key"], step["attempt"], status="failed",
                                               error="the run record for this step is missing")
                    self._block(job, "a step's run record disappeared")
                    return
                if run.status in TERMINAL:
                    self._reconcile_run_step(job, spec, step, run)
                    return
            if (step["status"] == "running" and not step["run_id"]
                    and (job["id"], step["step_key"], step["attempt"]) not in inflight):
                # A handler that was running when its process died (or lost the supervisor
                # role) leaves no result. Handlers are required to be idempotent and
                # effect-free, so the attempt is sealed as interrupted and the step's own
                # retry policy decides whether it runs again.
                self.store.finish_job_step(job["id"], step["step_key"], step["attempt"], status="failed",
                                           output={"interrupted": True},
                                           error="the handler was interrupted before it finished; its inputs are reused")
                return
        if any(step["status"] == "running" for step in steps):
            if job["status"] == "queued":
                self.store.update_job_status(job["id"], "running")
            return

        # 2. find the next unfinished step in definition order
        outputs = {key: [s for s in rows if s["status"] == "succeeded"][-1]["output"]
                   for key, rows in by_key.items() if any(s["status"] == "succeeded" for s in rows)}
        for step_spec in spec.steps:
            rows = by_key.get(step_spec.key, [])
            succeeded = any(row["status"] == "succeeded" for row in rows)
            if succeeded:
                continue
            if not all(any(r["status"] == "succeeded" for r in by_key.get(dep, [])) for dep in step_spec.deps):
                self._block(job, f"step {step_spec.key} is waiting on a dependency that did not succeed")
                return
            prior = rows[-1] if rows else None
            if prior is not None and prior["status"] in ("failed", "unknown", "blocked"):
                attempts = len(rows)
                effect_free = bool(prior["output"].get("interrupted")) and not prior["output"].get("effects")
                if (prior["status"] == "failed" and effect_free and attempts <= step_spec.retries):
                    pass  # retry under policy below
                else:
                    self._block(job, f"step {step_spec.key} ended {prior['status']}: {prior['error'] or 'no detail'}")
                    return
            attempt = len(rows) + 1
            input_hash = _hash({"input": job["input"], "prior": outputs, "revision": spec.revision})
            self._start_step(job, spec, step_spec, attempt, input_hash, outputs)
            return

        # 3. every step succeeded
        self.store.update_job_status(job["id"], "succeeded")

    def _block(self, job: dict, reason: str) -> None:
        self.store.update_job_status(job["id"], "blocked", reason)

    def _start_step(self, job: dict, spec: JobSpec, step: StepSpec, attempt: int,
                    input_hash: str, outputs: dict) -> None:
        context = HandlerContext(job_id=job["id"], state_dir=Path(self.config.state_dir),
                                 work_dir=self._work_dir(job["id"]))
        if step.kind == "handler":
            if not self.store.start_job_step(job["id"], step.key, attempt, input_hash=input_hash):
                return
            future = self._pool.submit(self._run_handler, step, job, outputs, context)
            with self._lock:
                self._inflight[future] = (job, step, attempt, input_hash)
            return
        if step.kind == "run":
            builder = PROMPT_BUILDERS.get(step.prompt or step.key)
            prompt = builder(job["input"], outputs, context) if builder else step.prompt
            run = Run(bot_id=job["bot_id"], prompt=prompt, origin="job", job_id=job["id"], job_step=step.key)
            if not self.store.start_job_step(job["id"], step.key, attempt, input_hash=input_hash, run_id=run.id):
                return
            task = Task(bot_id=job["bot_id"], kind="on_demand", prompt=prompt)
            try:
                self.store.submit_run(run, task)
            except Exception as exc:
                self.store.finish_job_step(job["id"], step.key, attempt, status="failed",
                                           error=f"run could not be admitted: {type(exc).__name__}: {exc}")
                self._block(job, f"step {step.key} could not be admitted")
            return
        self.store.update_job_status(job["id"], "blocked", f"step {step.key} has an unknown kind {step.kind}")

    def _run_handler(self, step: StepSpec, job: dict, outputs: dict,
                     context: HandlerContext) -> tuple[dict, str]:
        """Worker thread: no database access, never raises."""
        handler = HANDLERS.get(step.key)
        if handler is None:
            return {}, "handler is not registered"
        try:
            return handler(job["input"], outputs, context)
        except Exception as exc:  # noqa: BLE001 - report, never propagate into the loop
            return {}, f"{type(exc).__name__}: {' '.join(str(exc).split())[:200]}"

    def _collect(self) -> None:
        done = [future for future in list(self._inflight) if future.done()]
        for future in done:
            with self._lock:
                entry = self._inflight.pop(future, None)
            if entry is None:
                continue
            job, step, attempt, _input_hash = entry
            try:
                output, error = future.result()
            except Exception as exc:  # cancelled
                output, error = {}, f"{type(exc).__name__}"
            if error:
                self.store.finish_job_step(job["id"], step.key, attempt, status="failed", error=error,
                                           output={"interrupted": True})
            else:
                applier = APPLIERS.get(step.key)
                if applier is not None:
                    try:
                        error = applier(self.store, job, output)
                    except Exception as exc:  # noqa: BLE001 - the applier runs on the loop thread
                        error = f"{type(exc).__name__}: {' '.join(str(exc).split())[:200]}"
                if error:
                    self.store.finish_job_step(job["id"], step.key, attempt, status="failed", error=error,
                                               output={"interrupted": True})
                else:
                    self.store.finish_job_step(job["id"], step.key, attempt, status="succeeded", output=output)

    def _reconcile_run_step(self, job: dict, spec: JobSpec, step: dict, run: Run) -> None:
        if run.status.value == "succeeded":
            message = self.store.last_assistant_text(run.id)
            self.store.finish_job_step(job["id"], step["step_key"], step["attempt"], status="succeeded",
                                       output={"run_id": run.id, "message": message, "message_chars": len(message)})
            return
        if run.status.value in ("outcome_unknown", "stopped"):
            self.store.finish_job_step(
                job["id"], step["step_key"], step["attempt"], status="unknown",
                output={"run_id": run.id, "effects": True},
                error=f"run ended {run.status.value}; external effects may have happened and are not replayed")
            self._block(job, f"step {step['step_key']} needs review: {run.status.value}")
            return
        effects = self.store.run_action_count(run.id)
        attempts = len([row for row in self.store.job_steps(job["id"]) if row["step_key"] == step["step_key"]])
        spec_step = next((s for s in spec.steps if s.key == step["step_key"]), None)
        retries = spec_step.retries if spec_step else 0
        if effects == 0 and attempts <= retries and run.exit_reason in ("interrupted", "error"):
            self.store.finish_job_step(job["id"], step["step_key"], step["attempt"], status="failed",
                                       output={"run_id": run.id, "interrupted": True, "effects": 0},
                                       error=f"run was interrupted before any effect ({run.exit_reason}); retrying")
            return
        self.store.finish_job_step(job["id"], step["step_key"], step["attempt"], status="failed",
                                   output={"run_id": run.id, "effects": effects},
                                   error=f"run ended {run.status.value}: {run.error or run.exit_reason or 'no detail'}")
        self._block(job, f"step {step['step_key']} failed")
