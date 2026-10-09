# Changelog

## Dashboard accent polish (2026-10-09)

- Replaced the remaining one-sided accents on specialist checkpoint rows and quoted chat replies with subtle full outlines. Reply tests now use the professional Bot display name exposed by the interface and assert the quote's balanced border.

## Scoped fact memory continuation (schema v15, local)

- Replace automatic per-bot fact/system injection with explicitly retrieved, human-reviewed chat facts and bounded FTS5.
- Fence proposals against expired/lost ownership, cancellation and terminal state. Preserve immutable revisions and reviews; sharing is explicit and never crosses bots.
- Show review/revision/archive in chat and paginated management while memory is disabled. Archive retains history and backups; permanent scoped deletion remains pending.
- Import legacy facts as unreviewed and unscoped, preserve pre-upgrade backups, and verify fact hashes during held restoration.
- Correct the typed resource-change contract to accept restore-state invalidations introduced in schema v14.

All notable changes to hutch (formerly "openbot"). Format follows Keep a Changelog; versioning is semantic.

## [Unreleased]

### Added

- Schema v34 adds one owner-confirmed fresh attempt from a tightly gated checkpoint for failed/stopped built-in coordinator tasks. The new run gets only the reviewed task brief/constraints and the latest committed assistant text as untrusted progress; prior actions, receipts, selected facts, credentials and tool results do not transfer. Unknown effects, any recorded action, newer specialist work, pending questions, changed permissions, external runtimes and archived chats stay blocked. Exact retries are idempotent. This is not process resume and may use additional model quota.
- Purpose-based Bot names now preserve common hyphenated phrases, ignore trailing request clauses, and use an organizer label for organization requests; suggestions remain local, editable, and stable-address-aware.
- The workspace coordinator now has scoped task-drafting guidance and a clearer specialist review: the operator can edit the goal, add an expected deliverable and constraints, inspect the specialist's saved settings, and confirm dispatch while the source request remains linked. Task wording cannot grant access; live model drafting quality remains unverified.

- Experimental Outlook Calendar read access now uses a local public-client PKCE sign-in, Linux Secret Service refresh-token storage, and one selected-calendar grant per Bot. The tool returns bounded title, time, and location fields only. Microsoft consent remains account-wide and must be revoked in Microsoft settings; no live account or consent has been verified. Outlook Mail and calendar writes are unavailable.
- Studio Bot creation now takes four reviewable screens. It reuses the selected latest chat request, suggests an editable purpose-based name and address, carries a configured chat/workspace model route forward, and starts with a managed workspace, no tools and no schedule. Optional capabilities and limits remain available before a complete review; saving still starts no run.
- Schema v32 lets the owner optionally select up to eight current reviewed facts from the coordinator Bot or exact coordinator chat during specialist task review. The exact values and provenance are stored with that task and passed as untrusted run context, never specialist saved memory; the UI previews the serialized 6,000-character bound and warns that provider-retained copies cannot be recalled.
- Schema v31 adds a bounded, append-only, content-free progress timeline for reviewed coordinator-to-specialist tasks. Existing task markers are backfilled from committed events; new markers are written transactionally from the child run's event stream and linked to the task/run. Checkpoint rows reject in-place edits, while deleting the owning task removes its timeline. API responses include the materialized total and latest 16 markers, and the chat task card presents them. This is an audit timeline, not restart continuation: there is no resume action, and unknown effects still require reconciliation. Hidden reasoning, prompts, action arguments, tool output and secrets are not copied into checkpoints.
- Schema v29 adds an experimental coordinator-to-specialist task handoff. The user reviews the selected specialist, its saved model/tools/action policy/workspace, an editable task brief, and optional assumptions before dispatch. The durable parent timeline keeps the source request, coordinator draft, reviewed brief, target settings snapshot, task status and latest specialist reply; opening the specialist chat remains a direct route. Only the reviewed brief and assumptions enter the child conversation, while that Bot's own enabled memory and workspace still apply. Exact retries replay safely, changed payloads conflict, and changed specialist settings fail before execution. Schema v30 lets the user attach one exact successful specialist response to a coordinator follow-up. The immutable transcript/export link records the task and source message, and only a bounded JSON-escaped response enters that run as untrusted context; files, credentials, permissions and memory are not shared. Live external-provider execution, specialist allowlists, resumable checkpoints and plan-level cancellation remain pending.
- Bots now have a human-facing display name separate from their stable local address. Guided setup proposes both from the stated purpose using a deterministic local rule; names remain editable and reviewed, and no model request or run is made for naming. The CLI accepts `--display-name`, and legacy slugs get readable labels. Schema v28 persists workspace coordinator selection; Bot settings can assign that role, the selected Bot opens as the default Studio chat, and the roster marks it.
- Experimental Google Calendar lookup is available when the operator configures a Desktop OAuth client and Linux Secret Service. The local PKCE flow stores refresh credentials outside SQLite; each Bot is restricted by Hutch to one selected calendar and can read only bounded event titles, times and locations. Google grants account-level read-only scope, and no live account/consent-screen check or event write is claimed. Gmail remains unavailable.
- Built-in conversation runs can ask durable single- or multi-select questions in Studio. Schema v26 stores the immutable prompt/options and answer link; a selection submits a normal, idempotent user turn and cannot approve or authorize an action. The public workflow page qualifies this as built-in chat behavior. Mixed provider tool-call batches are rejected before execution. OpenCode/Pi and final release validation remain unavailable or pending.
- Studio's composer model picker marks alternate routes as one-message, conversation-scoped overrides and clears them after an accepted send. A separate **Save as Bot default** action validates and updates the Bot route used by later chats and scheduled runs.
- Preferences can set a validated workspace model route and inference mode for new Bots. Chat-sourced and workspace-default choices remain editable in the setup draft; an explicit choice wins. Changing this preference leaves existing Bots, conversations and runs unchanged.
- Studio's New Bot flow can seed an editable draft from the latest user message in the active chat. A configured non-mock model route from that chat's Bot is an editable suggestion for the new Bot's saved default. The user can opt out; Hutch copies no other conversation turns, persists the original request provenance, and still requires review before saving. It creates no run and does not infer permissions or account access.
- Studio conversations can reply to a specific Bot message. The composer shows a removable, bounded reference; same-chat scope, untrusted quote labelling, stable idempotent retries and transcript/export provenance are enforced by schema v25.
- Experimental local Linux browser handoff now blocks agent typing into detected credential, OTP, payment-secret and token fields before input or durable action creation, redacts browser type values from events/receipts, and prevents screenshots while a conventional sensitive field is visible. People can enter credentials and complete CAPTCHA/2FA directly in the same live browser profile, then resume the current wait without a page reload; Hutch never types secrets or solves challenges. The field detector and live third-party path are not exhaustive or verified.
- Document the Grok Bot message-first named-Bot and coordinator workflow as a product reference. Record Hutch's context-aware task-brief requirements, explicit authority boundaries, durable cross-Bot result delivery, user-reported organization complaints, and the decision to retain per-Bot workspace/browser isolation. No Grok Bot account or live integration was tested.
- Experimental reverse-proxy HTTPS support now requires an explicit trusted proxy address/CIDR, exact public-host allowlist and HTTPS
  forwarding. Untrusted forwarding metadata is stripped, malformed public hosts are rejected, and the capability API exposes the
  configured-but-fixture-tested status. HTTP and WebSocket Origin schemes must match normalized HTTPS. Hutch still does not provision
  a tunnel or claim live remote validation.
- Studio can download a bounded conversation JSON export after showing its scope. It contains whitelisted metadata and ordered message text/provenance; the manifest explicitly excludes credentials, receipts, workspace content, artifact bytes and memory, and warns that message text is copied verbatim.
- Bots can own up to 100 independently timed recurring tasks, each with its own name, timezone,
  catch-up policy and prompt. Settings, per-task v1 CRUD and `hutch bot schedules` manage them;
  older schedule fields remain aliases for the first task. Schema v20 separates occurrence claims
  by task, and schema v21 keeps removed task IDs reserved so occurrence history cannot be reused.
- The marketing workflow now describes named recurring tasks, and the settings journey has
  inspected desktop, tablet and phone captures for add, edit, remove and primary promotion.
- Versioned standalone run submission at `POST /api/v1/tasks/runs` now requires an idempotency key and stores the run, task and replay result atomically. Exact retries return the original run, changed requests conflict, and the legacy run route remains available as a compatibility alias.
- Versioned human resume now requires the current `human_needed` event sequence, a live owner lease and an idempotency key. Each wait episode can be resumed once; stale requests and a second device cannot replay an old click to resume a later challenge.
- Studio chat now places Resume beside the current human-needed event and submits its sequence through the versioned API. Earlier challenges stay visible without an active Resume action; accepted requests show a clear pending state and retries reuse the same per-wait key.
- OpenCode Go Connections now explain the provider-issued API-key handoff without reading OpenCode's private auth files or reusing its login session. Connections also include an opt-in, eligibility-unconfirmed Sign in with ChatGPT preview using PKCE/OIDC, account-specific reauthorization hints, a protected local account store and a fixed streaming Responses API route; local functions use the preview's `additional_tools` input format. Provider-enforced output limits are unavailable, so usage allowances remain estimates.
- Transcript file-delivery intents are now recorded once per committed event batch in the same SQLite transaction. Schema v16 removes the per-event trigger without changing crash recovery, visible delivery errors or FULL-sync behavior.
- Bots can use a fresh workspace per run, a private Hutch-managed workspace shared across that bot's runs and chats, or a validated existing folder. The default remains fresh; managed files survive bot deletion and are excluded from database-only backups.
- Executor health uses a steady status mark with text and connection-state changes instead of a decorative pulse between health checks.
- Studio's working dots now stay steady while the visible label carries the state; server-rendered page headings use a roomier 1.4 line-height.
- Server-rendered live/reconnecting status now uses a steady dot; the text reports connection changes without a continuous pulse.
- Successful `write_file` actions now expose immutable, SHA-256-verified downloads directly in Studio chat without expanding tool details, up to 4 MB per file and 16 MB per run.
- Experimental phone/browser pairing now has a real `/pair` exchange page, a compact paired-device manager in Connections, current-device status, and one-click revocation with a safe self-revoke return. Device session and pairing responses have explicit v1 schemas; the marketing site now describes this path as experimental.
- Optional, user-enabled browser notifications now bring a generic Needs you alert to a background tab. They disclose no chat, bot or action details, and work only while the Hutch tab remains open.
- Full tool outputs clipped from model context are now immutable, run-scoped artifacts with recorded size and SHA-256. The chat provides a direct download; a bounded typed API lists versions, and downloads refuse missing, symlinked, oversized or hash-changed content.
- Per-tool output caps are configurable through the bot API. When output is clipped for model context, Studio shows a source card for the complete verified artifact; opening it serves inert plain text through a hash-checked compatibility route. Artifact limits are 4 MB each and 16 MB per run.
- Owners can explicitly share a verified artifact reference to a selected other chat. Both the source and receiving chat show the active grant and can revoke it; the target gets a provenance-labelled Files entry and a target-bound download. Bytes stay in the source run and never enter the target workspace or model context.
- Experimental `delegate_task` is an explicit per-bot opt-in for the supervised built-in Strict Offline Linux executor. Each child request always pauses for human approval, receives only its task text, gets a private per-run workspace, and inherits the immutable root capability and budget limits. Depth, lifetime child count, steps and duration are bounded; Stop cascades through the lineage. The default global limit supports one child at a time. External runtimes, parallel public child calls and automatic artifact/file transfer remain unavailable.
- Schemas v22–v24 add immutable same-bot run lineage, inherited tree-budget reservations, cancellation intent and a credential-free capability snapshot. The experimental child tool uses these controls only through the supervised Strict Offline Linux executor; historical rows without a snapshot remain ineligible.
- Experimental per-bot `offline` inference mode. Linux workers run in fresh bubblewrap namespaces, including verified network and PID isolation, and send model HTTP through private per-run Unix-socket brokers fixed to configured numeric loopback endpoints. The local IPv4/IPv6/PID probe and fixture Ollama request pass here. Browser/web-fetch tools are removed, provider/proxy environment is scrubbed, and saved connection/key files are masked inside workers; live model-server behavior and provenance remain unverified.
- Per-bot local model-route and Hybrid controls in Settings, the API, and CLI. Local-route mode
  filters hosted models and blocks hosted message overrides/fallbacks, including recognized
  Ollama cloud-tagged names. This setting does not promise strict offline behavior; local services
  and network-capable tools can still use the network.
- Legacy bots on the unavailable Pi or OpenCode executor can be moved to Hutch's built-in runtime
  from Settings after a valid Hutch model route is saved. The API accepts only `builtin`, refuses
  the switch while any run is active, and does not import credentials or sessions from either CLI.
- Marketing headings now describe model choice, approvals and stop cleanup directly; refreshed
  desktop, tablet and phone captures record hashes for the final website source. Fixed a stale
  stylesheet cache tag and added a regression check for local asset hashes.
- A versioned provider compatibility matrix is available at `/api/v1/compatibility`; it separates
  route-level fixture support from unverified endpoint/model capabilities and lists dated sources.
- OpenAI's `max_completion_tokens` is selected only for the exact official HTTPS API host; other
  OpenAI-compatible endpoints use `max_tokens` even when their URL contains a lookalike string.
- Generic provider field errors no longer trigger a duplicate non-streaming request; that recovery
  is reserved for errors that identify streaming/SSE incompatibility. Uncertain charges remain
  reserved, and a different paid route still waits for outward approval.
- Bots may opt into a same-session visible browser handoff on a Linux desktop. Login challenges
  pause only when the person can use that owned browser; Resume reloads and rechecks the challenge.
  Cross-process leases protect each bot's profile and the single local handoff slot. Settings show
  the current host capability reason and headless runs fail clearly. HTTP(S) and WebSocket traffic
  now goes through an owned loopback proxy that re-resolves and pins each connection to a checked
  public address; local Chromium tests cover rebinding across a redirect. Live public destinations,
  non-HTTP browser traffic, headed challenges, and phone handoff remain unverified or unavailable.

### Fixed

- Coordinator task-review request and quoted-answer blocks use quiet full outlines instead of side-tab accent stripes, with responsive evidence at desktop/tablet/phone widths.
- Stopping a delegated run now atomically marks its persisted descendants for cancellation before cleanup begins. The supervisor signals every owned descendant process; queued descendants stop immediately, while owned work remains visibly Cancelling until cleanup is verified. A racing child submission is either included in the cancellation tree or refused by the parent's stored cancel intent.
- Delegated children run only after a fresh outward approval, in a private 0700 per-run workspace with the immutable root capability and budget snapshot. They receive task text only; no parent transcript, browser, host folder or automatic artifact transfer is inherited. Dispatch and parent cancellation remain supervised, and historical children without a capability snapshot fail closed.
- Schema v14 restores database snapshots into a new private directory with old work quarantined,
  original process identities detached from cleanup authority, device sessions revoked and
  schedules paused. Submission, worker and supervisor claims refuse execution until a local
  operator review is recorded. Restoring never signals or modifies source processes. Snapshot
  hashes, migration, transcript/intent validation and installed executor/UI fingerprint checks
  precede activation; credentials, browser profiles and user files remain separately backed up.
- Schema v13 snapshots arguments and reviewed authority before an effect, requires an unexpired
  fence for owned receipt writes, and atomically seals missing receipts with Needs review.
  Receipt storage failure stops further tools. Immutable operator reconciliation records checked
  outcomes separately; it preserves the original status and event chain. Chat and the paginated
  Needs you drawer retain uncertain actions, including historical Done runs with receipt gaps.
- Matching uncertain effects in the same conversation require reconciliation before a new attempt
  can repeat them. The builtin runtime reads bounded current receipt guidance at execution;
  unrelated private conversations retain separate contexts. Legacy arguments remain explicitly unknown.
- Schema v12 enqueues JSONL delivery with committed events, verifies file prefixes and retries
  after restart without duplicate rows. Damaged mirrors are preserved before reconstruction;
  pending errors stay visible without changing a Done run. Delivery is bounded and joined before
  database closure. FULL WAL synchronization makes action prerequisites durable before admission,
  subject to storage honoring synchronization; live power-cut certification remains unavailable.
- Provider settlement/release requires unexpired worker ownership and cannot change the reserved
  run, bot, model, provider or account. Changed duplicate settlement conflicts; uncertain usage
  requires explicit reconciliation. Unresolved holds stay counted across midnight/quota rollover.
- Admit a worker approval and its waiting state atomically. Refuse full-request overwrites and
  expire decisions for lost/stopped execution before they can grant standing permission.

- Queued messages cannot replace an executing or waiting conversation attempt as the main Stop
  target. Older active approvals stay visible beyond the chat window; failed refresh retains
  review details with Retry instead of hiding the control or reporting completion.
  Header Review brings an older request into view; phone attempt labels wrap without clipping.

- Expired leases cannot renew or authorize owner actions, approvals, reservations, progress or
  status changes before recovery. Buffered worker replies validate ownership at commit, and late
  receipts cannot overwrite uncertain outcomes. Worker startup refuses an expired claim.

- Join worker signal listeners on completion and execution errors, and join cancellation cleanup
  before terminal status. Serialize cleanup verification so a stale survivor report cannot win.
- Refuse database closure while the event writer remains alive; preserve its connection and allow
  closure to be retried after it exits. Closing state refuses new buffered events.
- Stop expires pending approvals in its cancellation transaction; later requests expire immediately
  and stale workers cannot admit a new request.
- Remove the production mock runtime and `hutch demo seed`; `hutch init` now creates only state,
  and bot creation requires an actual configured route. Existing mock-route records remain readable
  for audit but fail before worker/action start with an actionable `model_unavailable` result. The
  deterministic scenario runtime is test-only and excluded from built wheels. The website now
  shows an inspected empty first-run capture instead of seeded mock runs or scripted approvals.
- Check restore execution hold before route validation in CLI/API run requests, so held restored
  state reports the required review step even when its historical bot has no usable model route.

### Added
- **Transactional resource replay:** schema v11 adds content-free invalidations with typed pages/SSE,
  history cursors, gap detection and consistent snapshot reconciliation. Silent process commits
  remain replayable; chat/attention updates preserve drafts and focus. Approval admission includes
  its inline review event, and canonical decisions survive a missing worker response. The separate
  JSONL mirror uses schema v12's separate recoverable delivery; no remote-support claim is added.
- **Bounded local inference:** one caller and eight FIFO waiters across Hutch processes. The slot
  releases before tools/human waits, Stop removes queued callers before reservation, and kernel
  ownership expires on process death. Native Ollama rechecks measured memory headroom; fit remains
  estimated and other local protocols lack validated memory admission. Recorded queue time is
  separate from Hutch overhead; chat shows the wait reason. Strict offline modes remain pending.
- **Provider authority and retry accounting:** hosted account/destination changes require a
  per-run outward decision, including from a hosted primary. Reviewed routes cannot change
  during approval or provider creation. Cached credentials refresh before calls; the unsafe
  legacy routing override is removed and basic credentials in endpoint URLs are refused.
  A failed stream retains uncertain usage and each retry reserves another attempt.
- **Exact-action and history repairs:** file approvals bind contents, destination and revision;
  descriptor-based writes refuse symlink or changed-revision destinations. Browser mutations
  bind text, URL and profile and always ask. Strict extra mounts retain their read-only grants
  and reject credential-containing ancestors. Final assistant messages and terminal status commit
  together; sealed runs reject stale reply mutations. See the realignment continuation ledger.
- **Conversation-first navigation:** one bot roster and settings destination; inline action decisions
  and a cross-bot Needs you drawer. Monitor contains Activity/history, with filtered Fleet at ten bots.
  Human and approval waits remain visible during queue-discovery failures; phone reminders occupy
  their own layout row, and an older queued turn cannot hide already executing work.
  Legacy navigation aliases preserve browser Back. Drafts belong to their conversation, stopping bots
  show “Stopping,” and queue failures retain requests. Approval commands carry immutable hashes and
  idempotency keys; expiry waits for server confirmation. See `docs/realignment/navigation.md`.
- **Shared provider usage reservations (partial S5):** schema v10 atomically reserves per-bot tokens, per-run/per-bot currency estimates,
  and configured shared-account quota/cost limits before builtin hosted calls. Successful replies settle actual usage once; uncertain
  outcomes stay held until a terminal run is reconciled from the provider record. Connections page and `/api/v1` expose held values.
  Currency checks are estimates and do not guarantee the provider's final bill. Pi/OpenCode remain disabled; live billing is unverified.
- **Repeatable performance evidence:** the benchmark runner now retains raw repetitions and host/revision/harness metadata; the
  pre-realignment archive and current branch have same-harness captures with a data-quality notebook and explicit sampling limits.
- **Marketing evidence:** remove seeded mock-run imagery and scripted approval controls; replace the product preview with an
  inspected capture of the real empty first-run UI and verify it at desktop, tablet and phone widths.
- **Global transcript replay:** `/api/v1/events` provides bounded cross-run pages and `/api/v1/events/stream` resumes with
  `Last-Event-ID`. A missing or future cursor directs the client to a bounded consistent snapshot and a replay watermark.
- **Canonical conversation persistence and v1 API (partial):** schema v8 imports each old run into a separate legacy conversation;
  new conversation/message/archive commands use atomic `Idempotency-Key` records and reject key reuse with changed arguments. Run
  admission snapshots up to 12 prior messages and 16,000 characters for the builtin runtime. FTS5 searches messages explicitly;
  search results are not injected into prompts. Studio supports durable thread switching and archive. Versioned stop and approval
  resolution also use idempotency keys. `/api/v1` now includes sanitized connection metadata, schedules, explicit capability records,
  and cross-run transcript replay with bounded snapshot reconciliation.
- **Experimental remote pairing:** schema v9 adds single-use 60-second pairing codes and hash-only, revocable device sessions with
  sliding 30-day expiry. Direct off-loopback binding requires `--allow-remote` plus TLS certificate/key. Pairing attempts are
  rate-limited; the phone UI, live control routes, tunnel support and device validation remain unavailable.
- **Fail-closed external runtimes:** legacy Pi/OpenCode selections now stop before spawning a subprocess because their permissions,
  process containment and provider-budget paths are not governed. OpenCode `--auto` and the broken Pi RPC adapter are removed from
  the execution path. Browser profiles and contexts are instance-owned per bot; fixture tests verify separate profile directories.
- **Phone menu keyboard control:** the Studio navigation now keeps Tab inside its full-screen mobile menu, moves focus to the first
  link on open and restores focus to the toggle on Escape. Added a browser regression test and saved desktop/tablet/phone captures.
- **Owned run cleanup and recovery:** production CLI, web, and daemon attempts use worker processes; recovery atomically fences expired
  owners before signalling; process records carry boot/start identity and pidfd cleanup never signals a reused PID/PGID. Incomplete
  cleanup remains visible and retries instead of claiming the run stopped. A leased supervisor coordinates schedule/recovery work.
- **Bounded shell execution:** captured stdout/stderr is drained into a fixed buffer; Linux strict mode uses bubblewrap plus a
  delegated systemd cgroup and fails closed. SQLite migrations serialize across processes, use the online backup API, and have a
  tested restore path. Store shutdown joins registered engine workers before closing the database.
- Composer options collect suggestions, rehearsal and Enter behavior beside the model selector;
  rehearsal labels disclose model calls and reads. Canonical messages, approvals and idempotent
  Stop survive the shared-checkout merge. Options restore focus on Escape; phone primary controls
  have 44px targets, cancelled notices use the actual status and recorded queue time remains visible
  without completed model steps.
- **UI-complaint research** ([docs/research/complaints.md](docs/research/complaints.md#7-ui--interface-complaints-design-signals)):
  documented interface failures across shipped agent UIs — Claude Code's saturated-on-black
  regression, ChatGPT accent churn, Codex role ambiguity, colour-only status dots — with a
  traceability table for the dashboard.
- **Design system** ([docs/design-system.md](docs/design-system.md)): one set of WCAG-AA-verified
  tokens (surfaces, text roles, semantic status colors, radius/type/spacing/motion scales) shared by
  the dashboard, marketing site, and legacy SPA; documented component anatomy for tool lines,
  approval gates, status chips, budget meters, empty states, dialogs, and toasts.
- **Emoji audit gate**: `scripts/audit_emoji.py` (improved Python port of varve's audit-emoji.mjs —
  HTML-entity, escape-sequence, and surrogate-pair detection; greppable waivers) wired into `pytest`
  via `tests/test_emoji_audit.py`. Pictographic emoji and icon-like text characters are banned;
  UI iconography is inline SVG only.
- Runs view: wired status filters and search (previously rendered with no listeners), shareable
  `#/runs?status=…&q=…` state, "show more" pagination, keyboard-operable rows, distinct empty states.
- **Studio shell truthfulness + a11y**: the whole `<main>` is no longer a live region (it announced
  the entire page on every poll); announcements go through a bounded `#live-status` region that
  reports lifecycle changes only — run started/waited/finished, approval required, connection lost.
  The daemon badge no longer claims a hardcoded "live": health is established from `/api/health` with
  a heartbeat and degrades to `reconnecting`/`offline`. A 3-dot working indicator shows while a bot is
  actually computing (never for a waiting-for-human run). Contract tests in `tests/test_studio_shell.py`.
- **Run status labels**: the Studio and server-rendered run lists show lifecycle labels such as
  “Stopping” while owned cleanup is underway. Queued, resource-waiting, recovery and cancellation
  states remain active in the UI; an unknown future status stays visible until the server provides
  its label and terminal bit.
- **Approval review + app-wide attention**: the chat feed and the approvals queue share one
  approval card — the action in plain language first, a "Review details" disclosure (tool, why you
  are asked, reversibility, parsed segments, raw request), the exact scope of an "always allow"
  grant with a pointer to revoke it, and no always-allow for outward actions. Decisions are
  server-authoritative: a stale click that loses a cross-device race reconciles against
  `GET /api/approvals/{id}` and shows who actually decided. Client expiry disables controls while
  checking the persisted outcome. The Needs you drawer carries the count throughout the app,
  and a new arrival is announced once through the bounded live region. Queue + "Recently decided" (`?status=resolved`) refresh across
  devices every 5s. Browser coverage: `tests/e2e/test_browser.py::test_a_stale_approval_click_shows_the_other_devices_decision`.
- **Reference map** ([docs/research/reference-map.md](docs/research/reference-map.md)): verified
  this session against the Grok Bot changelog (v0.68.1) and the two Open WebUI issues (#31656
  closed, #30055 open) — observed patterns, evidence, Hutch equivalents, and the deliberate
  decisions, with the unverified gaps stated. This pass' typing label follows the reference
  (the bot's name is dropped from the working status).
- **Marketing site signature system**: an intro stage, a poster wordmark the hutch character passes
  through (two exactly-registered layers with the subject between them), an aurora-light character with
  a geometric line face, neural connection lines, a live status pill, a scroll-linked receding hero
  heading, spotlight cursor tracking and morphing glows on the bento cards, and a hover-revealed action
  on each project card. All motion is removed under `prefers-reduced-motion` (intro deleted, reveals
  forced visible, zoom/parallax off). Browser tests in `tests/e2e/test_website.py`.

### Changed
- **Dashboard (server-rendered): monochrome-first pass.** Retired the tinted status fills and the
  violet token; state now reads as glyph + word + a 6px dot or a 2px rail, and the one softened
  emerald accent is reserved for the primary action and the active nav. Restrained serif page title,
  12px panels, calmer density; `aria-current` on the active nav, `aria-live` on the live pill, and a
  labelled approval badge. Direction in [docs/design-system.md](docs/design-system.md).
- **Legacy SPA studio + marketing site: monochrome-first alignment.** The studio's `-bg` tint tokens
  are neutral and violet is retired (tool names, memory keys, the third bot-avatar hue), with the
  decorative dot-grid gone and 12px panels; the site drops `--violet` and moves labels to sentence
  case. All three surfaces now share the retired-violet / neutral-tint rule.
- **Studio feed** (legacy SPA): tool call/result pairs merge into compact expandable one-line entries;
  4+ steps collapse under a "tool steps" group; expansion persists per run; run errors are alert rows.
- **Approvals**: live fail-closed TTL countdowns everywhere (previously static text), flipping to
  "expired — denied"; consistent amber gate card across studio feed and approvals queue.
- **Composer**: per-bot daily token budget meter (amber >= 70%, red >= 100%), icon send button,
  Up-arrow recall of the last prompt.
- **Dialogs/toasts**: `role=dialog` modals with focus trap, Escape/backdrop close, and focus
  restoration; `window.confirm` replaced by styled destructive confirms; toasts gained dismiss
  buttons and errors persist until dismissed.
- **Marketing site**: tokens aligned with the dashboard (AA text roles), comparison-matrix negatives
  calmed from a wall of red pills to quiet metadata, one primary action per viewport, 14px code
  windows, lowercase brand casing throughout, skip link/`<main>`/focus rings/reduced-motion, and an
  accessible mobile drawer (`aria-expanded`, Escape, focus return).
- **Server-rendered dashboard**: token values aligned onto the shared system (obsidian surfaces,
  12/8px radii, emerald focus rings) without structural changes.
- **Hero gradient-text bug fixed**: `filter` + `background-clip: text` on the same element painted the
  whole text box as a solid block in Chromium (visible in the pre-change baseline). The heading now
  falls back to a solid accent and only applies the clipped gradient inside `@supports`.
- **Stale browser tests re-pointed at the single UI** (the server transcript/overview pages redirect
  into the SPA since 27a73ed): the phone approval journey now targets `#/approvals`, and a live SPA
  transcript journey replaces the retired server SSE DOM test.

## [0.1.0] — 2026-10-07

First MVP.

### Changed
- **Renamed the project openbot → hutch** before any public push: "openbot" is taken on PyPI and
  collides with unrelated GitHub projects. Candidate research (PyPI, GitHub, web/marketing) in
  [docs/research/naming.md](docs/research/naming.md); `botshed` documented as fallback.

### Added
- Bot management: CRUD, starter templates (research-briefing, repo-sweeper, tidy-downloads),
  pause/resume, per-bot memory and sticky tool allows — via CLI, dashboard, and REST API.
- Runtimes: built-in agent loop (OpenAI-compatible: OpenAI, Ollama, llama.cpp, LM Studio, custom
  base URLs), deterministic mock runtime (offline demos/tests), Pi adapter (RPC stdio), OpenCode
  adapter (headless run).
- Tools: workspace-jailed shell (scrubbed env, HOME redirect), path-jailed file read/list/write,
  SQLite-backed memory, SSRF-guarded web fetch, optional Playwright browser with persistent
  per-bot profiles and pause-to-human on login/CAPTCHA walls.
- Safety: compound-command policy engine (deny/ask/allow) with secret-path, escalation,
  pipe-to-interpreter and exfiltration denylists; fail-closed approvals with sticky always-allows.
- Scheduling: IANA-timezone cron with DST-gap/ambiguity handling, catch-up coalescing or visible
  skip, per-bot single-instance locks.
- Engine: run dispatch with global concurrency, per-run hard caps (steps, wall clock, daily
  tokens), stop/stop-all, append-only transcripts (SQLite + JSONL).
- Interfaces: Typer CLI (`hutch`), FastAPI dashboard with live transcripts/approval queue/spend
  meters, headless daemon, `demo seed` for offline exploration.
- Docs: architecture (decision log), safety model, bot-config reference, roadmap, and incident
  research with requirement traceability.
- Tests: 70 tests covering the safety parser, DST math, engine lifecycle, API, and CLI.
- **Design system → brutalist-modern (Oct 2026):** neutral `#0a0a0a` cards with a 1px glass
  ring; accent blue `#52a8ff` for active states and success green `#62c073` for positive
  indicators; square (0px) buttons, 100px pill chips, monospace data rows; a subtle radial
  accent glow; and a full-screen mobile menu for the header nav on the app, server dashboard
  and marketing site. The site also gains scroll-reveal animations, floating parallax cards and
  a stacked text echo. See [docs/design-system.md](docs/design-system.md).
- **Studio → whole app + data viz:** the chat SPA is now self-contained with an **Overview** triage
  view (`GET /api/overview`), a **bento** Bots grid, and a **Timeline** column on the Runs table
  (per-run duration bars, blue/amber/red). See [docs/design-system.md](docs/design-system.md).
- **One UI:** the duplicate server pages redirect into the studio SPA; run detail gains a KPI bento
  and a model/tools/hutch timing timeline. See [docs/design-system.md](docs/design-system.md).
