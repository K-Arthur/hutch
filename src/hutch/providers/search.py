"""Provider-native search transport: one connection's declared route, one request.

The route declaration and the wire rules live in :mod:`hutch.providers.search_wire`; this
module owns only the HTTP call, the redirect refusal and the translation of a provider error
into a message a person can act on.

This is the provider's own search, not Hutch's local grounding fan-out
(``tools/live_search``). The distinction is deliberate and must stay visible in every
surface: here the search *and* the summarising answer both happen at the provider, the
provider bills for each search round separately from tokens, and the citations are
provider-supplied data that Hutch reports verbatim rather than fetches or verifies.

Two rules that were learned from a real refusal rather than assumed:

* the key travels only to the configured endpoint, and redirects are refused because the
  bearer token would follow the ``Location`` header to another host;
* the vendor puts the actionable reason in ``error.param``, not ``error.message``. Reading
  only the message turned "this account has not activated the search plugin" into the
  generic "Param Incorrect" and left Hutch guessing at a cause.
"""

from __future__ import annotations

from typing import Any, Optional

from ..connection_endpoints import redirect_refusal
from .search_wire import (Citation, MAX_QUERY_CHARS, SearchError, SearchResult, SearchRoute,
                          build_payload, parse_search_response, route_from_template)

__all__ = ["Citation", "MAX_QUERY_CHARS", "SearchError", "SearchResult", "SearchRoute",
           "WebSearchClient", "build_payload", "parse_search_response", "route_from_template"]

_MAX_ERROR_DETAIL = 400


class WebSearchClient:
    """One provider-native search request. Nothing is retried here."""

    def __init__(self, *, base_url: str, api_key: str, route: SearchRoute,
                 provider_name: str = "search", headers: Optional[dict[str, str]] = None,
                 timeout: float = 180.0, http_client: Any = None):
        if not str(base_url or "").strip():
            raise SearchError("this connection has no endpoint to send a search to")
        self.base_url = str(base_url).rstrip("/")
        self.api_key = api_key
        self.route = route
        self.provider_name = provider_name
        self.headers = dict(headers or {})
        self.timeout = max(5.0, min(float(timeout), 600.0))
        self._http_client = http_client

    def search(self, query: str) -> SearchResult:
        payload = build_payload(self.route, query)
        import httpx

        client, owned = self._http_client, False
        if client is None:
            from ..offline import httpx_offline_options

            base_url, transport, trust_env = httpx_offline_options(self.base_url,
                                                                   self.provider_name)
            client = httpx.Client(
                base_url=base_url, trust_env=trust_env, transport=transport,
                timeout=httpx.Timeout(connect=10.0, read=self.timeout, write=60.0, pool=5.0))
            owned = True
        url = "/chat/completions" if owned else f"{self.base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}", **self.headers}
        try:
            resp = client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise SearchError(
                f"{self.provider_name} did not answer the search within {self.timeout:g}s. "
                "The provider may have performed and billed the search; Hutch did not retry "
                "it.") from exc
        except httpx.HTTPError as exc:
            raise SearchError(
                f"cannot reach the search endpoint at {self.base_url}: {exc}") from exc
        finally:
            if owned:
                client.close()
        if 300 <= resp.status_code < 400:
            raise SearchError(str(redirect_refusal(self.provider_name,
                                                   resp.headers.get("location"))))
        if resp.status_code >= 400:
            raise SearchError(self._error_from_response(resp))
        try:
            body = resp.json()
        except ValueError as exc:
            raise SearchError("the search endpoint returned a non-JSON body") from exc
        return parse_search_response(body, self.route)

    def _error_from_response(self, resp: Any) -> str:
        status = resp.status_code
        detail = ""
        param = ""
        try:
            body = resp.json()
            error = body.get("error") if isinstance(body, dict) else None
            if isinstance(error, dict):
                detail = error.get("message") or ""
                # These vendors put the actionable reason in ``param`` rather than
                # ``message``; discarding it replaced a precise cause with a guess.
                param = error.get("param") or ""
            elif error:
                detail = str(error)
        except ValueError:
            detail = ""
        detail = " ".join(str(detail or f"HTTP {status}").split())[:_MAX_ERROR_DETAIL]
        param = " ".join(str(param).split())[:_MAX_ERROR_DETAIL]
        reason = f"{detail} ({param})" if param and param.lower() not in detail.lower() else detail
        activation_hint = ""
        if "websearchenabled" in param.lower().replace(" ", "") and "false" in param.lower():
            activation_hint = (
                " The account has not activated the provider's web-search plugin; activate it "
                "in the provider console, then retry. This is an account entitlement, not a "
                "Hutch setting.")
        if status in (401, 403):
            return (f"{self.provider_name} rejected the credential for search ({reason}). "
                    "The web-search plugin also has to be activated in the provider console."
                    + activation_hint)
        if status == 402:
            return f"{self.provider_name} has no available credit or quota for search: {reason}"
        if status == 429:
            return f"{self.provider_name} rate-limited the search: {reason}"
        if status in (400, 422):
            return (f"{self.provider_name} refused the search request: {reason}."
                    + activation_hint)
        return f"{self.provider_name} returned HTTP {status} for search: {reason}"
