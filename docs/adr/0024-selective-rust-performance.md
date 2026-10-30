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
2. The XLSX write stage was the one prototype candidate (small typed boundary, measured ms-scale
   pure-Python work). It was measured (see "Prototype measurement and final decision" below); the
   operation-level gain would clear the threshold, but the kernel is rejected/deferred for this
   release because it cannot be shipped within the current packaging window and its end-to-end
   effect does not justify a second native build. The Python generator, its tests and the
   independent openpyxl read-back gate remain the supported implementation.
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


## Prototype measurement and final decision (2026-10-29, same programme)

The only candidate with a plausible operation-level win was the XLSX write stage. It was
prototyped and measured rather than argued about:

- A disposable PyO3 0.29.3 + rust_xlsxwriter 0.90.2 cdylib was built against the locked venv
  Python (PYO3_PYTHON pointer; writable CARGO_HOME scratch; not committed).
- PyO3 trivial-call overhead measured 0.167 us/call, so call overhead is not the issue.
- Rust wrote a 5000x3-cell numeric workbook (write + zip) in 24.1 ms median (min 22.3, max 32.6)
  on the loaded host.
- The current Python XLSX path on the quieter host: 5000-row generation total 296.6 ms median
  (p95 318.4), of which `_write_workbook` is 108.7 ms, normalize 17.3 ms, the independent
  openpyxl read-back gate 174.0 ms (59%), declared-value verification 2.0 ms, preview 0.01 ms.

So a native write stage would plausibly remove ~85 ms of ~297 ms (about 28%, before spec
serialisation and the Python<->Rust copy), which would clear the operation-level P11 threshold.
It is nevertheless **rejected/deferred for this release**, deliberately and with the numbers
written down:

1. **Shipping path is unavailable in this programme window.** A user-installed wheel would need
   the Rust extension built and packaged through the project's mandatory install (build backend,
   dependencies, `uv.lock`). Those manifests are another session's uncommitted work in the main
   checkout; changing them cannot be merged safely here, and an optional .so that pip users never
   receive would not improve the product at all.
2. **The end-to-end effect is small relative to the workflow.** Document creation is normally
   preceded by model drafting (seconds); the measured saving is tens of milliseconds on unusually
   large (5000-row) spreadsheets and a few milliseconds on ordinary ones.
3. **The largest part of the cost is the safety gate, not the writer.** The independent openpyxl
   read-back is 59% of generation time and must stay independent; eliminating it to make a kernel
   look faster would be a safety regression, not an optimisation.
4. **Maintenance vs value.** A second native build unit, pinned Rust dependencies, CI coverage and
   a fallback path are a permanent cost for a sub-100 ms win on one optional operation.

Revisit when all of: the packaging/manifest window is clear, document generation is a primary user
workflow, and a shippable optional-extension path (maturin/abi3 wheels with pure-Python fallback)
is accepted by the maintainer. Until then the Python generator, its tests and its independent
validation gate remain the supported implementation; no Rust performance replacement is adopted.
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