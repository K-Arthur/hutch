# Roadmap

## Owner-requested product scope added 2026-10-09

The product owner identified chat-led bot setup, structured choice prompts, Google Calendar,
Gmail and Outlook integrations, a named coordinator Bot, and human completion of credentials/CAPTCHA as
key product requirements. Studio has purpose-derived editable Bot naming, a user-reviewed chat-seeded
setup draft, typed built-in-runtime choices, inline approvals, and an experimental read-only Calendar
path. The named coordinator now has one user-confirmed, durable cross-Bot handoff to a selected specialist;
multi-step team planning and restart-safe checkpoints remain open. Gmail and Outlook are not implemented.
Keep chat as the normal work surface and make Bot configuration, handoff review, and approvals appear in
context. The roster should remain small by default; use a searchable Fleet surface as the setup grows.
Roughly ten Bots is the owner's initial heuristic, not a measured threshold.

1. **Typed choices, core implemented (schema v26):** conversational built-in runs can ask a bounded
   single-select or multi-select question. The question/options and one-use answer persist across
   restart; answering creates an idempotent user turn anchored to the Bot's question. It supplies
   information only; a tool action or permission still requires its own approval. External runtime
   support and final desktop/tablet/phone visual/release validation remain open.
2. Make bot setup conversational and context-aware. Carry forward the purpose, constraints, model,
   tools, and workspace choices the user has already stated; ask only for unresolved information.
   Show the complete staged configuration for review, then create idempotently only after explicit
   confirmation. Creating a bot never starts a run by itself. Keep the direct configuration route
   available during rollout.
3. **Coordinator foundation landed; multi-step orchestration remains open.** One Bot can be named the
   workspace coordinator, with its own direct conversation. A completed answer can be turned into an
   editable brief for one selected existing Bot after explicit review; provenance, assumptions, target
   settings, child chat/run, status and latest reply are linked in the coordinator timeline. Only the
   reviewed brief and assumptions cross into the specialist chat. A user may explicitly attach the exact
   successful specialist response to a coordinator follow-up as untrusted text. Extend with a reusable owner-approved
   specialist list, selected artifact/context references, safe restart continuation, parent cancellation,
   cost display, bounded prompt questions, and delivery reconciliation. Schema v31 now records content-free
   committed-event markers and exposes a bounded timeline, but tasks cannot resume after restart yet. Prompt refinement
   cannot grant capabilities or change standing instructions. Creating a reusable specialist or changing
   its role needs separate review and confirmation.
4. **Google Calendar read lookup is implemented as an experimental local path (IG-5 partial).**
   The operator must configure a Google Desktop OAuth client and Linux Secret Service; no live
   account or consent-screen verification has been completed. Google authorizes read-only access
   account-wide while Hutch exposes only the selected calendar to each Bot. Calendar writes are
   still unavailable. Next implement named Gmail/Outlook connections only after scope and review
   requirements are settled; event creation, message sending and every external write must have a
   fresh review showing account, destination and complete payload. Keep refresh credentials in the
   OS credential store rather than SQLite, transcripts, prompts or browser storage.

5. Give the workspace and each Bot an explicit model default. The workspace choice seeds new-Bot
   setup; the coordinator and each specialist keep their own editable route and inference mode.
   A chat/run override applies once unless the user chooses **Save as this Bot’s default**. Show
   the actual provider/model and usage for every run, keep route readiness visible, and fail with
   an actionable reason if a selected route is unavailable. Never silently switch to a hosted
   provider, another billing account, or a different inference mode. Coordinator dispatch uses the
   target Bot’s saved default unless the user explicitly selects an allowed per-task override.
6. Continue the checkpoint work for coordinator and specialist tasks. The current schema-v31 journal
   records ordered markers for committed messages/status/decisions/human waits and artifact references,
   linked to the child run's immutable route/permission snapshot. It excludes event content, model
   reasoning and action payloads. Add continuation only after persisting a versioned, validated execution
   state and proving safe boundaries across restart. If an external effect may have happened without a
   verified receipt, keep `outcome_unknown` for reconciliation instead of replaying it. Keep the owning
   child's wait visible while recovery is unavailable.
7. Keep long-term memory Bot-scoped and separate from chats, task briefs, artifacts, receipts and
   credentials. Users can choose the memory policy for each Bot and inspect, revise, disable or
   clear retained facts. A child receives only task text and explicitly selected context. Sharing a
   fact or artifact across Bots is a visible, revocable, provenance-carrying grant; task context is
   not silently promoted into a specialist’s standing memory, and coordinator memory is never
   inherited by a specialist.
8. Let users reply to a particular Bot message. The message action attaches its stable ID and a
   short author-labeled excerpt to the composer; the user can clear or replace it before sending.
   Persist the relationship with the user message and display it in the transcript so the reply
   stays understandable later. Validate that the source belongs to the same conversation, include
   only the explicitly selected cross-message reference beyond the normal bounded chat context,
   and treat its contents as untrusted text with no action authority. Keep the action reachable by
   keyboard and phone touch.

Gmail body search/read requires Google restricted OAuth scopes under the current provider
documentation. Public support depends on completing the required Google app verification and any
security assessment; until then this integration must remain unavailable or explicitly limited to
a verified capability. These features must not appear in marketing as supported until their real
OAuth, recovery, revocation, action-receipt and desktop/tablet/phone journeys pass. No account,
provider request or scope has been enabled by this planning update.

This product direction follows the useful parts of Grok Bot's official documentation: named Bots
have durable roles, setup starts in chat, one outcome is assigned to one owner at each delegation
stage, and asynchronous handoffs return to a visible conversation. Hutch deliberately does not
copy Grok Bot's account-wide shared computer, files, browser sessions, and command credentials;
Hutch retains isolated workspaces and explicit context/artifact sharing. The source review,
including group-chat limits, recovery behavior, and individual user complaints, is recorded in
[`research/grok-bot-product-review-2026-10-09.md`](research/grok-bot-product-review-2026-10-09.md).

Schema v15 adds chat-scoped reference proposals, exact-revision human review, explicit sharing,
bounded FTS5 recall and retained review history. Memory disabled in bot settings also disables
runtime use while retaining human management. Facts are not automatically injected into system
prompts. Clipped tool outputs and successful `write_file` snapshots now have run-scoped version
records and SHA-256-verified downloads; generated-file links appear directly in Studio chat while
tool details stay collapsed. Owners can add a verified artifact reference to another selected chat;
both chats show the active grant and can revoke it. The target-bound download is revocable, and no
bytes enter the target workspace or model context.
Optional generic browser alerts work while the Hutch tab is open; they do not provide background push.
Per-bot Hutch-managed workspaces and up to 100 independently scheduled tasks are implemented.
Conversation export is scoped and explains what it excludes. A general artifact library, delegated
artifact transfer, webhook/push notifications, permanent scoped deletion, and the named workspace
coordinator with cross-Bot handoff remain open. A narrow same-bot `delegate_task` preview is available only for supervised
Strict Offline Linux runs; it does not complete the broader S6 collaboration plan.

## Phase 0 — MVP (shipped, Oct 2026)

- [x] Bot CRUD + starter templates (CLI, dashboard, REST)
- [x] Built-in agent loop (OpenAI-compatible: OpenAI / Ollama / llama.cpp / LM Studio / custom base URL)
- [x] Recover legacy Pi/OpenCode bot records by explicitly moving an idle bot to Hutch's built-in executor after its saved Hutch model route validates. This does not enable either external runtime or copy its credentials.
- [x] Per-bot Hybrid and Local model routing; known hosted route/fallback switching is blocked in Local mode. Local tools may still use the network.
- [x] Test-only deterministic scenario fixture — exercises policy and tool plumbing without a model; not packaged or selectable in production
- [ ] External runtime adapters (Pi, OpenCode): currently fail closed. Offline bounded protocol helpers exist; process I/O drainers, loss-recoverable OpenCode events, permission brokering, sandboxed process ownership, shared budget reservations and route/session mapping are required before re-enabling.
- [x] Tools: shell (workspace-jailed, minimal env, HOME redirect), files (path jail),
      memory (SQLite facts), web_fetch (SSRF guards, clipping), browser (Playwright optional,
      persistent per-bot profiles, pause-to-human)
- [x] Policy engine: compound-command parser, deny/ask/allow, secret-path + egress denylists,
      URL scheme/private-range guards
- [x] Human-in-the-loop approvals: fail-closed TTL, sticky always-allows, dashboard + CLI
- [x] Scheduler: IANA-timezone cron, DST-gap/ambiguity handling, catch-up coalescing,
      skip policy with visible markers, per-bot single-instance lock
- [x] Caps: max_steps, wall-clock kill, daily token cap
- [x] Atomic pre-call reservations for per-bot budgets and configured shared provider accounts; reconcile uncertain charges after checking the provider record. Currency limits remain price/prompt estimates.
- [x] Append-only transcripts (SQLite + JSONL per run), staleness surfaced in dashboard
- [x] Dashboard (live transcripts, approvals, meters, stop) + CLI + daemon
- [x] Test suite (70 tests) covering safety parser, DST math, engine lifecycle, API, CLI

## Phase 1 — hardening (next)

- [ ] Container-per-run isolation (podman/docker) as an opt-in sandbox level
- [ ] Configurable policy packs per bot (site-specific allowlists, egress domains)
- [ ] Strict Offline end-to-end gate. Experimental Linux worker isolation uses fresh bubblewrap network/PID namespaces and a per-run Unix-socket model broker; this host probe and a fixture-provider request pass. No live local model journey is verified, and model-server provenance remains outside the boundary. Local explicitly means local inference with ordinary tool policy.
- [ ] Run retries with backoff + idempotency keys for external actions
- [ ] Notifications beyond tab-open browser alerts (webhook, service-worker push and closed-tab delivery)
- [ ] Snapshot/export of bot definitions (YAML in/out) for sharing
- [ ] Secret per-bot credentials via OS keyring (referenced, never in prompts)

## Phase 2 — capability

- [ ] Vector memory (local embeddings, sqlite-vec) with inspectable recall
- [ ] Webhook/event triggers (file-watch, HTTP inbox) alongside cron
- [ ] Multi-step workflow templates (chained runs, hand-off artifacts)
- [ ] Pi/OpenCode adapters: match published RPC/CLI contracts; broker approvals and provider budgets; strict process containment
- [~] Bounded same-bot `delegate_task` preview: Strict Offline and process-executor only, always human-approved, private child workspaces, task-text-only context, bounded depth/steps/time and inherited usage reservations. Parallel children, specialist selection, artifact transfer, cross-bot delegation and a plan UI are not implemented; see `realignment/delegation.md`.
- [~] Browser tool: same-session human handoff is experimental on a local Linux desktop; HTTP(S)/WebSocket DNS-pinned egress has local Chromium fixture coverage. Live headed challenges, non-HTTP traffic, remote phone handoff and per-bot download directories remain

## Phase 3 — scale-out (deliberately far)

- [ ] Cross-OS support (macOS, Windows) — GUI automation paths differ per OS
- [ ] Multi-user access to one hutch instance (auth + roles)
- [ ] Optional remote access (tailscale/SSH guidance, or relay) — stays opt-in, never a cloud default
- [ ] A2A collaboration between bots (scoped, auditable)

## Current realignment progress

- **Database restore: isolated workflow implemented.** Schema v14 validates snapshots in a new
  private directory, detaches source process records, quarantines old work and holds new execution
  for local review. Device sessions/standing grants are revoked and schedules paused. Snapshot
  scope excludes credentials, profiles and user files. Production service cutover and power-cut
  certification remain separate verification gaps; this is not rollback of external effects.
- **Conversation persistence: partial.** Schema v8 stores canonical messages and maps runs to conversations. Historical runs are
  imported separately. The local v1 API snapshots at most 12 prior messages / 16,000 characters for builtin runs and supports
  FTS5 search. The Studio selects threads, displays restart-persistent history and archives without deleting it. Bounded JSON export
  is opt-in and includes an explicit disclosure; permanent scoped deletion remains unavailable.
- **Studio navigation and approvals: consolidated.** Studio has one bot roster and one settings destination; the same exact-action
  approval card appears in the originating chat and in the cross-chat Needs you drawer. Monitor holds activity and run history. Fleet
  appears as a filtered view at ten bots; ten is a reversible operator heuristic, not a measured user threshold. This avoids a
  second bot-management destination for small fleets while retaining a focused view for larger ones. Responsive and interaction
  evidence is in `docs/realignment/navigation-visual-validation.md`.
- **API: partial.** Versioned health, status labels, bots, conversations, search, runs, approvals and usage aliases are present.
  Create/message/archive, stop, and approval resolution use transactional idempotency. Cross-run ordered transcript SSE, bounded
  event pages and snapshot reconciliation are present. Schema v11 adds transactional resource invalidations,
  epoch/committed-ID replay, canonical approval summaries and targeted UI refresh. Schema v12 adds
  recoverable bounded JSONL delivery, visible errors and FULL WAL synchronization. Schema v17 adds
  explicit, idempotent, revocable references to verified artifacts across chats; the receiving chat
  gets provenance and a target-bound download, not a file copy or model-context injection. The source
  Files list shows active recipient chats and can revoke their grants. Schema v18 adds durable
  invalidations to both chats when access changes. A general
  artifact library, delegated artifact transfer, automatic event retention and complete capability verification remain open.
  Resume and standalone run creation now use versioned idempotent commands; their legacy routes remain compatibility aliases.
- **Provider compatibility: route-level matrix implemented.** `GET /api/v1/compatibility` records supported,
  experimental, unavailable and blocked routes with dated sources, request fields Hutch sends/omits and fixture/live
  verification limits. Exact OpenAI host matching now selects its token-limit field. Per-connection/model capability
  records and opt-in per-model tool probes remain open. Offline tests cover unsupported host isolation,
  hosted routes and overrides, endpoint validation, tool omission, environment scrubbing, a local-only
  namespace probe, and a fake-provider request through the broker. Live model/backend provenance remains unverified.
  fields, auth/quota rejection, held uncertain usage and the outward approval required before switching paid routes;
  live billing behavior remains unverified.
- **Action review: local fixtures.** Schema v13 retains immutable intents and separate operator
  reconciliation. Uncertain receipt sealing is transactional; chat and Needs you surface review.
  Same-conversation repeat guards and bounded current builtin context notes are implemented.
  Browser/external-runtime authority gaps and live effect verification remain open.
- **Remote pairing: experimental.** Direct off-loopback access requires explicit TLS binding. `/pair` exchanges single-use codes and
  Connections lists and revokes device sessions. An operator-managed HTTPS reverse proxy can be explicitly trusted by source network
  and public hostname; Hutch does not provision a tunnel. Browser/PTY/desktop controls and physical-device/private-network verification
  remain open. No real proxy path has been validated.
- **Release posture.** Source is private and unpublished. A paired device cannot keep a sleeping host running or reach a service after
  disconnection.

## Non-goals

CAPTCHA solving, bot-detection evasion, acting as a hosted service, or autonomy without
supervision. These conflict with the product's premise.
