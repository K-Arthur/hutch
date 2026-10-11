# Typed conversation outputs — failure research and text-to-output audit (2026-10-10)

Foundation-slice research for the typed output-block contract (`src/hutch/outputblocks.py`,
schema v54). Part A is an evidence ledger of first-hand failure reports in other apps that
this feature must not repeat; part B audits Hutch's current text-to-output path with
`path:line` findings.

**Method.** Every external row below was re-verified first-hand on 2026-10-10 by fetching
the issue page (WebFetch) and quoting the report. Web search was **not** rate-limited, but
additional searches for further first-hand reports returned only secondary/SEO write-ups or
issue-list pages without a specific verifiable thread (details under "Known class" below);
no invented citations are included.

---

## Part A — evidence ledger

### A.1 ComfyUI #6888 — previews leak across browser tabs (node-ID-only keying)

| Field | Value |
|---|---|
| Source + URL | Comfy-Org/ComfyUI issue #6888 — https://github.com/Comfy-Org/ComfyUI/issues/6888 |
| Date | Opened 2025-02-20; closed 2025-02-21 as duplicate of ComfyUI_frontend #2660 ("Belongs to UI project") |
| App + version | ComfyUI 0.3.14, frontend 1.8.14, Chrome 133, Win 11 (custom nodes disabled) |
| Reported vs confirmed | Reported with a concrete reproduction (queue a workflow in one tab; a second tab holding a copy with the same node IDs updates its Preview Image and KSampler progress too). **Reporter-suspected** root cause, quoted: "communication is simply based on Node Id as the unique client-server message identifier, whereas it should probably be 'Browser Tab Session Id - ComfyUI Workspace Tab - Node Id'". No maintainer analysis in the thread; label "Potential Bug" only — so: reported, reproduced by reporter, root cause not officially confirmed. |
| Resolution | Closed as duplicate of ComfyUI_frontend #2660; no fix recorded in this thread. |
| Hutch applicability | High. Any rich preview keyed only by node/tool identity will cross-contaminate sessions; Hutch runs are already the unit of isolation, and blocks must be bound to their producing run, not to "the chart for tool X". |
| Design response in this codebase | Every block envelope carries `provenance {run_id, tool, job_id?}` (`src/hutch/outputblocks.py:84`, `BlockProvenance`), and blocks travel only on the `tool_result` event of the run that produced them (`src/hutch/runtime/steps.py:286-296`). Nothing keys a preview by tool name alone. |
| Regression test | T-OUTPUTS-5 — `tests/test_outputblocks.py::test_block_budget_keeps_the_first_24_and_reports_the_rest` + provenance shape coverage in the fixture round-trip tests; event placement pinned by `tests/test_steps_blocks.py::test_valid_blocks_pass_onto_the_event_and_not_into_the_model_text`. |

### A.2 ComfyUI #9393 — WebSocket notifications stop flowing while work completes

| Field | Value |
|---|---|
| Source + URL | Comfy-Org/ComfyUI issue #9393 — https://github.com/Comfy-Org/ComfyUI/issues/9393 |
| Date | Opened 2025-08-18; **still open as of 2026-10-10** (labels: "Potential Bug", "bug-cop:response-received") |
| App + version | ComfyUI 0.3.43 (custom nodes disabled) |
| Reported vs confirmed | Reported by the author ("after running for some time (possibly more than 10 hours, the time is random), it becomes unable to receive WebSocket messages"); independently reproduced by a second user (2025-10-15) with a sharper trigger: **resubmitting an identical prompt (same seed)** yields only a status/sid message and no progress/executing events, while "the queue shows zero remaining" — the server completed the work; the client just never hears about it. Confirmed-by-reproduction, unresolved. |
| Resolution | Open; no fix or root-cause explanation in the thread as of verification date. |
| Hutch applicability | High, two ways. (a) Identical resubmits must be idempotent and observable, never silently deduplicated into "nothing happened". (b) A consumer that misses one notification must not wait forever. |
| Design response in this codebase | (a) `media_jobs.idempotency_key` is UNIQUE and `Store.create_media_job` raises `IdempotencyConflict` on reuse (`src/hutch/store.py:7546`, table DDL `src/hutch/store.py:1350-1376`), so a resubmit is refused loudly instead of duplicated silently. (b) Block results are carried as **data on the persisted `tool_result` event** (`src/hutch/runtime/steps.py:290-296`), not as fire-and-forget pushes; the transcript, not a socket, is the source of truth. (c) Result-level budgets (`MAX_BLOCKS_PER_RESULT`, `MAX_BLOCK_JSON_CHARS`) are enforced in `parse_blocks` (`src/hutch/outputblocks.py:47-50`) so a job cannot balloon a notification. |
| Regression test | T-OUTPUTS-6 — `tests/test_outputs_store.py::test_media_job_lifecycle_guards_and_idempotency` (duplicate idempotency_key raises); budget tests in `tests/test_outputblocks.py::test_block_budget_keeps_the_first_24_and_reports_the_rest`, `::test_json_char_budget_downgrades_overflow_to_an_error_entry`. |

### A.3 open-webui #27399 — artifact panel re-forces itself open on every streamed token

| Field | Value |
|---|---|
| Source + URL | open-webui/open-webui issue #27399 — https://github.com/open-webui/open-webui/issues/27399 |
| Date | Opened 2026-07-24; fixed 2026-07-26 (PR #27400, "Addressed in dev") |
| App + version | Open WebUI current dev at commit fe4b31942, "Detect Artifacts Automatically" enabled |
| Reported vs confirmed | Reported and **maintainer-confirmed** ("confirmed issue" label). The artifact side panel "reopens immediately (effectively on every token) until generation completes" while an html/svg code block streams, and shows the **stale previous artifact** the whole time. Root cause in the report: `markdownUpdateHandler` in `ContentRenderer.svelte` calls `showArtifacts.set(true)` on every matching streamed token "with no completion check"; the fix gates the handler on the component's `done` prop. |
| Resolution | Fixed 2026-07 by PR #27400. |
| Hutch applicability | High. Any per-token/per-chunk re-entry into presentation state duplicates and desynchronizes previews. Hutch's blocks are validated **once**, after a tool completes — never per streamed token — and the model-facing text is untouched by them. |
| Design response in this codebase | `call_tool` runs `parse_blocks` exactly once, after the tool has finished (`src/hutch/runtime/steps.py:286-296`); there is no streaming re-entry point and no setter a stream can flip. The frontend (a later lane) is specified to render blocks from the immutable event data (`docs/research/outputs-block-contract-2026-10-10.md`), not from live stream scraping. |
| Regression test | T-OUTPUTS-3 — `tests/test_steps_blocks.py::test_valid_blocks_pass_onto_the_event_and_not_into_the_model_text` (validation is post-completion, single-shot) and `::test_model_facing_text_is_unchanged_when_a_tool_has_no_blocks`. |

### A.4 open-webui #14541 — failed artifact render destroys the source and hides the error

| Field | Value |
|---|---|
| Source + URL | open-webui/open-webui issue #14541 — https://github.com/open-webui/open-webui/issues/14541 |
| Date | Opened 2025-05-31; closed (completed) 2025-11-21 by maintainer tjbck |
| App + version | Open WebUI 0.6.10 (Docker), Ollama 0.7.1, Firefox |
| Reported vs confirmed | Reported with a minimal reproduction (a `mermaid` code block containing "syntax error" → `UnknownDiagramError` in console). Actual behavior quoted: "the entire code block is removed and the text is printed as plain text" and "the error is not surfaced to the user anywhere." The reporter's expectation: "it should still render in a code block as a fallback, not as regular text", with the error shown too. Confirmed by reproduction; no maintainer analysis in the thread, closed as completed months later. |
| Resolution | Closed as completed 2025-11 (no fix commit cited in the thread content). |
| Hutch applicability | Critical. This is the canonical "fancy render fails → reader loses both the content and the diagnostic" failure. The block contract is designed so this is structurally impossible. |
| Design response in this codebase | (1) `text_fallback` is a REQUIRED, non-blank, ≤4000-char readable alternative on **every** block (`src/hutch/outputblocks.py:455-470`, validator at `:472-476`); a renderer that cannot draw a block always has the text. (2) One invalid block never sinks the others: `parse_blocks` returns valid blocks plus labeled `{id?, kind?, error}` entries and **never raises** (`src/hutch/outputblocks.py:568`); the errors are persisted on the event as `data["block_errors"]` (`src/hutch/runtime/steps.py:290-296`) so the diagnostic is data, not a console line. |
| Regression test | T-OUTPUTS-2 — `tests/test_outputblocks.py::test_text_fallback_is_required_and_must_be_readable`, `::test_unknown_kind_degrades_to_a_labeled_fallback_error`, `::test_the_invalid_fixture_is_rejected_with_one_labeled_error`; `tests/test_steps_blocks.py::test_one_bad_block_is_isolated_and_labeled`, `::test_blocks_key_present_even_when_everything_was_rejected`. |

### A.5 open-webui #14823 — displayed code garbles immediately after execution

| Field | Value |
|---|---|
| Source + URL | open-webui/open-webui issue #14823 — https://github.com/open-webui/open-webui/issues/14823 |
| Date | Opened 2025-06-10; fixed in dev by commit 21d616f; closed 2025-06-26 |
| App + version | Open WebUI v0.6.13 (pip), Ollama 0.9.0, Ubuntu 24.04; Code Interpreter on (Pyodide and Jupyter) |
| Reported vs confirmed | Reported with a screen recording: "The code is first generated correctly by the LM, but becomes malformed right after execution" — "Portions of lines become all mixed together". The reporter's own follow-up showed formatting was correct after a page reload or block re-expand, i.e. **the stored content was intact; the defect was client-side rendering during/after the run**. Confirmed by reproduction; fixed by maintainer. |
| Resolution | Fixed 2025-06 by commit 21d616f. |
| Hutch applicability | Critical for the code-execution lane. Whatever is *displayed* as "the code that ran" must be frozen at execution time and independent of any live client state. |
| Design response in this codebase | `code_receipt` is a receipt, not a view: `source_sha256` is validated against `sha256(source)` at parse time (`src/hutch/outputblocks.py:157-170`) and the contract states it is the hash of the **exact executed source** — the display source of truth. Post-execution edits cannot rewrite what ran, and a drifted pair is a labeled error, never a silent divergence. Execution evidence (`ordinal`, `environment_generation`, timestamps, status, tail bounds) rides in the same immutable payload (`src/hutch/outputblocks.py:131-155`). |
| Regression test | T-OUTPUTS-1 — `tests/test_outputblocks.py::test_code_receipt_hash_binding_rejects_a_drifted_source`, `::test_code_receipt_over_100k_chars_is_rejected`; fixture `tests/fixtures/blocks/code_receipt.json` pins the golden shape. |

### A.6 open-webui #22267 — reasoning-block HTML leaks into the artifact preview

| Field | Value |
|---|---|
| Source + URL | open-webui/open-webui issue #22267 — https://github.com/open-webui/open-webui/issues/22267 |
| Date | Opened 2026-03-05; "fixed" 2026-03-08 (commit 35bc831); **reopened 2026-03-09**; locked to collaborators and converted to discussion #23008 on 2026-03-25 ("Unable to reproduce with the latest dev") |
| App + version | Open WebUI v0.8.8 (Docker); reproduced again on v0.8.10 |
| Reported vs confirmed | Reported and reproduced by multiple users across reasoning models (Mistral Magistral/Ministral 3, Z.ai GLM 4.7, Google Gemini 3): raw thinking-block code appears in the artifact frame before the real artifact, "containing many addtional '>' symbols". Per Gemini 3: "each line of its reasoning chain begins with a '<' character, this prevents the previewed webpage from being displayed." Confirmed by reproduction; the incomplete first fix is why the issue was reopened. |
| Resolution | Reopened 2026-03, locked, moved to discussion #23008 — **unresolved** as far as this thread shows. |
| Hutch applicability | Critical. Scraping model prose (assistant messages, reasoning text) for renderable content is the root cause; prose must be inert. |
| Design response in this codebase | There is **no code path** from message prose or model-facing tool text to blocks. Blocks exist only when a tool explicitly supplies `data['blocks']` (`src/hutch/runtime/steps.py:286`); message events are emitted with raw prose and never scanned (`src/hutch/runtime/builtin.py:652,686`). This invariant is pinned by tests, not by convention. |
| Regression test | T-OUTPUTS-4 — `tests/test_steps_blocks.py::test_tool_output_text_containing_block_json_is_never_parsed`, `::test_message_prose_is_never_parsed_for_blocks`. |

### A.7 Known class (no single citation): silent code-interpreter environment expiry

**Status of the evidence, honestly stated.** ChatGPT-style code-interpreter environments are
known to expire silently and lose in-memory state between messages, and users react by
demanding explicit lifecycle and state-loss disclosure. On 2026-10-10 web search surfaced
community discussion of exactly this (e.g. an OpenAI Community thread titled "ChatGPT
environment keeps resetting in a particular chat", Sep 2024, and user discussions of the
"Code execution has been reset" error), but the results were forum links I could not
retrieve as first-hand pages — my fetch attempt at the candidate thread URL returned
HTTP 404 — and no specific, verifiable GitHub issue came up. Per this document's method,
**no citation is claimed** for this row; the class is included because it is common
knowledge among users of these products and the ask explicitly calls it out.

| Field | Value |
|---|---|
| Source + URL | None verifiable (search-derived only; candidate community.openai.com thread fetch → 404) |
| Date | Reports span 2023–2025 (forum discussions) |
| App + version | ChatGPT Code Interpreter / Advanced Data Analysis (class behavior, all versions) |
| Reported vs confirmed | Widely reported by users; never officially documented per-session TTL behavior. Reported symptoms: files uploaded earlier become inaccessible mid-conversation, DataFrame state vanishes between messages, the model "loses the ability to run code" in one specific chat, and the recovery is always "start a new session" — discovered only after the loss. |
| Resolution | Unresolved class behavior; vendors treat it as product lifecycle, not a bug. |
| Hutch applicability | High for the code-execution lane: Hutch will own a real workspace directory per conversation, so silent expiry would be a data-loss bug Hutch created, not inherited. |
| Design response in this codebase | `workspace_sessions` (schema v54, `src/hutch/store.py:1350-1398`) makes environment lifecycle durable state: one row per conversation with `generation` (monotonic environment generation, CHECK ≥ 1), `status` ('active'/'expired'/'terminated', CHECK-constrained), `env_fingerprint`, `workspace_dir`. Transitions are guarded in `Store.transition_workspace_session` (`src/hutch/store.py:7671`) by optimistic concurrency on `generation` (stale callers get `RevisionConflict`, never a clobber), and `code_receipt.execution.environment_generation` (`src/hutch/outputblocks.py:135`) binds every receipt to the generation that produced it — so "which environment did this run in" is queryable, and a stale receipt is detectable instead of silently wrong. |
| Regression test | T-OUTPUTS-7 — `tests/test_outputs_store.py::test_workspace_session_upsert_and_generation_guard`, `::test_the_downgrade_helper_knows_v51_and_reopening_recreates_the_tables`. |

### A.8 Search for further first-hand reports

Three targeted searches were run on 2026-10-10 (not rate-limited): Claude artifact
disappearance complaints, ChatGPT code-interpreter state-loss issues, and open-webui stale/
wrong-artifact reports. Results were secondary write-ups (XDA, iduno.io, miinideck.com,
VentureBeat), a VentureBeat report on shared-artifact *exposure* (a privacy incident, not a
rendering-contract failure), and issue-list pages without a specific verifiable thread. The
strongest candidate (OpenAI Community, Sep 2024) is covered under A.7. **Conclusion: the six
verified issues above are the citable first-hand corpus for this feature; nothing further
met the evidence bar.**

---

## Part B — audit of Hutch's current text-to-output path (branch `outputs/unified` @ 4ac6041)

### B.1 The tool result is untyped prose plus a free-form data dict

`ToolResult` (`src/hutch/tools/base.py:20-24`) is exactly three fields:

```python
@dataclass
class ToolResult:
    ok: bool
    output: str = ""          # text fed back to the model
    data: dict[str, Any] = field(default_factory=dict)
```

`output` is the only channel the model sees. `data` is a free-form dict consumed by
convention, not schema: today's known keys are `simulated`/`blocked` (`base.py:31-37`),
`command`/`exit_code`/`sandbox` (`tools/shell.py:156`), `workspace_file` (attached by
`call_tool`, `runtime/steps.py:275-280`), and `document` (attached by `call_tool`,
`runtime/steps.py:283-284`). There is no validation anywhere on `data` contents before they
land on an event.

### B.2 call_tool: persistence into tool_result events and the 12k model truncation

`call_tool` (`src/hutch/runtime/steps.py:238-322`):

1. Emits `tool_call` with frozen, recorded arguments (`:267`).
2. Runs the tool through `_run_with_receipt` (intent/receipt bracketing, ADR-0003).
3. Post-processes `write_file` into a hash-recorded workspace snapshot (`:275-280`).
4. Truncates for the model: `DEFAULT_TOOL_LIMIT = 12_000` chars per tool call
   (`runtime/steps.py:46`, PF-2), via `truncate_for_model` (`:134-160`) which saves the full
   output as an immutable artifact (`save_artifact`, `:100-130`; 4 MB/16 MB caps at
   `:48-50`) and appends an `[N of M characters omitted; full output saved as artifact ...]`
   note. The memory-side ceiling is `MAX_TOOL_OUTPUT = 1_000_000` (`tools/base.py:231`) with
   `clip` (`base.py:234-237`).
5. Builds the `tool_result` event data: `{"tool", "ok", "output" (first `output_chars`),
   `artifact`/`artifact_sha256`/`artifact_bytes`/`chars`, optional `workspace_file`,
   `document`, `simulated`}` (`runtime/steps.py:281-316`) and emits it (`:321`).

**As of this slice**, `call_tool` also validates typed blocks when a tool supplies
`data['blocks']` (`runtime/steps.py:214-236`, wiring at `:286-296`): serialized blocks land
on `data['blocks']`, labeled rejections on `data['block_errors']`, and the model receives
only a one-line `[presented: …]` summary appended after truncation.

### B.3 Execution story: jailed bash only

The only code-execution surface is `ShellTool` (`src/hutch/tools/shell.py:22-157`): a
single `/bin/bash -c` invocation (`shell.py:87`) with:

- workspace-cwd and `HOME` pointed at the run workspace (`shell.py:73-78`) — the Grok
  home-directory-upload incident is named in the module docstring (`shell.py:1-7`);
- policy gating and Rehearse simulation (`shell.py:54-61`);
- OS containment: `sandbox.mode_for` (`src/hutch/sandbox.py:416`), fail-closed checks
  (`shell.py:63-69`, `:88-93`), `sandbox.shell_argv` / `policy_for` (`sandbox.py:491`, `:529`)
  building the bubblewrap/systemd-run argv, and `sandbox.status()` (`sandbox.py:110`) as the
  availability probe; strict mode refuses shell network access outright (`shell.py:47-52`);
- own process group, registered for guaranteed teardown (`shell.py:99`, `base.py:77-196`),
  drain-with-deadline capture (`shell.py:105-143`), timeout/stop semantics (`shell.py:148-152`).

**What is absent**: there is no Python execution tool, no REPL/session process, and no
persistent interpreter anywhere in `src/hutch/tools/` (directory listing verified: base,
browser, choice, delegation, documents, files, filewrite, google_*/outlook_*, memory,
shell, webfetch). Every execution is one jailed bash command; there is no notion of an
environment generation that survives between commands — which is precisely the gap
`workspace_sessions` (v51) begins to close.

### B.4 Storage role model: documents

`src/hutch/documents/storage.py` is the pattern for durable output bytes: content-addressed
immutable versions (`doc_id/vNNN-<sha8>/<name>`, `storage.py:1-22`), stage→journal→promote→
row-insert commit protocol (`storage.py:180-230`), serve-time re-verification of size and
SHA-256 before anyone sees bytes (`read_version`, `storage.py:245-277`), no-symlink path
walks (`storage.py:232-241`), and crash reconciliation that deletes only what no row can
reach (`storage.py:320-366`). SQLite identities live in `_migrate_50`'s tables
(`src/hutch/store.py:1244-1286` for DDL context; accessor style at `store.py:6043-6090`).
Media bytes have **no** equivalent today — there is no media store, only documents.

### B.5 Migration machinery (the v51 insertion point)

`_MIGRATIONS` (`src/hutch/store.py:1391-1397`) is an ordered list; `SCHEMA_VERSION =
1 + len(_MIGRATIONS)` (`store.py:1398`, now 51). `_upgrade` (`store.py:1507-1549`) takes a
file lock, backs the database up before upgrading, refuses newer-than-current databases
(`:1519-1522`), runs `_SCHEMA` then `_MIGRATIONS[version-1]` in one `BEGIN EXCLUSIVE`, and
stamps `user_version` per step. `_migrate_51` (`store.py:1339-1387`) follows the `_migrate_50`
style with `IF NOT EXISTS` idempotency guards and cheap CHECK constraints on every
enumerated column. The schema-downgrade test helper
(`_remove_later_conversation_schema`, `tests/test_delegation.py:179-220`) now knows the v51
tables and indexes (the way c9dd168 taught it v50).

### B.6 The frontend renders escaped plain text; nothing typed

Orientation only (this slice does not edit `app.js`). `pairToolEvents`
(`src/hutch/server/static/app.js:4177`) pairs call/result events; `toolLineHtml`
(`app.js:4235`) renders the result's `d.output` through `toolOutputHtml` (`app.js:4286-4297`),
which is `esc(text)` — escaped plain text with a 600-char clip (`OUTPUT_CLIP`,
`app.js:4284`) and a show-more button. The only structured attachments are hash-verified
download chips: artifacts (`artifactDownloadHtml`, `app.js:4299-4311`) and created
files/documents (`createdFilesHtml`, `app.js:4313-4343`). **There is no typed-block
renderer**: no chart/table/flowchart drawing, no `data.blocks` consumer (the key does not
appear anywhere in app.js), and no block-error surface. A tool could emit perfectly good
JSON on an event today and the user would see its raw escaped text.

### B.7 Explicit statement of what is absent (the honest inventory)

- **Uploads**: no uploads table existed before v51, no upload tool, no intake path — a user
  cannot hand a file to a conversation (v51 adds the registry; the intake lane builds on it).
- **Media storage**: no media byte store, no media tables before v51 (`media_jobs` is a job
  ledger, not a byte store), no media serving route. `media` blocks reference bytes that no
  code writes yet.
- **Python execution**: none (B.3). Only jailed bash. `code_receipt` currently has no
  producer; the contract is ahead of the capability by design.
- **Typed widgets**: none (B.6). The frontend path is escaped plain text plus download
  chips. `parse_blocks` has exactly one production caller so far: `call_tool`.
- **Prose parsing**: correctly absent and now pinned: message and reasoning text are never
  scanned for blocks (`runtime/builtin.py:652,686` emit raw prose; the only `blocks` strings
  in the codebase are the unrelated docgen content spec, `tools/documents.py:69`,
  `documents/docgen/docxgen.py:155`, `documents/docgen/pdfdoc.py:345`).

### B.8 Failure-class → mechanism map

| Failure class (ledger row) | Mechanism in this codebase | Regression tests |
|---|---|---|
| Cross-session preview leak (A.1) | `provenance {run_id, tool, job_id?}` on every envelope; blocks only on their own run's event | T-OUTPUTS-5 |
| Silent dedup / unbounded notification (A.2) | UNIQUE `idempotency_key` + `IdempotencyConflict`; result budgets in `parse_blocks`; transcript-as-truth event placement | T-OUTPUTS-6 |
| Per-token presentation re-entry (A.3) | Single post-completion validation in `call_tool`; no stream re-entry; model text untouched | T-OUTPUTS-3 |
| Failed render loses source + diagnostic (A.4) | Required non-blank `text_fallback` everywhere; never-raise `parse_blocks`; persisted `block_errors` | T-OUTPUTS-2 |
| Post-execution display drift (A.5) | `code_receipt.source_sha256` == sha256(source), enforced at parse | T-OUTPUTS-1 |
| Prose scraping leaks reasoning (A.6) | No prose→blocks path; only `data['blocks']` | T-OUTPUTS-4 |
| Silent environment expiry (A.7) | `workspace_sessions` generation/status/fingerprint; guarded transitions; `execution.environment_generation` binding | T-OUTPUTS-7 |
