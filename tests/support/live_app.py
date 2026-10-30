"""Start a real local uvicorn server around a Hutch app for browser tests.

The e2e modules each carried their own copy of this; new modules share it.
"""

from __future__ import annotations

import threading
import time
from contextlib import contextmanager

import uvicorn


@contextmanager
def serve(app):
    """Yield the base URL of `app` served on a free loopback port; stop it on exit."""
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error", lifespan="on"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while not server.started and time.time() < deadline:
        time.sleep(0.02)
    assert server.started, "local Hutch server did not start"
    port = server.servers[0].sockets[0].getsockname()[1]
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        assert not thread.is_alive()


class PageWatch:
    """Collect console errors, page errors and failed requests for one page."""

    def __init__(self, page) -> None:
        self.errors: list[str] = []
        page.on("pageerror", lambda error: self.errors.append(f"pageerror: {error}"))
        page.on("console", lambda msg: self.errors.append(f"console: {msg.text}") if msg.type == "error" else None)
        page.on("requestfailed", lambda req: self.errors.append(f"requestfailed: {req.url}"))

    def clear(self) -> None:
        self.errors.clear()


def horizontal_overflow(page) -> int:
    """Pixels by which the document is wider than the viewport (0 means none)."""
    return page.evaluate("Math.max(0, document.documentElement.scrollWidth - window.innerWidth)")
