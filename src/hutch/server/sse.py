"""Server-sent events with gap-free resume (UI-3) and coalesced delivery (PF-9).

The failure this exists to avoid: OpenCode's event stream ignored ``Last-Event-ID``, so a backgrounded
tab silently lost every event emitted while it was away (opencode #25657). Here the cursor *is* the
per-run event ``seq`` and the source of truth is the database, not a ring buffer:

* each message carries ``id: <last seq>``; browsers echo it as ``Last-Event-ID`` on reconnect;
* the server replays everything with ``seq > cursor`` straight from SQLite, so any gap, of any length,
  is filled exactly once, including after a server restart;
* bursts are coalesced (a short wait, then one message of up to 200 events) so a chatty run does
  not become one network message per event.

Streams are asyncio generators that wait on a bus subscription, so an idle open stream costs no thread.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Callable, Optional

from starlette.exceptions import HTTPException
from starlette.requests import Request

from ..lifecycle import TERMINAL
from ..durable_changes import SnapshotRequired
from ..models import Event, RunStatus

BATCH = 200
COALESCE_SECONDS = 0.08
KEEPALIVE_SECONDS = 15.0
GLOBAL_POLL_SECONDS = 1.0       # writers in another process cannot wake this Store's in-process bus
FINISHED = tuple(TERMINAL)    # one definition: hutch.lifecycle
MAX_SQLITE_CURSOR = 2**63 - 1


def sse_message(event: str, payload: dict[str, Any], id_: int | str | None = None) -> bytes:
    """JSON payloads keep multi-line HTML on one ``data:`` line, as the SSE framing requires."""
    head = f"id: {id_}\n" if id_ is not None else ""
    return f"{head}event: {event}\ndata: {json.dumps(payload, separators=(',', ':'))}\n\n".encode()


def phone_change_page(page: dict[str, Any]) -> dict[str, Any]:
    """Collapse broad resource invalidations to one content-free phone refresh hint."""
    changes = page.get("changes") or []
    safe_changes = []
    if changes:
        latest = changes[-1]
        safe_changes.append({"id": latest["id"], "resource": "state", "resource_id": "state",
                             "operation": "updated", "ts": latest["ts"], "context": {}})
    return {**page, "changes": safe_changes}


def resume_cursor(request: Request, after: int = 0) -> int:
    """``Last-Event-ID`` (set by the browser on reconnect) wins over the page's initial ``?after=``."""
    header = request.headers.get("last-event-id", "").strip()
    cursor = int(header) if header.isdigit() else max(0, after)
    if cursor > MAX_SQLITE_CURSOR:
        raise HTTPException(422, "event cursor exceeds the supported integer range")
    return cursor


async def run_event_stream(request: Request, store, run_id: str, cursor: int,
                           render: Callable[[list[Event], Any], dict[str, Any]],
                           auth_check: Callable[[], bool] | None = None):
    bus = store.bus
    loop = asyncio.get_running_loop()
    wake = asyncio.Event()
    unsubscribe = bus.subscribe([f"run:{run_id}"], lambda: loop.call_soon_threadsafe(wake.set))
    try:
        yield b"retry: 1500\n\n"
        while True:
            if auth_check is not None and not await asyncio.to_thread(auth_check):
                yield sse_message("auth_expired", {"reason": "session_expired_or_revoked"})
                return
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
                if auth_check is not None and not await asyncio.to_thread(auth_check):
                    yield sse_message("auth_expired", {"reason": "session_expired_or_revoked"})
                    return
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
                await asyncio.wait_for(wake.wait(), timeout=min(1.0, KEEPALIVE_SECONDS)
                                       if auth_check is not None else KEEPALIVE_SECONDS)
            except asyncio.TimeoutError:
                if auth_check is not None and not await asyncio.to_thread(auth_check):
                    yield sse_message("auth_expired", {"reason": "session_expired_or_revoked"})
                    return
                if auth_check is None or KEEPALIVE_SECONDS <= 1:
                    yield b": keepalive\n\n"
    finally:
        unsubscribe()


async def global_event_stream(request: Request, store, cursor: int,
                              auth_check: Callable[[], bool] | None = None):
    """Durable cross-run transcript replay ordered by SQLite's global event ID.

    A restored database can be behind a device's Last-Event-ID, and future retention may remove old rows. In either case
    replay cannot be complete: ask the client to reconcile from the bounded snapshot endpoint, without advancing its SSE ID.
    """
    bus = store.bus
    loop = asyncio.get_running_loop()
    wake = asyncio.Event()
    unsubscribe = bus.subscribe(["events"], lambda: loop.call_soon_threadsafe(wake.set))
    last_keepalive = loop.time()
    try:
        yield b"retry: 1500\n\n"
        while True:
            if auth_check is not None and not await asyncio.to_thread(auth_check):
                yield sse_message("auth_expired", {"reason": "session_expired_or_revoked"})
                return
            wake.clear()
            oldest, high = await asyncio.to_thread(store.global_event_bounds)
            if cursor > high or (oldest and cursor < oldest - 1):
                yield sse_message("snapshot_required", {
                    "reason": "event_cursor_unavailable",
                    "snapshot_url": "/api/v1/snapshot",
                    "event_cursor": high,
                })
                return
            events = await asyncio.to_thread(store.list_global_events, cursor, BATCH)
            if events:
                if len(events) < BATCH:
                    await asyncio.sleep(COALESCE_SECONDS)
                    events += await asyncio.to_thread(store.list_global_events, events[-1].id, BATCH - len(events))
                cursor = events[-1].id
                if auth_check is not None and not await asyncio.to_thread(auth_check):
                    yield sse_message("auth_expired", {"reason": "session_expired_or_revoked"})
                    return
                yield sse_message("events", {"events": [event.model_dump() for event in events], "cursor": cursor}, cursor)
                continue
            if await request.is_disconnected():
                return
            timeout = min(GLOBAL_POLL_SECONDS, max(0.05, KEEPALIVE_SECONDS - (loop.time() - last_keepalive)))
            try:
                await asyncio.wait_for(wake.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                if auth_check is not None and not await asyncio.to_thread(auth_check):
                    yield sse_message("auth_expired", {"reason": "session_expired_or_revoked"})
                    return
                if loop.time() - last_keepalive >= KEEPALIVE_SECONDS:
                    yield b": keepalive\n\n"
                    last_keepalive = loop.time()
    finally:
        unsubscribe()


async def resource_change_stream(request: Request, store, cursor: str | None,
                                 auth_check: Callable[[], bool] | None = None,
                                 redact: bool = False):
    """Replay transactional resource invalidations; missed wakeups only delay polling.

    A gap ends this stream without an SSE ID so a client cannot silently skip it.
    Reconcile current resources, then open a new stream at snapshot.change_cursor.
    """
    loop = asyncio.get_running_loop()
    wake = asyncio.Event()
    topics = ["events", "bots", "conversations", "approvals", "work"]
    unsubscribe = store.bus.subscribe(topics, lambda: loop.call_soon_threadsafe(wake.set))
    last_keepalive = loop.time()
    try:
        yield b"retry: 1500\n\n"
        while True:
            if auth_check is not None and not await asyncio.to_thread(auth_check):
                yield sse_message("auth_expired", {"reason": "session_expired_or_revoked"})
                return
            wake.clear()
            try:
                page = await asyncio.to_thread(store.list_resource_changes, cursor, BATCH)
            except SnapshotRequired as exc:
                yield sse_message("snapshot_required", {
                    "reason": "change_cursor_unavailable", "message": str(exc),
                    "snapshot_url": "/api/v1/snapshot",
                })
                return
            if page["changes"]:
                cursor = page["cursor"]
                if auth_check is not None and not await asyncio.to_thread(auth_check):
                    yield sse_message("auth_expired", {"reason": "session_expired_or_revoked"})
                    return
                yield sse_message("changes", phone_change_page(page) if redact else page, cursor)
                continue
            if await request.is_disconnected():
                return
            try:
                await asyncio.wait_for(wake.wait(), timeout=GLOBAL_POLL_SECONDS)
            except asyncio.TimeoutError:
                if auth_check is not None and not await asyncio.to_thread(auth_check):
                    yield sse_message("auth_expired", {"reason": "session_expired_or_revoked"})
                    return
                if loop.time() - last_keepalive >= KEEPALIVE_SECONDS:
                    yield b": keepalive\n\n"
                    last_keepalive = loop.time()
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
