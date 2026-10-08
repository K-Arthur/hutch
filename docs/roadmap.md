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

## Non-goals

CAPTCHA solving, bot-detection evasion, acting as a hosted service, or autonomy without
supervision. These conflict with the product's premise.
