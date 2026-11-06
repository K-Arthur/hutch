"""Backends driven by a :class:`MediaRoute` row: a shared base and the ``sync`` protocol.

Everything that varies between providers is in the route table. What stays here is the behavior
that must be identical for all of them:

* the result is held durably before ``submit`` returns (the provider has been paid by then);
* a request is validated against the route's documented limits before any billable call;
* an HTTP 200 is not success: an in-body failure envelope, a refusal marker, or a response with no
  media is reported as what it is, with a note that the provider may have billed;
* a refusal is :class:`MediaRefused`, never a generic failure;
* nothing is retried.

**Protocol-verified, live-unverified.** Tests drive these backends against ``httpx.MockTransport``
and a real loopback server for failure injection; no provider account was exercised.
"""

from __future__ import annotations

import base64
import binascii
from typing import Any, Mapping, Optional

from ..fetch import FetchError, download
from ..spool import MediaSpool, ResultHold, SpoolError
from .base import VERIFICATION_TAG, MediaRefused
from .http_call import MediaHttpError, RouteHttp, auth_headers, resolve_headers
from .route_spec import MediaRoute
from .route_values import RouteInputError, request_values
from .wire import WireError, envelope_problem, fill, fill_path, media_item, dig

_FORMATS = {"image": ["png", "jpeg", "webp"], "audio": ["wav"], "video": ["mp4", "webm"]}
_BILLED = "the provider may have billed this request; Hutch did not retry it"


class RouteBackendError(RuntimeError):
    """A route backend could not complete a call; the text says what was and was not billed."""


class RouteBackendBase:
    def __init__(self, route: MediaRoute, *, base_url: str, api_key: str, connection: str = "",
                 billing: str = "", credential_label: str = "",
                 headers: Optional[Mapping[str, str]] = None, client: Any = None,
                 spool: Optional[MediaSpool] = None):
        self.route = route
        self.connection = connection
        self.name = f"{route.id}:{connection}" if connection else route.id
        self.provider = route.provider
        self.billing = billing
        self.credential_label = credential_label
        self._api_key = api_key
        self._extra = dict(headers or {})
        self._hold = ResultHold(spool)
        timeout = float(route.limits.get("timeout_seconds") or 180)
        self._http = RouteHttp(base_url=base_url, provider=route.provider, timeout=timeout,
                               client=client)

    # ------------------------------------------------------------ identity

    def capabilities(self) -> dict[str, Any]:
        return {
            "backend": self.name, "kinds": [self.route.kind],
            "output_formats": {self.route.kind: _FORMATS[self.route.kind]},
            "voices": list(self.route.limits.get("voices") or []),
            "default_voice": self.route.defaults.get("voice"),
            "max_text_chars": self.route.limits.get("prompt_chars"),
            "protocol": self.route.protocol, "provider": self.provider,
            "model": self.route.model, "billing": self.billing, "connection": self.connection,
            "credential": self.credential_label, "route": self.route.id,
            "durable_results": self._hold.durable or self.route.protocol == "task",
            "verified": VERIFICATION_TAG, "status": self.route.status,
            "editing": False, "partial_previews": False, "max_width": None, "max_height": None,
            "max_seconds": (self.route.limits.get("seconds") or {}).get("max"),
        }

    def approval_detail(self, request: Mapping[str, Any]) -> dict[str, Any]:
        """What the approval prompt shows: who receives the words and who pays."""
        return {"route": self.route.id, "provider": self.provider, "model": self.route.model,
                "endpoint": self._http.base_url, "connection": self.connection or "(none)",
                "credential": self.credential_label, "billing": self.billing or "unknown",
                "prompt_chars": len(str(request.get("prompt") or "")),
                "note": "the prompt leaves this machine; the provider's account is charged"}

    def validate(self, request: Mapping[str, Any]) -> None:
        """Raise :class:`RouteInputError` when the request is outside the route's limits."""
        request_values(self.route, request)

    def _headers(self) -> dict[str, str]:
        headers = {**self._extra, **resolve_headers(self.route.headers),
                   **auth_headers(self.route.auth, self._api_key)}
        return headers

    def can_recover(self, job: Mapping[str, Any]) -> bool:
        return False

    def cancel(self, job: Mapping[str, Any]) -> Optional[dict[str, Any]]:
        return None


class SyncRouteBackend(RouteBackendBase):
    """One request returns the finished media; the result is held before submit returns."""

    def submit(self, req: Mapping[str, Any]) -> str:
        try:
            values = request_values(self.route, req)
        except RouteInputError as exc:
            raise RouteBackendError(str(exc)) from exc
        spec = self.route.request
        try:
            response = self._http.send(
                str(spec.get("method", "POST")), fill_path(spec["path"], values),
                headers=self._headers(), body=fill(spec.get("body"), values),
                params=fill(spec.get("query") or {}, values) or None, may_bill=True)
            data = self._media_from(response)
        except MediaHttpError as exc:
            raise RouteBackendError(str(exc)) from exc
        except WireError as exc:
            raise RouteBackendError(f"{exc}; {_BILLED}") from exc
        try:
            return self._hold.put(data, meta={"route": self.route.id, "model": self.route.model})
        except SpoolError as exc:
            raise RouteBackendError(
                f"the result arrived but could not be held ({exc}); {_BILLED}") from exc

    def poll(self, job: Mapping[str, Any]) -> dict[str, Any]:
        if self._hold.has(str(job.get("upstream_job_id") or "")):
            return {"status": "succeeded"}
        return {"status": "failed",
                "error": "no held result exists for this job; this provider answers in one request "
                         "and the result cannot be fetched again without paying again"}

    def fetch(self, job: Mapping[str, Any]) -> bytes:
        handle = str(job.get("upstream_job_id") or "")
        if not self._hold.has(handle):
            raise RouteBackendError("no held result for this job; it cannot be re-fetched "
                                    "without paying again")
        try:
            return self._hold.get(handle)
        except SpoolError as exc:
            raise RouteBackendError(f"the held result is unusable: {exc}") from exc

    def can_recover(self, job: Mapping[str, Any]) -> bool:
        return self._hold.durable and self._hold.has(str(job.get("upstream_job_id") or ""))

    # ------------------------------------------------------------ response

    def _media_from(self, response: Any) -> bytes:
        spec = self.route.response
        if spec.get("kind") == "bytes":
            return self._bytes_body(response, spec)
        body = response.json()
        problem = envelope_problem(body, spec.get("envelope") or {})
        if problem:
            message, refused = problem
            if refused:
                raise MediaRefused(message)
            raise WireError(message)
        encoded = media_item(body, spec.get("media") or {})
        if encoded is None:
            self._refusal_or_empty(body, spec)
        return self._decode(encoded, spec.get("encoding", "base64"))

    def _bytes_body(self, response: Any, spec: Mapping[str, Any]) -> bytes:
        kind = str(response.headers.get("content-type", "")).split(";")[0].strip().lower()
        accept = tuple(spec.get("accept") or ())
        if accept and not kind.startswith(accept):
            raise WireError(f"the provider answered {kind or 'no content type'} instead of "
                            f"{'/'.join(accept)} media")
        if not response.body:
            raise WireError("the provider answered success with an empty body")
        return response.body

    @staticmethod
    def _refusal_or_empty(body: Any, spec: Mapping[str, Any]) -> None:
        marker = spec.get("refusal_when") or {}
        if marker and (dig(body, marker.get("path", "")) or 0) > marker.get("gt", 0):
            raise MediaRefused(str(marker.get("reason", "the provider's safety filter blocked "
                                                          "the result")))
        raise WireError("the provider answered success without any media")

    @staticmethod
    def _decode(encoded: str, encoding: str) -> bytes:
        try:
            if encoding == "hex":
                return bytes.fromhex(encoded)
            if encoding == "url":
                return download(encoded)
            return base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise WireError(f"the media was not valid {encoding}") from exc
        except FetchError as exc:
            raise WireError(str(exc)) from exc

    def duration_seconds(self, job: Mapping[str, Any]) -> Optional[float]:
        """Length of a held wav clip, read from its header; None for other kinds."""
        if self.route.kind != "audio":
            return None
        from .speech_wire import wav_duration

        try:
            return wav_duration(self._hold.get(str(job.get("upstream_job_id") or "")))
        except SpoolError:
            return None
