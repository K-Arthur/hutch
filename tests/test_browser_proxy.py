import socket
import socketserver
import threading

import pytest

from hutch.browser_proxy import PinnedBrowserProxy


class _Origin(socketserver.BaseRequestHandler):
    def handle(self):
        data = bytearray()
        while b"\r\n\r\n" not in data:
            part = self.request.recv(4096)
            if not part:
                return
            data.extend(part)
        self.server.requests.append(bytes(data))
        if self.server.mode == "echo":
            self.request.sendall(data[data.find(b"\r\n\r\n") + 4:])
            return
        status = b"101 Switching Protocols\r\n" if self.server.mode == "upgrade" else b"200 OK\r\n"
        body = b"pinned response"
        headers = b"" if self.server.mode == "upgrade" else (
            f"Content-Length: {len(body)}\r\nConnection: close\r\n".encode("ascii"))
        self.request.sendall(b"HTTP/1.1 " + status + headers + b"\r\n" + (b"" if self.server.mode == "upgrade" else body))


class _OriginServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, mode="http"):
        self.mode = mode
        self.requests = []
        super().__init__(("127.0.0.1", 0), _Origin)


class _Echo(socketserver.BaseRequestHandler):
    def handle(self):
        while data := self.request.recv(4096):
            self.request.sendall(data)


class _EchoServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def _resolver_for(addresses):
    calls = []

    def resolver(host, port, **kwargs):
        calls.append((host, port))
        return [(socket.AF_INET if ":" not in item else socket.AF_INET6,
                 socket.SOCK_STREAM, 6, "", (item, port)) for item in addresses]

    return resolver, calls


def _read_all(sock):
    parts = []
    while True:
        data = sock.recv(4096)
        if not data:
            return b"".join(parts)
        parts.append(data)


def test_http_proxy_connects_to_checked_numeric_address_and_rewrites_origin_form():
    origin = _OriginServer()
    thread = threading.Thread(target=origin.serve_forever, daemon=True)
    thread.start()
    resolver, dns_calls = _resolver_for(["93.184.216.34"])
    connected = []

    def connector(address, port, timeout):
        connected.append((address, port))
        return socket.create_connection(origin.server_address, timeout)

    proxy = PinnedBrowserProxy(resolver=resolver, connector=connector).start()
    try:
        with socket.create_connection(proxy._server.server_address, timeout=2) as client:
            client.sendall(b"GET http://safe.example:8080/path?q=1 HTTP/1.1\r\n"
                           b"Host: attacker.example\r\nProxy-Connection: keep-alive\r\n"
                           b"Proxy-Authorization: Basic c2VjcmV0\r\n\r\n")
            response = _read_all(client)
        assert response.startswith(b"HTTP/1.1 200 OK") and response.endswith(b"pinned response")
        assert connected == [("93.184.216.34", 8080)]
        assert dns_calls == [("safe.example", 8080)]
        request = origin.requests[0]
        assert request.startswith(b"GET /path?q=1 HTTP/1.1\r\n")
        assert b"Host: safe.example:8080\r\n" in request
        assert b"Proxy-Authorization" not in request and b"Proxy-Connection" not in request
        assert b"Connection: close\r\n" in request
    finally:
        proxy.close()
        origin.shutdown()
        origin.server_close()
        thread.join(timeout=2)


def test_proxy_rejects_a_dns_rebinding_answer_before_connecting():
    resolver, dns_calls = _resolver_for(["93.184.216.34", "127.0.0.1"])
    connected = []
    blocked = []
    proxy = PinnedBrowserProxy(resolver=resolver,
                               connector=lambda address, port, timeout: connected.append((address, port)),
                               on_block=lambda url, reason: blocked.append((url, reason))).start()
    try:
        with socket.create_connection(proxy._server.server_address, timeout=2) as client:
            client.sendall(b"CONNECT rebind.example:443 HTTP/1.1\r\nHost: rebind.example:443\r\n\r\n")
            response = _read_all(client)
        assert response.startswith(b"HTTP/1.1 403 Forbidden")
        assert b"resolves to a non-public address" in response
        assert dns_calls == [("rebind.example", 443)]
        assert connected == []
        assert blocked and blocked[0][0] == "https://rebind.example:443"
    finally:
        proxy.close()


def test_block_log_omits_url_path_query_and_userinfo():
    resolver, _ = _resolver_for(["127.0.0.1"])
    blocked = []
    proxy = PinnedBrowserProxy(resolver=resolver, on_block=lambda url, reason: blocked.append((url, reason))).start()
    try:
        with socket.create_connection(proxy._server.server_address, timeout=2) as client:
            client.sendall(b"GET http://rebind.example/private?token=secret HTTP/1.1\r\n\r\n")
            response = _read_all(client)
        assert response.startswith(b"HTTP/1.1 403 Forbidden")
        assert blocked[0][0] == "http://rebind.example"
        assert "secret" not in str(blocked)
    finally:
        proxy.close()


def test_proxy_preserves_websocket_upgrade_headers():
    origin = _OriginServer(mode="upgrade")
    thread = threading.Thread(target=origin.serve_forever, daemon=True)
    thread.start()
    resolver, _ = _resolver_for(["93.184.216.34"])
    connector = lambda _address, _port, timeout: socket.create_connection(origin.server_address, timeout)
    proxy = PinnedBrowserProxy(resolver=resolver, connector=connector).start()
    try:
        with socket.create_connection(proxy._server.server_address, timeout=2) as client:
            client.sendall(b"GET ws://socket.example/socket HTTP/1.1\r\nHost: socket.example\r\n"
                           b"Connection: keep-alive, Upgrade\r\nUpgrade: websocket\r\n\r\n")
            response = _read_all(client)
        assert response.startswith(b"HTTP/1.1 101 Switching Protocols")
        request = origin.requests[0]
        assert request.startswith(b"GET /socket HTTP/1.1\r\n")
        assert b"Connection: Upgrade\r\n" in request and b"upgrade: websocket\r\n" in request
    finally:
        proxy.close()
        origin.shutdown()
        origin.server_close()
        thread.join(timeout=2)


def test_connect_tunnel_pins_the_destination_and_forwards_tls_stream_bytes():
    origin = _EchoServer(("127.0.0.1", 0), _Echo)
    thread = threading.Thread(target=origin.serve_forever, daemon=True)
    thread.start()
    resolver, dns_calls = _resolver_for(["93.184.216.34"])
    connected = []

    def connector(address, port, timeout):
        connected.append((address, port))
        assert port == 443
        return socket.create_connection(origin.server_address, timeout=timeout)

    proxy = PinnedBrowserProxy(resolver=resolver, connector=connector).start()
    try:
        with socket.create_connection(proxy._server.server_address, timeout=2) as client:
            client.settimeout(2)
            client.sendall(b"CONNECT safe.example:443 HTTP/1.1\r\nHost: safe.example:443\r\n\r\n")
            response = bytearray()
            while b"\r\n\r\n" not in response:
                response.extend(client.recv(4096))
            assert bytes(response).startswith(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            client.sendall(b"TLS client hello fixture")
            assert client.recv(4096) == b"TLS client hello fixture"
        assert connected == [("93.184.216.34", 443)]
        assert dns_calls == [("safe.example", 443)]
    finally:
        proxy.close()
        origin.shutdown()
        origin.server_close()
        thread.join(timeout=2)
        assert not thread.is_alive()


@pytest.mark.parametrize("request_bytes", [
    b"CONNECT safe.example:0 HTTP/1.1\r\nHost: safe.example:0\r\n\r\n",
    b"CONNECT safe.example:443 HTTP/1.1\r\nHost: safe.example:443\r\nX-Test: safe\x00value\r\n\r\n",
])
def test_proxy_rejects_invalid_authority_or_control_headers_without_resolving(request_bytes):
    resolver, dns_calls = _resolver_for(["93.184.216.34"])
    proxy = PinnedBrowserProxy(resolver=resolver).start()
    try:
        with socket.create_connection(proxy._server.server_address, timeout=2) as client:
            client.sendall(request_bytes)
            response = _read_all(client)
        assert response.startswith(b"HTTP/1.1 400 Bad Request")
        assert dns_calls == []
    finally:
        proxy.close()
