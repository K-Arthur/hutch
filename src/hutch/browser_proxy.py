"""A loopback HTTP proxy that pins browser connections to checked public addresses.

Chromium still owns TLS for CONNECT tunnels, so the browser keeps the original hostname for SNI and certificate checks. DNS is
resolved by this proxy, every answer is checked, and the socket connects to one of those numeric addresses without resolving the
hostname again. Plain HTTP and WebSocket upgrade requests use the same checked-and-pinned connection path. Chromium's implicit
loopback/link-local proxy bypass is removed by the browser launch configuration; see the upstream proxy contract in ADR-0006.
"""

from __future__ import annotations

import ipaddress
import contextlib
import re
import select
import socket
import socketserver
import threading
import time
from typing import Callable, Optional
from urllib.parse import urlsplit

from .netguard import LocalAccess, NetGuardError, display_url_origin, resolve_public, screen_url

MAX_CONNECTIONS = 64
MAX_HEADER_BYTES = 32 * 1024
CONNECT_TIMEOUT = 10.0
IDLE_TIMEOUT = 300.0
_HEADER_NAME = re.compile(rb"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")
_REQUEST_LINE = re.compile(rb"^([!#$%&'*+.^_`|~0-9A-Za-z-]+) ([^\x00-\x20\x7f]+) (HTTP/1\.[01])$")


class BrowserProxyError(RuntimeError):
    """The pinned egress proxy could not start or stop cleanly."""


class _Download:
    def __init__(self, url, referrer, path, check):
        self.url, self.referrer, self.path, self.check = url, referrer, path, check
        self.claimed = False
        self.done = threading.Event()
        self.data = None
        self.error = ""


class _ProxyServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = False
    block_on_close = True
    request_queue_size = MAX_CONNECTIONS

    def __init__(self, handler, resolver, connector, on_block, local_access=None):
        self.resolver = resolver
        self.local_access = local_access or LocalAccess()
        self.local_origins = self.local_access.origins
        self.connector = connector or (lambda address, port, timeout: socket.create_connection((address, port), timeout))
        self.on_block = on_block
        self.idle_timeout = IDLE_TIMEOUT
        self._slots = threading.BoundedSemaphore(MAX_CONNECTIONS)
        self._active_lock = threading.Lock()
        self._active: set[socket.socket] = set()
        self._download_lock = threading.Lock()
        self.download = None
        super().__init__(("127.0.0.1", 0), handler, bind_and_activate=True)

    def process_request(self, request, client_address):
        if not self._slots.acquire(blocking=False):
            request.close()
            return
        self.track(request)
        try:
            super().process_request(request, client_address)
        except Exception:
            self.untrack(request)
            self._slots.release()
            request.close()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.untrack(request)
            self._slots.release()

    def track(self, sock: socket.socket) -> None:
        with self._active_lock:
            self._active.add(sock)

    def untrack(self, sock: socket.socket) -> None:
        with self._active_lock:
            self._active.discard(sock)

    def close_active(self) -> None:
        with self._active_lock:
            active = tuple(self._active)
        for sock in active:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass

    def server_close(self):
        self.close_active()
        super().server_close()


class _ProxyHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        self.request.settimeout(IDLE_TIMEOUT)
        self._upstreams: list[socket.socket] = []
        self._tunnel_started = False
        try:
            header, extra = self._read_header(self.request)
            if header is None:
                return
            lines = header.split(b"\r\n")
            if not lines or not lines[0]:
                raise ValueError("empty proxy request")
            match = _REQUEST_LINE.fullmatch(lines[0])
            if match is None:
                raise ValueError("malformed proxy request line")
            method, target, version = (part.decode("ascii") for part in match.groups())
            headers = self._parse_headers(lines[1:])
            if method.upper() == "CONNECT":
                self._connect_tunnel(target, headers, extra)
            else:
                self._forward_http(method, target, version, headers, extra)
        except NetGuardError as exc:
            self._report_block(getattr(self, "target", ""), exc.reason)
            if not self._tunnel_started:
                self._error(403, "Forbidden", exc.reason)
        except (ValueError, UnicodeError) as exc:
            if not self._tunnel_started:
                self._error(400, "Bad Request", str(exc))
        except (OSError, TimeoutError) as exc:
            if not self._tunnel_started:
                self._error(502, "Bad Gateway", str(exc))
        finally:
            for upstream in self._upstreams:
                self.server.untrack(upstream)
                try:
                    upstream.close()
                except OSError:
                    pass

    @staticmethod
    def _read_header(sock: socket.socket, *, check=None, deadline=None) -> tuple[Optional[bytes], bytes]:
        data = bytearray()
        while True:
            if check:
                check()
            if deadline is not None and time.monotonic() > deadline:
                raise ValueError("proxy header exceeded its deadline")
            marker = data.find(b"\r\n\r\n")
            if marker >= 0:
                end = marker + 4
                if end > MAX_HEADER_BYTES:
                    raise ValueError("proxy headers exceed the size limit")
                return bytes(data[:end]), bytes(data[end:])
            if len(data) > MAX_HEADER_BYTES:
                raise ValueError("proxy request headers exceed the size limit")
            part = sock.recv(4096)
            if not part:
                return None, b""
            data.extend(part)

    @staticmethod
    def _parse_headers(lines: list[bytes]) -> list[tuple[str, str]]:
        result = []
        for line in lines:
            if not line:
                continue
            if b":" not in line:
                raise ValueError("malformed proxy request header")
            name, value = line.split(b":", 1)
            if not _HEADER_NAME.fullmatch(name):
                raise ValueError("malformed proxy request header name")
            value = value.strip(b" \t")
            if any(byte < 32 and byte != 9 or byte == 127 for byte in value):
                raise ValueError("control character in proxy request header")
            result.append((name.decode("ascii").lower(), value.decode("latin-1")))
        connection_tokens = {token.strip().lower() for name, value in result if name == "connection"
                             for token in value.split(",") if token.strip()}
        if connection_tokens.intersection({"content-length", "transfer-encoding"}):
            raise ValueError("Connection cannot nominate request-framing headers")
        preserve_upgrade = "upgrade" in connection_tokens and any(name == "upgrade" for name, _ in result)
        lengths = [value for name, value in result if name == "content-length"]
        if lengths and any(value != lengths[0] for value in lengths):
            raise ValueError("conflicting Content-Length headers")
        if lengths and (not lengths[0].isascii() or not lengths[0].isdecimal()):
            raise ValueError("invalid Content-Length header")
        transfer_encodings = [value for name, value in result if name == "transfer-encoding"]
        if lengths and transfer_encodings:
            raise ValueError("ambiguous request framing")
        if len(transfer_encodings) > 1 or (transfer_encodings and transfer_encodings[0].lower() != "chunked"):
            raise ValueError("unsupported Transfer-Encoding header")
        result = [(name, value) for name, value in result
                  if name not in {"host", "connection", "proxy-authorization", "proxy-connection", "keep-alive"}
                  and (name not in connection_tokens or (name == "upgrade" and preserve_upgrade))]
        return result

    def _parse_authority(self, authority: str) -> tuple[str, int]:
        value = urlsplit("//" + authority)
        if not value.hostname or value.username is not None or value.password is not None:
            raise ValueError("invalid CONNECT authority")
        if value.path or value.query or value.fragment:
            raise ValueError("invalid CONNECT authority")
        if value.port is None:
            raise ValueError("CONNECT requires an explicit port")
        if not 1 <= value.port <= 65535:
            raise ValueError("CONNECT port is outside the valid range")
        host = value.hostname.rstrip(".")
        self.target = f"https://[{host}]:{value.port}" if ":" in host else f"https://{host}:{value.port}"
        reason = screen_url(self.target)            # tunnels cannot be inspected: no local-development allowance
        if reason:
            raise NetGuardError(reason)
        return host, value.port

    def _open_checked(self, host: str, port: int, *, local_ok: bool = False) -> socket.socket:
        local = self.server.local_origins
        if local_ok and local and local.allows("http", host, port):
            addresses = local.addresses(host)        # approved local development origin: loopback literals, no DNS
        else:
            addresses = resolve_public(host, port, self.server.resolver)
        failures = []
        for address in addresses:
            try:
                ipaddress.ip_address(address)  # never pass a hostname to the connector
                upstream = self.server.connector(address, port, CONNECT_TIMEOUT)
                upstream.settimeout(None)
                self.server.track(upstream)
                self._upstreams.append(upstream)
                return upstream
            except OSError as exc:
                failures.append(exc)
        detail = failures[-1] if failures else "no usable public address"
        raise OSError(f"could not connect to a checked public address for '{host}': {detail}")

    def _connect_tunnel(self, authority: str, _headers, extra: bytes) -> None:
        host, port = self._parse_authority(authority)
        upstream = self._open_checked(host, port)
        self.request.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        self._tunnel_started = True
        if extra:
            upstream.sendall(extra)
        self._pump(self.request, upstream)

    def _forward_http(self, method: str, target: str, version: str,
                      headers: list[tuple[str, str]], extra: bytes) -> None:
        candidate = target
        if candidate.lower().startswith("ws://"):
            candidate = "http://" + candidate[5:]
        self.target = candidate
        reason = screen_url(candidate, self.server.local_origins)
        if reason:
            raise NetGuardError(reason)
        parts = urlsplit(candidate)
        if parts.scheme.lower() != "http" or not parts.hostname:
            raise ValueError("the HTTP proxy accepts absolute HTTP requests; HTTPS must use CONNECT")
        host = parts.hostname.rstrip(".")
        port = parts.port if parts.port is not None else 80
        if not 1 <= port <= 65535:
            raise ValueError("HTTP proxy port is outside the valid range")
        local_ok = self.server.local_origins.allows("http", host, port)
        if local_ok:
            context = self.server.local_access.refusal(candidate, headers)
            if context:
                raise NetGuardError(context)
        with self.server._download_lock:
            download = self.server.download
            if download is not None and download.url == candidate:
                if download.claimed or method != "GET" or dict(headers).get("referer") != download.referrer or extra:
                    raise NetGuardError("managed download changed or repeated; no automatic retry")
                download.claimed = True
            else:
                download = None
        upstream = self._open_checked(host, port, local_ok=local_ok)
        path = parts.path or "/"
        if parts.query:
            path += "?" + parts.query
        request_line = f"{method} {path} {version}\r\n".encode("latin-1")
        upgrade = any(name == "upgrade" for name, _ in headers)
        host_header = f"[{host}]" if ":" in host else host
        if port != 80:
            host_header += f":{port}"
        outgoing = [request_line, f"Host: {host_header}\r\n".encode("latin-1")]
        if download:
            download.check()
            headers = [(name, value) for name, value in headers if name != "accept-encoding"] + [("accept-encoding", "identity")]
        outgoing.extend(f"{name}: {value}\r\n".encode("latin-1") for name, value in headers)
        outgoing.append((b"Connection: Upgrade\r\n" if upgrade else b"Connection: close\r\n"))
        outgoing.append(b"\r\n")
        upstream.sendall(b"".join(outgoing))
        if extra:
            upstream.sendall(extra)
        if download:
            try:
                from .tools.browser_files import read_download
                data = read_download(upstream, self._read_header, download.path, download.check)
                response = (f"HTTP/1.1 200 OK\r\nContent-Type: text/plain; charset=utf-8\r\n"
                            f"Content-Length: {len(data)}\r\nConnection: close\r\n\r\n").encode()
                download.data = data
                self.request.sendall(response + data)
            except Exception:
                # No server exception text, cookies, paths or partial bytes in diagnostics.
                download.error = "managed download failed its response, size or authority checks; inspect before retrying"
                self._error(502, "Bad Gateway", download.error)
            finally:
                download.done.set()
            return
        self._tunnel_started = upgrade
        self._pump(self.request, upstream)

    def _pump(self, client: socket.socket, upstream: socket.socket) -> None:
        while True:
            readable, _, _ = select.select([client, upstream], [], [], self.server.idle_timeout)
            if not readable:
                return
            for source in readable:
                data = source.recv(64 * 1024)
                if not data:
                    return
                (upstream if source is client else client).sendall(data)

    def _report_block(self, target: str, reason: str) -> None:
        callback = self.server.on_block
        if callback:
            try:
                callback(display_url_origin(target), reason)
            except Exception:
                pass

    def _error(self, status: int, label: str, reason: str) -> None:
        safe = " ".join(str(reason).split())[:500]
        body = f"Hutch browser egress blocked the request: {safe}\n".encode("utf-8", "replace")
        response = (f"HTTP/1.1 {status} {label}\r\nContent-Type: text/plain; charset=utf-8\r\n"
                    f"X-Hutch-Egress-Block: 1\r\n"
                    f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n").encode("ascii")
        try:
            self.request.sendall(response + body)
        except OSError:
            pass


class PinnedBrowserProxy:
    """Owned, bounded loopback proxy. It validates and pins each new HTTP(S)/WebSocket connection."""

    def __init__(self, *, resolver: Optional[Callable[..., list]] = None,
                 connector: Optional[Callable[[str, int, float], socket.socket]] = None,
                 on_block: Optional[Callable[[str, str], None]] = None,
                 local_access: Optional[LocalAccess] = None):
        self._server = _ProxyServer(_ProxyHandler, resolver, connector, on_block, local_access)
        self._thread: Optional[threading.Thread] = None
        self._closed = False

    @property
    def url(self) -> str:
        host, port = self._server.server_address
        return f"http://{host}:{port}"

    def start(self) -> "PinnedBrowserProxy":
        if self._closed:
            raise BrowserProxyError("a closed browser proxy cannot be restarted")
        if self._thread is None:
            self._thread = threading.Thread(target=self._server.serve_forever, name="hutch-browser-proxy", daemon=False)
            self._thread.start()
        return self

    @contextlib.contextmanager
    def managed_download(self, url, referrer, path, check):
        download = _Download(url, referrer, path, check)
        with self._server._download_lock:
            if self._server.download is not None or self._closed:
                raise BrowserProxyError("a managed download is already active or the proxy is closed")
            self._server.download = download
        try:
            yield download
        finally:
            with self._server._download_lock:
                if self._server.download is download:
                    self._server.download = None
            download.data = None  # bounded ephemeral bytes, no download spool

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._thread is not None:
            self._server.shutdown()
            self._server.close_active()
            self._server.server_close()
            self._thread.join(timeout=5)
            if self._thread.is_alive():
                raise BrowserProxyError("browser proxy listener did not stop")
            self._thread = None
        else:
            self._server.server_close()
