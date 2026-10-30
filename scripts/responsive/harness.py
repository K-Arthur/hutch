"""Processes and browser sessions used by the responsive validation run."""

from __future__ import annotations

import functools
import http.server
import threading
import time
from pathlib import Path


def _wait_until(predicate, timeout_s: float, message: str) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    raise RuntimeError(message)


class LiveApp:
    """Run the real Hutch app on an ephemeral loopback port with a fresh store."""

    def __init__(self) -> None:
        self._server = None
        self._thread = None

    def start(self) -> str:
        import uvicorn

        from hutch.server.app import create_app
        from responsive.seeding import seed_workspace

        app = create_app()
        seed_workspace(app.state.store)
        config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error", lifespan="on")
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run, daemon=True)
        self._thread.start()
        _wait_until(lambda: self._server.started, 15, "Hutch preview did not start")
        port = self._server.servers[0].sockets[0].getsockname()[1]
        return "http://127.0.0.1:%d" % port

    def stop(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=10)
        self._server = None
        self._thread = None


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass


class SiteServer:
    """Serve the static marketing site from website/ on an ephemeral port."""

    def __init__(self) -> None:
        self._httpd = None
        self._thread = None

    def start(self) -> str:
        directory = str(Path(__file__).resolve().parents[2] / "website")
        handler = functools.partial(_QuietHandler, directory=directory)
        self._httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        port = self._httpd.server_address[1]
        return "http://127.0.0.1:%d" % port

    def stop(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._httpd = None
        self._thread = None


def launch_browser(playwright, headed: bool = False):
    """Launch Chromium, falling back to Firefox when Chromium is unavailable."""
    last_error = None
    for engine in (playwright.chromium, playwright.firefox):
        try:
            return engine.launch(headless=not headed)
        except Exception as error:  # pragma: no cover - environment dependent
            last_error = error
    raise RuntimeError("no Playwright browser is installed: %s" % last_error)
