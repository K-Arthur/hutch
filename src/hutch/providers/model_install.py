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

import json
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Iterator, Optional

from ..models import iso, utcnow
from .base import ProviderError
from .locality import CLOUD_TAG
from .model_names import parse_model_name, same_model

#: Two installs at once is plenty for a person on one machine, and bounds both memory
#: and the runtime's own download queue.
MAX_CONCURRENT_INSTALLS = 2
#: A finished job is kept so the UI can read the outcome; older ones are dropped.
MAX_RETAINED_JOBS = 32
#: A progress line repeats the same digest many times; only state changes are worth keeping.
_MAX_STATUS_CHARS = 200


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


@dataclass
class InstallJob:
    id: str
    model: str
    state: str = "starting"          # starting | running | done | failed | cancelled
    status: str = ""
    completed: int = 0
    total: int = 0
    digest: str = ""
    error: str = ""
    resumed: bool = False
    started_at: str = field(default_factory=lambda: iso(utcnow()))
    updated_at: str = field(default_factory=lambda: iso(utcnow()))
    finished_at: str = ""
    cancel_requested: bool = False

    @property
    def percent(self) -> Optional[float]:
        """Percent of the *current* blob. None when the runtime has not said how large it is."""
        if not self.total:
            return None
        return round(min(100.0, 100.0 * self.completed / self.total), 1)

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id, "model": self.model, "state": self.state, "status": self.status,
            "completed": self.completed, "total": self.total, "percent": self.percent,
            "digest": self.digest, "error": self.error, "resumed": self.resumed,
            "started_at": self.started_at, "updated_at": self.updated_at,
            "finished_at": self.finished_at,
            "cancel_requested": self.cancel_requested,
        }


def _read_events(resp: Any) -> Iterator[dict[str, Any]]:
    """Parse the runtime's ndjson progress stream."""
    for line in resp.iter_lines():
        if not line or not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            yield event


def _apply(job: InstallJob, event: dict[str, Any]) -> None:
    """Fold one runtime event into the job. Unknown keys are ignored, not guessed at."""
    status = str(event.get("status") or "")
    if status:
        job.status = status[:_MAX_STATUS_CHARS]
    if isinstance(event.get("digest"), str) and event["digest"]:
        job.digest = event["digest"]
    total = event.get("total")
    completed = event.get("completed")
    if isinstance(total, (int, float)) and total > 0:
        # A new blob restarts the byte counters; showing 100% of the old one would lie.
        if job.total and job.completed >= job.total and total != job.total:
            job.completed = 0
        job.total = int(total)
    if isinstance(completed, (int, float)) and completed >= 0:
        job.completed = int(completed)
    if event.get("error"):
        job.error = str(event["error"])[:_MAX_STATUS_CHARS * 2]
    job.updated_at = iso(utcnow())


class ModelInstaller:
    """A bounded, in-process registry of model installs for one runtime.

    The authoritative record of what is installed is always the runtime's own model list
    (``/api/tags``), never this registry: a job that says ``done`` is *confirmed* against
    the runtime before it is reported as finished, and a restart loses jobs but not truth.
    """

    def __init__(self, provider: Any):
        self.provider = provider
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
            raise ProviderError("bad_request", f"{name} is already being installed ({active.state}); "
                                              f"wait for it or cancel it first", provider="ollama")
        if not allow_existing:
            for installed_name in self.installed():
                if _same_model(installed_name, name):
                    raise ProviderError("bad_request", f"{name} is already installed", provider="ollama")
        with self._lock:
            running = sum(1 for j in self._jobs.values() if j.state in ("starting", "running"))
            if running >= MAX_CONCURRENT_INSTALLS:
                raise ProviderError("bad_request",
                                    f"{running} installs are already running; finish or cancel one first",
                                    provider="ollama")
            self._counter += 1
            job = InstallJob(id=f"install-{self._counter}", model=name)
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

    def _finish(self, job: InstallJob, state: str, *, error: str = "") -> None:
        with self._lock:
            job.state = state
            job.error = error
            job.finished_at = iso(utcnow())
            job.updated_at = job.finished_at
            if state == "done":
                job.status = "success"
                job.completed = job.total or job.completed

    def _run(self, job: InstallJob) -> None:
        """Own one pull. Success is confirmed against the runtime, never assumed."""
        try:
            for event in self.provider.pull_events(job.model, should_stop=lambda: job.cancel_requested):
                _apply(job, event)
                if job.cancel_requested:
                    self._finish(job, "cancelled", error="cancelled before the download finished")
                    return
                if job.error:
                    self._finish(job, "failed", error=job.error)
                    return
                if job.state == "starting":
                    job.state = "running"
                if job.status == "success":
                    break
            else:
                # The stream ended without the runtime saying `success`.
                if job.cancel_requested:
                    self._finish(job, "cancelled", error="cancelled before the download finished")
                else:
                    self._finish(job, "failed", error="the download stream ended before the runtime reported success")
                return
        except ProviderError as exc:
            self._finish(job, "cancelled" if job.cancel_requested else "failed",
                         error="cancelled" if job.cancel_requested else str(exc))
            return
        except Exception as exc:  # a runtime crash must not kill the server thread silently
            self._finish(job, "failed", error=f"{type(exc).__name__}: {exc}")
            return
        # `success` from the runtime is necessary, not sufficient: confirm the model is
        # actually listed before telling anyone the install worked.
        present = any(_same_model(name, job.model) for name in self.installed())
        if not present:
            self._finish(job, "failed",
                         error="the runtime reported success but does not list the model; check `ollama list`")
            return
        job.resumed = False
        self._finish(job, "done")
