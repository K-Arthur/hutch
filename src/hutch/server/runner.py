"""Run the dashboard server so that stopping it is prompt and quiet.

Open event streams (a dashboard tab keeps several) otherwise hold uvicorn's graceful shutdown until its timeout
cancels them: every Ctrl+C waited ten seconds and printed an ASGI traceback. Here the moment uvicorn is told to
exit (a signal, or the desktop host setting `should_exit`) every stream is woken and ends itself, so the listener
closes and the scheduler and store stop straight away. The timeout stays as the net for a request that is slow
for another reason.
"""

from __future__ import annotations

import sys

import uvicorn

from . import sse

GRACEFUL_SECONDS = 10
STARTUP_FAILURE = 3             # uvicorn's own exit code when the server never started


class GracefulServer(uvicorn.Server):
    """A uvicorn server that tells open event streams to finish as soon as it is asked to exit."""

    async def startup(self, sockets=None) -> None:
        sse.SHUTTING_DOWN.clear()       # a server started later in the same process begins with streams allowed
        await super().startup(sockets=sockets)

    @property
    def should_exit(self) -> bool:
        return self.__dict__.get("_should_exit", False)

    @should_exit.setter
    def should_exit(self, value: bool) -> None:
        self.__dict__["_should_exit"] = value
        if value:
            sse.begin_shutdown()


def serve(**options) -> None:
    """`hutch serve`: the dashboard app factory on the given host and port."""
    config = uvicorn.Config("hutch.server.app:create_app", factory=True, timeout_graceful_shutdown=GRACEFUL_SECONDS, **options)
    server = GracefulServer(config)
    try:
        server.run()
    except KeyboardInterrupt:       # uvicorn re-raises the Ctrl+C it already handled; stopping the server is not an error
        return
    if not server.started:
        sys.exit(STARTUP_FAILURE)
