"""Framing/equality tests for the coalesced global event SSE payload (perf programme D6-C).

The global stream used to build [event.model_dump() ...] and re-encode the whole payload
with json.dumps. The byte-framed helper serializes each event once; this test pins the wire
shape to the legacy encoding so the change is a pure serialization optimisation.
"""

from __future__ import annotations

import json

from hutch.models import Event, EventType
from hutch.server.sse import global_events_message, sse_message


def _events(count: int = 5) -> list[Event]:
    out = []
    for index in range(count):
        out.append(Event(id=index + 1, run_id="run_1", seq=index + 1, hash="h" * 12,
                         type=EventType.message,
                         data={"role": "assistant", "index": index,
                               "text": "line one\nline two with unicode: caf\u00e9 \u4f60\u597d " * (index + 1),
                               "nested": {"values": [1, 2.5, None, True], "empty": {}}}))
    return out


def _decode(frame: bytes) -> tuple[str, int, dict]:
    text = frame.decode("utf-8")
    lines = text.split("\n")
    assert lines[-1] == "" and lines[-2] == "", "an SSE frame ends with a blank line"
    event = next(line.split(": ", 1)[1] for line in lines if line.startswith("event: "))
    id_ = int(next(line.split(": ", 1)[1] for line in lines if line.startswith("id: ")))
    data = next(line.split(": ", 1)[1] for line in lines if line.startswith("data: "))
    return event, id_, json.loads(data)


def test_global_events_message_matches_the_legacy_payload_shape():
    events = _events(7)
    cursor = events[-1].id
    legacy = sse_message("events", {"events": [event.model_dump() for event in events], "cursor": cursor}, cursor)
    framed = global_events_message(events, cursor)
    assert _decode(framed) == _decode(legacy)
    # Wire bytes may differ in non-ASCII escaping (pydantic writes UTF-8; the legacy json.dumps
    # escaped it). EventSource decodes text/event-stream as UTF-8 and the dashboard parses the
    # same JSON value, so the comparison below is the compatibility contract.
    assert json.loads(legacy.decode("utf-8").split("data: ", 1)[1]) == \
        json.loads(framed.decode("utf-8").split("data: ", 1)[1])


def test_global_events_message_keeps_multiline_content_on_one_data_line():
    event = _events(1)[0]
    event.data["text"] = "first\nsecond\nthird"
    frame = global_events_message([event], event.id)
    data_lines = [line for line in frame.decode("utf-8").split("\n") if line.startswith("data: ")]
    assert len(data_lines) == 1
    assert "\\n" in data_lines[0]


def test_global_events_message_handles_an_empty_batch():
    frame = global_events_message([], 42)
    event, id_, data = _decode(frame)
    assert (event, id_, data) == ("events", 42, {"events": [], "cursor": 42})


def test_global_events_message_preserves_large_batches():
    events = _events(200)
    cursor = events[-1].id
    _, _, data = _decode(global_events_message(events, cursor))
    assert len(data["events"]) == 200
    assert data["cursor"] == cursor
    assert data["events"][0]["run_id"] == "run_1" and data["events"][-1]["id"] == cursor