"""Dashboard hardening: a local approval endpoint must not be drivable from any web page.

Threats this closes (research §3, docs/research/offerings-and-failures.md):

* **Cross-site request forgery** — any page the user visits can POST to http://127.0.0.1:8787.
  A body-less ``POST /approvals/<id>/approve`` is all it takes (serialwarden #56, GAIA #3365).
  → every unsafe request must be same-origin (``Origin`` / ``Sec-Fetch-Site``), and HTML form posts
  must also carry the per-session CSRF token (double-submit cookie).
* **DNS rebinding** — an attacker hostname re-resolves to 127.0.0.1, making the attacker's page
  *same-origin* with the dashboard. → the ``Host`` header must be loopback or explicitly allowed.
* **Exposure** — OpenClaw's dashboard listened on all interfaces unauthenticated and printed a bearer
  token inside a logged URL. → binding off-loopback needs ``--allow-remote`` *and* an auth token that is
  only ever shown once on the terminal, never embedded in a URL or log line.

Non-browser clients (curl, scripts, the CLI) send neither ``Origin`` nor ``Sec-Fetch-Site`` and are not
a CSRF vector, so they pass the origin check. They remain subject to the Host and auth checks.
"""

from __future__ import annotations

import hmac
import hashlib
import ipaddress
import os
import secrets
from typing import Iterable, Optional
from urllib.parse import urlsplit

from starlette.requests import Request
from starlette.responses import PlainTextResponse, RedirectResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}
CSRF_COOKIE = "hutch_csrf"
AUTH_COOKIE = "hutch_auth"
LOOPBACK_NAMES = {"localhost", "localhost.localdomain"}
OPEN_PATHS = ("/login", "/static/", "/api/health")


def _host_only(host_header: str) -> str:
    h = host_header.strip().lower()
    if h.startswith("["):  # [::1]:8787
        return h[1:].split("]", 1)[0]
    return h.rsplit(":", 1)[0] if h.count(":") == 1 else h


def is_loopback_host(host: str) -> bool:
    if host in LOOPBACK_NAMES or host.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def allowed_hosts_from_env() -> set[str]:
    raw = os.environ.get("HUTCH_ALLOWED_HOSTS", "")
    return {h.strip().lower() for h in raw.split(",") if h.strip()}


def auth_digest(token: str) -> str:
    return hmac.new(b"hutch-dashboard", token.encode(), hashlib.sha256).hexdigest()


class SecurityMiddleware:
    """Pure ASGI middleware: Host allow-list, same-origin checks, CSRF cookie, optional token auth."""

    def __init__(self, app: ASGIApp, *, extra_hosts: Iterable[str] = (), auth_token: Optional[str] = None):
        self.app = app
        self.extra_hosts = {h.lower() for h in extra_hosts} | allowed_hosts_from_env()
        self.auth_token = auth_token
        self._digest = auth_digest(auth_token) if auth_token else None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request = Request(scope, receive)
        host_header = request.headers.get("host", "")
        host = _host_only(host_header)

        # 1. DNS rebinding: only loopback / explicitly allowed names. With a token configured the
        #    attacker cannot authenticate anyway, so remote names are permitted.
        if not (is_loopback_host(host) or host in self.extra_hosts or self.auth_token):
            await PlainTextResponse(
                f"hutch: unexpected Host '{host_header}'. Use http://127.0.0.1:<port>, or set "
                "HUTCH_ALLOWED_HOSTS to allow this name.", status_code=421)(scope, receive, send)
            return

        # 2. CSRF: unsafe methods must be same-origin (browsers always send Origin on cross-site POST).
        if request.method in UNSAFE and not self._same_origin(request, host_header):
            await PlainTextResponse("hutch: cross-site request refused (Origin / Sec-Fetch-Site).",
                                    status_code=403)(scope, receive, send)
            return

        # 3. Auth (only when a token is configured, i.e. remote binding).
        path = request.url.path
        if self._digest and not path.startswith(OPEN_PATHS) and not self._authed(request):
            if request.method == "GET" and "text/html" in request.headers.get("accept", ""):
                await RedirectResponse("/login", status_code=303)(scope, receive, send)
            else:
                await PlainTextResponse("hutch: authentication required.", status_code=401)(scope, receive, send)
            return

        # 4. Per-session CSRF token (double-submit cookie), exposed to templates via request.state.
        token = request.cookies.get(CSRF_COOKIE)
        fresh = token is None
        if fresh:
            token = secrets.token_urlsafe(32)
        scope.setdefault("state", {})["csrf"] = token

        async def send_with_cookie(message):
            if fresh and message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"set-cookie", (
                    f"{CSRF_COOKIE}={token}; Path=/; SameSite=Strict; HttpOnly").encode()))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_cookie)

    @staticmethod
    def _same_origin(request: Request, host_header: str) -> bool:
        origin = request.headers.get("origin")
        if origin is not None:
            if origin == "null":
                return False
            return urlsplit(origin).netloc.lower() == host_header.strip().lower()
        site = request.headers.get("sec-fetch-site")
        if site is not None:
            return site in ("same-origin", "none")
        return True  # not a browser: no ambient credentials to abuse

    def _authed(self, request: Request) -> bool:
        cookie = request.cookies.get(AUTH_COOKIE, "")
        if self._digest and hmac.compare_digest(cookie, self._digest):
            return True
        bearer = request.headers.get("authorization", "")
        return bool(self.auth_token and bearer.startswith("Bearer ")
                    and hmac.compare_digest(bearer[7:], self.auth_token))


def check_csrf(request: Request, submitted: Optional[str]) -> bool:
    """HTML forms / htmx posts must echo the session token (double-submit)."""
    cookie = request.cookies.get(CSRF_COOKIE)
    return bool(cookie and submitted and hmac.compare_digest(cookie, submitted))


def new_auth_token() -> str:
    return secrets.token_urlsafe(24)
