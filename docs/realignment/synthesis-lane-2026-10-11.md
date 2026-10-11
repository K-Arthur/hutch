# Grounded synthesis + Workspace lane (2026-10-11)

Lane plan and checkpoint for: source-grounded two-host Audio Overview / infographic from a
20-post thread or complex whitepaper, interactive join/answer/resume, and governed Google
Workspace actions (Docs brief, Sheets table, Drive placement, Calendar/reminder semantics).

## Coordination (read before editing)

* Base: `grounding/evidence` @ `a28263a` (schema v51, evidence layer). Branch
  `synthesis/grounded` in `.worktrees/synthesis`. Local commits only; no push.
* Other lanes are active and untouched by this lane: `.worktrees/grounding` (evidence
  follow-up), `.worktrees/outputs*` (typed blocks v51 collision, Python workspace, media,
  widgets). Do not edit files dirty in those worktrees.
* Schema numbering: both `grounding/evidence` (v51) and `outputs/unified` (v51) exist.
  This lane takes **v52+**; the final integrator renumbers at merge time if ordering
  differs. One integrator applies migrations to `store.py`.
* Reuse, do not rebuild: documents pipeline (v50) for rendering/serving, grounding
  evidence tables for source identity, `ToolResult.data` refs for chat rendering,
  approval gate + action receipts for every lasting effect.

## Failure-driven design (evidence in `docs/research/synthesis-workspace-failures-2026-10-11.md`)

| Failure class (source) | Design response |
|---|---|
| Name-lookup sheet targets, wrong sheet with multi-input (F3 n8n#20372) | Bind writes to stable spreadsheet+sheet IDs; validate returned range; never re-resolve by name at write time |
| Append loads whole large sheet / OOM (F4 n8n#11234) | append uses `values.append` + header-only read; bounded reads |
| Interactive controls unavailable, no working interrupt (F1, F2) | Playback-only vs interactive explicitly modeled; interruption stops narrative and clears queued audio client-side, independent of any server signal; UI exposes why interaction is unavailable |
| Server may omit barge-in when user speaks as turn begins (F2) | Client-side stop/queue-clear + explicit turn ownership; regression test for speak-at-turn-start |
| NotebookLM third voice / speaker switches (R1) | Stable speaker IDs + segment validation; per-segment speaker check in assembly; never let a provider add a third voice silently |
| Public-URI requirement for Docs inline images (R9) | No silent public exposure: Drive attachment/link with honest inline limitation |
| Tasks `due` discards time (R10) | Exact-time reminders never routed to Tasks; event-relative overrides or Hutch routine only |
| Duplicate writes on lost responses | Durable effect ledger + idempotency keys; caller-assigned Calendar event IDs; reconcile before retry |
| Correction stale derivatives | Manifest revision + `depends_on` edges; any claim/number change marks dependent outputs stale with the reason; prior versions retained |

## Contracts (frozen in this lane)

1. **Synthesis manifest** (`synthesis/model.py`): versioned, links sources+revisions,
   coverage, audience/language/depth, claims with typed spans (post/page/figure/table),
   numbers/units, caveats, contradictions, generation settings, and output versions.
   Audio/infographic/brief/table derive from one manifest revision. Never a numeric
   confidence score; missing values stay missing.
2. **Ingestion** (`synthesis/ingest.py`): thread reconstruction follows the author's
   reply chain (engagement order is not order), preserves quote/attachment/edit state,
   reports "N of M accessible" with typed gaps and never invents posts; whitepaper
   extraction records sections, candidates for tables/figures/equations/footnotes with
   page locators, refuses encrypted input, and reports scanned/image-only pages instead
   of silently synthesizing from nothing.
3. **Storage** (`synthesis/storage.py`): content-addressed, staged→journal→promote→fsync
   commit mirroring `documents/storage.py`; every artifact row carries sha256+bytes;
   failed validation is never promoted as ready.
4. **TTS adapters** (`synthesis/tts.py`, later slice): provider capability discovery
   (Gemini multi-speaker ≤2 prebuilt voices; per-turn single-speaker fallback), verbatim
   transcript separated from style metadata, PCM/WAV handled per the actual response
   format, segment retry without regenerating unaffected segments.
5. **Interactive playback** (`synthesis/playback.py`, later slice): explicit states
   (narrative/listening/thinking/answering/resuming/paused/disconnected/failed), heard
   position separate from generated position, cancelled answers never replayed.
6. **Workspace actions** (`actions/` + `tools/`, later slice): inspectable operation plan,
   typed effect ledger, per-service authority (read/draft/metered/cloud-create/edit/
   move/share/notify), bound to stable IDs, verified by read-back receipts.

## Slices and status

| Slice | Contents | State |
|---|---|---|
| S0 | Lane plan, failure ledger, integration-base record | this file + research doc |
| S1 | Manifest contract + ingestion + storage + schema v52 + tests | **implemented, local tests green** (48 tests: model 19, ingest 13, storage 11, +5 authoring) |
| S2 | Two-host script authoring + TTS adapters + assembly + transcript/chapters | **implemented (protocol-verified vs fake servers); live provider calls unexecuted (no keys on this host)** |
| S3 | Infographic renderer (deterministic SVG) + exports + accessible companion | planned |
| S4 | Interactive join/answer/resume state machine + UI audio surface | planned (design gate first) |
| S5a | Workspace request contracts (Docs tabs/revisions, Sheets RAW+append, Drive ids/uploads, Calendar events, reminder routing) | **implemented, local tests green** (17 tests, no I/O) |
| S5b | Workspace OAuth transport + executors + action plan/effect orchestration | **implemented, local tests green** (10 plan-engine + 8 fake-Google transport tests; live Google unexecuted — no account) |
| S5c | Tool layer: ingest_source, register_manifest, register_script, render_audio_overview, plan_workspace_action, run_workspace_plan | **implemented, local tests green** (8 tool tests; registered in groups `synthesis`/`workspace`, hidden in Strict Offline for the network tools) |
| S5d | Calendar: relative reminders on create, conditional (`If-Match`) reminder updates, plan-step executors with grant checks | **implemented, local tests green** (6 client tests + 2 tool tests; live Google unexecuted) |
| S5e | Connections API for the Workspace OAuth callback + hash-verified artifact download routes | **implemented, local tests green** (3 route tests; fake/local only) |
| S6 | UI integration (source selector, coverage, format controls, action drawer) | planned (design gate first) |
| S7 | Integrated acceptance, visual/audio evidence, independent verification | planned |

### S1/S2/S5 evidence boundary (2026-10-11)

* Verified locally: manifest/claim/quantity invariants and invalidation; thread reconstruction
  against the 20-post fixture (quote post, attachment, correction, duplicate, deleted post,
  unreachable remainder; "16 of 20 accessible"); PDF structure extraction on real generated
  PDFs; storage commit/verify/reconcile semantics; TTS request shapes, retry policy, key
  redaction and per-segment idempotency against local fake HTTP servers; transcript VTT with
  labeled estimate alignment; Workspace request contracts (tabs, RAW values, reminder
  routing); the OAuth client, Docs/Sheets/Drive flows, reconciliation and the governed
  action-plan engine against a local fake Google API (including a five-step journey where an
  append targets the spreadsheet a prior step created).
* Unexecuted: any real provider call (no Gemini/OpenAI key on this host), any real Google
  Workspace call (no connected account or OAuth client), Calendar executor wiring, and
  rendering actual audio a person has listened to. The TTS and Workspace routes must be
  live-verified before any "listened/verified" claim.
* Determinism: `deterministic_draft` is a plainly-labeled offline script used for tests and
  strict-offline derivatives; it is not presented as good dialogue.
* Deliberate non-claims: no UI exists yet; no scheduling/notifications have been configured;
  nothing has been pushed, deployed, or shared with anyone.

## Budgets (local reference machine; measure, then revise)

* ingest: ≤ 200 pages / 2 MB text per source; ≤ 40k chars per page; total context ≤ 400k chars.
* thread: ≤ 500 posts fetched, ≤ 200 in the ordered argument; attachments metadata only.
* tts: one segment ≤ 1,500 chars; retry ≤ 2 per segment; no regeneration of unchanged segments.
* artifacts: audio ≤ 128 MB; script json ≤ 4 MB; infographic SVG ≤ 8 MB; per-run synthesis ≤ 512 MB.

## Next slice notes (2026-10-12)

* **Calendar (S5d, done 2026-10-12):** `create_event(reminders=...)` posts relative overrides
  and verifies them in the read-back; `update_event_reminders` reviews the event, updates
  conditionally with `If-Match` on the current etag (a human edit between review and write
  is refused with "the event changed since it was reviewed"), and verifies the result;
  mismatch or unverifiable outcomes raise outcome-unknown and are never retried blind.
  Plan steps (`event_create`, `cloud_edit` for reminders) execute through the Bot's
  Google Calendar grant; a reminder step with no `reminders` and no `reset_default` fails
  instead of silently clearing reminders. `routine_config` steps remain unbound (Hutch
  routine creation is a separate reviewed integration).
* **Connections API (S5e, done 2026-10-12):** `/api/v1/connections/google-workspace` (status +
  accounts), `/sign-in` (PKCE start, loopback-only callback), `/callback` (consumed query via the
  security allowlist, honest error redirect), `/accounts/{id}/disconnect`; artifact routes
  `GET /api/v1/synthesis/artifacts/{id}/content` (hash-verified, range-capable) and
  `GET /api/v1/synthesis/manifests/{id}`. The **Connections UI** surface and the audio/infographic
  UI remain before the in-app acceptance journey.
* **UI** (source selector, coverage, audio player with Join/Ask, infographic view, action
  drawer) starts with the mandatory Figma Community research and a 3–4 route review.

## Verification commands

`uv run --frozen pytest -q tests/test_synthesis_model.py tests/test_synthesis_ingest.py` on this
branch; full offline suite before each commit; browser/audio evidence recorded in
`docs/realignment/artifacts/synthesis-*/` when the UI/audio slices land. Live provider and
Google checks are explicitly unexecuted until credentials are provided (see ledger).
