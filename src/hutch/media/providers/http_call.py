"""One HTTP call for a table-driven media route.

Shared by the ``sync`` and ``task`` backends so the rules live once:

* the credential travels only to the configured origin, through the address-pinning transport
  (``offline.httpx_offline_options``), and redirects are refused because a redirect would carry the
  credential to another host;
* the response body is read with a bound, never unbounded into memory;
* an HTTP failure becomes a sentence that names the cause class (credential, balance, rate limit)
  with the provider's own words, and says plainly when the request may already have been billed;
* nothing is retried here. A retried billable call can pay twice.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from ...connection_endpoints import redirect_refusal
from ..fetch import FetchError, read_bounded
from .wire import WireError, classify_status, error_detail

#: A JSON answer that embeds base64 media is larger than the media; this bounds the answer.
MAX_RESPONSE_BYTES = 140_000_000


class MediaHttpError(RuntimeError):
    """The provider could not be reached or answered with a failure."""

    def __init__(self, message: str, *, status: int = 0, kind: str = "client", billed: bool = False):
        super().__init__(message)
        self.status, self.kind, self.billed = status, kind, billed


@dataclass(frozen=True)
class RouteResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes

    def json(self) -> Any:
        try:
            return json.loads(self.body.decode("utf-8"))
        except ValueError as exc:
            raise WireError("the provider answered with a body that is not JSON") from exc


def auth_headers(auth: Mapping[str, Any], api_key: str) -> dict[str, str]:
    """The credential header for a route's ``auth`` block ({"header", "scheme"})."""
    header = str(auth.get("header") or "Authorization")
    scheme = str(auth.get("scheme", "Bearer"))
    return {header: f"{scheme} {api_key}" if scheme else api_key}


def resolve_headers(template: Mapping[str, str]) -> dict[str, str]:
    """Static route headers; ``{uuid}`` becomes a fresh id per request (PixVerse requires it)."""
    return {name: str(value).replace("{uuid}", str(uuid.uuid4())) for name, value in template.items()}


class RouteHttp:
    def __init__(self, *, base_url: str, provider: str, timeout: float = 180.0,
                 client: Any = None):
        if not str(base_url or "").strip():
            raise MediaHttpError(f"{provider} has no endpoint configured")
        self.base_url = str(base_url).rstrip("/")
        self.provider = provider
        self.timeout = max(5.0, min(float(timeout), 600.0))
        self._client = client

    def send(self, method: str, path: str, *, headers: Mapping[str, str],
             body: Optional[Any] = None, params: Optional[Mapping[str, Any]] = None,
             may_bill: bool = False) -> RouteResponse:
        import httpx

        client, owned = self._client, False
        if client is None:
            from ...offline import httpx_offline_options

            base, transport, trust_env = httpx_offline_options(self.base_url, self.provider)
            client = httpx.Client(base_url=base, transport=transport, trust_env=trust_env,
                                  timeout=httpx.Timeout(connect=10.0, read=self.timeout,
                                                        write=60.0, pool=5.0))
            owned = True
        url = path if owned else f"{self.base_url}{path}"
        try:
            with client.stream(method, url, headers=dict(headers), params=dict(params or {}),
                               json=body) as response:
                status, reply_headers = response.status_code, dict(response.headers)
                if 300 <= status < 400:
                    raise MediaHttpError(str(redirect_refusal(self.provider,
                                                              reply_headers.get("location"))))
                data = _read_all(response)
        except httpx.TimeoutException as exc:
            raise MediaHttpError(self._timeout_text(may_bill), kind="timeout",
                                 billed=may_bill) from exc
        except httpx.HTTPError as exc:
            raise MediaHttpError(f"cannot reach {self.provider} at {self.base_url}: {exc}",
                                 kind="network") from exc
        except FetchError as exc:
            raise MediaHttpError(f"{self.provider} sent a response that was refused: {exc}",
                                 kind="client") from exc
        finally:
            if owned:
                client.close()
        if status >= 400:
            raise self._status_error(status, data)
        return RouteResponse(status, reply_headers, data)

    def _timeout_text(self, may_bill: bool) -> str:
        tail = (" The provider may have received and billed the request; Hutch did not retry it."
                if may_bill else "")
        return f"{self.provider} did not answer within {self.timeout:g}s.{tail}"

    def _status_error(self, status: int, data: bytes) -> MediaHttpError:
        try:
            detail = error_detail(json.loads(data.decode("utf-8")), status)
        except ValueError:
            detail = f"HTTP {status}"
        kind = classify_status(status)
        lead = {"auth": "rejected the credential", "credit": "has no available credit or quota",
                "rate": "rate-limited the request", "server": "failed on its side",
                "client": f"refused the request (HTTP {status})"}[kind]
        return MediaHttpError(f"{self.provider} {lead}: {detail}", status=status, kind=kind)


def _read_all(response: Any) -> bytes:
    return read_bounded(response, MAX_RESPONSE_BYTES, allow_empty=True)
