# Roadmap

## Phase 0 — MVP (shipped, Oct 2026)

- [x] Bot CRUD + starter templates (CLI, dashboard, REST)
- [x] Built-in agent loop (OpenAI-compatible: OpenAI / Ollama / llama.cpp / LM Studio / custom base URL)
- [x] Deterministic mock runtime — full pipeline offline, no API key
- [ ] External runtime adapters (Pi, OpenCode): currently fail closed. Permission brokering, sandboxed process ownership, bounded I/O and shared budget reservations are required before re-enabling.
- [x] Tools: shell (workspace-jailed, minimal env, HOME redirect), files (path jail),
      memory (SQLite facts), web_fetch (SSRF guards, clipping), browser (Playwright optional,
      persistent per-bot profiles, pause-to-human)
- [x] Policy engine: compound-command parser, deny/ask/allow, secret-path + egress denylists,
      URL scheme/private-range guards
- [x] Human-in-the-loop approvals: fail-closed TTL, sticky always-allows, dashboard + CLI
- [x] Scheduler: IANA-timezone cron, DST-gap/ambiguity handling, catch-up coalescing,
      skip policy with visible markers, per-bot single-instance lock
- [x] Caps: max_steps, wall-clock kill, daily token cap
- [x] Append-only transcripts (SQLite + JSONL per run), staleness surfaced in dashboard
- [x] Dashboard (live transcripts, approvals, meters, stop) + CLI + daemon
- [x] Test suite (70 tests) covering safety parser, DST math, engine lifecycle, API, CLI

## Phase 1 — hardening (next)

- [ ] Container-per-run isolation (podman/docker) as an opt-in sandbox level
- [ ] Configurable policy packs per bot (site-specific allowlists, egress domains)
- [ ] Run retries with backoff + idempotency keys for external actions
- [ ] Approval notifications (desktop notification / webhook) beyond the dashboard badge
- [ ] Snapshot/export of bot definitions (YAML in/out) for sharing
- [ ] Secret per-bot credentials via OS keyring (referenced, never in prompts)

## Phase 2 — capability

- [ ] Vector memory (local embeddings, sqlite-vec) with inspectable recall
- [ ] Webhook/event triggers (file-watch, HTTP inbox) alongside cron
- [ ] Multi-step workflow templates (chained runs, hand-off artifacts)
- [ ] Pi/OpenCode adapters: match published RPC/CLI contracts; broker approvals and provider budgets; strict process containment
- [ ] Browser tool: same-session human handoff, pinned egress, and per-bot download dirs (profiles are now isolated)

## Phase 3 — scale-out (deliberately far)

- [ ] Cross-OS support (macOS, Windows) — GUI automation paths differ per OS
- [ ] Multi-user access to one hutch instance (auth + roles)
- [ ] Optional remote access (tailscale/SSH guidance, or relay) — stays opt-in, never a cloud default
- [ ] A2A collaboration between bots (scoped, auditable)

## Current realignment progress

- **Conversation persistence: partial.** Schema v8 stores canonical messages and maps runs to conversations. Historical runs are
  imported separately. The local v1 API snapshots at most 12 prior messages / 16,000 characters for builtin runs and supports
  FTS5 search. The Studio selects threads, displays restart-persistent history and archives without deleting it.
- **API: partial.** Versioned health, status labels, bots, conversations, search, runs, approvals and usage aliases are present.
  Create/message/archive, stop, and approval resolution use transactional idempotency. Global SSE replay, workspaces/artifacts,
  capability records and idempotent resume/bot-run commands remain open.
- **Remote pairing: experimental.** Direct off-loopback access requires explicit TLS binding. One-time codes issue revocable device
  sessions; source-IP attempts are throttled. The phone UI, PTY/browser controls, tunnel path, and physical-device verification remain
  open. Linux loopback remains the supported service boundary; do not present remote access as a shipped phone feature.
- **Release posture.** Source is private and unpublished. A paired device cannot keep a sleeping host running or reach a service after
  disconnection.

## Non-goals

CAPTCHA solving, bot-detection evasion, acting as a hosted service, or autonomy without
supervision. These conflict with the product's premise.
