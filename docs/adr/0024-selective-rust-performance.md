# ADR-0024: Selective Rust for performance - measured decisions and gate

Status: accepted (2026-10-29). Evidence: docs/perf/plan-2026-10-29.md,
benchmarks/results/hotpaths-2026-10-30.json, .dsh/long-horizon/hutch-perf/artifacts/profiles/.

## Context

The performance programme (2026-10-29) profiled Hutch's real control paths before choosing
optimisations. Existing policy already constrains Rust: ADR-0001 rejected a Rust control-plane
rewrite (no evidence; 0.24 ms/step measured), ADR-0016 deferred a Rust process supervisor, and
docs/realignment/desktop-production-2026-10-26.md P11 requires equivalent tests plus >=20% p95 or
>=30% memory improvement including IPC before any additional Rust performance replacement.
docs/performance.md records the measured baseline and was written before the current event outbox
and validation paths.

Measured findings that frame the decision:

- The engine step CPU is dominated by SQLite run/step/health writes (~60% cumulative sqlite execute),
  not by JSON-schema validation (1.3% of profiled step CPU) or JSON serialization.
- Tool-call validation costs 63.8 us/call; a cached Python path is 29.8 us (2.19x) with no boundary.
- SSE frames cost 0.554 ms per 200 events; model_dump_json bytes-join is 23.5% faster in pure Python.
- Token accounting is quadratic across steps (83.6x time for 10x steps) and fixable in Python.
- XLSX generation for 5000 rows costs 245.9 ms median / 315.3 ms p95: ~31% writer,
  ~60% independent openpyxl read-back gate. The writer is pure Python; the gate must stay independent.
- Streaming assembly is linear (~30 MB/s); 200 KB (a rare upper bound) costs 7.0 ms.
- pydantic-core and sqlite3 are already native; uvicorn already uses uvloop/httptools.

## Decision

1. Adopt no Rust replacement for validation, JSON/SSE serialization, streaming assembly, SQLite
   marshalling, token accounting, workspace discovery or the orchestrator. For validation and SSE the
   measured Python improvements are adopted instead; for the rest the operation is sub-ms, already
   native, linear, or its contract duplication risk exceeds any measured gain.
2. Prototype one optional kernel - the XLSX write stage - because it is the only measured ms-scale
   pure-Python CPU operation with a small typed boundary and a fallback-friendly seam. Adopt it only
   if the pre-registered threshold in docs/perf/plan-2026-10-29.md is met through one Python driver
   including conversion, with the Python generator retained as reference/fallback and the independent
   openpyxl read-back gate unchanged. Otherwise record reject-measured with the A/B data.
3. No mandatory Rust dependency: if adopted, the kernel is an optional built artifact; a pure-Python
   fallback always exists, and a missing extension is not an error. No pyproject/uv.lock changes are
   made for it (the checkout's manifests are another session's parked files); the crate is a separate
   build unit under native/ with its own tests, and CI builds/tests it explicitly.
4. Do not target free-threaded CPython builds; keep modules GIL-compatible.
5. Do not trade event durability for throughput: append_event's per-event durable outbox commit stays.
   Throughput (5.4-6.2k ev/s) still exceeds the documented 1,000 ev/s gate by >5x; docs will state the
   trade-off honestly rather than change a recovery contract as a performance optimisation.

## Consequences

- The programme delivers measured, reversible Python/algorithmic improvements first, which is what the
  measured hot paths justify. No second executor, no parallel validator, no mandatory native build.
- If the XLSX prototype fails the gate, document-generating users keep the status quo; if it passes,
  large XLSX creation p95 improves by the measured amount with an unchanged validation gate.
- Revisit conditions: document generation becomes a dominant user workflow; a dashboard/SSE or
  per-step budget appears that Python cannot meet after the adopted fixes; or a future profile shows
  a >20% p95 kernel candidate that is not security- or contract-critical.

## Rejected alternatives

| Option | Why rejected now |
|---|---|
| Rust JSON-Schema validator | Would duplicate the canonical execution contract and refusal text (a fourth implementation); measured 63.8 us/call is 1.3% of step CPU. |
| Rust JSON/SSE serializer | pydantic-core already serializes in Rust; measured Python improvement is 23.5%; a PyO3 boundary would add conversion copies. |
| Rust streaming assembler | Linear work; typical 2 KB stream is 0.063 ms; rare 200 KB is 7 ms against network/model wait. |
| Rust token counter | 0.60 ms/call and better solved by caching in Python; JSON boundary costs comparable to the arithmetic. |
| Rust orchestrator/CLI | Pre-rejected by ADR-0001/0016; 0.24-0.25 ms/step measured overhead; a second executor would be a safety regression. |
| Rust SQLite reader/writer | sqlite3 is C; row<->model conversion is pydantic-core (Rust); bounded API pages are ~1.5 ms. |
| Full or partial rewrite | docs/requirements.md declares a Rust rewrite out of scope; no measured evidence supports it. |

## Evidence and verification

- Harness: `PYTHONPATH=$PWD/src <venv>/bin/python -m benchmarks.hotpaths` (n/min/median/p95/max/CV,
  loadavg, machine identity, harness hash; isolated state per case).
- Decision protocol: docs/research/performance-rust-2026-10-29.md section 8 (pre-register threshold,
  interleaved A/B through one driver, boundary counted, equivalence tests, repeat on a second session).
- Any adopted kernel must also pass: focused pytest for touched behaviour, `python -m benchmarks.run --check`,
  audits, and the independent verifier gate.
