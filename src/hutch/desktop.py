"""Private desktop sidecar, with a bounded stdin/stdout readiness protocol.

The native host supplies an ephemeral owner token through stdin. It never
appears in arguments, URLs, the readiness line, or worker environments. Closing
the host's pipe requests normal server/worker shutdown; it does not leave an
unowned listener behind. The existing server owns policy and state.
"""

from __future__ import annotations

import json
import os
import socket
import sys
import threading
import time

PROTOCOL_VERSION = 1


def main() -> int:
    # A desktop launched with arbitrary remote/proxy configuration must still
    # bind privately. Remote access is an explicit separate CLI workflow.
    for key in ("HUTCH_REMOTE_ENABLED", "HUTCH_TRUSTED_PROXIES", "HUTCH_ALLOWED_HOSTS"):
        os.environ.pop(key, None)
    try:
        raw = sys.stdin.buffer.readline(4097)
        if not raw.endswith(b"\n") or len(raw) > 4096:
            raise ValueError
        bootstrap = json.loads(raw)
        token, nonce = bootstrap["token"], bootstrap["nonce"]
        if (not isinstance(token, str) or not 32 <= len(token) <= 128
                or not isinstance(nonce, str) or not 16 <= len(nonce) <= 128):
            raise ValueError
    except (ValueError, TypeError, KeyError):
        print("Hutch desktop startup requires a valid private host handshake.", file=sys.stderr)
        return 2

    import uvicorn
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    port = listener.getsockname()[1]
    os.environ["HUTCH_DASHBOARD_PORT"] = str(port)
    os.environ["HUTCH_EXECUTOR"] = "process"
    os.environ["HUTCH_AUTH_TOKEN"] = token
    try:
        from .server.app import create_app
        app = create_app()
    finally:
        # SecurityMiddleware captured the token as its constructor argument.
        # Workers and model tools must never inherit owner authority.
        os.environ.pop("HUTCH_AUTH_TOKEN", None)
    del token, bootstrap, raw
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port,
        access_log=False, log_level="error", timeout_graceful_shutdown=10))

    def host_pipe():
        # Any next line or EOF means Quit/host loss. No agent can obtain this
        # pipe: the worker launcher replaces stdin with DEVNULL.
        sys.stdin.buffer.readline(4097)
        server.should_exit = True

    def readiness():
        deadline = time.monotonic() + 30
        while not server.started and not server.should_exit and time.monotonic() < deadline:
            time.sleep(.02)
        if not server.started:
            server.should_exit = True
            return
        print(json.dumps({"protocol": PROTOCOL_VERSION, "port": port, "nonce": nonce,
                          "pid": os.getpid()}), flush=True)

    threading.Thread(target=host_pipe, name="hutch-desktop-host", daemon=True).start()
    threading.Thread(target=readiness, name="hutch-desktop-ready", daemon=True).start()
    try:
        server.run(sockets=[listener])
    finally:
        listener.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
