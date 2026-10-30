# Performance engineering and selective Rust: external research record (2026-10-29)

Phase 1 research for the Hutch performance programme. This file is the research record, not a
performance claim: nothing here was benchmarked on Hutch's hardware. External numbers are quoted
from their sources with the source's own hardware stated where it is stated at all.
Access date for every URL below: 2026-10-29. Repository-internal documents are cited by path.

**Evidence grades used throughout**

- **E / established**: documented behaviour, specification, or a measurement with a stated method that
  is not primarily the vendor's own marketing claim.
- **R / individual report**: a bug report, issue, or benchmark run by one reporter. Direction is
  informative; magnitude is not a Hutch result.
- **U / unverified**: a claim with no method, no code, or no reproducible measurement. Treat as a
  hypothesis to test, never as evidence for a decision.

**Why this document exists.** The programme's Phase 1 gate (D2 in the charter) requires that the
decision to introduce or reject Rust be based on external evidence plus the repository's own policy,
before any profiling result is allowed to drive a migration. The conclusion below is a shortlist to
measure, not a decision.

---

## 1. Native Python extensions in 2026: PyO3, maturin, abi3, fallback, CI cost, free-threading

### 1.1 Current PyO3 practice

| Source | Date | Finding | Grade |
|---|---|---|---|
| [PyO3 user guide, Features reference](https://pyo3.rs/main/features) | accessed 2026-10-29 | PyO3 has two stable-ABI flavours: `abi3` (Python 3.2+, **not loadable by free-threaded builds**) and `abi3t` (Python 3.15+, loadable by both GIL and free-threaded builds). Version-specific `abi3-pyXY` features select a minimum Python. | E |
| [PyO3 user guide, Building and distribution](https://pyo3.rs/main/building-and-distribution) | accessed 2026-10-29 | The free-threaded build cannot load `abi3` wheels; both builds can load `abi3t`. Packaging tools are maturin and setuptools-rust; `PYO3_BUILD_EXTENSION_MODULE` distinguishes extension builds. | E |
| [maturin guide, Bindings](https://www.maturin.rs/bindings.html) | accessed 2026-10-29 | A single maturin build selects **one** stable-ABI family. Publishing both `abi3` and `abi3t` wheels requires separate builds (`maturin build --interpreter python3.10`, `--interpreter python3.15t`). Mixing both features in one build does not produce both wheels. | E |
| [PyO3 issue #3827, "Performance: calling overhead"](https://github.com/PyO3/pyo3/issues/3827) | created 2024-02-11 | A reporter measured a trivial PyO3 `#[pyfunction]` at 33.5 ns/call versus 12.6 ns/call for a hand-written fastcall C function on the same interpreter: roughly 20-40 ns of per-call overhead in the reporter's scenarios. | R |
| [PyO3 guide, Supporting Free-Threaded CPython](https://pyo3.rs/v0.29.2/free-threading) | accessed 2026-10-29 | Since PyO3 0.28 modules default to attesting thread safety; `#[pymodule(gil_used = true)]` opts out and makes the interpreter re-enable the GIL at import with a RuntimeWarning. Free-threaded support is not automatic for unsafe code that assumed the GIL. | E |
| [pydantic performance tips](https://docs.pydantic.dev/latest/concepts/performance/) | accessed 2026-10-29 | A widely used Python project with a native core advises reusing validators/serialisers rather than constructing them per call, and validates JSON directly (`model_validate_json`) instead of parse-then-validate. The Rust core is an implementation detail; the guidance is about avoiding repeated setup. | E |

### 1.2 What "current best practice" means concretely

1. **One extension module, one narrow purpose.** The mature pattern (pydantic-core, orjson, ruff) is a
   native core that owns one data-path operation and exposes plain Python objects at the boundary, not
   a second executor or a shadow runtime.
2. **Ship wheels, not compilers.** Maturin builds the wheel; users never need Rust. Anything requiring
   a local `cargo` build at `pip install` time is a packaging cost that a local-first product should not
   impose.
3. **Stable ABI is a deliberate choice.** `abi3` gives one wheel across Python 3.x but excludes
   free-threaded builds; `abi3t` needs Python 3.15+. Targeting the repository's floor (Hutch requires
   Python 3.11+) with version-specific wheels is simpler and faster, but multiplies wheel count.
4. **The pure-Python fallback must be the reference implementation.** Import-with-try/except and a
   feature flag are the standard pattern; the fallback is what tests compare against.
5. **Call overhead is real but small; marshalling is the cost that matters.** 20-40 ns per call is
   irrelevant at Hutch's call frequencies (one validation per tool call, tens of events per step). The
   cost that decides a migration is converting a large Python object graph into Rust values and back:
   every dict, list, string and int crossing the boundary is a copy or a reference-count operation.

### 1.3 Free-threading implications for a local-first desktop app

| Source | Date | Finding | Grade |
|---|---|---|---|
| [Python docs, What's new in 3.14](https://docs.python.org/3/whatsnew/3.14.html) | 3.14 released 2025-10-07 | "Free-threaded Python is officially supported" in 3.14 (PEP 779), after the 3.13 experimental build. Free-threaded mode improvements and a new type of interpreter are listed as headline items. | E |
| [Python docs, Python support for free threading](https://docs.python.org/3/howto/free-threading-python.html) | accessed 2026-10-29 | The free-threaded build has additional overhead: on pyperformance the average single-threaded overhead ranges from about 1% on macOS aarch64 to about 8% on x86-64 Linux. It also typically uses more memory. | E |
| [PEP 703](https://peps.python.org/pep-0703/) | 2023 | Technical design of the optional GIL; threads attach/detach instead of acquiring a global lock. | E |

**Applicability to Hutch.** Hutch is Python 3.11+ (charter: Python 3.13.15 on the dev machine) and
single-user local-first; the parallelism that free-threading unlocks is not currently a bottleneck
because steps are I/O- and inference-bound and the control plane already spawns one worker OS process
per run (ADR-0001). A free-threaded build would *cost* 1-8% single-threaded CPU and more memory in
exchange for parallelism Hutch does not need yet, and a native extension that opts out
(`gil_used = true`) silently re-enables the GIL on import. **Recommendation: do not target
free-threaded builds in this programme; do not build abi3t wheels; keep the extension optional and
GIL-compatible.** Independent verification: none needed for the policy; the overhead range is
published documentation, not a Hutch measurement.

### 1.4 Wheel and CI build cost

Maturin's documented workflow (above) implies: one wheel per OS/arch/Python tag. Hutch's CI already
runs 3.11/3.12/3.13 on Linux plus Windows/macOS platform jobs. A Rust extension adds a `cargo build`
job with its own toolchain, caching, and per-platform artefacts; PyO3 issue #3827 exists in a mature
project where per-call overhead is still discussed, which is a reminder that native code is a
long-term maintenance surface (MSRV, PyO3 minor-version churn, ABI, free-threaded transitions).
**This is a real cost that must be paid by a measured end-to-end win, not by an operation-level win
alone.**

---

## 2. Rust versus Python for CPU kernels relevant to Hutch

Overall framing: Python's hot primitives are largely already C. The standard `json` scanner is C
([CPython `Modules/_json.c`](https://github.com/python/cpython/blob/main/Modules/_json.c)), `sqlite3`
wraps the C SQLite library ([Python docs](https://docs.python.org/3/library/sqlite3.html)), and Hutch's
ASGI server uses native parsers when the standard extra is installed. A Rust kernel therefore competes
with C, not with interpreted Python. Published ratios of 2-4x over stdlib are plausible; ratios of
100x only appear when the Python path is itself pure Python (as in the JSON Schema case below).

### 2.1 JSON Schema validation

**Evidence.** The jsonschema-rs project publishes a Python benchmark suite comparing jsonschema-rs,
Python `jsonschema` 4.26.0 and `fastjsonschema` 2.21.2, Python 3.14.0, Rust 1.96.1
([benchmark suite](https://github.com/stranger6667/jsonschema/blob/339325524bf2618013b2cab1e4d4629e70c83b0b/crates/jsonschema-py/BENCHMARKS.md),
accessed 2026-10-29):

| Benchmark (schema/instance) | fastjsonschema | jsonschema | jsonschema-rs validate |
|---|---|---|---|
| OpenAPI (18 KB / 4.5 MB) | - (unsupported format) | 525.05 ms | 2.03 ms |
| Swagger (25 KB / 3.0 MB) | - | 910.55 ms | 2.60 ms |
| GeoJSON Canada (4.8 KB / 2.1 MB) | 10.18 ms | 692.15 ms | 0.65 ms |
| CITM catalog (2.3 KB / 501 KB) | 4.66 ms | 72.79 ms | 0.74 ms |
| Fast valid (595 B / 55 B) | 1.83 us | 31.79 us | 230.10 ns |
| FHIR (3.3 MB / 2.1 KB) | 2.41 ms | 11.44 ms | 5.04 us |
| Recursive (1.4 KB / 449 B) | - | 1.14 s | 9.75 us |

**Grade: published maintainer benchmark (R, trending E for direction).** Methodology is explicit
(pinned library versions, fixed fixtures, interpreter versions), but the harness, fixtures and the
winning library share one maintainer, and the machine is not stated. The README reports a single
number per cell, not n/median/p95, so noise is unknown.

**Applicability to Hutch (corrected against the source).** Hutch's `src/hutch/toolcalling/validate.py`
does **not** primarily use the `jsonschema` package. `validate_call` (line 216) runs a local bounded
validator first and only then, if the optional `jsonschema` package is importable, runs a Draft 2020-12
validator as an additional refusal check (lines 229-236, 269-277). The canonical contract is the tool's
registered `parameters` schema and the module explicitly refuses schemas it cannot certify. Hutch's
tool schemas are small and tool arguments are small relative to these fixtures; the per-call cost is
tens of microseconds at most, once per tool call. Replacing this with a Rust validator would create a
**fourth** implementation of the execution contract and shift error-message wording, which the module
treats as canonical repair text. The 230 ns-2 ms figures above do not apply to the bounded validator,
which is already considerably cheaper than `jsonschema`.

**Opportunity.** Low, unless profiling shows validation dominating a step with very large arguments
(large document bodies, workflow node results, structured model answers). Even then, the honest
alternative is to cache compiled validators / pre-analyse schemas once per tool (the pydantic
"reuse the validator" guidance) rather than to rewrite the contract in Rust.

**Independent verification required.** Yes before any migration: (a) confirm which validator path is
actually active in the installed environment; (b) measure `validate_call` per call on real catalog
schemas and on worst-case large arguments; (c) confirm that a Rust validator reproduces every canonical
refusal message, including unsupported-keyword refusals.

### 2.2 JSON parse and serialise

**Evidence.** The community `json_benchmark` suite benchmarks Python JSON readers/writers with pinned
library versions, min/max/mean per fixture, and a correctness minefield; tables regenerated 2026-07-13
([TkTech/json_benchmark](https://github.com/TkTech/json_benchmark), accessed 2026-10-29). Complete-load
timings in ms (lower is better; hardware not stated in the README):

| Fixture | json | ujson | rapidjson | simdjson | msgspec | orjson | yyjson |
|---|---|---|---|---|---|---|---|
| canada.json (2.25 MB) | 23.84 | 11.13 | 24.67 | 7.27 | 6.61 | 6.01 | 4.50 |
| citm_catalog (1.73 MB) | 6.23 | 4.47 | 4.52 | 3.39 | 3.09 | 2.42 | 1.78 |
| twitter (0.57 MB) | 2.69 | 1.70 | 1.86 | 1.39 | 1.06 | 0.81 | 0.87 |

**Grade: R (published community benchmark, method stated, not independently replicated; hardware and
CPU governor unknown).** The project also reports correctness failures for some libraries, which is the
more decision-relevant fact.

The orjson README claims `dumps` is "something like 10x as fast as json" and `loads` "something like
2x", with wheels for CPython 3.10-3.15
([orjson README](https://github.com/ijl/orjson), accessed 2026-10-29). **Grade: U for the 10x/2x
magnitudes** (vendor claim, no method in the statement); direction agrees with the independent suite
for loads (about 2.5-4x on these fixtures).

A separate 2026-05-14 polyglot benchmark by the Perry project reports serde_json at 186-197 ms versus
simdjson at 24 ms for a ~1 MB blob parsed and re-serialised 50 times, with medians, p95 and sigma
([Perry JSON polyglot results](https://github.com/PerryTS/perry/blob/v0.5.1158/benchmarks/json_polyglot/RESULTS.md)).
**Grade: R, and self-interested** (it exists to show its own runtime's numbers); it does not include
Python. Its useful message is that serde_json is not faster than an optimized C parser: a Rust JSON
kernel must beat CPython's C scanner by a constant factor, and it must do so *including* the cost of
converting the result into Python objects.

**Applicability to Hutch.** JSON is genuinely on every hot path: event persistence/serialisation,
SSE payloads, snapshots, tool-result records, provider request bodies. `src/hutch/server/sse.py:40`
(`sse_message`) and `src/hutch/server/app.py` (`json.dumps(value, ensure_ascii=False,
separators=(",", ":"))` at line 937 and other sites) serialise on every event burst.

**Opportunity.** The cheapest version of this win is not Rust: it is a maintained native wheel such as
orjson/msgspec used through the normal dependency mechanism. That is a Python dependency decision, not
a Rust migration, and it should be measured first. A Rust kernel `encode_event_json(payload) -> bytes`
would still hand a `dict` to Rust and copy a `bytes` back — the copy is unavoidable, and the conversion
of the payload dict into Rust values costs about as much as the serialisation saved.

**Independent verification required.** Yes: measure Hutch's actual payloads (event burst, snapshot,
tool result) with stdlib vs a native wheel vs a Rust prototype, including boundary conversion.
A 20% p95 win on the *operation* is plausible for serialisation of large payloads; a 20% p95 win on
the *end-to-end* step is not, because JSON serialisation is a fraction of a 0.25 ms control-plane step.

### 2.3 Streaming / incremental JSON

**Evidence.** The json_benchmark suite compares SAX-style streaming parsers on full documents: yyjson
(SAX) versus ijson (yajl2_c) on canada.json 22.69 ms vs 8.70 ms, on fgo.json (48.8 MB) 495.10 ms vs
315.41 ms, on otfcc.json (66.4 MB) 1020.10 ms vs 646.01 ms (source and date as above). Note these are
both native parsers; the Python-level ijson wrapper is already backed by a C parser. **Grade: R.**

**Applicability to Hutch.** `src/hutch/toolcalling/streamassembly.py:60`
(`OpenAIChatStreamAssembler`) does not parse a large JSON document. It reassembles small JSON argument
fragments from SSE deltas into a dict per tool call. The work is small, allocation-heavy, and inside the
provider stream loop, so it is a plausible per-token cost but not a "large document" problem. There is
no published benchmark for "reassemble fragmented tool-call argument JSON" in any language; any claim
about it would be unverified until Hutch measures its own fixture.

**Opportunity.** Real only if profiling shows stream assembly as a top cost during long streaming turns.
A Rust assembler would receive each small delta via PyO3 (20-40 ns overhead plus conversion) and return
small structures; the boundary traffic is proportional to the number of deltas, which is exactly the
thing that could make Rust slower for tiny chunks.

**Independent verification required.** Yes; and the first comparison must be against a cheaper Python
algorithm (accumulate into a list of strings, single `json.loads` at the end), not against Rust.

### 2.4 Text diff

**Evidence.** CPython issue #106865 reports that `difflib.SequenceMatcher.get_opcodes()` "takes several
minutes to return a list of tuples for two identical files that are 70kb long", and asked for a
documentation warning; it was addressed by a docs PR
([python/cpython#106865](https://github.com/python/cpython/issues/106865), created 2023-07-18, closed).
**Grade: R (individual report) accepted by CPython as a documentation problem**, i.e. CPython chose to
document rather than reimplement.

The Rust `similar` crate implements Myers/Patience/LCS-style algorithms with Criterion and allocation
benchmarks plus a generative performance fuzzer that isolates each algorithm and saves reproducible
input pairs ([similar README](https://github.com/mitsuhiko/similar), accessed 2026-10-29). **Grade: E
for the existence of a rigorous benchmark harness; not a Python-vs-Rust ratio.**

Also relevant: opencode issue #60305 describes an LCS matrix allocated proportional to
old-lines x new-lines for line-ending alignment; the reporter says a 48 KB file can consume hundreds of
MiB and that larger regions grow quadratically in memory and work
([anomalyco/opencode#60305](https://github.com/anomalyco/opencode/issues/60305), created 2026-10-29,
open). **Grade: R**, with a reproduction script in the issue.

**Applicability to Hutch (corrected).** `grep -r difflib src/hutch` returns **no matches**. Hutch does
not currently call `difflib` from product code. A diff kernel therefore has no call site to speed up
today; it would be new functionality, which is out of scope for this programme. If a diff is
introduced later for file-edit review, the correct first answer is an algorithm with a documented
complexity bound (histogram/patience diff, line-level with size caps), not a language migration.

**Opportunity.** None in the current tree. **Do not migrate.** Revisit only if a future feature adds a
diff on large files and a Python algorithm with bounded complexity is still measured too slow.

### 2.5 HTTP / SSE framing

**Evidence.** uvicorn's standard extra installs "Cython-based" dependencies: `uvloop` for the event loop
and `httptools` for the HTTP protocol
([uvicorn README](https://github.com/Kludex/uvicorn), accessed 2026-10-29). **Grade: E** for the fact that
the HTTP parsing and event-loop layers are already native when the standard extra is installed.

**Applicability to Hutch.** `src/hutch/server/sse.py:37` (`sse_message`) does an f-string plus
`json.dumps` per message; framing itself is trivial and the transport is already native. SSE is a
textual protocol over an existing connection: no framing win is available from Rust that is not
already available from the JSON serialiser.

**Opportunity.** Only the JSON encoding inside the frame (section 2.2), not the framing. **Do not
migrate framing.**

### 2.6 SQLite row marshalling

**Evidence.** No credible published cross-language benchmark for "SQLite rows -> Python objects" was
found for this record; Python's `sqlite3` is a C extension around the C SQLite library, and
`rusqlite` is a Rust wrapper around the same C library
([Python sqlite3 docs](https://docs.python.org/3/library/sqlite3.html),
[rusqlite docs](https://docs.rs/rusqlite/latest/rusqlite/), accessed 2026-10-29).
**Grade: E for the architecture (both wrap C SQLite); U for any speedup claim.**

**Applicability to Hutch.** `src/hutch/store.py` is the single writer with group commit; measured at
~52,000 event inserts/s on the dev machine ([docs/performance.md](../performance.md)). The remaining
Python-side cost is the row -> `Event`/`Run` dataclass conversion. A Rust layer would still need to
hand Python objects back: for a list of 2,000 events, the conversion cost largely moves rather than
disappears, and the SQLite call itself dominates.

**Opportunity.** Low. The published-design win here is batching/columnar retrieval and avoiding
per-row object construction, not Rust. **Independent verification required** before any claim; no
external benchmark exists to borrow.

---

## 3. Competitor and ecosystem failures: what actually goes wrong

Method: GitHub issue search through the public API plus direct issue reads; each row names the symptom
as reported, whether a root cause is documented in the issue, the response, and whether Hutch could
realistically solve the same class of problem. These are reports, not reproduced defects.

| Product | Source (date) | Reported symptom | Documented root cause | Response | Grade | Could Hutch solve it? |
|---|---|---|---|---|---|---|
| opencode | [anomalyco/opencode#60305](https://github.com/anomalyco/opencode/issues/60305) (2026-10-29, open) | Edit tool allocates an LCS matrix proportional to old x new line counts; a 48 KB file can consume hundreds of MiB; larger regions grow quadratically in memory and work | Yes: matrix size is the product of line counts | Open; reporter supplied a repro script against a dev commit | R | Only as an algorithmic fix (bounded diff / histogram), not as a language fix. Hutch has no diff call site. |
| cline | [cline/cline#14092](https://github.com/cline/cline/pull/14092) (2026-09-13, open) | Streaming reasoning deltas amplified memory and SQLite writes | Yes: every `assistant.delta`/`reasoning.delta` chunk was persisted as an event | Fix proposed: deltas live-only, finished events durable, event filters before snapshot serialisation | R (PR author's description) | Yes, and Hutch's design already separates live streaming from durable events; the lesson is to verify that the durable path is not storing every delta. |
| opencode | [anomalyco/opencode#59678](https://github.com/anomalyco/opencode/issues/59678) (2026-10-27, closed) | Desktop renderer died with `SchemaError: Expected object` right after the long-lived `GET /api/event` SSE connection closed; reload re-crashed; sidecar server was healthy and the run completed via the API | Partly: server did not log event payloads, so the offending frame was not identified; the client's error path on stream loss was the trigger | Closed; not enough evidence recorded in the issue to know the fix | R | Yes: Hutch's SSE resume uses `Last-Event-ID` plus cursor (`src/hutch/server/sse.py:54`); the real lesson is that the *client* must treat a stream drop as recoverable, and the server must be able to identify the last frame it sent. |
| opencode | [anomalyco/opencode#60005](https://github.com/anomalyco/opencode/issues/60005) (2026-10-28, closed) | After restart, a plugin-provided server's session list loaded forever; renderer logged `event stream disconnected` every second against `http://127.0.0.1:0` | Yes: transport endpoint restored from an "offline" placeholder and never reconnected | Closed | R | Yes, as a startup-state bug class: Hutch's owned-backend approach (ADR-0020) already binds a real loopback port; the measurement-relevant lesson is that reconnect loops are a startup-latency multiplier. |
| OpenClaw | [openclaw/openclaw#150634](https://github.com/openclaw/openclaw/issues/150634) (2026-09-17, closed) | Provider stream hard-closed after ~10 minutes; blind retry loop issued full-content updates, and perceived streaming dropped to ~2-3 chars/s in the destination UI while another UI showed ~10 chars/s | Yes: retries were full-content PUTs against a dead stream | Closed; report documents the retry storm | R | Yes as a client policy: bounded retries, no full-content resend. Not a Rust issue. |
| n8n | [n8n-io/n8n#37342](https://github.com/n8n-io/n8n/issues/37342) (2026-08-28, open) | Queue-mode main process grows ~40 MiB/s off-heap until OOMKill; workers stable; growth tracks number of executions enqueued | Yes: allocation growth tracks enqueued executions, not payload size; V8 heap cap does not bound it | Open | R (detailed numbers in the report) | Partly: Hutch's queue is SQLite rows claimed by workers (ADR-0001), so the specific off-heap shape does not transfer; the transferable lesson is to monitor RSS per process role and bound in-memory queues. |
| Continue | [continuedev/continue#12053](https://github.com/continuedev/continue/issues/12053) (2026-04-06, closed) | Chat UI becomes progressively slower as a conversation grows (500k+ tokens, multiple compressions); still slow after context compression, so it is not the prompt size | Not stated in the report; the behaviour points at client-side transcript/history work per render | Closed | R | Yes, and directly relevant: Hutch must render long transcripts from paginated/coalesced data, and the P11-scale test (>=10k events) is the right guard. |
| Letta | [letta-ai/letta#2425](https://github.com/letta-ai/letta/issues/2425) (2025-02-09, closed) | A user with ~2k messages blocks the whole server after 2-3 replies; one reply takes >1 min versus 10-15 s for a new user | Not documented | Closed | R | Partly: Hutch's equivalent risk is loading full history per step; the fix class is indexing/pagination, not Rust. |
| LangGraph | [langchain-ai/langgraph#9078](https://github.com/langchain-ai/langgraph/issues/9078) (2026-09-25, closed) | Product of two defects: runs left `running` by a dead process are never reset and permanently wedge their thread; `Threads.sweep_ttl` is a stub so TTL never frees anything; server leaks until OOM-killed | Yes, with code excerpts and version numbers | Postgres runtime already rolls back orphan runs at startup; the in-memory runtime did not | R | Yes, and Hutch already has the equivalent mechanism (leases/fences, ADR-0001). The research value is a test case: recovery from orphaned runs must be verified under restart. |
| OpenClaw | [openclaw/openclaw#138499](https://github.com/openclaw/openclaw/issues/138499) (2026-09-04, open) | A timed-out cron run left its session-scoped CLI task `running` for 5+ hours; gateway restart then waited on it | Yes: session-scoped task ownership was not terminated with the session | Open | R | Yes; Hutch's worker process group + lease design (ADR-0001) targets exactly this, and the issue is already cited by the repo. |
| ZeroClaw | [zeroclaw-labs/zeroclaw#10780](https://github.com/zeroclaw-labs/zeroclaw/issues/10780) (2026-09-11, open) | No proactive token-budget compaction; only message-count trimming; long tool-using turns re-send a large prompt | Yes: `context_compression` removed, `keep_recent`/`collapse_tool_results` inert | Open | R | Partly: this is a context-management defect, not a CPU defect; Hutch's prompt sizing (`src/hutch/context.py`) is the corresponding subsystem. |

### 3.1 Patterns worth designing against (mapped to Hutch files)

1. **Event streams amplify work when every delta is persisted, serialised, or re-rendered.** cline
   #14092 is the clearest documented case. Hutch: `store.append_event`, `sse.sse_message`,
   `app.py` snapshot/global endpoints; verify deltas are not durable rows and that coalescing bounds
   the number of frames per burst (Hutch already coalesces at 0.08 s, `sse.py:30`).
2. **Quadratic data-structure choices dominate real defects, not language speed.** opencode #60305
   (LCS matrix), Continue #12053 (per-render history work), LangGraph #9078 (unbounded retention).
   The programme's rule to compare algorithmic/data-structure/caching fixes before language migration
   is exactly right, and these reports are the evidence.
3. **Stream loss and reconnect loops are treated as UI or startup bugs.** opencode #59678/#60005,
   OpenClaw #150634. Hutch's `Last-Event-ID` resume and bounded `retry: 1500` are the right mitigations.
4. **Memory growth tracks enqueue/retention, not payload size.** n8n #37342, LangGraph #9078,
   Letta #2425. Bound queues and retention.
5. **Orphaned work after crashes is a correctness and capacity bug, not a perf micro-issue.** OpenClaw
   #138499, LangGraph #9078. Hutch's fences/leases are the answer; tests should cover restart recovery.
6. **Client rendering cost is a first-class performance surface.** Continue #12053 shows a UI that gets
   slower with conversation length even when the model context is compressed. For Hutch this means the
   P11-scale dashboard test (>=50 bots, >=10k events) and pagination are the acceptance surface, not
   Python CPU kernels.

The repository's own [complaints.md](complaints.md) and
[offerings-and-failures.md](offerings-and-failures.md) already record the product-level complaint
history (single comments on HN, quarantined and corrected items). This section deliberately adds only
performance-shaped reports with a URL, a date, and where possible a documented cause.

---

## 4. Hutch's own Rust policy: the exact constraints a migration must satisfy

Read for this record: [ADR-0001](../adr/0001-control-plane-and-owned-execution.md),
[ADR-0016](../adr/0016-rust-process-supervisor-deferred.md),
[ADR-0020](../adr/0020-canonical-opencode-tools-and-desktop-host.md),
[ADR-0022](../adr/0022-host-platform-adapters.md), [docs/performance.md](../performance.md),
[docs/requirements.md](../requirements.md), and
[docs/realignment/desktop-production-2026-10-26.md](../realignment/desktop-production-2026-10-26.md).

**C1 - The P11 gate (verbatim).** "Rust native host; additional Rust performance replacement only after
equivalent tests and >=20% p95 or >=30% memory improvement including IPC"
(desktop-production-2026-10-26.md line 19, state: "In progress - required Rust host; no
performance-driven replacement adopted"). The improvement must be on the measured operation *including
IPC/boundary cost*, with tests equivalent to the Python path it replaces.

**C2 - No full rewrite.** requirements.md, "Out of scope (unchanged)": "A Rust rewrite, messaging
channels, hardware peripherals, ...". The charter repeats: "no full Rust rewrite", "no second
executor", "no unmeasured speed claim".

**C3 - Rust is for required native ownership, not speed.** ADR-0022: "Rust is used for required native
ownership, not a measured Python speed replacement" and "No additional dependency or Rust performance
claim is introduced." ADR-0020: "Rust is used for native integration; no unmeasured speedup or Rust
agent-loop replacement is claimed. ADR 0016's performance requirement remains in force."

**C4 - The supervisor boundary is closed.** ADR-0016 keeps the Python process supervisor and says any
future Rust path "must stay limited to spawn/supervise/capture/report; product policy, scheduling,
approvals, and persistence stay in Python." It may be revisited only if a measured gap remains after
Python fixes (for example cancellation-to-exit p95 beyond an agreed budget), and the fallback "must
never restore false cancellation or unbounded buffering."

**C5 - The control plane was already measured and rejected as a Rust target.** ADR-0001 option D
("Rewrite the control plane in Rust") was rejected because Hutch's measured control-plane cost is
0.24 ms/step and the idle footprint 41-66 MB; "inference, not the orchestrator, dominates", and
ZeroClaw publishes no method for its footprint claims. Any candidate that only touches the step loop
is therefore pre-rejected by existing evidence.

**C6 - Inference latency is not addressable here.** docs/performance.md: a real model call is 1-60 s
while the measured Hutch overhead per step is 0.25 ms; the document explicitly warns not to infer
production inference or tool latency from that number. A CPU-path win cannot move user-perceived step
latency in any realistic session unless it is on the *document generation* or *dashboard* path where
there is no model wait.

**C7 - The existing regression gate.** `python -m benchmarks.run --check` exits non-zero on a >20%
regression; baselines are machine-keyed; docs/performance.md states the harness reports the minimum of
11 runs and uses "a 20% tolerance plus absolute floors so a single clock tick cannot fail the build".
A new kernel must not break this gate and should be measured with the same discipline.

**C8 - Packaging must stay parked-safe.** ADR-0022's file-lock and credential work added no new Rust
for performance; R3 in the charter notes the parked session's uncommitted files may include
`pyproject.toml`/`uv.lock`, so a Rust extension must be optional and separately built, with a
pure-Python fallback and no forced lockfile/pyproject edits unless explicitly justified.

**C9 - Behavioural contract is canonical.** Tool-call validation, approval semantics, redaction, and
the local-first security model are execution contracts, not implementation details
(`src/hutch/toolcalling/validate.py` docstring; ADR-0006/0007 referenced by the ADRs above). Any Rust
replacement must reproduce refusals and error text, not just speed up the happy path.

---

## 5. Measurement methodology for a noisy 4C/8T laptop

The dev machine is an AMD Ryzen 3 5300U (4C/8T, 22 GiB, no GPU), and the recorded baseline was taken
"on a busy desktop (a second coding agent was running)" with CLI timings varying by ~30% between
back-to-back runs ([docs/performance.md](../performance.md)). Methodology therefore decides whether a
result is real.

### 5.1 Distributions, not means

- **Report n, median, p95, min, max, and the full run list.** Percentiles describe the user-visible tail;
  a mean hides it. Python's `pyperf` exists specifically to run reliable benchmarks, calibrate, detect
  instability ("`pyperf check`"), and report min/max/mean/median/percentiles per benchmark
  ([pyperf documentation](https://pyperf.readthedocs.io/en/latest/), accessed 2026-10-29). Criterion.rs
  records repeated samples per benchmark, classifies outliers, and bootstraps a confidence interval
  before comparing runs, with explicit warmup and analysis phases
  ([Criterion analysis process](https://bheisler.github.io/criterion.rs/book/analysis.html), accessed
  2026-10-29).
- **A tail claim needs a tail sample.** A p95 is unstable with 10 samples (that is the maximum of the
  sample). Use at least 200 samples for a p95 claim, or state that the number is not a p95.
- **Beware passive benchmarking.** Brendan Gregg's "Active Benchmarking" guidance: passive benchmarking
  collects numbers without checking what is being measured; run the benchmark in steady state, inspect
  the system while it runs, and treat a bar chart with no supporting evidence as suspect
  ([brendangregg.com/activebenchmarking.html](https://www.brendangregg.com/activebenchmarking.html),
  accessed 2026-10-29). This is the exact failure mode available to this programme on a laptop.

### 5.2 Cold starts and short processes: minimum-of-N

`hutch status`/`hutch version` and worker start-up are cold-process measurements: process creation,
imports and first-touch page faults dominate, and the distribution is right-skewed by background load.
The established practical approach is to run N repetitions and report the minimum (best achievable
under minimal interference) *and* the median/p95 to show the spread; hyperfine does at least 10 runs,
supports warmup and prepare commands, and performs statistical outlier detection to expose interference
([hyperfine README](https://github.com/sharkdp/hyperfine), accessed 2026-10-29). The repository already
uses min-of-11 for cold CLI timings and says why. Use the same estimator for before/after comparisons,
and compare distributions, not single minima.

### 5.3 Controlling the machine

- **Isolate state.** Fresh `HUTCH_HOME` per run; for SQLite throughput use a fresh directory on a fast
  local filesystem (`/dev/shm` as docs/performance.md suggests) so disk queue does not become the
  measurement.
- **Interleave A/B.** Run baseline and candidate alternately within one session (A/B/A/B) rather than
  all of A then all of B; slow drift on a laptop (thermal, background updates) then affects both.
- **Record load.** Log `/proc/loadavg`, the number of other agent processes, and whether the machine was
  on battery; a result taken while another suite runs is not comparable to a quiet run.
- **Absolute floors.** Treat differences below a floor (for example 1 ms, or 5% of the operation) as
  unmeasurable regardless of percentage, matching the existing gate's floor discipline.
- **Two sessions.** Repeat the final comparison on a second day; a 20% threshold that only appears once
  is not evidence. This is a proposed discipline, not an external standard.

### 5.4 Why microbenchmarks mislead here

A criterion-style microbenchmark of a Rust function will show a large speedup that can vanish once the
real call path is measured, for four reasons documented above: (a) PyO3 call overhead is 20-40 ns per
call (issue #3827); (b) the Python object -> Rust value conversion is proportional to payload size and
is the dominant cost for large payloads; (c) the Python implementation is often already C (JSON, SQLite,
HTTP parsing); and (d) at the measured 0.25 ms Hutch overhead per step, the total operation is small enough that
saved microseconds are invisible against model waits and UI work. Therefore **the acceptance benchmark
must be the real operation measured through Python**, not a Criterion result.

---

## 6. Candidate shortlist

Frequency and cost estimates below are hypotheses from the code shape, not measurements; each row's
last column is what must be measured before any decision. "P11 bar end-to-end" means >=20% p95 or >=30%
memory on a measured operation *including* IPC, with an honest statement of end-to-end effect.

| Kernel | Exact Hutch operation (file:symbol) | Expected operation-level evidence | Boundary/IPC risk | Plausible P11 bar end-to-end? | Measure first |
|---|---|---|---|---|---|
| JSON serialisation of events/snapshots | `src/hutch/server/sse.py:37 sse_message`, `src/hutch/server/app.py` `json.dumps` sites, `store.append_event` payload | 2.5-4x loads and a claimed ~10x dumps over stdlib in published benchmarks (R; own workload unmeasured) | Medium: payload dict must be converted; result bytes copied back | **Possible on the operation at scale; unlikely end-to-end on a step.** Dashboard burst/large snapshot is the only place with enough milliseconds | Payload sizes and count per burst; stdlib vs native-wheel first (cheaper than Rust) |
| JSON Schema validation | `src/hutch/toolcalling/validate.py:216 validate_call`, `:133 analyze_schema` | Published jsonschema-rs numbers are 100-2000x faster than Python `jsonschema` (R) but Hutch's active path is a bounded custom validator, not `jsonschema` | High: canonical refusal messages and unsupported-keyword semantics must be reproduced | **No.** Once per tool call, small arguments; hundreds of microseconds at most against a 0.25 ms step | Actual per-call cost and worst-case argument size; whether `jsonschema` is even installed |
| Streaming tool-call JSON assembly | `src/hutch/toolcalling/streamassembly.py:60 OpenAIChatStreamAssembler` | No published benchmark for fragmented tool-call argument assembly; unverified | High: per-delta boundary traffic; tiny chunks amplify call overhead | **Unlikely**, but it is the only per-token CPU path; worth profiling during long streams | Share of step CPU during a long streaming turn; count/s of deltas per turn |
| SQLite row marshalling | `src/hutch/store.py:8696 append_event`, `:8955 list_events` | None published; both wrap C SQLite (U for speedup) | High: rows become Python dataclasses; conversion moves rather than disappears | **No** on current evidence; store is measured at ~52k inserts/s | Row -> object cost share; larger batch/columnar alternatives |
| Token estimation / prompt sizing | `src/hutch/context.py:29 estimate_tokens`, `:56 prompt_tokens`; `runtime/fitloop.py:98 count_tokens` | Pure Python char counting/JSON dumps; a faster scan is plausible but total is sub-millisecond | Low; strings copied | **No.** Sub-ms operation, no user-visible latency path | Cost on largest realistic prompt; algorithmic alternative (incremental counts, avoid repeated dumps) |
| Document generation | `src/hutch/documents/docgen/{xlsx,docxgen,pptx,pdfdoc}.py` | Pure-Python cell/XML construction, large CPU work, no model wait; no published cross-language benchmark for these generators | Medium-high: workbook/document object model is large, boundary is the whole document | **Genuinely possible** on document-generation p95, but a Rust rewrite is large and duplicative | Wall time per document at realistic sizes; share of end-to-end generation; generateXML/zip cost split |
| Workspace discovery | `src/hutch/tools/files.py` list tool (os.walk) | Syscall-bound; no published evidence that Rust traversal beats os.scandir meaningfully | Low if batched, high if per-entry callbacks | **No** | Entry count x depth; scandir vs walk cost; ignore rules |
| HTTP/SSE framing | `sse.py:37`, uvicorn stack | Transport already native (uvicorn standard extra) (E) | N/A | **No** | Only the JSON payload cost (row 1) |
| CLI cold start / orchestration loop | `src/hutch/cli.py`, control plane | ADR-0001: control plane 0.24 ms/step, 41-66 MB idle; model latency dominates (E, repo measurement) | A Rust CLI is a second executor | **No**, and pre-rejected by ADR-0001/0016 | Nothing; lazy imports are the existing fix (275 ms status already) |

**Provisional verdict for Phase 2.** The shortlist that deserves measurement is: (1) event/snapshot JSON
serialisation at dashboard scale, (2) document generation, and (3) streaming assembly as a profiling
target that likely resolves to a Python algorithm fix. Everything else is either measured to be
sub-millisecond, already native, or has no call site. **No candidate currently has evidence that it can
clear the P11 bar end-to-end without a measurement that does not yet exist.**

---

## 7. Explicit do-not-migrate list

| Do not migrate | Reason |
|---|---|
| Orchestration/step loop/control plane | ADR-0001 option D rejected with measured evidence (0.24 ms/step, 41-66 MB idle); ADR-0016 keeps the supervisor in Python; requirements.md lists a Rust rewrite as out of scope |
| Process supervisor, cancellation, descendant accounting | ADR-0016; existing pidfd/process-group design is correctness-critical; a future Rust path limited to spawn/supervise/capture/report is allowed only after a measured gap |
| Approval/scheduling/persistence policy | ADR-0016: these stay in Python regardless of any Rust helper |
| SQLite store and migrations | ADR-0001 single coordinator; batch/group-commit evidence already positive; no external evidence of a gain |
| HTTP/ASGI layer and SSE framing | uvicorn uses native parsers/event loop already; framing is trivial |
| Auth, approval, redaction, security middleware | Correctness/security boundary; no performance evidence and high risk |
| Tool-call validation semantics | Canonical contract; a fourth validator risks divergence for an unmeasurable per-step gain |
| Token estimation | Sub-millisecond pure-Python arithmetic; algorithmic fix suffices |
| Text diff | No call site in `src/hutch`; new functionality, out of scope |
| Workspace `os.walk` | Syscall/I/O bound; no published evidence of a meaningful win |
| Prompt/provider request construction | Network and model latency dominate by 3-5 orders of magnitude |
| Full or dashboard-wide Rust rewrite | requirements.md out of scope; no per-operation justification |

---

## 8. The exact measurement protocol for accepting or rejecting a Rust kernel

1. **Name the operation and its call frequency.** One sentence each: `file:symbol`, input shapes and
   sizes, calls per step and per session. Compute the theoretical ceiling:
   `max_saving_per_step = per_op_cost x calls_per_step`. If that ceiling is below the absolute floor
   (proposed 1 ms per step), stop: no end-to-end claim is possible and the candidate can only be
   justified as an operation-level win with an explicit "no user-visible effect" statement.
2. **Pre-register the threshold before measuring.** Accept only if the measured operation (including
   Python <-> Rust conversion, call overhead and any copying) improves p95 by >=20%, or memory by >=30%,
   matching P11. Report the end-to-end delta separately and honestly; operation-level success with no
   end-to-end effect is allowed only with that sentence written down.
3. **Build the harness on isolated state.** Fresh state dir per run (`HUTCH_HOME`), `/dev/shm` for SQLite
   throughput, deterministic fixture, no live provider, no real credentials. Record machine metadata,
   `/proc/loadavg`, and the other-agent-process state.
4. **Measure the noise floor first.** Run the Python reference 11 times; record min, median, p95, max and
   the coefficient of variation. Estimate the minimum detectable effect (for example twice the half-width
   of the run-to-run interval). If the candidate's expected effect is below that, the comparison is
   undecidable on this machine and must not be reported as a rejection either.
5. **Measure the Python operation directly**, with `pyperf` for in-process work (n >= 200 samples for a p95)
   and `hyperfine` for cold-process work (>=10 runs plus warmup, report min/median).
6. **Measure the Rust implementation at the same operation boundary.** Criterion is acceptable for the
   Rust-internal cost only; the decision number must come from a Python driver timing
   `operation(args)` for both implementations in the same process shape, including conversion. Interleave
   A/B/A/B in one session.
7. **Count the boundary.** Record payload sizes, number of boundary crossings per operation, and peak RSS
   (VmHWM) plus `tracemalloc` for the Python side. A memory win must include the extension's own
   residency (a Rust extension adds a few MB of mapped code and allocator arenas).
8. **Prove behavioural equivalence before believing the benchmark.** Run the existing focused pytest for
   the touched behaviour against both paths; the pure-Python fallback stays the reference. For validation
   or serialisation, add an equality test over the full fixture corpus (same refusal text, same bytes).
9. **Re-run end-to-end after integration**: the P11-scale scenario (>=50 bots, >=10k events), a long
   multi-tool mock run, document generation, plus `python -m benchmarks.run --check`. A candidate that
   passes the microbenchmark but regresses the existing gate is rejected.
10. **Record and classify.** One JSON artifact per candidate under `docs/research/artifacts/perf-2026-10-29/`
    with command, n, min/median/p95/max, machine metadata, and a verdict field of
    `adopt / reject-unmeasured / reject-measured / defer`. Every number in docs/performance.md must be
    traceable to one of these artifacts; anything not measured is labelled unverified.
11. **Repeat the winning comparison on a second day.** Only then is it evidence rather than one session's
    noise.

### 8.1 Alignment with the repository harness (`benchmarks/hotpaths.py`)

The profiling workstream's harness (untracked at the time of writing) already records what section 8
asks for: per-case `n/min/median/mean/p95/max/stdev` via `summarize()`, machine identity
(`cpu`, `cores`, `python`, `platform`, `total_memory_mb`), `load_avg_1m_5m_15m`, git head and a dirty
flag, and a harness SHA-256 (`machine()`, `benchmarks/hotpaths.py:110`). Its `FULL_SAMPLES = 7` means
the reported `p95` is effectively the sample maximum: with n=7 the linear-interpolated 95th percentile
sits at position 5.7 of 0..6, so it is dominated by the largest observation. For a P11 accept/reject
decision, either raise samples for the deciding case or label the field `p95(n=7)` and treat it as a
max; do not compare two 7-sample "p95" values as if they were tail estimates. The two-process A/B
requirement in step 6 (same Python driver, both implementations) is not satisfied by the current harness
and must be added for a Rust candidate.

---

## 9. Open questions and claims that remain unverified

- No candidate has been measured on Hutch's hardware in this phase; every ratio above is external.
- The jsonschema-rs table is a maintainer-run benchmark with single numbers per cell; the actual Hutch
  validator path (bounded validator + optional jsonschema) was not benchmarked.
- The orjson 10x serialisation claim is a vendor statement; the independent suite retrieved only load
  benchmarks in the tables above.
- There is no published benchmark for fragmented streaming tool-call JSON assembly, SQLite row
  marshalling, or Hutch-style SSE bursts; those claims must be generated locally or left unverified.
- Whether any candidate can clear the P11 bar end-to-end remains open (charter Q1) and is answered only
  by the protocol in section 8.
- Python 3.14 lists `difflib` among its optimisations (What's new in 3.14, accessed 2026-10-29); the
  magnitude was not researched because Hutch has no diff call site and targets 3.11+.

---

## 10. Source ledger

External sources, all accessed 2026-10-29 unless a publication date is given.

| # | Source | URL | Date | Grade |
|---|---|---|---|---|
| 1 | PyO3 guide, Features reference | https://pyo3.rs/main/features | accessed 2026-10-29 | E |
| 2 | PyO3 guide, Building and distribution | https://pyo3.rs/main/building-and-distribution | accessed 2026-10-29 | E |
| 3 | PyO3 guide, Supporting Free-Threaded CPython | https://pyo3.rs/v0.29.2/free-threading | accessed 2026-10-29 | E |
| 4 | maturin guide, Bindings (abi3/abi3t) | https://www.maturin.rs/bindings.html | accessed 2026-10-29 | E |
| 5 | PyO3 issue #3827, calling overhead | https://github.com/PyO3/pyo3/issues/3827 | created 2024-02-11 | R |
| 6 | jsonschema-rs Python benchmark suite | https://github.com/stranger6667/jsonschema/blob/339325524bf2618013b2cab1e4d4629e70c83b0b/crates/jsonschema-py/BENCHMARKS.md | accessed 2026-10-29; harness states Python 3.14.0 / Rust 1.96.1 | R |
| 7 | orjson README | https://github.com/ijl/orjson | accessed 2026-10-29 | U (magnitudes) |
| 8 | TkTech json_benchmark (Python JSON readers/writers, streaming) | https://github.com/TkTech/json_benchmark | tables regenerated 2026-07-13 | R |
| 9 | Perry JSON polyglot benchmark (serde_json vs simdjson) | https://github.com/PerryTS/perry/blob/v0.5.1158/benchmarks/json_polyglot/RESULTS.md | 2026-05-14 | R (self-interested) |
| 10 | similar crate (diff algorithms, benchmarks, fuzzer) | https://github.com/mitsuhiko/similar | accessed 2026-10-29 | E (harness) |
| 11 | CPython issue #106865 (difflib performance warning) | https://github.com/python/cpython/issues/106865 | created 2023-07-18 | R |
| 12 | CPython `Modules/_json.c` (stdlib JSON is C) | https://github.com/python/cpython/blob/main/Modules/_json.c | accessed 2026-10-29 | E |
| 13 | Python docs, What's new in 3.14 (free-threading officially supported) | https://docs.python.org/3/whatsnew/3.14.html | 3.14 released 2025-10-07 | E |
| 14 | Python docs, Python support for free threading (1-8% overhead) | https://docs.python.org/3/howto/free-threading-python.html | accessed 2026-10-29 | E |
| 15 | PEP 703 | https://peps.python.org/pep-0703/ | 2023 | E |
| 16 | uvicorn README (uvloop/httptools native) | https://github.com/Kludex/uvicorn | accessed 2026-10-29 | E |
| 17 | Python docs, sqlite3 | https://docs.python.org/3/library/sqlite3.html | accessed 2026-10-29 | E |
| 18 | rusqlite docs | https://docs.rs/rusqlite/latest/rusqlite/ | accessed 2026-10-29 | E |
| 19 | pydantic performance tips | https://docs.pydantic.dev/latest/concepts/performance/ | accessed 2026-10-29 | E |
| 20 | Brendan Gregg, Active Benchmarking | https://www.brendangregg.com/activebenchmarking.html | accessed 2026-10-29 | E |
| 21 | Criterion.rs, Analysis Process | https://bheisler.github.io/criterion.rs/book/analysis.html | accessed 2026-10-29 | E |
| 22 | pyperf documentation | https://pyperf.readthedocs.io/en/latest/ | accessed 2026-10-29 | E |
| 23 | hyperfine README | https://github.com/sharkdp/hyperfine | accessed 2026-10-29 | E |
| 24 | cline PR #14092 (streaming event amplification) | https://github.com/cline/cline/pull/14092 | 2026-09-13 | R |
| 25 | opencode issue #60305 (quadratic LCS memory in edit) | https://github.com/anomalyco/opencode/issues/60305 | 2026-10-29 | R |
| 26 | opencode issue #59678 (SSE drop, renderer fatal) | https://github.com/anomalyco/opencode/issues/59678 | 2026-10-27 | R |
| 27 | opencode issue #60005 (event stream retries port 0) | https://github.com/anomalyco/opencode/issues/60005 | 2026-10-28 | R |
| 28 | OpenClaw issue #150634 (retry storm, slow perceived streaming) | https://github.com/openclaw/openclaw/issues/150634 | 2026-09-17 | R |
| 29 | OpenClaw issue #138499 (timed-out cron task left running) | https://github.com/openclaw/openclaw/issues/138499 | 2026-09-04 | R |
| 30 | n8n issue #37342 (off-heap memory growth in queue mode) | https://github.com/n8n-io/n8n/issues/37342 | 2026-08-28 | R |
| 31 | Continue issue #12053 (UI slow in long conversations) | https://github.com/continuedev/continue/issues/12053 | 2026-04-06 | R |
| 32 | Letta issue #2425 (thousands of messages block server) | https://github.com/letta-ai/letta/issues/2425 | 2025-02-09 | R |
| 33 | LangGraph issue #9078 (orphan runs, TTL stub) | https://github.com/langchain-ai/langgraph/issues/9078 | 2026-09-25 | R |
| 34 | ZeroClaw issue #10780 (context compaction removed) | https://github.com/zeroclaw-labs/zeroclaw/issues/10780 | 2026-09-11 | R |

Repository sources: [ADR-0001](../adr/0001-control-plane-and-owned-execution.md),
[ADR-0016](../adr/0016-rust-process-supervisor-deferred.md),
[ADR-0020](../adr/0020-canonical-opencode-tools-and-desktop-host.md),
[ADR-0022](../adr/0022-host-platform-adapters.md),
[docs/performance.md](../performance.md), [docs/requirements.md](../requirements.md),
[docs/realignment/desktop-production-2026-10-26.md](../realignment/desktop-production-2026-10-26.md),
[complaints.md](complaints.md), [offerings-and-failures.md](offerings-and-failures.md).
