"""Streaming tool-call assembly: OpenAIChatStreamAssembler fed synthetic OpenAI SSE chunk dicts.

Measures the full fold (every chunk delivered) for ~2 KB / 20 KB / 200 KB tool-argument payloads
split into 64-character deltas, the way providers stream them. Reports wall time and MB/s and the
input-scaling ratio (10x payload -> time ratio; near 10 means linear assembly).
"""

from __future__ import annotations

import statistics
import time

SAMPLES_FULL = 200   # cheap in-process case: enough samples for a meaningful p95
SAMPLES_QUICK = 3
FRAGMENT_CHARS = 64
PREFIX = '{"command":"echo ready","note":"'
SUFFIX = '"}'


def _payload(size: int) -> str:
    target = size - len(PREFIX) - len(SUFFIX)
    if target < 8:
        raise ValueError(f"payload size {size} is too small for a realistic fixture")
    return PREFIX + "x" * target + SUFFIX


def _chunks(payload: str) -> list[dict]:
    fragments = [payload[i:i + FRAGMENT_CHARS] for i in range(0, len(payload), FRAGMENT_CHARS)]
    chunks: list[dict] = [
        {"id": "chatcmpl-bench", "object": "chat.completion.chunk", "model": "bench/demo",
         "choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}}]},
    ]
    for position, fragment in enumerate(fragments):
        entry: dict = {"index": 0, "function": {"arguments": fragment}}
        if position == 0:
            entry["id"] = "call_bench"
            entry["type"] = "function"
            entry["function"]["name"] = "shell"
        chunks.append({"id": "chatcmpl-bench", "model": "bench/demo",
                       "choices": [{"index": 0, "delta": {"tool_calls": [entry]}}]})
    chunks.append({"choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]})
    chunks.append({"choices": [], "usage": {"prompt_tokens": 128, "completion_tokens": len(fragments),
                                            "total_tokens": 128 + len(fragments)}})
    return chunks


def run(quick: bool, state) -> list[dict]:
    from hutch.toolcalling.streamassembly import OpenAIChatStreamAssembler

    n = SAMPLES_QUICK if quick else SAMPLES_FULL
    sizes = [(1024, "1kb"), (10240, "10kb"), (102400, "100kb")] if quick         else [(2048, "2kb"), (20480, "20kb"), (204800, "200kb")]
    cases: list[dict] = []
    medians: dict[str, float] = {}
    per_size: dict[str, list[float]] = {}
    for size, label in sizes:
        payload = _payload(size)
        chunks = _chunks(payload)
        samples: list[float] = []
        for _ in range(n):
            assembler = OpenAIChatStreamAssembler()
            started = time.perf_counter()
            for chunk in chunks:
                assembler.feed(chunk)
            calls = assembler.calls()
            elapsed = time.perf_counter() - started
            if len(calls) != 1 or calls[0]["arguments"] != payload or calls[0]["name"] != "shell":
                raise RuntimeError(f"assembler lost payload fidelity at {label}")
            samples.append(elapsed * 1000.0)
        median_ms = statistics.median(samples)
        medians[label] = median_ms
        per_size[label] = samples
        cases.append({
            "name": f"streaming.assemble_{label}_ms", "unit": "ms", "samples": samples, "better": "lower",
            "note": f"{size / 1e6 / (median_ms / 1000):.1f} MB/s, {len(chunks)} chunks, {len(payload):,} B args",
            "detail": {"payload_bytes": len(payload), "chunks": len(chunks),
                       "mb_per_s": size / 1e6 / (median_ms / 1000)},
        })
        cases.append({
            "name": f"streaming.throughput_{label}_mbs", "unit": "MB/s",
            "samples": [size / 1e6 / (value / 1000) for value in samples], "better": "higher",
            "note": "effective argument bytes per second through the assembler",
        })
    labels = [label for _size, label in sizes]
    for previous, current in zip(labels, labels[1:]):
        paired = [later / earlier if earlier else 0.0
                  for earlier, later in zip(per_size[previous], per_size[current])]
        cases.append({
            "name": f"streaming.scaling_{previous}_to_{current}_ratio", "unit": "x",
            "samples": paired, "better": "lower",
            "note": f"10x payload -> ~{statistics.median(paired):.1f}x wall time (10.0 = linear)",
            "detail": {"from_median_ms": medians[previous], "to_median_ms": medians[current]},
        })
    return cases
