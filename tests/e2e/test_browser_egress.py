"""Real Chromium checks for the browser's pinned local egress proxy.

All origins and proxy connections stay on loopback; fake DNS supplies only public answers.
"""

from __future__ import annotations

import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import Error as PlaywrightError, sync_playwright  # noqa: E402

from hutch.models import Bot  # noqa: E402
from hutch.tools.browser import BrowserTool  # noqa: E402


class _OriginHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        self.server.requests.append((self.path, self.headers.get("Host")))
        if urlsplit(self.path).path == "/redirect":
            self.send_response(302)
            self.send_header("Location", self.server.redirect_target)
            self.send_header("Content-Length", "0")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True
            return
        body = b"<title>Hutch pinned browser test</title><main>local fixture response</main>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def log_message(self, *_args):
        pass


class _OriginServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self):
        self.requests = []
        self.redirect_target = ""
        super().__init__(("127.0.0.1", 0), _OriginHandler)


def _public_resolver(addresses, calls):
    def resolve(host, port, **_kwargs):
        calls.append((host, port))
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port)) for address in addresses(host, port)]

    return resolve


def _launch_tool(config, name, resolver, connector, events):
    ctx = SimpleNamespace(
        config=config,
        bot=Bot(name=name),
        run=SimpleNamespace(id=f"run-{name}"),
        headless=True,
        emit=events.append,
        on_finish=[],
    )
    tool = BrowserTool(resolver=resolver, connector=connector)
    browser = tool._ensure(ctx)
    return tool, browser, ctx


def test_chromium_uses_pinned_proxy_for_the_actual_browser_request(config):
    origin = _OriginServer()
    thread = threading.Thread(target=origin.serve_forever, name="hutch-browser-proxy-origin", daemon=True)
    thread.start()
    dns_calls = []
    connected = []
    events = []
    resolver = _public_resolver(lambda _host, _port: ["93.184.216.34"], dns_calls)

    def connector(address, port, timeout):
        connected.append((address, port))
        assert port == origin.server_address[1]
        return socket.create_connection(origin.server_address, timeout=timeout)

    tool = None
    try:
        tool, browser, _ctx = _launch_tool(config, "pinned-browser-origin", resolver, connector, events)
        page = browser.pages[0]
        response = page.goto(f"http://safe.example:{origin.server_address[1]}/fixture?q=1",
                             wait_until="domcontentloaded", timeout=15_000)
        assert response is not None and response.status == 200
        assert page.title() == "Hutch pinned browser test"
        assert page.locator("main").inner_text() == "local fixture response"
        assert origin.requests and origin.requests[0] == ("/fixture?q=1", f"safe.example:{origin.server_address[1]}")
        assert connected and all(address == "93.184.216.34" for address, _ in connected)
        assert dns_calls and all(host == "safe.example" for host, _ in dns_calls)
    finally:
        if tool is not None:
            tool._teardown()
        origin.shutdown()
        origin.server_close()
        thread.join(timeout=2)
        assert not thread.is_alive()


def test_chromium_does_not_implicitly_bypass_proxy_for_a_loopback_url(config):
    origin = _OriginServer()
    thread = threading.Thread(target=origin.serve_forever, name="hutch-browser-loopback-origin", daemon=True)
    thread.start()
    events = []
    tool = None
    try:
        tool, browser, _ctx = _launch_tool(config, "pinned-browser-loopback", None, None, events)
        # Remove only the early URL route to prove that Chromium itself still sends local-address traffic to the proxy.
        browser.unroute("**/*")
        response = browser.pages[0].goto(f"http://127.0.0.1:{origin.server_address[1]}/must-not-reach-origin",
                                         wait_until="domcontentloaded", timeout=15_000)
        assert response is not None and response.status == 403
        assert "targeting a non-public address" in response.text()
        assert origin.requests == []
        assert any("127.0.0.1" in str(event.data) for event in events)
    finally:
        if tool is not None:
            tool._teardown()
        origin.shutdown()
        origin.server_close()
        thread.join(timeout=2)
        assert not thread.is_alive()


def test_chromium_webrtc_does_not_send_unproxied_udp(config):
    """A local STUN fixture proves the configured Chromium policy has no UDP bypass."""
    received = []
    stop = threading.Event()
    stun = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    stun.bind(("127.0.0.1", 0))
    stun.settimeout(0.1)
    port = stun.getsockname()[1]

    def receive():
        while not stop.is_set():
            try:
                packet, peer = stun.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                return
            received.append((packet, peer))

    thread = threading.Thread(target=receive, name="hutch-local-stun-fixture", daemon=True)
    thread.start()
    events = []
    tool = None
    try:
        # Negative control: without Hutch's policy, Chromium sends a STUN request directly to the fixture.
        with sync_playwright() as playwright:
            baseline = playwright.chromium.launch(headless=True)
            try:
                baseline_page = baseline.new_page()
                _gather_ice_candidates(baseline_page, port)
                deadline = time.monotonic() + 2
                while not received and time.monotonic() < deadline:
                    time.sleep(0.01)
            finally:
                baseline.close()
        assert received, "the local STUN fixture did not observe the direct-browser negative control"
        received.clear()

        tool, browser, _ctx = _launch_tool(config, "pinned-browser-webrtc", None, None, events)
        page = browser.pages[0]
        result = _gather_ice_candidates(page, port)
        assert result == "complete"
        assert not received, f"Chromium sent {len(received)} direct UDP datagram(s) to the local STUN fixture"
    finally:
        if tool is not None:
            tool._teardown()
        stop.set()
        stun.close()
        thread.join(timeout=2)
        assert not thread.is_alive()


def test_chromium_does_not_expose_a_local_file_after_an_http_redirect(config, tmp_path):
    marker = "hutch-local-file-redirect-must-not-be-readable"
    local_file = tmp_path / "private-fixture.txt"
    local_file.write_text(marker, encoding="utf-8")
    origin = _OriginServer()
    origin.redirect_target = local_file.as_uri()
    thread = threading.Thread(target=origin.serve_forever, name="hutch-browser-file-redirect", daemon=True)
    thread.start()
    events = []
    resolver = _public_resolver(lambda _host, _port: ["93.184.216.34"], [])
    connector = lambda _address, _port, timeout: socket.create_connection(origin.server_address, timeout=timeout)
    tool = None
    try:
        tool, browser, _ctx = _launch_tool(config, "pinned-browser-file-redirect", resolver, connector, events)
        page = browser.pages[0]
        try:
            page.goto(f"http://safe.example:{origin.server_address[1]}/redirect",
                      wait_until="domcontentloaded", timeout=15_000)
        except PlaywrightError as exc:
            assert "net::ERR_" in str(exc), str(exc)
        assert origin.requests == [("/redirect", f"safe.example:{origin.server_address[1]}")]
        page.wait_for_url("chrome-error://chromewebdata/", timeout=5_000)
        assert not page.url.startswith("file:")
        assert marker not in page.content()
    finally:
        if tool is not None:
            tool._teardown()
        origin.shutdown()
        origin.server_close()
        thread.join(timeout=2)
        assert not thread.is_alive()


def _gather_ice_candidates(page, port):
    return page.evaluate("""async (port) => {
        const peer = new RTCPeerConnection({iceServers: [{urls: `stun:127.0.0.1:${port}`}]});
        peer.createDataChannel('egress-check');
        await peer.setLocalDescription(await peer.createOffer());
        const deadline = Date.now() + 6000;
        while (peer.iceGatheringState !== 'complete' && Date.now() < deadline)
            await new Promise(resolve => setTimeout(resolve, 50));
        const state = peer.iceGatheringState;
        peer.close();
        return state;
    }""", port)


def test_chromium_proxy_rechecks_dns_on_redirect_after_the_early_route_allows_it(config):
    origin = _OriginServer()
    origin.redirect_target = f"http://rebind.example:{origin.server_address[1]}/private?token=fixture-secret"
    thread = threading.Thread(target=origin.serve_forever, name="hutch-browser-rebinding-origin", daemon=True)
    thread.start()
    dns_calls = []
    connected = []
    events = []
    answer_count = 0

    def answers(_host, _port):
        nonlocal answer_count
        answer_count += 1
        return ["93.184.216.34"] if answer_count <= 2 else ["127.0.0.1"]

    resolver = _public_resolver(answers, dns_calls)

    def connector(address, port, timeout):
        connected.append((address, port))
        return socket.create_connection(origin.server_address, timeout=timeout)

    tool = None
    try:
        tool, browser, _ctx = _launch_tool(config, "pinned-browser-rebinding", resolver, connector, events)
        response = browser.pages[0].goto(f"http://rebind.example:{origin.server_address[1]}/redirect",
                                         wait_until="domcontentloaded", timeout=15_000)
        assert response is not None and response.status == 403, {
            "status": response.status if response else None,
            "dns_answers": answer_count,
            "dns_calls": dns_calls,
            "connections": connected,
            "origin_requests": origin.requests,
        }
        assert "resolves to a non-public address" in response.text()
        assert answer_count == 3  # route allows the start; proxy pins it; redirect gets a fresh private answer
        assert connected == [("93.184.216.34", origin.server_address[1])]
        assert origin.requests == [("/redirect", f"rebind.example:{origin.server_address[1]}")]
        assert any("resolves to a non-public address" in str(event.data) for event in events)
        assert all("fixture-secret" not in str(event.data) for event in events)
    finally:
        if tool is not None:
            tool._teardown()
        origin.shutdown()
        origin.server_close()
        thread.join(timeout=2)
        assert not thread.is_alive()
