# Changelog

All notable changes to hutch (formerly "openbot"). Format follows Keep a Changelog; versioning is semantic.

## [Unreleased]

### Added
- **Canonical conversation persistence and v1 API (partial):** schema v8 imports each old run into a separate legacy conversation;
  new conversation/message/archive commands use atomic `Idempotency-Key` records and reject key reuse with changed arguments. Run
  admission snapshots up to 12 prior messages and 16,000 characters for the builtin runtime. FTS5 searches messages explicitly;
  search results are not injected into prompts. Studio supports durable thread switching and archive. Global event replay and remote
  pairing remain open.
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
