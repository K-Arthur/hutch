"""Stream continuity: versioned cursors, at-least-once reading, honest liveness.

Two real, documented stream shapes are encoded here, because both teach a lesson that a
single integer cursor would erase (mission sections 6 and 13):

* **Jetstream**: cursors are *instance-local* sequence numbers (inclusive, monotonic,
  possibly non-contiguous after a rebuild). The same ``?cursor=`` parameter also accepts
  v1-style unix-microsecond timestamps, told apart **by magnitude** (>= 1e15 is a
  timestamp). A client that compares the two namespaces silently drops every event
  (issue #349), so this module never compares across kinds or instances, and migrating
  between them is an explicit, recorded operation with a rewind margin.
* **Wikimedia EventStreams**: SSE ``id`` is a JSON array of topic/partition/(offset or
  timestamp); offsets are per-Kafka-cluster and timestamps are the multi-DC-stable resume
  unit. The connection is closed server-side after ~15 minutes, canary events appear at
  least hourly (broken-vs-quiet), and there is no server-side filtering.

A live heartbeat proves connectivity, not correct filtering and not complete delivery.
``LivenessState`` therefore separates: connected, last event, last canary, coverage gap.
"""

from __future__ import annotations

import json
import ipaddress
import socket
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Iterable, Iterator, Optional, Sequence

from ..netguard import NetGuardError, resolve_public, screen_url
from .clock import UTC, Clock


JETSTREAM_TIMESTAMP_THRESHOLD = 1_000_000_000_000_000  # 1e15: v1 timestamp vs v2 seq
WIKIMEDIA_SERVER_TIMEOUT = timedelta(minutes=15)
WIKIMEDIA_CANARY_INTERVAL = timedelta(hours=1)
DEFAULT_REWIND = 500  # seqs to rewind when switching an instance (at-least-once covers it)


class CursorKind(str, Enum):
    seq = "seq"                       # instance-local monotonic sequence
    timestamp_micros = "timestamp_micros"  # unix microseconds (Jetstream v1 style)
    structured_json = "structured_json"    # topic/partition/(offset|timestamp) array
    opaque = "opaque"                 # server-defined token, echoed verbatim


class CursorMismatch(ValueError):
    """A cursor was compared or resumed against the wrong kind/instance, never silent."""


@dataclass
class StreamCursor:
    """A persisted cursor with enough identity to be resumed safely.

    ``schema_version`` protects the *semantics*: when the meaning of a stored cursor
    changes (for example a rebuild renumbers an instance's seq space), bump it and the
    old value is migrated explicitly instead of being reused blindly.
    """

    adapter: str
    instance: str
    kind: str
    value: Any
    schema_version: int = 1
    filter_revision: str = ""
    updated_at: str = ""
    note: str = ""

    def to_json(self) -> dict[str, Any]:
        return {"adapter": self.adapter, "instance": self.instance, "kind": self.kind,
                "value": self.value, "schema_version": self.schema_version,
                "filter_revision": self.filter_revision, "updated_at": self.updated_at, "note": self.note}

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "StreamCursor":
        return cls(adapter=str(data.get("adapter", "")), instance=str(data.get("instance", "")),
                   kind=str(data.get("kind", CursorKind.opaque.value)), value=data.get("value"),
                   schema_version=int(data.get("schema_version", 1)),
                   filter_revision=str(data.get("filter_revision", "")),
                   updated_at=str(data.get("updated_at", "")), note=str(data.get("note", "")))

    def same_lineage(self, other: "StreamCursor") -> bool:
        return (self.adapter == other.adapter and self.instance == other.instance
                and self.kind == other.kind and self.schema_version == other.schema_version)


def parse_jetstream_cursor(value: Any, *, instance: str, schema_version: int = 2) -> StreamCursor:
    """Classify a Jetstream cursor value per the documented magnitude rule.

    ``< 1e15`` is a v2 sequence; ``>= 1e15`` is a v1 unix-microsecond timestamp. The kind
    is recorded so no later comparison can mix them (issue #349's silent-drop class).
    """
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise CursorMismatch(f"jetstream cursor must be an integer, got {value!r}") from None
    if number < 0:
        raise CursorMismatch("jetstream cursors are non-negative")
    if number >= JETSTREAM_TIMESTAMP_THRESHOLD:
        return StreamCursor(adapter="jetstream", instance=instance, kind=CursorKind.timestamp_micros.value,
                            value=number, schema_version=schema_version,
                            note="v1-style timestamp cursor; the server maps it to a replay position, "
                                 "and the exact start is not guaranteed")
    return StreamCursor(adapter="jetstream", instance=instance, kind=CursorKind.seq.value, value=number,
                        schema_version=schema_version,
                        note="v2 sequence cursor; inclusive replay start (seq >= cursor)")


def migrate_jetstream_cursor(cursor: StreamCursor, *, new_instance: str, rewind: int = DEFAULT_REWIND,
                             direction: str = "seq") -> tuple[StreamCursor, str]:
    """Move a cursor to a new instance explicitly: rewind by a margin and rely on dedup."""
    if cursor.adapter != "jetstream":
        raise CursorMismatch("not a jetstream cursor")
    if cursor.kind != CursorKind.seq.value:
        raise CursorMismatch("only sequence cursors can be rewound across instances; "
                             "timestamps need the server's lookback floor")
    value = max(0, int(cursor.value) - (rewind if direction == "seq" else 0))
    return (StreamCursor(adapter=cursor.adapter, instance=new_instance, kind=cursor.kind, value=value,
                         schema_version=cursor.schema_version, filter_revision=cursor.filter_revision,
                         updated_at=cursor.updated_at),
            f"rewound {rewind} seqs for the instance switch; at-least-once delivery covers the overlap")


def wikimedia_cursor(ids: list[dict[str, Any]], *, note: str = "") -> StreamCursor:
    """Build a structured cursor from an SSE ``id`` array (topic/partition/offset|timestamp)."""
    if not isinstance(ids, list) or any(not isinstance(entry, dict) for entry in ids):
        raise CursorMismatch("wikimedia stream ids are JSON arrays of {topic, partition, offset|timestamp}")
    cleaned = []
    uses_timestamp = False
    for entry in ids:
        row = {k: entry[k] for k in ("topic", "partition", "offset", "timestamp") if k in entry}
        if "timestamp" in row and row["timestamp"] is not None:
            uses_timestamp = True
        cleaned.append(row)
    return StreamCursor(adapter="wikimedia-eventstreams", instance="stream.wikimedia.org",
                        kind=CursorKind.structured_json.value, value=cleaned,
                        note=note or ("reconnect with Last-Event-ID verbatim; offsets are per-cluster, "
                                      "timestamps are the multi-DC-stable resume unit"
                                      if uses_timestamp else "offsets present; a cluster switch invalidates them"))


@dataclass
class SSEEvent:
    event: str = "message"
    data: str = ""
    id: str = ""
    retry: Optional[int] = None


def parse_sse(stream: Iterable[str]) -> Iterator[SSEEvent]:
    """Minimal bounded SSE framing: event/data/id/retry fields, last-wins per the HTML spec,
    comments (``:``) ignored except as a heartbeat signal to the reader loop."""
    event, data, last_id, retry = "message", [], "", None
    for raw in stream:
        line = raw.rstrip("\r\n")
        if not line:
            if data or last_id or event != "message":
                yield SSEEvent(event=event, data="\n".join(data), id=last_id, retry=retry)
            event, data, last_id, retry = "message", [], "", None
            continue
        if line.startswith(":"):
            continue
        field_name, _, value = line.partition(":")
        value = value[1:] if value.startswith(" ") else value
        if field_name == "event":
            event = value
        elif field_name == "data":
            data.append(value)
        elif field_name == "id":
            last_id = value
        elif field_name == "retry":
            try:
                retry = int(value)
            except ValueError:
                pass


# ------------------------------------------------------------------ liveness

@dataclass
class LivenessState:
    """Honest stream diagnostics. Heartbeat != filter correctness != delivery completeness."""

    connected: bool = False
    connected_at: Optional[datetime] = None
    last_event_at: Optional[datetime] = None
    last_canary_at: Optional[datetime] = None
    events: int = 0
    duplicates: int = 0
    late: int = 0
    gaps: int = 0
    gap_note: str = ""
    reconnects: int = 0
    state: str = "unknown"           # live | quiet | gap | stale | unsupported | blocked

    def report(self, now: datetime) -> dict[str, Any]:
        if not self.connected:
            return {"state": self.state, "connected": False,
                    "detail": self.gap_note or "no connection",
                    "gap_note": self.gap_note, "events": self.events, "duplicates": self.duplicates,
                    "late": self.late, "gaps": self.gaps, "reconnects": self.reconnects,
                    "note": ("no live connection: a heartbeat would prove connectivity only; it cannot prove "
                             "filtering, delivery completeness, or current evidence")}
        quiet_for = (now - (self.last_event_at or self.connected_at or now)).total_seconds()
        canary_age = (now - self.last_canary_at).total_seconds() if self.last_canary_at else None
        return {
            "state": self.state, "connected": True,
            "connected_at": self.connected_at.isoformat() if self.connected_at else None,
            "last_event_at": self.last_event_at.isoformat() if self.last_event_at else None,
            "events": self.events, "duplicates": self.duplicates, "late": self.late,
            "gaps": self.gaps, "gap_note": self.gap_note, "reconnects": self.reconnects,
            "quiet_seconds": round(quiet_for, 1),
            "canary_age_seconds": None if canary_age is None else round(canary_age, 1),
            "note": ("quiet is not broken: canary events (at most hourly on Wikimedia streams) are the "
                     "liveness signal; a live connection still does not prove filtering or coverage"),
        }


class StreamPump:
    """Generic at-least-once pump: dedupe by an event key, tolerate overlaps and late items,
    count duplicates and gaps, and never let a replayed event extend a cancelled watch."""

    def __init__(self, *, key_fn: Callable[[dict], str], clock: Clock, max_seen: int = 5000):
        self._key_fn = key_fn
        self._clock = clock
        self._seen: "OrderedDict[str, None]" = OrderedDict()
        self._max_seen = max_seen
        self.liveness = LivenessState()
        self.cursor: Optional[StreamCursor] = None

    def _remember(self, key: str) -> bool:
        """True when this key is new (not a duplicate)."""
        if key in self._seen:
            self._seen.move_to_end(key)
            self.liveness.duplicates += 1
            return False
        self._seen[key] = None
        while len(self._seen) > self._max_seen:
            self._seen.popitem(last=False)
        return True

    def observe(self, event: dict, *, event_key: str, event_time: Optional[datetime] = None,
                cursor: Optional[StreamCursor] = None) -> bool:
        """Record one received event; returns False when it was a duplicate."""
        nov = self._clock.now()
        self.liveness.connected = True
        self.liveness.connected_at = self.liveness.connected_at or nov
        if not self._remember(event_key):
            return False
        self.liveness.events += 1
        if event_time and self.liveness.last_event_at and event_time < self.liveness.last_event_at:
            self.liveness.late += 1
        self.liveness.last_event_at = event_time or nov
        if event.get("canary"):
            self.liveness.last_canary_at = nov
        if cursor is not None:
            if self.cursor is not None and not self.cursor.same_lineage(cursor):
                raise CursorMismatch(
                    f"cursor lineage changed mid-stream ({self.cursor.adapter}/{self.cursor.instance}/"
                    f"{self.cursor.kind} -> {cursor.adapter}/{cursor.instance}/{cursor.kind})")
            self.cursor = cursor
        self.liveness.state = "live"
        return True

    def advance(self, cursor: StreamCursor) -> None:
        """Move the read position without counting an event (e.g. frames filtered out).

        Delivery position and evidence admission are different things: a window where the
        term filter matches nothing still made progress over the wire, and a later resume
        must not restart from a stale position.
        """
        if self.cursor is not None and not self.cursor.same_lineage(cursor):
            raise CursorMismatch(
                f"cursor lineage changed mid-stream ({self.cursor.adapter}/{self.cursor.instance}/"
                f"{self.cursor.kind} -> {cursor.adapter}/{cursor.instance}/{cursor.kind})")
        self.cursor = cursor

    def record_gap(self, note: str) -> None:
        self.liveness.gaps += 1
        self.liveness.gap_note = note
        if self.liveness.state not in ("blocked", "stale"):
            self.liveness.state = "gap"

    def record_reconnect(self, *, reason: str) -> None:
        self.liveness.reconnects += 1
        self.liveness.state = "quiet" if self.liveness.state == "live" else self.liveness.state
        self.liveness.gap_note = self.liveness.gap_note or f"reconnect: {reason}"


# ------------------------------------------------------------------ live readers

def _open_pinned_stream(url: str, *, timeout: float, headers: dict[str, str], _redirects: int = 0):
    """SSE-capable streaming GET with the same SSRF checks as ``netguard.safe_get``:

    screen the URL, resolve every address to a public one, pin the connection to it, and
    keep the Host/SNI as the name. One redirect is allowed only to another public name.
    Returns ``(response, client, context_manager)``; the caller owns closing both.
    """
    import httpx
    reason = screen_url(url)
    if reason:
        raise NetGuardError(reason)
    from urllib.parse import urlsplit
    parts = urlsplit(url)
    https = parts.scheme.lower() == "https"
    host = (parts.hostname or "").rstrip(".")
    port = parts.port or (443 if https else 80)
    ip = resolve_public(host, port)[0]
    netloc = f"[{ip}]:{port}" if ":" in ip else f"{ip}:{port}"
    pinned = parts._replace(netloc=netloc).geturl()
    hdrs = {"Host": host, **headers}
    extensions = {"sni_hostname": host} if https else {}
    client = httpx.Client(timeout=timeout, follow_redirects=False)
    manager = client.stream("GET", pinned, headers=hdrs, extensions=extensions)
    response = manager.__enter__()
    if response.status_code in (301, 302, 303, 307, 308):
        location = response.headers.get("location")
        manager.__exit__(None, None, None)
        client.close()
        if not location:
            raise NetGuardError("redirect without a location")
        if _redirects >= 1:
            raise NetGuardError("too many redirects")
        from urllib.parse import urljoin
        return _open_pinned_stream(urljoin(url, location), timeout=timeout, headers=headers,
                                   _redirects=_redirects + 1)
    return response, client, manager


def read_wikimedia_stream(*, pump: StreamPump, stream_key: str = "recentchange",
                          since: Optional[str] = None, last_event_id: Optional[str] = None,
                          max_events: int = 600, max_seconds: float = 120.0,
                          filter_fn: Optional[Callable[[dict], bool]] = None,
                          stop: Optional[Callable[[], bool]] = None,
                          clock: Clock, host: str = "stream.wikimedia.org") -> dict[str, Any]:
    """Bounded live read of one Wikimedia EventStreams topic with verbatim resume.

    Returns a diagnostics report; the caller decides whether to continue watching. The read
    is explicitly bounded (events and seconds), a one-time query never becomes persistent
    monitoring, and a cancelled investigation's cursor is not resumed by anything else.
    """
    import httpx  # noqa: F401 - present wherever the app's HTTP stack is

    stop = stop or (lambda: False)
    base = f"https://{host}/v2/stream/{stream_key}"
    params = []
    if last_event_id:
        params.append(("Last-Event-ID", last_event_id))  # header, handled below
    url = base + (f"?since={since}" if since else "")
    headers = {"User-Agent": "hutch/0.1 (+local agent platform)", "Accept": "text/event-stream"}
    if last_event_id:
        headers["Last-Event-ID"] = last_event_id
    deadline = time.monotonic() + max_seconds
    received = 0
    try:
        response, client, manager = _open_pinned_stream(url, timeout=30.0, headers=headers)
    except NetGuardError as exc:
        pump.liveness.state = "blocked"
        pump.record_gap(f"blocked: {exc.reason}")
        return pump.liveness.report(clock.now())
    except Exception as exc:  # noqa: BLE001
        pump.liveness.state = "stale"
        pump.record_gap(f"connect failed: {type(exc).__name__}: {exc}")
        return pump.liveness.report(clock.now())
    try:
        if response.status_code != 200:
            pump.liveness.state = "blocked" if response.status_code in (401, 403) else "stale"
            pump.record_gap(f"HTTP {response.status_code} from the stream endpoint")
            return pump.liveness.report(clock.now())
        pump.liveness.connected = True
        for event in parse_sse(response.iter_lines()):
            if stop() or time.monotonic() > deadline or received >= max_events:
                break
            if event.event == "error":
                pump.record_gap(f"server error event: {event.data[:200]}")
                break
            try:
                payload = json.loads(event.data)
            except ValueError:
                pump.record_gap("unparseable event payload; skipped (payload not treated as evidence)")
                continue
            if not isinstance(payload, dict):
                continue
            if event.id:
                try:
                    pump.cursor = wikimedia_cursor(json.loads(event.id),
                                                   note="resumed with the raw Last-Event-ID")
                except (ValueError, CursorMismatch):
                    pump.record_gap("stream id was not the documented JSON array; cursor left unchanged")
            is_canary = (payload.get("meta") or {}).get("domain") == "canary"
            if is_canary:
                pump.observe({"canary": True}, event_key=f"canary:{event.id}", cursor=pump.cursor)
                continue
            if filter_fn is not None and not filter_fn(payload):
                continue
            event_time = None
            raw_dt = (payload.get("meta") or {}).get("dt") or payload.get("dt")
            if raw_dt:
                try:
                    event_time = datetime.fromisoformat(str(raw_dt).replace("Z", "+00:00")).astimezone(UTC)
                except ValueError:
                    event_time = None
            key = str((payload.get("meta") or {}).get("id") or event.id or "")
            if pump.observe(payload, event_key=key or json.dumps(payload, sort_keys=True)[:200],
                            event_time=event_time, cursor=pump.cursor):
                received += 1
    except Exception as exc:  # noqa: BLE001
        pump.record_reconnect(reason=f"read ended: {type(exc).__name__}: {exc}")
    finally:
        try:
            manager.__exit__(None, None, None)
            client.close()
        except Exception:  # noqa: BLE001
            pass
    if pump.liveness.state == "live":
        pump.liveness.state = "quiet" if received == 0 else "live"
    return pump.liveness.report(clock.now())


# ------------------------------------------------------------------ Jetstream client contract

@dataclass
class JetstreamEvent:
    seq: Optional[int]
    time_us: Optional[int]
    kind: str
    did: str
    collection: str
    rkey: str
    payload: dict = field(default_factory=dict)

    def dedup_key(self) -> str:
        if self.seq is not None:
            return f"seq:{self.seq}"
        return f"evt:{self.did}:{self.collection}:{self.rkey}"


def parse_jetstream_event(raw: str) -> Optional[JetstreamEvent]:
    """Parse one Jetstream websocket message in either documented wire shape.

    * **v1** (flat): ``{did, seq, time_us, kind, commit: {operation, collection, rkey, record}}``
    * **v2** (nested): ``{$type: "message", payload: {$type: ".../commit", did, seq, time,
      witnessedAt, collection, rkey, operation, record}}`` with ISO-8601 times (observed on the
      live instance 2026-10-11; the initial v1-shaped parser silently treated those frames as
      unknown fields, which the live smoke test caught).

    Both are normalized to the v1-like shape downstream code expects; unknown shapes return
    None rather than guessed values. ``time_us`` is normalized to unix microseconds for
    ordering, and the raw v2 ISO times stay in ``payload`` for honest display.
    """
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    if isinstance(data.get("payload"), dict):
        body = data["payload"]
        body_type = str(body.get("$type") or "")
        kind = body_type.rsplit("#", 1)[-1] if "#" in body_type else ""
        if not kind:
            kind = str(body.get("operation") or "commit")
        seq_raw = body.get("seq")
        try:
            seq_int = int(seq_raw) if seq_raw is not None else None
        except (TypeError, ValueError):
            seq_int = None
        micros: Optional[int] = None
        for key in ("time", "witnessedAt", "time_us"):
            value = body.get(key)
            if value is None:
                continue
            if isinstance(value, str):
                try:
                    micros = int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1_000_000)
                    break
                except ValueError:
                    continue
            try:
                micros = int(value)
                break
            except (TypeError, ValueError):
                continue
        commit_body = {
            "operation": body.get("operation"), "collection": body.get("collection"),
            "rkey": body.get("rkey"), "record": body.get("record"), "cid": body.get("cid"),
            "rev": body.get("rev"), "seq": seq_int, "time": body.get("time"),
            "witnessedAt": body.get("witnessedAt"),
        }
        normalized = {"did": body.get("did"), "seq": seq_int, "time_us": micros, "kind": kind,
                      "commit": commit_body, "$v2": True,
                      "witnessedAt": body.get("witnessedAt")}
        return JetstreamEvent(seq=seq_int, time_us=micros, kind=kind, did=str(body.get("did") or ""),
                              collection=str(body.get("collection") or ""),
                              rkey=str(body.get("rkey") or ""), payload=normalized)
    commit = data.get("commit") or {}
    if not isinstance(commit, dict):
        commit = {}
    seq = data.get("seq")
    try:
        seq_int = int(seq) if seq is not None else None
    except (TypeError, ValueError):
        seq_int = None
    # v2 names the display time `time`; v1 used `time_us`. Both are unix micros in the flat shape.
    raw_time = data.get("time_us", data.get("time"))
    try:
        time_us = int(raw_time) if raw_time is not None else None
    except (TypeError, ValueError):
        time_us = None
    return JetstreamEvent(seq=seq_int, time_us=time_us, kind=str(data.get("kind") or commit.get("operation") or ""),
                          did=str(data.get("did") or ""), collection=str(commit.get("collection") or ""),
                          rkey=str(commit.get("rkey") or ""), payload=data)


def jetstream_readiness() -> tuple[str, str]:
    """Whether the live Jetstream reader can run here, honestly.

    The reader needs the optional ``websockets`` dependency (``hutch`` extra ``jetstream``).
    Without it the tool reports ``unsupported``, never a fake connection. Host reachability
    is a *runtime* question answered per connection, not a readiness claim.
    """
    try:
        import websockets  # noqa: F401
    except ImportError:
        return "unsupported", ("the optional websockets dependency is not installed (pip install 'hutch[jetstream]'); "
                               "the cursor/folding contract is tested offline but no live Jetstream connection is claimed")
    return "ready", ""


JETSTREAM_DEFAULT_HOST = "jetstream.us-west.bsky.network"


def _jetstream_target(host: str) -> tuple[str, str]:
    """Validate a configured Jetstream authority and return its fixed WSS endpoint.

    Only a DNS hostname (bare or explicit ``wss://`` authority) is accepted. In
    particular, configuration cannot downgrade TLS, select a port, or smuggle a
    path/query through the trusted websocket connection.
    """
    from urllib.parse import urlsplit

    value = str(host or "").strip()
    if not value:
        raise NetGuardError("Jetstream host is empty")
    parts = urlsplit(value if "://" in value else f"//{value}")
    if parts.scheme not in ("", "wss") or parts.username is not None or parts.password is not None:
        raise NetGuardError("Jetstream requires a public wss:// hostname without credentials")
    if parts.port not in (None, 443) or parts.path not in ("", "/") or parts.query or parts.fragment:
        raise NetGuardError("Jetstream configuration accepts only a hostname on port 443")
    hostname = (parts.hostname or "").rstrip(".").lower()
    if not hostname:
        raise NetGuardError("Jetstream host is invalid")
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        raise NetGuardError("Jetstream host must be a DNS hostname, not an IP address")
    # netguard's general browser/request URL policy intentionally accepts only HTTP(S);
    # apply its hostname screening to the TLS-equivalent HTTPS form here.
    reason = screen_url(f"https://{hostname}/")
    if reason:
        raise NetGuardError(reason)
    return f"wss://{hostname}/xrpc/network.bsky.jetstream.subscribeEvents", hostname


def _connect_jetstream(url: str, hostname: str, ws_connect):
    """Resolve and pin the TCP peer while preserving TLS SNI and certificate checks."""
    address = resolve_public(hostname, 443)[0]
    sock = socket.create_connection((address, 443), timeout=15)
    try:
        return ws_connect(url, sock=sock, server_hostname=hostname,
                          open_timeout=15, close_timeout=5, max_size=8_000_000)
    except Exception:
        sock.close()
        raise


def read_jetstream_stream(*, pump: StreamPump, host: str = JETSTREAM_DEFAULT_HOST,
                          cursor: Optional[StreamCursor] = None,
                          kinds: Sequence[str] = ("commit",), collections: Sequence[str] = (),
                          max_events: int = 400, max_seconds: float = 20.0,
                          filter_fn: Optional[Callable[[JetstreamEvent], bool]] = None,
                          sink: Optional[Callable[[JetstreamEvent], None]] = None,
                          stop: Optional[Callable[[], bool]] = None,
                          clock: Clock) -> dict[str, Any]:
    """Bounded live read of a Jetstream instance, at-least-once and cursor-explicit.

    Contract details that are load-bearing (Jetstream README, re-read 2026-10-11):

    * The cursor is an **instance-local sequence number**; the value is inclusive on replay
      (events with ``seq >= cursor``), so a resume re-receives at least its last event and
      this reader dedupes by seq. Timestamp cursors are accepted by the server but are a
      different namespace, they are never compared with seqs here.
    * Delivery is at-least-once, and seqs may have registered gaps after a rebuild; a
      sequence jump is tolerated, a malformed value is not invented.
    * Below the lookback floor the server answers ``CursorTooOld``: this reader records a
      bounded gap state instead of silently skipping ahead.
    * Deletes are positive marker events; the caller folds them. A bounded read that ends
      is reported with scanned/kept counts so "quiet" and "broken" stay distinct.
    """
    stop = stop or (lambda: False)
    try:
        from websockets.exceptions import InvalidStatus, WebSocketException
        from websockets.sync.client import connect as ws_connect
    except ImportError:
        pump.liveness.state = "unsupported"
        pump.record_gap("the optional websockets dependency is not installed")
        return pump.liveness.report(clock.now())

    from urllib.parse import urlencode
    params: list[tuple[str, str]] = [("maxMessageSizeBytes", "0")]  # keep markers; oversized folding stays safe
    if cursor is not None:
        expected_kind = CursorKind.seq.value if cursor.adapter == "jetstream" else cursor.kind
        # only the two documented namespaces may be sent; anything else is a lineage error
        if cursor.adapter != "jetstream" or expected_kind not in (CursorKind.seq.value, CursorKind.timestamp_micros.value):
            pump.record_gap(f"cursor lineage {cursor.adapter}/{cursor.kind} cannot be sent to Jetstream")
            pump.liveness.state = "gap"
            return pump.liveness.report(clock.now())
        params.append(("cursor", str(cursor.value)))
    if kinds:
        params.append(("kinds", ",".join(kinds)))
    if collections:
        params.append(("collections", ",".join(collections)))
    try:
        endpoint, hostname = _jetstream_target(host)
    except NetGuardError as exc:
        pump.record_gap(f"unsafe Jetstream host: {exc}")
        pump.liveness.state = "blocked"
        return pump.liveness.report(clock.now())
    url = f"{endpoint}?{urlencode(params)}"

    deadline = time.monotonic() + max_seconds
    received = 0
    scanned = 0
    try:
        with _connect_jetstream(url, hostname, ws_connect) as socket:
            pump.liveness.connected = True
            pump.liveness.connected_at = pump.liveness.connected_at or clock.now()
            while not stop() and time.monotonic() < deadline and received < max_events:
                remaining = deadline - time.monotonic()
                try:
                    raw = socket.recv(timeout=max(0.05, min(1.0, remaining)))
                except TimeoutError:
                    continue
                text = raw.decode("utf-8", errors="replace") if isinstance(raw, (bytes, bytearray)) else raw
                event = parse_jetstream_event(text if isinstance(text, str) else str(text))
                if event is None:
                    pump.record_gap("an unparseable frame was skipped; it is not treated as evidence")
                    continue
                scanned += 1
                event_time = None
                if event.time_us:
                    try:
                        event_time = datetime.fromtimestamp(event.time_us / 1_000_000, tz=UTC)
                    except (OverflowError, OSError, ValueError):
                        event_time = None
                next_cursor: Optional[StreamCursor] = None
                if cursor is None or cursor.kind == CursorKind.seq.value:
                    if event.seq is not None:
                        next_cursor = StreamCursor(adapter="jetstream", instance=host, kind=CursorKind.seq.value,
                                                   value=event.seq,
                                                   schema_version=cursor.schema_version if cursor else 2,
                                                   filter_revision=cursor.filter_revision if cursor else "",
                                                   note="inclusive replay start; dedupe by seq on resume")
                elif cursor.kind == CursorKind.timestamp_micros.value and event.time_us:
                    next_cursor = StreamCursor(adapter="jetstream", instance=host,
                                               kind=CursorKind.timestamp_micros.value, value=event.time_us,
                                               schema_version=cursor.schema_version,
                                               filter_revision=cursor.filter_revision,
                                               note="v1-style timestamp resume; the server maps it to a replay position")
                if next_cursor is not None:
                    # the read position advances on every parsed frame; the filter only decides
                    # what becomes evidence (a zero-match window must still resume forward)
                    pump.advance(next_cursor)
                if filter_fn is not None and not filter_fn(event):
                    continue
                if pump.observe({"seq": event.seq, "kind": event.kind, "did": event.did},
                                event_key=event.dedup_key(), event_time=event_time):
                    received += 1
                    if sink is not None:
                        try:
                            sink(event)
                        except Exception:  # noqa: BLE001 - one bad consumer must not kill the read
                            pass
    except InvalidStatus as exc:
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", 0)
        body = getattr(response, "body", b"") or b""
        body_text = body.decode("utf-8", errors="replace") if isinstance(body, (bytes, bytearray)) else str(body)
        if "CursorTooOld" in body_text:
            pump.liveness.state = "gap"
            pump.record_gap("CursorTooOld: the requested cursor is below this instance's lookback floor; "
                            "re-enter the archive from the last processed seq (bounded reader stopped instead of "
                            "silently skipping the gap)")
        elif status in (401, 403):
            pump.liveness.state = "blocked"
            pump.record_gap(f"HTTP {status} during the websocket handshake")
        else:
            pump.record_reconnect(reason=f"handshake failed (HTTP {status})")
    except WebSocketException as exc:
        pump.record_reconnect(reason=f"websocket error: {exc}")
    except OSError as exc:
        pump.liveness.state = "blocked"
        pump.record_gap(f"connect failed: {type(exc).__name__}: {exc}")
    except Exception as exc:  # noqa: BLE001 - transport failure is reported, never raised at the caller
        pump.record_reconnect(reason=f"read ended: {type(exc).__name__}: {exc}")
    if pump.liveness.state == "live":
        pump.liveness.state = "live" if received else "quiet"
    report = pump.liveness.report(clock.now())
    report["scanned"] = scanned
    report["scanned_note"] = (f"bounded live window: scanned {scanned} event(s), kept {received} after the filter "
                              f"(duplicates {pump.liveness.duplicates}); a bounded window is a sample, not complete "
                              "coverage")
    return report
