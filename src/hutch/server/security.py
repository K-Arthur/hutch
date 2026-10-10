"""Dashboard hardening: a local approval endpoint must not be drivable from any web page.

Threats this closes (research §3, docs/research/offerings-and-failures.md):

* **Cross-site request forgery** — any page the user visits can POST to http://127.0.0.1:8787.
  A body-less ``POST /approvals/<id>/approve`` is all it takes (serialwarden #56, GAIA #3365).
  → every unsafe request must be same-origin (``Origin`` / ``Sec-Fetch-Site``), and HTML form posts
  must also carry the per-session CSRF token (double-submit cookie).
* **DNS rebinding** — an attacker hostname re-resolves to 127.0.0.1, making the attacker's page
  *same-origin* with the dashboard. → the ``Host`` header must be loopback or explicitly allowed.
* **Exposure** — an unauthenticated dashboard on a network interface exposes bot data and execution.
  → loopback remains the default; remote mode requires an explicit private bind or trusted HTTPS proxy,
  exact Host/origin configuration, and a database-backed passkey session. The local owner bearer token
  is never accepted remotely, and phone pairing never issues a reusable dashboard token.

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
from urllib.parse import parse_qs, urlsplit

from starlette.requests import Request
from starlette.responses import PlainTextResponse, RedirectResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}
CSRF_COOKIE = "hutch_csrf"
AUTH_COOKIE = "hutch_auth"
DEVICE_COOKIE = "hutch_device"
SESSION_COOKIE = "hutch_session"
ENROLLMENT_COOKIE = "hutch_enroll"
FLOW_COOKIE = "hutch_flow"
MAX_PASSKEY_CREDENTIAL_BYTES = 256 * 1024
MAX_PASSKEY_VERIFY_BODY_BYTES = MAX_PASSKEY_CREDENTIAL_BYTES + 4096
LOOPBACK_NAMES = {"localhost", "localhost.localdomain"}
OPEN_EXACT_PATHS = {"/login", "/pair", "/api/v1/pairing/exchange",
                    "/api/v1/passkeys/login/options", "/api/v1/passkeys/login/verify",
                    "/api/v1/passkeys/registration/options", "/api/v1/passkeys/registration/verify",
                    "/api/health", "/api/v1/health"}


def is_open_path(path: str) -> bool:
    return path in OPEN_EXACT_PATHS or path.startswith("/static/")


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


class RequestBodyTooLarge(Exception):
    """A passkey verification request exceeded its bounded JSON body size."""


class SecurityMiddleware:
    """Pure ASGI boundary for Host/origin checks, local owner auth, and remote passkey sessions."""

    def __init__(self, app: ASGIApp, *, extra_hosts: Iterable[str] = (), auth_token: Optional[str] = None,
                 device_auth=None):
        self.app = app
        self.extra_hosts = {h.lower() for h in extra_hosts} | allowed_hosts_from_env()
        self.forwarded_hosts = allowed_hosts_from_env()
        self.auth_token = auth_token
        self._digest = auth_digest(auth_token) if auth_token else None
        self.device_auth = device_auth
        self.remote_enabled = os.environ.get("HUTCH_REMOTE_ENABLED") == "1"
        self.trusted_proxies = self._trusted_proxy_networks()

    @staticmethod
    def _trusted_proxy_networks() -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
        raw = os.environ.get("HUTCH_TRUSTED_PROXIES", "")
        networks = []
        for entry in raw.split(","):
            value = entry.strip()
            if not value:
                continue
            try:
                network = ipaddress.ip_network(value, strict=False)
            except ValueError as exc:
                raise ValueError("HUTCH_TRUSTED_PROXIES must contain valid IP addresses or CIDR ranges") from exc
            if network.prefixlen != network.max_prefixlen:
                raise ValueError("HUTCH_TRUSTED_PROXIES must contain exact proxy IPs (/32 or /128), not networks")
            networks.append(network)
        return tuple(networks)

    @staticmethod
    def _header_values(scope: Scope, name: bytes) -> list[bytes]:
        return [value for key, value in scope.get("headers", []) if key.lower() == name]

    @staticmethod
    def _strip_forwarded_headers(scope: Scope) -> Scope:
        def is_forwarding_header(key: bytes) -> bool:
            name = key.lower()
            return (name == b"forwarded" or name.startswith(b"x-forwarded-") or
                    name in {b"x-real-ip", b"x-original-host", b"x-original-proto", b"x-scheme",
                             b"x-url-scheme"})

        headers = scope.get("headers", [])
        if not any(is_forwarding_header(key) for key, _ in headers):
            return scope
        normalized = dict(scope)
        normalized["headers"] = [(key, value) for key, value in headers if not is_forwarding_header(key)]
        return normalized

    def _trusted_forwarded_scope(self, scope: Scope) -> tuple[Scope, bool, tuple[int, str] | None]:
        """Honor HTTPS forwarding only from an explicitly trusted proxy and allow-listed public host."""
        stripped_scope = self._strip_forwarded_headers(scope)
        present = stripped_scope is not scope
        client = scope.get("client")
        try:
            peer = ipaddress.ip_address(client[0]) if client else None
        except ValueError:
            peer = None
        trusted = peer is not None and any(peer in network for network in self.trusted_proxies)
        if not trusted:
            return stripped_scope, False, None
        if not present:
            return scope, False, None

        forwarded_host_values = self._header_values(scope, b"x-forwarded-host")
        forwarded_proto_values = self._header_values(scope, b"x-forwarded-proto")
        forwarded_for_values = self._header_values(scope, b"x-forwarded-for")
        if len(forwarded_host_values) != 1 or len(forwarded_proto_values) != 1 or len(forwarded_for_values) > 1:
            return scope, False, (400, "hutch: trusted proxy must send one X-Forwarded-Host and X-Forwarded-Proto.")
        try:
            external_host = forwarded_host_values[0].decode("ascii").strip()
            forwarded_proto = forwarded_proto_values[0].decode("ascii").strip().lower()
        except UnicodeDecodeError:
            return scope, False, (400, "hutch: trusted proxy sent invalid forwarding metadata.")
        if (not external_host or len(external_host) > 255 or
                any(char in external_host for char in "/\\?#@,;\r\n\t ")):
            return scope, False, (400, "hutch: trusted proxy sent an invalid public host.")
        try:
            parsed_host = urlsplit(f"//{external_host}")
            host = parsed_host.hostname or ""
            _ = parsed_host.port  # Access validates numeric range and syntax.
        except ValueError:
            return scope, False, (400, "hutch: trusted proxy sent an invalid public host.")
        if (not host or parsed_host.username is not None or parsed_host.password is not None or
                parsed_host.path or parsed_host.query or parsed_host.fragment):
            return scope, False, (400, "hutch: trusted proxy sent an invalid public host.")
        host = host.lower()
        if host not in self.forwarded_hosts:
            return scope, False, (421, "hutch: trusted proxy public host is not in HUTCH_ALLOWED_HOSTS.")
        if forwarded_proto != "https":
            return scope, False, (426, "hutch: trusted proxy must report HTTPS using X-Forwarded-Proto.")
        if not self.remote_enabled:
            return scope, False, (403, "hutch: trusted proxy access requires --allow-remote.")

        forwarded_client = None
        if forwarded_for_values:
            try:
                chain = [ipaddress.ip_address(part.strip()) for part in
                         forwarded_for_values[0].decode("ascii").split(",")]
            except (UnicodeDecodeError, ValueError):
                return scope, False, (400, "hutch: trusted proxy sent an invalid X-Forwarded-For chain.")
            if not chain or len(chain) > 16:
                return scope, False, (400, "hutch: trusted proxy X-Forwarded-For chain is invalid or too long.")
            chain.append(peer)
            forwarded_client = next((address for address in reversed(chain)
                                     if not any(address in network for network in self.trusted_proxies)), chain[0])

        normalized = dict(stripped_scope)
        normalized["scheme"] = "wss" if scope["type"] == "websocket" else "https"
        normalized_headers = [(key, value) for key, value in stripped_scope.get("headers", [])
                              if key.lower() != b"host"]
        normalized_headers.append((b"host", external_host.encode("ascii")))
        normalized["headers"] = normalized_headers
        if forwarded_client is not None and client is not None:
            normalized["client"] = (str(forwarded_client), client[1])
        normalized.setdefault("state", {})["hutch_trusted_proxy"] = True
        return normalized, True, None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "websocket":
            scope, trusted_proxy, error = self._trusted_forwarded_scope(scope)
            if error:
                await send({"type": "websocket.close", "code": 4403, "reason": error[1]})
                return
            await self._websocket(scope, receive, send, trusted_proxy=trusted_proxy)
            return
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        passkey_verify = scope.get("path") in {
            "/api/v1/passkeys/registration/verify", "/api/v1/passkeys/login/verify",
        }
        if passkey_verify:
            lengths = self._header_values(scope, b"content-length")
            if len(lengths) > 1:
                await PlainTextResponse("hutch: invalid passkey request length.", status_code=400)(scope, receive, send)
                return
            if lengths:
                try:
                    content_length = int(lengths[0].decode("ascii"))
                except (UnicodeDecodeError, ValueError):
                    await PlainTextResponse("hutch: invalid passkey request length.", status_code=400)(scope, receive, send)
                    return
                if content_length < 0:
                    await PlainTextResponse("hutch: invalid passkey request length.", status_code=400)(scope, receive, send)
                    return
                if content_length > MAX_PASSKEY_VERIFY_BODY_BYTES:
                    await PlainTextResponse("hutch: passkey credential payload is too large.", status_code=413)(
                        scope, receive, send)
                    return
        if scope.get("path") in ("/auth/callback", "/api/v1/connections/google-calendar/callback",
                                  "/api/v1/connections/google-mail/callback",
                                  "/api/v1/connections/outlook-calendar/callback",
                                  "/api/v1/connections/outlook-mail/callback",
                                  "/api/v1/connections/outlook-mail-send/callback"):
            # Authorization codes and state values must not survive in
            # Uvicorn's access-log scope, including rejected callback requests.
            query = scope.get("query_string", b"")
            if len(query) > 8192:
                scope["query_string"] = b""
                await PlainTextResponse("hutch: OAuth callback parameters are too large.", status_code=414)(
                    scope, receive, send)
                return
            scope["hutch_oauth_query"] = parse_qs(query.decode("ascii", errors="ignore"), keep_blank_values=True)
            scope["query_string"] = b""
        scope, trusted_proxy, forwarding_error = self._trusted_forwarded_scope(scope)
        if forwarding_error:
            status_code, detail = forwarding_error
            await PlainTextResponse(detail, status_code=status_code)(scope, receive, send)
            return
        # Tailscale Serve removes any client-supplied value and sets this marker
        # only for Funnel ingress. Hutch is deliberately private, so a public
        # Funnel must never reach even the anonymous pairing/login surface.
        if trusted_proxy and self._header_values(scope, b"tailscale-funnel-request"):
            await PlainTextResponse("hutch: public Funnel ingress is not accepted.", status_code=403)(
                scope, receive, send)
            return
        request = Request(scope, receive)
        host_header = request.headers.get("host", "")
        host = _host_only(host_header)

        # 1. DNS rebinding: only loopback / explicitly allowed names. With a token configured the
        #    attacker cannot authenticate anyway, so remote names are permitted.
        peer_is_local = self._peer_is_local(scope)
        if is_loopback_host(host) and not peer_is_local:
            await PlainTextResponse("hutch: a remote connection cannot use a loopback Host header.",
                                    status_code=421)(scope, receive, send)
            return
        if not (is_loopback_host(host) or host in self.extra_hosts or self.auth_token or self.remote_enabled):
            await PlainTextResponse(
                f"hutch: unexpected Host '{host_header}'. Use http://127.0.0.1:<port>, or set "
                "HUTCH_ALLOWED_HOSTS to allow this name.", status_code=421)(scope, receive, send)
            return

        # A configured Host name is not evidence that the request crossed a
        # network boundary for the one local in-process TestClient fixture.
        # Real direct requests are identified by their socket peer; proxy
        # requests are identified only after the exact trusted-proxy checks.
        client = scope.get("client")
        local_testclient = bool(client and client[0] == "testclient" and host == "testserver")
        remote_request = (trusted_proxy or not peer_is_local or
                          (not is_loopback_host(host) and not local_testclient))
        if not is_loopback_host(host) and host not in self.extra_hosts and not remote_request:
            # Do not let a loopback request reach Hutch through an attacker
            # controlled DNS-rebinding Host, even when remote mode is enabled.
            await PlainTextResponse(
                f"hutch: unexpected Host '{host_header}'. Use http://127.0.0.1:<port>, or set "
                "HUTCH_ALLOWED_HOSTS to allow this name.", status_code=421)(scope, receive, send)
            return
        if remote_request and scope.get("scheme") != "https":
            await PlainTextResponse("hutch: remote access requires HTTPS.", status_code=426)(scope, receive, send)
            return
        if remote_request and host not in self.extra_hosts:
            await PlainTextResponse("hutch: remote Host is not in HUTCH_ALLOWED_HOSTS.", status_code=421)(scope, receive, send)
            return
        scope.setdefault("state", {})["hutch_remote"] = remote_request

        # 2. CSRF: unsafe methods must be same-origin (browsers always send Origin on cross-site POST).
        if request.method in UNSAFE and not self._same_origin(request, host_header):
            await PlainTextResponse("hutch: cross-site request refused (Origin / Sec-Fetch-Site).",
                                    status_code=403)(scope, receive, send)
            return

        # 3. Local owner and paired-phone sessions are distinct principals. A local
        # owner token is never accepted over the network; remote access requires a
        # database-backed passkey session, checked on every request (including streams).
        path = request.url.path
        is_open = is_open_path(path)
        principal = None
        if remote_request and not self.remote_enabled:
            await PlainTextResponse("hutch: remote access is disabled.", status_code=403)(scope, receive, send)
            return
        if remote_request and not is_open:
            session_token = request.cookies.get(SESSION_COOKIE, "")
            principal = self.device_auth(session_token) if session_token and self.device_auth else None
            if not principal:
                if request.method == "GET" and "text/html" in request.headers.get("accept", ""):
                    await RedirectResponse("/login", status_code=303)(scope, receive, send)
                else:
                    await PlainTextResponse("hutch: paired passkey session required.", status_code=401)(scope, receive, send)
                return
        elif not remote_request:
            owner = self._owner_authed(request)
            paired_token = request.cookies.get(SESSION_COOKIE, "")
            principal = ({"kind": "owner", "capabilities": ["owner"]} if owner else
                         self.device_auth(paired_token) if paired_token and self.device_auth else
                         None if self._digest else {"kind": "owner", "capabilities": ["owner"]})
            if self._digest and not is_open and principal is None:
                if request.method == "GET" and "text/html" in request.headers.get("accept", ""):
                    await RedirectResponse("/login", status_code=303)(scope, receive, send)
                else:
                    await PlainTextResponse("hutch: authentication required.", status_code=401)(scope, receive, send)
                return

        scope.setdefault("state", {})["hutch_principal"] = principal

        # Passkey/session mutation endpoints are browser-only. SameSite cookies
        # are defense in depth; exact Origin and a custom header stop form CSRF.
        if (path.startswith("/api/v1/passkeys/") or path == "/api/v1/pairing/exchange"
                or path in {"/api/v1/session/logout", "/api/v1/session/activity"}):
            if request.method in UNSAFE and (request.headers.get("x-hutch-request") != "1"
                                             or not request.headers.get("origin")
                                             or not self._same_origin(request, host_header)):
                await PlainTextResponse("hutch: browser request verification failed.", status_code=403)(scope, receive, send)
                return

        # 4. Per-session CSRF token for server-rendered owner forms.
        token = request.cookies.get(CSRF_COOKIE)
        fresh = token is None
        if fresh:
            token = secrets.token_urlsafe(32)
        scope.setdefault("state", {})["csrf"] = token

        async def send_with_security_headers(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                existing = {key.lower() for key, _ in headers}
                security_headers = {
                    b"x-content-type-options": b"nosniff",
                    b"referrer-policy": b"no-referrer",
                    b"x-frame-options": b"DENY",
                    b"permissions-policy": b"camera=(), microphone=(), geolocation=()",
                }
                paired_request = bool(principal and principal.get("kind") == "paired")
                if remote_request or paired_request:
                    security_headers[b"content-security-policy"] = (
                        b"default-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; "
                        b"form-action 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                        b"img-src 'self' data:; connect-src 'self'")
                    security_headers[b"cache-control"] = b"private, no-store"
                    security_headers[b"pragma"] = b"no-cache"
                for key, value in security_headers.items():
                    if key not in existing:
                        headers.append((key, value))
                if fresh:
                    secure = "; Secure" if scope.get("scheme") == "https" else ""
                    headers.append((b"set-cookie", (
                        f"{CSRF_COOKIE}={token}; Path=/; SameSite=Strict; HttpOnly{secure}").encode()))
                message["headers"] = headers
            await send(message)

        app_receive = receive
        if passkey_verify:
            received_bytes = 0

            async def receive_limited():
                nonlocal received_bytes
                message = await receive()
                if message.get("type") == "http.request":
                    received_bytes += len(message.get("body", b""))
                    if received_bytes > MAX_PASSKEY_VERIFY_BODY_BYTES:
                        raise RequestBodyTooLarge
                return message

            app_receive = receive_limited
        try:
            await self.app(scope, app_receive, send_with_security_headers)
        except RequestBodyTooLarge:
            await PlainTextResponse("hutch: passkey credential payload is too large.", status_code=413)(
                scope, receive, send_with_security_headers)
        return

    @staticmethod
    def _same_origin(request: Request, host_header: str) -> bool:
        origin = request.headers.get("origin")
        if origin is not None:
            return SecurityMiddleware._origin_matches(origin, host_header, request.url.scheme)
        site = request.headers.get("sec-fetch-site")
        if site is not None:
            return site in ("same-origin", "none")
        return True  # not a browser: no ambient credentials to abuse

    @staticmethod
    def _origin_matches(origin: str, host_header: str, expected_scheme: str) -> bool:
        if origin == "null":
            return False
        try:
            parts = urlsplit(origin)
            _ = parts.port
        except ValueError:
            return False
        return (parts.scheme.lower() == expected_scheme.lower() and
                parts.netloc.lower() == host_header.strip().lower() and
                parts.username is None and parts.password is None and
                not parts.path and not parts.query and not parts.fragment)

    def _authed(self, request: Request) -> bool:
        """Backward-compatible predicate for local owner authentication only."""
        return self._owner_authed(request)

    def _owner_authed(self, request: Request) -> bool:
        cookie = request.cookies.get(AUTH_COOKIE, "")
        if self._digest and hmac.compare_digest(cookie, self._digest):
            return True
        bearer = request.headers.get("authorization", "")
        return bool(self.auth_token and bearer.startswith("Bearer ")
                    and hmac.compare_digest(bearer[7:], self.auth_token))

    @staticmethod
    def _peer_is_local(scope: Scope) -> bool:
        client = scope.get("client")
        if not client:
            return True
        try:
            return ipaddress.ip_address(client[0]).is_loopback
        except ValueError:  # Starlette's in-process TestClient uses "testclient".
            return True

    async def _websocket(self, scope: Scope, receive: Receive, send: Send, *, trusted_proxy: bool = False) -> None:
        headers = {k.lower(): v for k, v in scope.get("headers", [])}
        host_header = headers.get(b"host", b"").decode("latin-1")
        host = _host_only(host_header)
        origin = headers.get(b"origin", b"").decode("latin-1")
        peer_is_local = self._peer_is_local(scope)
        if is_loopback_host(host) and not peer_is_local:
            await send({"type": "websocket.close", "code": 4403, "reason": "remote loopback Host refused"})
            return
        if not (is_loopback_host(host) or host in self.extra_hosts or self.auth_token or self.remote_enabled):
            await send({"type": "websocket.close", "code": 4403, "reason": "unexpected Host"})
            return
        expected_origin_scheme = "https" if scope.get("scheme") == "wss" else "http"
        if origin and not self._origin_matches(origin, host_header, expected_origin_scheme):
            await send({"type": "websocket.close", "code": 4403, "reason": "cross-origin WebSocket refused"})
            return
        remote_request = trusted_proxy or not peer_is_local or (not is_loopback_host(host) and host not in self.extra_hosts)
        if remote_request and scope.get("scheme") != "wss":
            await send({"type": "websocket.close", "code": 4403, "reason": "remote WebSocket requires TLS"})
            return
        if remote_request:
            await send({"type": "websocket.close", "code": 4403, "reason": "remote WebSockets are disabled"})
            return
        if self._digest:
            bearer = headers.get(b"authorization", b"").decode("latin-1")
            auth_ok = bool(self.auth_token and bearer.startswith("Bearer ")
                           and hmac.compare_digest(bearer[7:], self.auth_token))
            if not auth_ok:
                await send({"type": "websocket.close", "code": 4401, "reason": "authentication required"})
                return
        await self.app(scope, receive, send)


def check_csrf(request: Request, submitted: Optional[str]) -> bool:
    """HTML forms / htmx posts must echo the session token (double-submit)."""
    cookie = request.cookies.get(CSRF_COOKIE)
    return bool(cookie and submitted and hmac.compare_digest(cookie, submitted))


def new_auth_token() -> str:
    return secrets.token_urlsafe(24)
