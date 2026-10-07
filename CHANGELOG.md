# Changelog

All notable changes to OpenBot. Format follows Keep a Changelog; versioning is semantic.

## [0.1.0] — 2026-10-07

First MVP.

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
- Interfaces: Typer CLI (`openbot`), FastAPI dashboard with live transcripts/approval queue/spend
  meters, headless daemon, `demo seed` for offline exploration.
- Docs: architecture (decision log), safety model, bot-config reference, roadmap, and incident
  research with requirement traceability.
- Tests: 70 tests covering the safety parser, DST math, engine lifecycle, API, and CLI.
