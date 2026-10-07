"""Server-sent events with gap-free resume (UI-3) and coalesced delivery (PF-9).

The failure this exists to avoid: OpenCode's event stream ignored ``Last-Event-ID``, so a backgrounded
tab silently lost every event emitted while it was away (opencode #25657). Here the cursor *is* the
per-run event ``seq`` and the source of truth is the database, not a ring buffer:

* each message carries ``id: <last seq>``; browsers echo it as ``Last-Event-ID`` on reconnect;
* the server replays everything with ``seq > cursor`` straight from SQLite, so any gap, of any length,
  is filled exactly once — including after a server restart;
* bursts are coalesced (a short wait, then one message of up to 200 events) so a chatty run does
  not become one network message per event.

Streams are asyncio generators that wait on a bus subscription, so an idle open stream costs no thread.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Callable, Optional

from starlette.requests import Request

from ..models import Event, RunStatus

BATCH = 200
COALESCE_SECONDS = 0.08
KEEPALIVE_SECONDS = 15.0
FINISHED = (RunStatus.succeeded, RunStatus.failed, RunStatus.stopped, RunStatus.skipped)


def sse_message(event: str, payload: dict[str, Any], id_: Optional[int] = None) -> bytes:
    """JSON payloads keep multi-line HTML on one ``data:`` line, as the SSE framing requires."""
    head = f"id: {id_}\n" if id_ is not None else ""
    return f"{head}event: {event}\ndata: {json.dumps(payload, separators=(',', ':'))}\n\n".encode()


def resume_cursor(request: Request, after: int = 0) -> int:
    """``Last-Event-ID`` (set by the browser on reconnect) wins over the page's initial ``?after=``."""
    header = request.headers.get("last-event-id", "").strip()
    if header.isdigit():
        return int(header)
    return max(0, after)


async def run_event_stream(request: Request, store, run_id: str, cursor: int,
                           render: Callable[[list[Event], Any], dict[str, Any]]):
    bus = store.bus
    loop = asyncio.get_running_loop()
    wake = asyncio.Event()
    unsubscribe = bus.subscribe([f"run:{run_id}"], lambda: loop.call_soon_threadsafe(wake.set))
    try:
        yield b"retry: 1500\n\n"
        while True:
            wake.clear()
            events = await asyncio.to_thread(store.list_events, run_id, cursor, BATCH)
            if events:
                if len(events) < BATCH:  # let the rest of a burst land, then send one message
                    await asyncio.sleep(COALESCE_SECONDS)
                    events += await asyncio.to_thread(store.list_events, run_id, events[-1].seq,
                                                      BATCH - len(events))
                run = await asyncio.to_thread(store.get_run, run_id)
                payload = render(events, run)
                payload.update(first=events[0].seq, last=events[-1].seq,
                               status=run.status.value if run else "unknown")
                cursor = events[-1].seq
                yield sse_message("batch", payload, cursor)
                continue
            run = await asyncio.to_thread(store.get_run, run_id)
            if run is None:
                yield sse_message("end", {"status": "missing", "last": cursor}, cursor)
                return
            if run.status in FINISHED:
                # status flips only after the final event is committed, but re-read once to be sure
                tail = await asyncio.to_thread(store.list_events, run_id, cursor, 1)
                if not tail:
                    yield sse_message("end", {"status": run.status.value, "last": cursor}, cursor)
                    return
                continue
            try:
                await asyncio.wait_for(wake.wait(), timeout=KEEPALIVE_SECONDS)
            except asyncio.TimeoutError:
                yield b": keepalive\n\n"
    finally:
        unsubscribe()


async def live_stream(request: Request, store, topics: list[str]):
    """Global 'something changed' stream for Home / approvals badge: coalesced refresh hints."""
    bus = store.bus
    loop = asyncio.get_running_loop()
    wake = asyncio.Event()
    unsubscribe = bus.subscribe(topics, lambda: loop.call_soon_threadsafe(wake.set))
    try:
        yield b"retry: 2000\n\n"
        yield sse_message("hello", {"topics": topics})
        while True:
            try:
                await asyncio.wait_for(wake.wait(), timeout=KEEPALIVE_SECONDS)
            except asyncio.TimeoutError:
                yield b": keepalive\n\n"
                continue
            await asyncio.sleep(0.25)  # coalesce a flurry of changes into one refresh
            wake.clear()               # clear AFTER the pause: a change landing later re-arms the event
            yield sse_message("refresh", {"t": 1})
    finally:
        unsubscribe()
