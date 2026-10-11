# Typed output blocks — the lanes' contract (2026-10-10)

This is the API other lanes code against. Implementation: `src/hutch/outputblocks.py`
(validated by `tests/test_outputblocks.py`), plumbing in `runtime.steps.call_tool`
(`tests/test_steps_blocks.py`), storage in schema v51 (`tests/test_outputs_store.py`).
Golden fixtures: `tests/fixtures/blocks/*.json`. Failure research behind every rule:
`docs/research/outputs-failures-2026-10-10.md`.

The one-paragraph version: **a tool that wants to present something rich puts raw block
dicts on `ToolResult.data["blocks"]`; `call_tool` validates them once, puts canonical
serialized dicts on the `tool_result` event under `data["blocks"]` plus labeled rejections
under `data["block_errors"]`, and the model sees only a one-line `[presented: …]` summary.
Message prose and model-facing tool text are never parsed for blocks — that code path does
not exist and tests pin its absence.**

---

## 1. Event placement (exact)

For a tool call `name` that returned `ToolResult(ok, output, data)` where `data` contains a
`"blocks"` key, the emitted `tool_result` event carries:

```jsonc
{
  "tool": "<name>",
  "ok": true,
  "output": "<first 2000 chars of (model output + the one-line summary)>",
  // ...artifact/workspace_file/document/simulated keys as today...
  "blocks":  [ <block>, <block>, ... ],   // canonical serialized dicts, see §2
  "block_errors": [ {"id"?: str, "kind"?: str, "error": str}, ... ]  // only when non-empty
}
```

Rules:

- `data["blocks"]` is present on the event **whenever the tool supplied a `blocks` key** —
  including an empty list. `data["block_errors"]` is present only when something was
  rejected (never `null`, never an empty array).
- Each `blocks` entry is a JSON-ready dict (pydantic `model_dump(mode="json",
  by_alias=True, exclude_none=True)`): `json.dumps(entry, separators=(",", ":"))` round-trips
  losslessly. Optional fields are **absent**, never `null`. Entry order preserves the
  tool's list order; budget-rejected blocks are dropped from `blocks` and reported in
  `block_errors`.
- The model-facing `result.output` is the tool's own (truncated) output with **at most one
  appended line**: `[presented: chart blk_4d5e6f7a8b9c0d1e, table blk_3c4d5e6f7a8b9c0d]` —
  or `[presented: none — N output block(s) failed validation]` when nothing survived. Block
  JSON never enters model text. Frontend consumers should treat `data["output"]` as
  model-visible commentary and render `data["blocks"]` as the actual presentation.
- If the tool's `blocks` value is not a list, that is one `block_errors` entry — never an
  exception, never silence.
- **Message events and reasoning text are never scanned.** There is no prose→blocks path.
  `tests/test_steps_blocks.py::test_message_prose_is_never_parsed_for_blocks` and
  `::test_tool_output_text_containing_block_json_is_never_parsed` pin this.

The summary line is built by `runtime/steps.py::_blocks_summary`; validation by
`outputblocks.parse_blocks`, which never raises.

## 2. Envelope (every block)

```jsonc
{
  "v": 1,                     // BLOCK_SCHEMA_VERSION; other values → labeled error
  "id": "blk_xxxxxxxxxxxxxxxx",   // 'blk_' + 16 lowercase hex
  "kind": "<one of §3>",
  "revision": 1,              // int >= 1
  "availability": "ready",    // 'ready' | 'pending' | 'failed' | 'revoked' | 'stale'
  "text_fallback": "…",       // REQUIRED, non-blank, <= 4000 chars — the readable
                              // alternative that MUST be shown if the rich render fails
  "provenance": { "run_id": "…", "tool": "…", "job_id"?: "…" },  // run_id/tool required
  "payload": { … }            // kind-specific, §3
}
```

Validation is pydantic v2 **strict** with `extra="forbid"` everywhere: wrong JSON types
(string for int, bool for int), unknown fields, and kind/payload mismatches are all
rejections with labeled errors. `code_receipt.source_sha256` must equal
`sha256(source)`. `flowchart` edges may cycle but may not dangle. `comparison` cells carry
exactly one of `value`/`state` and must reference declared item/criterion ids.

## 3. One example per kind (verbatim from tests/fixtures/blocks/*.json)

### text — `text.json`

```json
{"v": 1, "id": "blk_1a2b3c4d5e6f7a8b", "kind": "text", "revision": 1, "availability": "ready",
 "text_fallback": "The quick analysis found 42 answers and 3 caveats; details below.",
 "provenance": {"run_id": "run_0f1e2d3c4b5a6978", "tool": "shell"},
 "payload": {"content": "The analysis produced 42 answers. Three caveats apply: sampling bias, a two-second warmup, and one unresolved outlier."}}
```

### code_receipt — `code_receipt.json` (display source of truth, hash-bound)

```json
{"v": 1, "id": "blk_2b3c4d5e6f7a8b9c", "kind": "code_receipt", "revision": 1, "availability": "ready",
 "text_fallback": "Ran 2 lines of Python; it printed 'the answer is 42' and returned None.",
 "provenance": {"run_id": "run_0f1e2d3c4b5a6978", "tool": "shell"},
 "payload": {"source": "total = 40 + 2\nprint(f\"the answer is {total}\")\n",
             "language": "python",
             "source_sha256": "d91b3d89e2c88673abe67f53b6e2daec824e3d39aac7a96fa6b3525a1a2abe1b",
             "execution": {"ordinal": 1, "environment_generation": 3,
                           "started_at": "2026-10-10T12:00:00+00:00", "finished_at": "2026-10-10T12:00:01+00:00",
                           "status": "ok", "stdout_chars_total": 18, "stderr_chars_total": 0},
             "stdout_tail": "the answer is 42\n", "stderr_tail": "", "result_repr": "None",
             "produced_files": [{"name": "answer.txt", "sha256": "cc…cc", "bytes": 18}]}}
```

### table — `table.json`

```json
{"v": 1, "id": "blk_3c4d5e6f7a8b9c0d", "kind": "table", "revision": 1, "availability": "ready",
 "text_fallback": "Five cities previewed of eight; Lisbon is largest at 545,000.",
 "provenance": {"run_id": "run_0f1e2d3c4b5a6978", "tool": "shell"},
 "payload": {"columns": [{"name": "city", "dtype": "text"}, {"name": "population", "dtype": "number"}],
             "rows": [["Lisbon", 545000], ["Porto", 231000]], "row_total": 8,
             "truncation": {"omitted_rows": 6, "reason": "preview shows the two largest of eight cities"},
             "notes": "Population figures are 2021 census estimates."}}
```

### chart — `chart.json`

```json
{"v": 1, "id": "blk_4d5e6f7a8b9c0d1e", "kind": "chart", "revision": 1, "availability": "ready",
 "text_fallback": "Line chart: requests per second climbing from 0 to 30 over two seconds.",
 "provenance": {"run_id": "run_0f1e2d3c4b5a6978", "tool": "shell"},
 "payload": {"kind": "line",
             "series": [{"label": "requests/s", "points": [[0, 0], [1, 12], [2, 30]]}],
             "x": {"label": "elapsed", "unit": "s", "scale": "linear"},
             "y": {"label": "requests", "scale": "linear"},
             "source": "executed", "dataset_ref": "artifacts/001-shell.txt",
             "notes": "Sampled once per second during the load run."}}
```

### flowchart — `flowchart.json` (note the `"from"` key; cycles are valid)

```json
{"v": 1, "id": "blk_5e6f7a8b9c0d1e2f", "kind": "flowchart", "revision": 1, "availability": "ready",
 "text_fallback": "Flow: collect input -> validate -> store, with validation failures looping back.",
 "provenance": {"run_id": "run_0f1e2d3c4b5a6978", "tool": "shell"},
 "payload": {"nodes": [{"id": "collect", "label": "Collect input", "group": "ingest"},
                       {"id": "validate", "label": "Validate", "group": "ingest", "detail": "Rejects non-ASCII filenames"},
                       {"id": "store", "label": "Store"}],
             "edges": [{"from": "collect", "to": "validate"},
                       {"from": "validate", "to": "store", "label": "on success"},
                       {"from": "validate", "to": "collect", "label": "on rejection"}],
             "direction": "LR",
             "assumptions_note": "Ordering assumes the approval gate grants every write."}}
```

### timeline — `timeline.json`

```json
{"v": 1, "id": "blk_6f7a8b9c0d1e2f3a", "kind": "timeline", "revision": 1, "availability": "ready",
 "text_fallback": "Confirmed: request at 09:00 UTC; planned: deploy on 2026-10-11.",
 "provenance": {"run_id": "run_0f1e2d3c4b5a6978", "tool": "shell"},
 "payload": {"events": [
     {"id": "e1", "label": "Request received",
      "when": {"iso8601": "2026-10-10T09:00:00+00:00", "precision": "second", "timezone": "UTC"},
      "state": "confirmed", "source": "server log"},
     {"id": "e2", "label": "Planned deploy", "when": {"iso8601": "2026-10-11", "precision": "day"},
      "state": "planned"}]}}
```

### comparison — `comparison.json` (value XOR state per cell)

```json
{"v": 1, "id": "blk_7a8b9c0d1e2f3a4b", "kind": "comparison", "revision": 1, "availability": "ready",
 "text_fallback": "Local shell beats the cloud notebook on cost; the notebook cannot work offline.",
 "provenance": {"run_id": "run_0f1e2d3c4b5a6978", "tool": "shell"},
 "payload": {"items": [{"id": "local", "label": "Local shell"}, {"id": "cloud", "label": "Cloud notebook"}],
             "criteria": [{"id": "cost", "label": "Monthly cost", "unit": "USD"},
                          {"id": "offline", "label": "Works offline"}],
             "cells": [{"item": "local", "criterion": "cost", "value": "0", "citations": "hutch pricing doc"},
                       {"item": "cloud", "criterion": "cost", "value": "120"},
                       {"item": "local", "criterion": "offline", "value": "yes"},
                       {"item": "cloud", "criterion": "offline", "state": "unsupported"}],
             "ranking_note": "The local shell wins on both criteria for this user."}}
```

### media — `media.json` (alt_text required; the bytes live in the media store a later lane owns)

```json
{"v": 1, "id": "blk_8b9c0d1e2f3a4b5c", "kind": "media", "revision": 1, "availability": "ready",
 "text_fallback": "PNG image: bar chart of requests per second during the load test.",
 "provenance": {"run_id": "run_0f1e2d3c4b5a6978", "tool": "shell"},
 "payload": {"media_id": "media_0f1e2d3c4b5a6978", "version": 1,
             "sha256": "dd…dd", "mime": "image/png", "kind": "image",
             "alt_text": "Bar chart of requests per second climbing from 0 to 30 across a two-second load test.",
             "poster": {"media_id": "media_0f1e2d3c4b5a6979", "version": 1},
             "width": 800, "height": 600, "backend": "matplotlib", "generated_by": "deterministic"}}
```

### artifact_ref — `artifact_ref.json` (points at a documents-store version)

```json
{"v": 1, "id": "blk_9c0d1e2f3a4b5c6d", "kind": "artifact_ref", "revision": 1, "availability": "ready",
 "text_fallback": "Document: quarterly-report.pdf, version 2, 148,233 bytes.",
 "provenance": {"run_id": "run_0f1e2d3c4b5a6978", "tool": "shell"},
 "payload": {"ref_kind": "document", "id": "doc_0f1e2d3c4b5a6978", "version": 2,
             "name": "quarterly-report.pdf", "mime": "application/pdf", "bytes": 148233,
             "sha256": "ee…ee"}}
```

(`ee…ee` stands for the 64-hex digest in the fixture.)

### status — `status.json`

```json
{"v": 1, "id": "blk_0d1e2f3a4b5c6d7e", "kind": "status", "revision": 1, "availability": "ready",
 "text_fallback": "Rendering: chart 2 of 3 is in progress.",
 "provenance": {"run_id": "run_0f1e2d3c4b5a6978", "tool": "shell"},
 "payload": {"stage": "render", "detail": "Chart 2 of 3 is rendering.", "state": "running"}}
```

### invalid — `invalid.json` (must yield exactly one labeled error, zero blocks)

```json
{"v": 1, "id": "blk_NOT-VALID", "kind": "chart", "revision": 0, "availability": "weird",
 "provenance": {"run_id": "run_x", "tool": "shell"}, "payload": {"kind": "bar"}}
```

## 4. Bounds table (all enforced at parse; violations → labeled error entries)

| Where | Bound |
|---|---|
| Result level | ≤ `MAX_BLOCKS_PER_RESULT = 24` blocks; ≤ `MAX_BLOCK_JSON_CHARS = 256_000` compact-JSON chars **total** across serialized blocks; ≤ 96 input entries examined per call |
| Envelope | `text_fallback` 1–4000 chars (non-blank); `revision` ≥ 1; `id` = `blk_` + 16 lowercase hex |
| `provenance` | `run_id`, `tool`, `job_id?` each 1–128 chars |
| `text.content` | 1–20 000 chars |
| `code_receipt` | `source` 1–100 000 chars; `language` 1–40 (default `"python"`); `source_sha256` 64-hex == sha256(source); `execution.ordinal` ≥ 1; `execution.environment_generation` ≥ 1; `started_at`/`finished_at` 1–64 chars; `status` ∈ ok/error/timeout/cancelled/interrupt_unconfirmed; `stdout_chars_total`, `stderr_chars_total` ≥ 0; `stdout_tail`, `stderr_tail` ≤ 4000; `result_repr` ≤ 2000; ≤ 32 produced files `{name 1–200, sha256 64-hex, bytes ≥ 0}` |
| `table` | ≤ 64 columns `{name 1–200, dtype ∈ text/number/boolean/date/unknown (default unknown)}`; ≤ 500 rows (preview only), cells are JSON scalars (strings ≤ 2000); `row_total` ≥ 0 **and** ≥ len(rows); `truncation?` `{omitted_rows ≥ 0, reason 1–200}`; `notes?` ≤ 1000 |
| `chart` | `kind` ∈ line/bar/scatter/area; 1–8 series `{label 1–120, ≤ 2000 points}`; each point a 2-element `[number, number]`; axes `{label 1–200, unit? 1–40, scale ∈ linear/log/time}`; `source` ∈ executed/deterministic/estimated; `dataset_ref?` 1–200; `notes?` ≤ 500 |
| `flowchart` | ≤ 64 nodes `{id [A-Za-z0-9_-]{1,64}, label 1–200, group? 1–120, detail? ≤ 2000}`; ≤ 128 edges `{from, to, label? 1–120}`; endpoints must reference declared nodes; **cycles valid, dangles invalid**; `direction` ∈ LR/TB; `assumptions_note?` ≤ 1000 |
| `timeline` | ≤ 200 events `{id 1–64, label 1–200, when {iso8601 parseable, ≤ 40 chars, precision ∈ year/month/day/hour/minute/second, timezone? ≤ 64}, state ∈ reported/confirmed/planned/corrected, source? ≤ 300, corrected_from? ≤ 64}` |
| `comparison` | ≤ 24 items `{id 1–64, label 1–200}`; ≤ 24 criteria `{+ unit? 1–40}`; ≤ 576 cells `{item, criterion must reference declared ids; exactly one of value (1–300) or state ∈ unknown/not_applicable/unsupported; citations? ≤ 300}`; `ranking_note?` ≤ 500 |
| `media` | `media_id` = `media_` + 16 lowercase hex; `version` ≥ 1; `sha256` 64-hex; `mime` ∈ image/png, image/jpeg, image/webp, image/svg+xml, video/webm, video/mp4, audio/wav; `kind` ∈ image/video/animation/audio; **`alt_text` required**, non-blank, ≤ 600; `poster?`/`captions?` `{media_id, version ≥ 1}`; `duration_seconds?` ≥ 0 (finite); `width?`/`height?` ≥ 1; `backend` 1–64; `generated_by` ∈ deterministic/provider. (mime↔kind cross-consistency is deliberately not enforced.) |
| `artifact_ref` | `ref_kind` ∈ document/media; `id` = (`doc_`|`media_`) + 16 lowercase hex, **prefix must match ref_kind**; `version` ≥ 1; `name` 1–200; `mime` 1–128 (any string); `bytes` ≥ 0; `sha256` 64-hex |
| `status` | `stage` 1–64; `detail` ≤ 2000; `state` ∈ pending/running/final/failed/cancelled/stale/blocked/unknown |
| Error entries | Bounded by `MAX_BLOCKS_PER_RESULT` per call + one suppression-count entry; entries beyond input-entry cap collapse into one aggregate entry |

## 5. Unknown kinds / versions / bad blocks: labeled fallback, never a crash

`parse_blocks(value) -> tuple[list[dict], list[dict]]` **never raises**. For each entry:

- unknown `kind` → error entry `{"id": …, "kind": "slideshow", "error": "unknown block kind
  'slideshow'; known kinds: …"}`;
- unknown/missing `v` → error entry naming the version problem;
- schema violations → error entry whose `error` names the offending field(s);
- non-object entries and non-list inputs → error entries.

**Frontend lanes must render every `block_errors` entry as a visible labeled fallback chip
(with the kind if present), and render every valid block from `text_fallback` first if its
rich render fails.** Losing the diagnostic or the content is the one thing this contract
exists to make impossible (see `outputs-failures-2026-10-10.md` A.4).

Python API:

```python
from hutch.outputblocks import (BLOCK_SCHEMA_VERSION, MAX_BLOCKS_PER_RESULT,
                                MAX_BLOCK_JSON_CHARS, KNOWN_BLOCK_KINDS, OutputBlock,
                                parse_blocks, serialize_block, new_block_id, new_media_id,
                                block_json_chars)
blocks, errors = parse_blocks(value)   # value: Any; never raises
serialize_block(OutputBlock)           # -> canonical JSON-ready dict
```

## 6. Schema v51 storage — Store accessors (lanes call these; do not touch store.py)

Tables (`_migrate_51`, `src/hutch/store.py:1339`): `uploads`, `media_jobs`,
`workspace_sessions` — CHECK-constrained enumerated columns, `media_jobs.idempotency_key`
UNIQUE, indexed on `conversation_id` (uploads) and `run_id`/`conversation_id` (media_jobs).

Signatures (all on `Store`; reads return plain dicts):

```python
add_upload(conversation_id: str, filename: str, mime: str, byte_size: int, sha256: str, *,
           upload_id: str | None = None,          # default: "upl_" + 16 hex
           state: str = "ready",                  # ready|quarantined|expired|deleted
           created_at: str | None = None) -> dict
uploads_for_conversation(conversation_id: str, *, limit: int = 50) -> list[dict]   # newest first
get_upload(upload_id: str) -> dict | None
mark_upload_state(upload_id: str, state: str) -> dict       # ValueError on unknown state, KeyError if missing

create_media_job(*, run_id: str, conversation_id: str, kind: str, backend: str,
                 idempotency_key: str, requested: dict,
                 job_id: str | None = None,                 # default: "mj_" + 16 hex
                 created_at: str | None = None) -> dict     # starts 'queued';
                                                            # IdempotencyConflict on reused key
record_upstream_job(job_id: str, upstream_job_id: str, *, updated_at: str | None = None) -> dict
transition_media_job(job_id: str, to_status: str, *, result: dict | None = None,
                     error: str | None = None, cost_note: str | None = None,
                     updated_at: str | None = None) -> dict
#   guarded: queued→running|failed|cancelled; running→succeeded|failed|cancelled; terminal.
#   ValueError on illegal/unknown, KeyError on missing job.
get_media_job(job_id: str) -> dict | None                   # 'requested'/'result' parsed to dicts
media_jobs_for_run(run_id: str, *, limit: int = 100) -> list[dict]  # oldest first

upsert_workspace_session(conversation_id: str, generation: int, workspace_dir: str, *,
                         status: str = "active",            # active|expired|terminated
                         env_fingerprint: str | None = None,
                         created_at: str | None = None, updated_at: str | None = None) -> dict
get_workspace_session(conversation_id: str) -> dict | None
transition_workspace_session(conversation_id: str, to_status: str, *,
                             expected_generation: int,
                             updated_at: str | None = None) -> dict
#   optimistic concurrency: stale generation → RevisionConflict; illegal transition →
#   ValueError; missing → KeyError. active→expired|terminated; expired→active|terminated;
#   terminated is terminal. Generation itself changes only via upsert.
```

The schema-downgrade test helper (`_remove_later_conversation_schema` in
`tests/test_delegation.py`) knows the v51 tables/indexes, mirroring c9dd168's v50 change;
`SCHEMA_VERSION` is 51 (`tests/test_outputs_store.py::test_schema_version_is_51`).
