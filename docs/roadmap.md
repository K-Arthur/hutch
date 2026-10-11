# Roadmap

## Owner-requested product scope added 2026-10-09

The product owner identified chat-led bot setup, structured choice prompts, Google Calendar,
Gmail and Outlook integrations, a named coordinator Bot, and human completion of credentials/CAPTCHA as
key product requirements. Studio has purpose-derived editable Bot naming, a user-reviewed chat-seeded
setup draft, typed built-in-runtime choices, inline approvals, and an experimental read-only Calendar
path. The named coordinator now has one user-confirmed, durable cross-Bot handoff to an explicitly approved specialist;
multi-step team planning and restart-safe checkpoints remain open. Outlook Calendar read and separately
consented create-only event actions, plus Outlook Mail read, have experimental local integrations; none
has live provider verification. Gmail
has an owner-configured private-preview search limited to built-in Bots on loopback Local model routes;
public release remains unavailable pending Google's restricted-scope verification and any required
security assessment. No live Google account or consent was tested. Bot creation now offers a one-screen purpose-first
path when a workspace or chat model route is already configured, with a separate Customize path for the full advanced
editor. Missing routes require an explicit choice. The large-roster sidebar collapses idle unpinned Bots after ten total
Bots while keeping active work directly reachable. Research and anecdotal edge cases are recorded in
[`bot-setup-patterns-2026-10-09.md`](research/bot-setup-patterns-2026-10-09.md).
Keep chat as the normal work surface and make Bot configuration, handoff review, and approvals appear in
context. The roster should remain small by default; use a searchable Fleet surface as the setup grows.
Roughly ten Bots is the owner's initial heuristic, not a measured threshold. Frequent Bots can be
pinned in the primary roster without hiding active work; pinning is a navigation preference only.

1. **Typed choices, core implemented (schema v26):** conversational built-in runs can ask a bounded
   single-select or multi-select question. The question/options and one-use answer persist across
   restart; answering creates an idempotent user turn anchored to the Bot's question. It supplies
   information only; a tool action or permission still requires its own approval. External runtime
   support and final desktop/tablet/phone visual/release validation remain open.
2. Make bot setup conversational and context-aware. From any visible user message, the owner can
   start setup with that exact request; the top-bar path uses the latest request. Carry forward only
   the chosen request and explicitly selected earlier user context; never copy later messages,
   assistant replies, permissions or unrelated chats. Carry forward the purpose, constraints, model,
   tools, and workspace choices the user has already stated; ask only for unresolved information.
   Show the complete staged configuration for review, then create idempotently only after explicit
   confirmation. Creating a bot never starts a run by itself. Keep the direct configuration route
   available during rollout. Message-level source selection is implemented and responsive-fixture
   tested. The workspace coordinator can optionally return one tool-free response per refinement
   request, grounded in the exact source, current purpose and explicitly selected earlier user
   context. The user must review and apply it. Multi-round clarification and generative naming remain
   open; current deterministic, local naming suggestions still require user review.
3. **Coordinator foundation landed; multi-step orchestration remains open.** One Bot can be named the
   workspace coordinator, with its own direct conversation. A completed answer can be turned into an
   editable brief for one owner-approved existing Bot after explicit review; schema v41 adds a durable,
   initially empty specialist roster in coordinator settings and admission rechecks it atomically. Promoting
   a specialist to coordinator removes it from the roster without adding the former coordinator. Provenance, assumptions, target
   settings, child chat/run, status and latest reply are linked in the coordinator timeline. Only the
   reviewed brief and assumptions cross into the specialist chat. A user may explicitly attach the exact
   successful specialist response to a coordinator follow-up as untrusted text. Schema v34 adds one narrow,
   owner-confirmed fresh attempt from an eligible failed/stopped built-in task; it cannot restore a process,
   carry old tools/actions, or continue an unknown effect. Extend with selected artifact/context references,
   parent cancellation, cost display, bounded prompt questions,
   and delivery reconciliation. Prompt refinement cannot grant capabilities or change standing instructions.
   Creating a reusable specialist or changing its role needs separate review and confirmation.
4. **Calendar and mail connections remain experimental local paths (IG-5–IG-8 partial).**
   Each operator configures a Google Desktop or Microsoft public-client OAuth registration and
   Linux Secret Service; no live account or consent-screen verification has been completed. Provider
   grants are account-wide; Hutch limits each Bot to one selected calendar or mailbox. Outlook Calendar uses delegated
   `Calendars.ReadBasic`. Outlook Mail is a separate flow with delegated `Mail.Read`; each Bot can
   search at most ten matching messages and receives sender, subject, received time and a short
   untrusted preview. This read grant cannot send, edit, delete, forward or fetch attachments.
   A separate experimental Outlook send preview has its own `Mail.Send` sign-in and per-Bot grant,
   exact fresh approval for each message, and no automatic retry after uncertainty. Gmail search is a private
   preview using restricted, account-wide `gmail.readonly`; it returns only bounded sender/subject/date/snippet
   previews to built-in Bots whose model routes all use loopback Local endpoints and have no hosted
   fallback. A distinct Gmail send-only preview requests sensitive `gmail.send`, cannot search or read mail,
   and requires fresh exact approval for one plain-text message each time; it never retries an uncertain outcome.
   Google OAuth still authorizes broader account-level access, which Hutch cannot narrow, and no live account
   or consent was verified.
   Google Calendar now also has an owner-configured guest-free event-create preview: the owner must
   separately request Google's account-wide `calendar.events.owned` scope, grant one owned calendar
   to one Bot, and approve each exact event in context. Hutch verifies the returned event ID, title,
   time, description and location; uncertain outcomes are never retried automatically. Google's scope is broader than the single
   action Hutch exposes, and public OAuth verification plus live account consent remain open. Outlook
   Calendar also has a separate `Calendars.ReadWrite` sign-in and per-Bot selected-calendar grant for
   guest-free create-only events. The delegated scope reaches all account calendars and can change/delete events,
   while Hutch exposes create only on the selected calendar after exact per-event approval; it reads back the event
   before reporting success and holds uncertainty for reconciliation. No live Microsoft account or consent was tested.
   Mailbox changes outside the narrow Outlook/Gmail send previews remain unavailable.
   Event creation, message sending and every
   external write need a fresh review showing account, destination and complete payload. Keep refresh
   credentials in the OS credential store rather than SQLite, transcripts, prompts or browser storage.

5. Give the workspace and each Bot an explicit model default. The workspace choice seeds new-Bot
   setup; the coordinator and each specialist keep their own editable route and inference mode.
   A chat/run override applies once unless the user chooses **Save as this Bot’s default**. Show
   the actual provider/model and usage for every run, keep route readiness visible, and fail with
   an actionable reason if a selected route is unavailable. Never silently switch to a hosted
   provider, another billing account, or a different inference mode. Coordinator dispatch uses the
   target Bot’s saved default unless the user explicitly selects an allowed per-task override.
6. Extend the narrow schema-v34 checkpoint continuation only after proving each new boundary. The current
   journal records committed event markers; eligible failed/stopped built-in attempts can create one
   owner-confirmed fresh run only when no tool action or child work was recorded, the specialist chat has
   no later work or pending question, and the exact saved capability snapshot still matches. The fresh
   attempt receives only the reviewed brief, constraints and bounded untrusted assistant checkpoint.
   External runtimes, process restoration and uncertain effects are not continued. Keep `outcome_unknown`
   for reconciliation instead of replaying it.
7. Keep long-term memory Bot-scoped and separate from chats, task briefs, artifacts, receipts and
   credentials. Users can choose the memory policy for each Bot and inspect, revise, disable or
   clear retained facts. A child receives only task text and explicitly selected context. Sharing a
   fact or artifact across Bots is a visible, revocable, provenance-carrying grant; task context is
   not silently promoted into a specialist’s standing memory, and coordinator memory is never
   inherited by a specialist. Schema v38 implements a one-fact/one-recipient memory grant with
   immutable provenance and either-side revocation; broader memory-policy and multi-task sharing
   remain follow-up work.
8. Let users reply to a particular Bot message. The message action attaches its stable ID and a
   short author-labeled excerpt to the composer; the user can clear or replace it before sending.
   Persist the relationship with the user message and display it in the transcript so the reply
   stays understandable later. Validate that the source belongs to the same conversation, include
   only the explicitly selected cross-message reference beyond the normal bounded chat context,
   and treat its contents as untrusted text with no action authority. Keep the action reachable by
   keyboard and phone touch.
9. **OpenCode coding handoff (experimental, schema v39):** from a completed Studio exchange, review an editable task brief and
   prepare a durable task against the Bot's configured Git folder. The owner launches the installed OpenCode CLI locally from a
   Linux terminal; Hutch pins the branch to the reviewed commit and keeps the result in a separate worktree. OpenCode's own
   permission prompts, model sign-in and usage remain outside Hutch's broker and budget controls, and approved shell commands
   retain the user's host authority. This does not enable OpenCode/Pi as Hutch-managed runtimes. Live CLI startup/model behavior
   is still unverified; see the dated research and `/api/v1/code-handoffs` contract.

Gmail search requires Google's restricted OAuth scope under the current provider documentation.
Public support depends on completing the required Google app verification and any security
assessment; until then only the explicitly documented owner-configured private preview is available,
and marketing must label it experimental and unavailable for public release. These features must not appear in marketing as supported until their real
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
artifact transfer, webhook/push notifications, permanent scoped deletion, and multi-step workspace
coordination remain open. A narrow same-bot `delegate_task` preview is available only for supervised
Strict Offline Linux runs; it does not complete the broader S6 collaboration plan.

## Phase 0 — MVP (shipped, Oct 2026)

- [x] Bot CRUD + starter templates (CLI, dashboard, REST)
- [x] Built-in agent loop (OpenAI-compatible: OpenAI / Ollama / llama.cpp / LM Studio / custom base URL)
- [x] Recover legacy Pi/OpenCode bot records by explicitly moving an idle bot to Hutch's built-in executor after its saved Hutch model route validates. This does not enable either external runtime or copy its credentials.
- [x] Per-bot Hybrid and Local model routing; known hosted route/fallback switching is blocked in Local mode. Local tools may still use the network.
- [x] Test-only deterministic scenario fixture — exercises policy and tool plumbing without a model; not packaged or selectable in production
- [ ] External runtime adapters (Pi, OpenCode): currently fail closed. Offline bounded protocol helpers exist; process I/O drainers, loss-recoverable OpenCode events, permission brokering, sandboxed process ownership, shared budget reservations and route/session mapping are required before re-enabling.
- [x] Reviewed, owner-launched OpenCode CLI coding task: durable chat handoff, pinned isolated Git worktree, restrictive task profile, bounded iterations, verified process cleanup; no Hutch-managed runtime, brokered OpenCode approvals or Hutch usage cap
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
- [~] Guided new-Bot setup can preview, download, and import a strictly validated versioned YAML draft. Import fills an unsaved draft that still requires full review and explicit creation; importing or snapshotting existing Bot definitions remains open.
- [ ] Secret per-bot credentials via OS keyring (referenced, never in prompts)

## Phase 2 — capability

- [ ] Vector memory (local embeddings, sqlite-vec) with inspectable recall
- [ ] Webhook/event triggers (file-watch, HTTP inbox) alongside cron
- [ ] Multi-step workflow templates (chained runs, hand-off artifacts)
- [ ] Pi/OpenCode adapters: match published RPC/CLI contracts; broker approvals and provider budgets; strict process containment
- [~] Bounded same-bot `delegate_task` preview: Strict Offline and process-executor only, always human-approved, private child workspaces, task-text-only context, bounded depth/steps/time and inherited usage reservations. Parallel children, specialist selection, artifact transfer, cross-bot delegation and a plan UI are not implemented; see `realignment/delegation.md`.
- [~] Browser tool: same-session human handoff is experimental on a local Linux desktop; HTTP(S)/WebSocket DNS-pinned egress has local Chromium fixture coverage. Bounded HTTP handoff is locally verified with a process worker. Live headed challenges, non-HTTP traffic, physical phones and general download formats remain open. Immutable-ID profiles, reviewed workspace text uploads and bounded same-origin HTTP text downloads have real mixed-workflow coverage.

## Phase 3 — scale-out (deliberately far)

- [ ] Cross-OS support (macOS, Windows) — GUI automation paths differ per OS
- [ ] Multi-user access to one hutch instance (auth + roles)
- [~] Optional private phone supervision (passkeys over Tailscale Serve or trusted LAN HTTPS) — opt-in, remote remains disabled by default; live mobile/network validation and any broader relay access remain open
- [ ] A2A collaboration between bots (scoped, auditable)

## Current realignment progress

- **Database restore: isolated workflow implemented.** Schema v14 validates snapshots in a new
  private directory, detaches source process records, quarantines old work and holds new execution
  for local review. Device sessions/standing grants are revoked and schedules paused. Snapshot
  scope excludes credentials, profiles and user files. Production service cutover and power-cut
  certification remain separate verification gaps; this is not rollback of external effects.
- **Conversation persistence: partial.** Schema v8 stores canonical messages and maps runs to conversations. Historical runs are
  imported separately. The local v1 API snapshots at most 12 prior messages / 16,000 characters for builtin runs and supports
  FTS5 search. Studio exposes search from one compact header action: a POST-body query returns bounded excerpts from active,
  non-legacy chats, can be narrowed to one Bot, and opens the selected conversation without putting terms in the URL. The older GET
  search route remains compatible. The Studio selects threads, displays restart-persistent history and archives without deleting it. Bounded JSON export
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
  verification limits. Exact OpenAI host matching now selects its token-limit field. Schema v37 adds passive, immutable
  positive tool-call evidence from owned, usage-reserved Bot runs, bound to exact route revision and exposed through
  bounded `GET /api/v1/model-capabilities`; absent evidence remains unknown and no paid probe is run. Offline tests cover unsupported host isolation,
  hosted routes and overrides, endpoint validation, tool omission, environment scrubbing, a local-only
  namespace probe, and a fake-provider request through the broker. Live model/backend provenance remains unverified.
  fields, auth/quota rejection, held uncertain usage and the outward approval required before switching paid routes;
  live billing behavior remains unverified.
- **Action review: local fixtures.** Schema v13 retains immutable intents and separate operator
  reconciliation. Uncertain receipt sealing is transactional; chat and Needs you surface review.
  Same-conversation repeat guards and bounded current builtin context notes are implemented.
  Browser/external-runtime authority gaps and live effect verification remain open.
- **Phone supervision: experimental.** A one-use host code enrolls a user-verified passkey, then a paired phone can monitor runs,
  review approvals, Stop/Resume, and optionally start locally enabled Bots. Remote access requires explicit private HTTPS configuration;
  Tailscale Serve or trusted LAN TLS are documented. Session/route/CSRF/queue boundaries have automated coverage, including a real
  Uvicorn HTTPS test. iOS/Android and live-network validation remain open; bounded HTTP computer step control is locally verified; physical-phone input and public gateway access remain unverified/unsupported.
- **Release posture.** Source is private and unpublished. A paired device cannot keep a sleeping host running or reach a service after
  disconnection.

## Non-goals

CAPTCHA solving, bot-detection evasion, acting as a hosted service, or autonomy without
supervision. These conflict with the product's premise.
