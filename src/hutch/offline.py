"""Loopback-only model broker used by Strict Offline workers.

Offline workers run in a bubblewrap network namespace with no host interfaces.
Their HTTPX transport connects to a per-run Unix socket; the supervisor-side
broker forwards requests only to the bot's already-validated loopback model
origin. It never accepts an address or authority from the worker.
"""

from __future__ import annotations

import hashlib
import http.client
import ipaddress
import os
import socketserver
import tempfile
import threading
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Iterable
from urllib.parse import urlsplit

BROKER_MOUNT = "/run/hutch-offline"
MAX_REQUEST_BYTES = 64 * 1024 * 1024
MAX_BROKER_CONNECTIONS = 8
UPSTREAM_TIMEOUT_SECONDS = 900
CLIENT_IDLE_TIMEOUT_SECONDS = 900


def _origin(endpoint: str) -> tuple[str, str, int, str]:
    parts = urlsplit(endpoint)
    if (parts.scheme != "http" or not parts.hostname or parts.username is not None or
            parts.password is not None or parts.query or parts.fragment):
        raise ValueError("Strict Offline model brokers require a plain HTTP loopback endpoint")
    host = parts.hostname.lower()
    if "%" in parts.hostname:
        raise ValueError("Strict Offline model endpoints cannot use scoped IPv6 addresses")
    try:
        port = parts.port if parts.port is not None else 80
    except ValueError as exc:
        raise ValueError("Strict Offline model endpoint has an invalid port") from exc
    if not 1 <= port <= 65535:
        raise ValueError("Strict Offline model endpoint needs a valid nonzero port")
    try:
        address = ipaddress.ip_address(host)
    except ValueError as exc:
        raise ValueError("Strict Offline model broker endpoints must use numeric loopback addresses") from exc
    if not address.is_loopback:
        raise ValueError("Strict Offline model broker endpoints must use loopback")
    host = address.compressed
    authority = f"[{host}]:{port}" if ":" in host else f"{host}:{port}"
    return parts.scheme, host, port, authority


def broker_name(endpoint: str) -> str:
    scheme, host, port, _ = _origin(endpoint)
    return hashlib.sha256(f"{scheme}://{host}:{port}".encode()).hexdigest()[:24] + ".sock"


def broker_socket_path(directory: str | Path, endpoint: str) -> str:
    return str(Path(directory) / broker_name(endpoint))


def httpx_offline_options(base_url: str, provider: str) -> tuple[str, object | None, bool]:
    """Return canonical URL, a UDS transport, and trust_env for a worker provider.

    Outside an Offline worker this is a no-op. Inside one, there is deliberately
    no fallback to a direct TCP transport if the broker is missing.
    """
    directory = os.environ.get("HUTCH_OFFLINE_BROKER_DIR")
    if not directory:
        return base_url, None, True
    from .providers.registry import loopback_endpoint

    canonical = loopback_endpoint(provider, base_url)
    _origin(canonical)
    path = broker_socket_path(directory, canonical)
    if not Path(path).exists():
        raise RuntimeError("Strict Offline model broker is missing; no direct network fallback is allowed")
    import httpx
    return canonical, httpx.HTTPTransport(uds=path, retries=0), False


class _BoundedUnixHTTPServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True
    block_on_close = False
    request_queue_size = MAX_BROKER_CONNECTIONS

    def __init__(self, path: str, handler, broker: "LoopbackBroker"):
        self.broker = broker
        self._slots = threading.BoundedSemaphore(MAX_BROKER_CONNECTIONS)
        super().__init__(path, handler)

    def process_request(self, request, client_address):
        if not self._slots.acquire(blocking=False):
            request.close()
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()


class _BrokerHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server: _BoundedUnixHTTPServer

    def setup(self) -> None:
        self.request.settimeout(CLIENT_IDLE_TIMEOUT_SECONDS)
        super().setup()

    def handle_expect_100(self) -> bool:
        self._reject(417, "expect headers are not accepted by the model broker")
        return False

    def log_message(self, _format: str, *_args) -> None:
        return

    def end_headers(self) -> None:
        super().end_headers()
        self._headers_sent = True

    def _reject(self, status: int, message: str) -> None:
        body = message.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            self.wfile.write(body)
        except OSError:
            pass
        self.close_connection = True

    def _target_path(self) -> str | None:
        target = self.path
        if not target.startswith("/") or target.startswith("//") or any(c in target for c in "\r\n#"):
            return None
        parsed = urlsplit(target)
        if parsed.scheme or parsed.netloc or not parsed.path.startswith("/"):
            return None
        host_headers = self.headers.get_all("Host", [])
        if len(host_headers) != 1:
            return None
        supplied = host_headers[0]
        try:
            supplied_parts = urlsplit(f"http://{supplied}")
            supplied_host = (supplied_parts.hostname or "").lower()
            supplied_port = supplied_parts.port if supplied_parts.port is not None else 80
        except ValueError:
            return None
        if supplied_host != self.server.broker.host or supplied_port != self.server.broker.port:
            return None
        return target

    def _proxy(self) -> None:
        if self.command not in {"GET", "POST"}:
            self._reject(405, "method is not allowed by the model broker")
            return
        target_path = self._target_path()
        if target_path is None:
            self._reject(400, "request authority or path does not match the configured model endpoint")
            return
        if self.headers.get("Expect"):
            self._reject(417, "expect headers are not accepted by the model broker")
            return
        if self.headers.get("Transfer-Encoding"):
            self._reject(400, "chunked request bodies are not accepted by the model broker")
            return
        lengths = self.headers.get_all("Content-Length", [])
        if len(lengths) > 1:
            self._reject(400, "duplicate request lengths are not accepted by the model broker")
            return
        length = lengths[0] if lengths else "0"
        if not length.isascii() or not length.isdigit():
            self._reject(400, "invalid request length")
            return
        size = int(length)
        if size < 0 or size > MAX_REQUEST_BYTES:
            self._reject(413, "model request exceeds the broker's 64 MiB limit")
            return
        body = self.rfile.read(size) if size else None
        if size and len(body or b"") != size:
            self._reject(400, "request body ended early")
            return

        headers = {}
        hop_by_hop = {"connection", "keep-alive", "proxy-authorization", "proxy-authenticate", "transfer-encoding",
                      "upgrade", "trailer", "host", "content-length"}
        hop_by_hop.update(token.strip().lower()
                          for value in self.headers.get_all("Connection", [])
                          for token in value.split(",") if token.strip())
        for key, value in self.headers.items():
            if key.lower() not in hop_by_hop:
                headers[key] = value
        upstream = http.client.HTTPConnection(self.server.broker.host, self.server.broker.port,
                                               timeout=UPSTREAM_TIMEOUT_SECONDS)
        if not self.server.broker._register(upstream):
            self._reject(502, "the model broker is closing")
            return
        try:
            upstream.request(self.command, target_path, body=body, headers=headers)
            response = upstream.getresponse()
            self.send_response(response.status, http.client.responses.get(response.status, "Response"))
            response_hop_by_hop = set(hop_by_hop)
            response_hop_by_hop.update(token.strip().lower()
                                        for token in response.getheader("Connection", "").split(",")
                                        if token.strip())
            for key, value in response.getheaders():
                if key.lower() not in response_hop_by_hop and key.lower() != "content-length":
                    self.send_header(key, value)
            no_body = self.command == "HEAD" or response.status in (204, 205, 304)
            if no_body:
                self.send_header("Connection", "close")
            else:
                self.send_header("Transfer-Encoding", "chunked")
                self.send_header("Connection", "close")
            self.end_headers()
            if not no_body:
                # read1 returns available upstream frames without waiting for a
                # model stream to fill a large buffer.
                while chunk := response.read1(64 * 1024):
                    self.wfile.write(f"{len(chunk):X}\r\n".encode("ascii"))
                    self.wfile.write(chunk)
                    self.wfile.write(b"\r\n")
                    self.wfile.flush()
                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()
            self.close_connection = True
        except (OSError, http.client.HTTPException, TimeoutError):
            if not getattr(self, "_headers_sent", False):
                self._reject(502, "the configured loopback model service did not answer")
            self.close_connection = True
        finally:
            self.server.broker._unregister(upstream)
            upstream.close()

    do_GET = _proxy
    do_POST = _proxy
    do_HEAD = _proxy
    do_PUT = _proxy
    do_PATCH = _proxy
    do_DELETE = _proxy
    do_OPTIONS = _proxy


class LoopbackBroker:
    """One private Unix socket that forwards to one validated loopback origin."""

    def __init__(self, endpoint: str, directory: str):
        _, self.host, self.port, self.authority = _origin(endpoint)
        self.path = broker_socket_path(directory, endpoint)
        self.server = _BoundedUnixHTTPServer(self.path, _BrokerHandler, self)
        os.chmod(self.path, 0o600)
        self._active: set[http.client.HTTPConnection] = set()
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self.server.serve_forever, name="hutch-offline-broker", daemon=True)
        self._started = False
        self._closed = False

    def start(self) -> None:
        if self._closed:
            raise RuntimeError("cannot start a closed loopback model broker")
        self._thread.start()
        self._started = True

    def _register(self, conn: http.client.HTTPConnection) -> bool:
        with self._lock:
            if self._closed:
                conn.close()
                return False
            self._active.add(conn)
            return True

    def _unregister(self, conn: http.client.HTTPConnection) -> None:
        with self._lock:
            self._active.discard(conn)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            connections = list(self._active)
            self._active.clear()
        for conn in connections:
            conn.close()
        if self._started:
            self.server.shutdown()
            self._thread.join(timeout=2)
        self.server.server_close()
        try:
            Path(self.path).unlink()
        except FileNotFoundError:
            pass


class OfflineBrokerSet:
    """Run-scoped broker sockets for every local fallback/escalation endpoint."""

    def __init__(self, endpoints: Iterable[str]):
        self._temp = tempfile.TemporaryDirectory(prefix="hutch-o-", dir="/tmp")
        os.chmod(self._temp.name, 0o700)
        self.brokers = []
        self.directory = self._temp.name
        self._closed = False
        try:
            unique = {}
            for endpoint in endpoints:
                if endpoint:
                    unique.setdefault(broker_name(endpoint), endpoint)
            for endpoint in unique.values():
                self.brokers.append(LoopbackBroker(endpoint, self._temp.name))
        except BaseException:
            for broker in self.brokers:
                broker.close()
            self._temp.cleanup()
            self._closed = True
            raise

    def start(self) -> None:
        try:
            for broker in self.brokers:
                broker.start()
        except BaseException:
            for broker in self.brokers:
                broker.close()
            self._temp.cleanup()
            self._closed = True
            raise

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for broker in self.brokers:
            broker.close()
        self._temp.cleanup()
