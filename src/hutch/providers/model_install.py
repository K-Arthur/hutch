"""Install and remove local models, through the runtime's own model registry.

Only Ollama has one. ``POST /api/pull`` streams ndjson status events ending in
``success``; ``DELETE /api/delete`` removes a model. LM Studio and llama.cpp have no
equivalent, so this module deliberately does not invent a uniform abstraction over them:
a llama.cpp user manages GGUF files themselves, and pretending otherwise would be the
"artificial uniform download mechanism" the brief rules out.

What this module will not do:

* start a download because a model was *selected* - installing is an explicit,
  user-initiated operation with its own confirmation;
* exceed a fixed number of concurrent pulls, or buffer progress without bound;
* claim an install succeeded because the request returned 200. Success means the
  runtime's stream ended with ``success`` **and** the model appears in ``/api/tags``.

Progress is reported from the runtime's own byte counters, so an interrupted pull shows
the bytes it really has. Ollama's blobs are content-addressed and verified by digest, so
re-running an interrupted pull resumes rather than restarting, and this module says so
instead of implementing resume itself.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Optional

from ..models import iso, utcnow
from .base import ProviderError
from .install_errors import (InstallFailure, cancelled_failure, classify_install_error,
                             interrupted_failure, unconfirmed_failure)
from .install_jobs import InstallJob, _apply, _apply_plan
from .install_plan import InstallPlan, build_plan, record_rate
from .locality import CLOUD_TAG
from .model_names import parse_model_name, same_model

#: Two installs at once is plenty for a person on one machine, and bounds both memory
#: and the runtime's own download queue.
MAX_CONCURRENT_INSTALLS = 2
#: A finished job is kept so the UI can read the outcome; older ones are dropped.
MAX_RETAINED_JOBS = 32


def validate_model_name(name: str, *, allow_cloud: bool = False) -> str:
    """Return the canonical model name or refuse it before any request is made.

    The grammar is the runtime's own (see ``model_names``), so real Hugging Face names and
    mixed-case quant tags are accepted. A cloud-tagged model runs on someone else's
    computer, so pulling one is a data-sharing choice: it is refused unless the caller
    passes ``allow_cloud`` after an explicit confirmation.
    """
    parsed = parse_model_name(name)
    canonical = parsed.canonical()
    if not allow_cloud and CLOUD_TAG.search(f"{parsed.model}:{parsed.tag}"):
        raise ValueError(f"'{name}' is a cloud model: it runs on a remote service, not this computer. "
                         "Confirm the data-sharing choice before adding it.")
    return canonical


def _same_model(a: str, b: str) -> bool:
    return same_model(a, b)


class ModelInstaller:
    """A bounded, in-process registry of model installs for one runtime.

    The authoritative record of what is installed is always the runtime's own model list
    (``/api/tags``), never this registry: a job that says ``done`` is *confirmed* against
    the runtime before it is reported as finished, and a restart loses jobs but not truth.
    """

    def __init__(self, provider: Any, state_dir: Optional[Path] = None):
        self.provider = provider
        self.state_dir = Path(state_dir) if state_dir is not None else None
        self._lock = threading.Lock()
        self._jobs: dict[str, InstallJob] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._counter = 0

    # ------------------------------------------------------------------ queries

    def job(self, job_id: str) -> Optional[InstallJob]:
        with self._lock:
            return self._jobs.get(job_id)

    def jobs(self) -> list[InstallJob]:
        with self._lock:
            return sorted(self._jobs.values(), key=lambda j: j.started_at, reverse=True)

    def installed(self) -> dict[str, Any]:
        """The runtime's own model list, keyed by name. Empty when the runtime is down."""
        try:
            return {m.name: m for m in self.provider.list_models()}
        except Exception:
            return {}

    def plan(self, model: str) -> InstallPlan:
        """What is known before a pull, for the page and for ``start``'s own check."""
        name = validate_model_name(model)
        return build_plan(name, base_url=str(getattr(self.provider, "base_url", "") or ""),
                          state_dir=self.state_dir)

    def _active_for(self, model: str) -> Optional[InstallJob]:
        with self._lock:
            for job in self._jobs.values():
                if job.state in ("starting", "running") and _same_model(job.model, model):
                    return job
        return None

    # ------------------------------------------------------------------ mutations

    def start(self, model: str, *, allow_existing: bool = False) -> InstallJob:
        """Begin installing ``model``. Refuses duplicates, concurrent pulls and re-installs.

        ``allow_existing`` is for an explicit "repair" action by the user; a plain install
        of a model that is already present returns the existing model instead of
        re-downloading gigabytes for no reason.
        """
        name = validate_model_name(model)
        active = self._active_for(name)
        if active is not None:
            # A double click or a second tab joins the one download instead of starting
            # another or showing a spurious error.
            return active
        if not allow_existing:
            for installed_name in self.installed():
                if _same_model(installed_name, name):
                    raise ProviderError("bad_request", f"{name} is already installed", provider="ollama")
        preflight = self.plan(name)
        if preflight.blocked:
            raise ProviderError("bad_request", preflight.blocked, provider="ollama")
        with self._lock:
            running = sum(1 for j in self._jobs.values() if j.state in ("starting", "running"))
            if running >= MAX_CONCURRENT_INSTALLS:
                raise ProviderError("bad_request",
                                    f"{running} installs are already running; finish or cancel one first",
                                    provider="ollama")
            resumed = any(_same_model(j.model, name) and j.state in ("cancelled", "failed")
                          and j.received_bytes > 0 for j in self._jobs.values())
            self._counter += 1
            job = InstallJob(id=f"install-{self._counter}", model=name, resumed=resumed)
            _apply_plan(job, preflight)
            # An interrupted earlier attempt leaves verified blobs behind; say so rather
            # than implying the whole download will run again.
            self._jobs[job.id] = job
            self._trim()
        thread = threading.Thread(target=self._run, args=(job,), name=f"install-{job.id}", daemon=True)
        with self._lock:
            self._threads[job.id] = thread
        thread.start()
        return job

    def cancel(self, job_id: str) -> bool:
        """Ask a running install to stop. Returns False when there is nothing to cancel."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.state not in ("starting", "running"):
                return False
            job.cancel_requested = True
            job.status = "cancelling"
        return True

    def remove(self, model: str) -> str:
        """Delete a model from the runtime. Refuses while that model is being installed."""
        name = validate_model_name(model)
        active = self._active_for(name)
        if active is not None:
            raise ProviderError("bad_request", f"{name} is being installed right now; cancel it first",
                                provider="ollama")
        try:
            self.provider.delete_model(name)
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError("other", f"could not remove {name}: {exc}", provider="ollama") from exc
        return name

    # ------------------------------------------------------------------ worker

    def _trim(self) -> None:
        """Drop the oldest finished jobs once the registry grows past its bound."""
        finished = [j for j in self._jobs.values() if j.state not in ("starting", "running")]
        if len(self._jobs) <= MAX_RETAINED_JOBS:
            return
        finished.sort(key=lambda j: j.finished_at or j.started_at)
        for job in finished[: len(self._jobs) - MAX_RETAINED_JOBS]:
            self._jobs.pop(job.id, None)
            self._threads.pop(job.id, None)

    def _finish(self, job: InstallJob, state: str, *,
                failure: Optional[InstallFailure] = None) -> None:
        rate = job.bytes_per_second
        with self._lock:
            job.state = state
            if failure is not None:
                job.error = failure.detail
                job.error_code = failure.code
                job.error_message = failure.message
                job.action = failure.action
            job.finished_at = iso(utcnow())
            job.updated_at = job.finished_at
            if state == "done":
                job.status = "success"
                job.completed = job.total or job.completed
        record_rate(self.state_dir, rate, job.model)

    def _fail(self, job: InstallJob, text: str) -> None:
        self._finish(job, "failed", failure=classify_install_error(
            text, free_bytes=job.free_bytes, size_bytes=job.size_bytes))

    def _run(self, job: InstallJob) -> None:
        """Own one pull. Success is confirmed against the runtime, never assumed."""
        try:
            for event in self.provider.pull_events(job.model, should_stop=lambda: job.cancel_requested):
                _apply(job, event)
                if job.cancel_requested:
                    self._finish(job, "cancelled", failure=cancelled_failure())
                    return
                if job.error:
                    self._fail(job, job.error)
                    return
                if job.state == "starting":
                    job.state = "running"
                if job.status == "success":
                    break
            else:
                # The stream ended without the runtime saying `success`.
                if job.cancel_requested:
                    self._finish(job, "cancelled", failure=cancelled_failure())
                else:
                    self._finish(job, "failed", failure=interrupted_failure())
                return
        except ProviderError as exc:
            if job.cancel_requested:
                self._finish(job, "cancelled", failure=cancelled_failure())
            else:
                self._fail(job, str(exc))
            return
        except Exception as exc:  # a runtime crash must not kill the server thread silently
            self._fail(job, f"{type(exc).__name__}: {exc}")
            return
        # `success` from the runtime is necessary, not sufficient: confirm the model is
        # actually listed before telling anyone the install worked.
        present = any(_same_model(name, job.model) for name in self.installed())
        if not present:
            self._finish(job, "failed", failure=unconfirmed_failure())
            return
        self._finish(job, "done")
