"""Event / SSE serialization: 200 real Event models through the two serialization shapes.

Compares list(model_dump()) + json.dumps(separators) against the per-event model_dump_json()
joined into bytes, which is the shape the SSE writer uses. Reports ms per 200 events and the
dump_json share of the slower path.
"""

from __future__ import annotations

import json
import statistics
import time

SAMPLES_FULL = 200   # cheap in-process case: enough samples for a meaningful p95
SAMPLES_QUICK = 3
EVENTS = 200


def _events(count: int = EVENTS) -> list:
    from hutch.models import Event, EventType

    out = []
    for index in range(count):
        kind = index % 5
        if kind == 0:
            out.append(Event(run_id="run_bench", seq=index, type=EventType.message,
                             data={"role": "assistant",
                                   "content": f"Step {index}: I inspected the generated report and noted "
                                              "that the totals match the invoice lines. " * 3}))
        elif kind == 1:
            out.append(Event(run_id="run_bench", seq=index, type=EventType.tool_call,
                             data={"call_id": f"call_{index}", "tool": "shell",
                                   "arguments": json.dumps({"command": "ls -la reports",
                                                            "workdir": "reports"}, separators=(",", ":"))}))
        elif kind == 2:
            out.append(Event(run_id="run_bench", seq=index, type=EventType.tool_result,
                             data={"call_id": f"call_{index}", "ok": True,
                                   "output": ("report-2026-10.csv  totals verified  " * 30)[:1600]}))
        elif kind == 3:
            out.append(Event(run_id="run_bench", seq=index, type=EventType.step,
                             data={"model_wait_ms": 812.5, "tool_ms": 34.2, "overhead_ms": 0.31,
                                   "prompt_tokens": 4210, "completion_tokens": 311,
                                   "finish_reason": "tool_calls"}))
        else:
            out.append(Event(run_id="run_bench", seq=index, type=EventType.log,
                             data={"kind": "context", "severity": "ok",
                                   "note": "prompt and tools use 42% of the 8192-token window"}))
    return out


def _time_once(fn) -> float:
    started = time.perf_counter()
    fn()
    return (time.perf_counter() - started) * 1000.0


def run(quick: bool, state) -> list[dict]:
    n = SAMPLES_QUICK if quick else SAMPLES_FULL
    events = _events(EVENTS)

    def dump_only() -> None:
        [event.model_dump() for event in events]

    def dump_plus_dumps() -> None:
        json.dumps([event.model_dump() for event in events], separators=(",", ":"))

    def dump_json_joined() -> None:
        b"[" + b",".join(event.model_dump_json().encode("utf-8") for event in events) + b"]"

    left = json.loads(json.dumps([event.model_dump() for event in events], separators=(",", ":")))
    right = json.loads(b"[" + b",".join(event.model_dump_json().encode("utf-8") for event in events) + b"]")
    if left != right:
        raise RuntimeError("model_dump+json.dumps and model_dump_json disagree; serialization benchmark invalid")

    samples = {"events.model_dump_200_ms": [], "events.dump_plus_dumps_200_ms": [],
               "events.dump_json_joined_200_ms": []}
    for _ in range(n):
        samples["events.model_dump_200_ms"].append(_time_once(dump_only))
        samples["events.dump_plus_dumps_200_ms"].append(_time_once(dump_plus_dumps))
        samples["events.dump_json_joined_200_ms"].append(_time_once(dump_json_joined))

    cases = [
        {"name": "events.model_dump_200_ms", "unit": "ms", "samples": samples["events.model_dump_200_ms"],
         "better": "lower", "note": "pydantic dump only: 200 dicts"},
        {"name": "events.dump_plus_dumps_200_ms", "unit": "ms",
         "samples": samples["events.dump_plus_dumps_200_ms"], "better": "lower",
         "note": "list of model_dump() + one json.dumps(separators)"},
        {"name": "events.dump_json_joined_200_ms", "unit": "ms",
         "samples": samples["events.dump_json_joined_200_ms"], "better": "lower",
         "note": "per-event model_dump_json() joined to bytes (SSE shape)"},
    ]
    plus = statistics.median(samples["events.dump_plus_dumps_200_ms"])
    joined = statistics.median(samples["events.dump_json_joined_200_ms"])
    ratios = [joined / plus if plus else 0.0
              for joined, plus in zip(samples["events.dump_json_joined_200_ms"],
                                      samples["events.dump_plus_dumps_200_ms"])]
    from hutch.server.sse import sse_message

    nl = chr(10).encode()
    payload = {"events": [event.model_dump(exclude={"id"}) for event in events],
               "first": events[0].seq, "last": events[-1].seq, "status": "running"}
    frame = sse_message("batch", payload, events[-1].seq)
    if (b"event: batch" + nl) not in frame or not frame.endswith(nl + nl):
        raise RuntimeError("sse_message did not produce a well-framed batch frame")
    sse_samples = [_time_once(lambda: sse_message("batch", payload, events[-1].seq)) for _ in range(n)]
    payload_bytes = len(frame)
    sse_median = statistics.median(sse_samples)
    cases.append({"name": "events.sse_batch_200_ms", "unit": "ms", "samples": sse_samples,
                  "better": "lower",
                  "note": f"one coalesced 200-event SSE frame; {payload_bytes:,} B payload "
                          f"({payload_bytes / EVENTS:,.0f} B/event), event=batch",
                  "detail": {"payload_bytes": payload_bytes, "bytes_per_event": payload_bytes / EVENTS}})
    cases.append({"name": "events.sse_batch_mbs", "unit": "MB/s",
                  "samples": [payload_bytes / 1e6 / (value / 1000) for value in sse_samples],
                  "better": "higher", "note": "serialized SSE bytes per second (200-event burst)"})
    cases.append({"name": "events.sse_batch_vs_dump_json_ratio", "unit": "x",
                  "samples": [sse / joined if joined else 0.0
                              for sse, joined in zip(sse_samples,
                                                     samples["events.dump_json_joined_200_ms"])],
                  "better": "lower",
                  "note": f"full SSE frame / per-event model_dump_json join; frame median {sse_median:.2f} ms"})

    cases.append({"name": "events.dump_json_vs_plus_dumps_ratio", "unit": "x",
                  "samples": ratios, "better": "lower",
                  "note": "dump_json joined time / dump+json.dumps time (<1 = faster)",
                  "detail": {"plus_dumps_median_ms": plus, "dump_json_median_ms": joined}})
    for key in list(samples):
        cases.append({"name": key.replace("_200_ms", "_per_event_us"), "unit": "us",
                      "samples": [value / EVENTS * 1000 for value in samples[key]], "better": "lower",
                      "note": "per-event serialization cost"})
    return cases
