"""The ``task`` protocol: submit returns an id, polling names the result, fetch downloads it.

Nothing is held between calls. Every later call needs only the upstream id in the ledger (and the
request's model), so a job started before a restart is polled, fetched and cancelled the same way
after it. The result URL is consumed in ``fetch`` through the bounded downloader and is never
stored; provider credentials are not sent to the result host.

Status mapping is data (``task.poll.running|done|failed|refused``). A status the route does not
list is treated as still running, because the vendors that document this (xAI: "any other value
means keep polling") say so; the caller's bounded polling then reports a job that never resolves.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from ..fetch import FetchError, download
from .base import MediaRefused
from .http_call import MediaHttpError
from .route_backend import RouteBackendBase, RouteBackendError
from .route_values import RouteInputError, request_values
from .wire import WireError, dig, envelope_problem, fill, fill_path

_BILLED = "the provider may have billed this request; Hutch did not retry it"


class TaskRouteBackend(RouteBackendBase):
    # ------------------------------------------------------------ submit

    def submit(self, req: Mapping[str, Any]) -> str:
        try:
            values = request_values(self.route, req)
        except RouteInputError as exc:
            raise RouteBackendError(str(exc)) from exc
        spec = self.route.request
        path, request_body = self._build(spec, values)
        try:
            response = self._http.send(
                str(spec.get("method", "POST")), path, headers=self._headers(), body=request_body,
                params=fill(spec.get("query") or {}, values) or None, may_bill=True)
            body = response.json()
            self._raise_envelope(body, self.route.task.get("envelope"))
        except MediaHttpError as exc:
            raise RouteBackendError(str(exc)) from exc
        except WireError as exc:
            raise RouteBackendError(f"{exc}; {_BILLED}") from exc
        task_id = dig(body, self.route.task["id_path"])
        if not isinstance(task_id, (str, int)) or isinstance(task_id, bool) or not str(task_id):
            raise RouteBackendError(f"the provider accepted the request but returned no task id; "
                                    f"{_BILLED}")
        return str(task_id)

    # ------------------------------------------------------------ poll

    def poll(self, job: Mapping[str, Any]) -> dict[str, Any]:
        spec = self.route.task["poll"]
        try:
            body = self._poll_body(job)
        except MediaHttpError as exc:
            return self._poll_http_problem(exc)
        except WireError as exc:
            return {"status": "running", "note": f"the status answer was unreadable ({exc})"}
        try:
            self._raise_envelope(body, self.route.task.get("envelope"))
        except MediaRefused as exc:
            return {"status": "failed", "refused": True, "error": str(exc)}
        except WireError as exc:
            return {"status": "failed", "error": str(exc)}
        return self._state_from(body, spec)

    def _poll_body(self, job: Mapping[str, Any]) -> Any:
        spec = self.route.task["poll"]
        values = self._job_values(job)
        response = self._http.send(str(spec.get("method", "GET")), fill_path(spec["path"], values),
                                   headers=self._headers(), params=fill(spec.get("query") or {},
                                                                        values) or None)
        return response.json()

    def _state_from(self, body: Any, spec: Mapping[str, Any]) -> dict[str, Any]:
        raw = dig(body, spec.get("status_path", ""))
        status = str(raw) if raw is not None else ""
        error = dig(body, spec.get("error_path", "")) if spec.get("error_path") else None
        if status in [str(s) for s in spec.get("refused", [])]:
            return {"status": "failed", "refused": True,
                    "error": str(error or "the provider's content moderation declined the request")}
        if status in [str(s) for s in spec.get("failed", [])] or (
                status in [str(s) for s in spec.get("done", [])] and error):
            return {"status": "failed", "error": str(error or f"the provider reported {status!r}")}
        if status in [str(s) for s in spec.get("done", [])]:
            return {"status": "succeeded"}
        return {"status": "running", "note": f"provider status {status or 'unknown'}"}

    @staticmethod
    def _poll_http_problem(exc: MediaHttpError) -> dict[str, Any]:
        if exc.status == 404:
            return {"status": "failed",
                    "error": "the provider no longer knows this task (it may have expired); "
                             f"{exc}"}
        # The job is still running upstream; a poll hiccup must not fail paid work.
        return {"status": "running", "note": f"the last status check failed: {exc}"}

    # ------------------------------------------------------------ fetch

    def fetch(self, job: Mapping[str, Any]) -> bytes:
        result = self.route.task["result"]
        try:
            body = self._poll_body(job)
            body = self._second_hop(job, body, result) if result.get("via") else body
            self._refused_if_flagged(body, result)
            url = dig(body, result.get("url_path", ""))
            if not isinstance(url, str) or not url:
                raise RouteBackendError("the finished task named no result URL")
            return download(url)
        except MediaHttpError as exc:
            raise RouteBackendError(str(exc)) from exc
        except WireError as exc:
            raise RouteBackendError(str(exc)) from exc
        except FetchError as exc:
            raise RouteBackendError(f"{exc}; the task finished and may have been billed") from exc

    def _second_hop(self, job: Mapping[str, Any], state: Any, result: Mapping[str, Any]) -> Any:
        hop = result["via"]
        values = self._job_values(job)
        for name, path in (hop.get("take") or {}).items():
            values[name] = dig(state, path)
        response = self._http.send(str(hop.get("method", "GET")), fill_path(hop["path"], values),
                                   headers=self._headers(),
                                   params=fill(hop.get("query") or {}, values) or None)
        return response.json()

    @staticmethod
    def _refused_if_flagged(body: Any, result: Mapping[str, Any]) -> None:
        path = result.get("refused_if_true")
        if path and dig(body, path) is True:
            raise MediaRefused(str(result.get(
                "refused_reason", "the provider's safety filter blocked the result")))

    # ------------------------------------------------------------ cancel

    def cancel(self, job: Mapping[str, Any]) -> Optional[dict[str, Any]]:
        spec = self.route.task.get("cancel")
        if not spec:
            return None
        try:
            response = self._http.send(str(spec.get("method", "DELETE")),
                                       fill_path(spec["path"], self._job_values(job)),
                                       headers=self._headers())
        except (MediaHttpError, WireError):
            return None
        confirmed = [int(c) for c in spec.get("confirm_codes", [200, 204])]
        if response.status in confirmed:
            return {"cancelled": True, "how": f"{spec.get('method', 'DELETE')} {response.status}"}
        return None

    # ------------------------------------------------------------ helpers

    def _job_values(self, job: Mapping[str, Any]) -> dict[str, Any]:
        model = str(self.route.model)
        return {"task_id": str(job.get("upstream_job_id") or ""), "model": model,
                "model_app": "/".join(model.split("/")[:2])}

    @staticmethod
    def _raise_envelope(body: Any, envelope: Optional[Mapping[str, Any]]) -> None:
        problem = envelope_problem(body, dict(envelope or {}))
        if problem:
            message, refused = problem
            raise (MediaRefused(message) if refused else WireError(message))
