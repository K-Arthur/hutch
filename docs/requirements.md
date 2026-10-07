# Requirements (v0.2) and implementation status

Source: *Hutch requirements v0.2 draft*, 7 Oct 2026 (UI = dashboard, LM = local models,
CO = collaboration, SR = safety and reliability, PF = performance). IDs are stable so issues and
commits can cite them. Evidence for the *why* is in
[research/offerings-and-failures.md](research/offerings-and-failures.md).

**Status key:** `done` — implemented and covered by a test or a recorded measurement ·
`partial` — implemented with a stated gap · `later` — scheduled after v0.1 per the draft ·
`planned` — not yet built.

> Performance numbers in the draft are *proposed targets*. Measured values live in
> [performance.md](performance.md) and the committed `benchmarks/baseline.json`.

*Status column last updated: initial commit (everything `planned`); updated as phases land.*

## Dashboard and app

| ID | Requirement | Phase | Status | Where |
|---|---|---|---|---|
| UI-1 | Home shows Needs you / Running now / Stale | MVP | planned | |
| UI-2 | Stop all in every header; per-run Stop kills child processes | MVP | planned | |
| UI-3 | Run detail streams over SSE and resumes gap-free via event sequence | MVP | planned | |
| UI-4 | Run detail: steps, elapsed, spend, context vs caps | MVP | planned | |
| UI-5 | Approvals inbox: parsed segments, rule, once/always/deny, countdown | MVP | planned | |
| UI-6 | Every waiting state names its cause and a fix | MVP | planned | |
| UI-7 | New bot: template gallery → purpose, model preset, permissions+budget; YAML view | MVP | planned | |
| UI-8 | First run: mock demo / local model that fits / API key; seeded demo bots | MVP | planned | |
| UI-9 | Schedules page: next runs in each bot's zone, coalesced misses, pause all | MVP | planned | |
| UI-10 | Memory page with provenance, edit, delete, export | Later | planned *(pulled forward)* | |
| UI-11 | Usage page: spend by bot/provider/day; escalation log | Later | planned *(pulled forward)* | |
| UI-12 | Server-rendered templates + HTMX, no build step; stop/approve are plain POSTs | MVP | planned | |
| UI-13 | Approvals inbox usable at phone width | Later | planned *(pulled forward)* | |
| UI-14 | Localhost app run by a user-level systemd service; Tauri shell after v0.1 | MVP, then later | planned | |

## Local models and presets

| ID | Requirement | Phase | Status | Where |
|---|---|---|---|---|
| LM-1 | Ollama provider uses native chat API, always sets context size | MVP | planned | |
| LM-2 | Startup self-check: fact at top of a long prompt must be recalled | MVP | planned | |
| LM-3 | Warn before a run when prompt + tools exceed effective context | MVP | planned | |
| LM-4 | Hardware probe: RAM, GPU memory, Apple Silicon, installed runtimes | MVP | planned | |
| LM-5 | Models page: fits / tight / won't fit + actual context | MVP | planned | |
| LM-6 | Models are scheduled resources; batching; cold load is a visible state | MVP | planned | |
| LM-7 | Task presets: router, research, extraction, coding, planner, vision | MVP | planned | |
| LM-8 | Different presets for planner/executor/summarizer roles | Later | later | |
| LM-9 | One-step escalation on malformed calls / loop / overflow, within spend cap | MVP | planned | |
| LM-10 | Local-default bots ask before first hosted call | MVP | planned | |
| LM-11 | Reliability harness per model/quant/runtime/template | MVP | planned | |
| LM-12 | Re-measure when runtime or model file changes | Later | later | |
| LM-13 | Tool-call repair; ≤ 8 tools by default | MVP | planned | |
| LM-14 | Editable hosted price file with verified-on date in UI | MVP | planned | |
| LM-15 | API key access; subscription only via vendor CLI behind a terms warning; no token extraction | MVP | planned | |
| LM-16 | Show each model's license; flag non-Apache/MIT | Later | later | |

## Bot collaboration

| ID | Requirement | Phase | Status | Where |
|---|---|---|---|---|
| CO-1 | One planner and a fixed list of allowed specialists | v0.1 | planned | |
| CO-2 | Structured messages: task, result, question — no free chat | v0.1 | planned | |
| CO-3 | Specialists cannot message each other; only the planner wakes a bot | v0.1 | planned | |
| CO-4 | Own workspace per specialist; explicit, logged file copy; per-bot memory | v0.1 | planned | |
| CO-5 | Planner sees results and artifact refs, not transcripts | v0.1 | planned | |
| CO-6 | Engine enforces max hops, tasks, parallel specialists, wall-clock | v0.1 | planned | |
| CO-7 | Plan budget split into per-task slices | v0.1 | planned | |
| CO-8 | Same task posted twice pauses the plan | v0.1 | planned | |
| CO-9 | Stop plan kills every child run | v0.1 | planned | |
| CO-10 | Child approvals in the one inbox tagged with plan; bounded plan-level approval | v0.1 | planned | |
| CO-11 | Plan page: board + handoff timeline with cost | v0.1 | planned | |

## Safety and reliability

| ID | Requirement | Phase | Status | Where |
|---|---|---|---|---|
| SR-1 | One runtime/model crash affects only its own runs; health per runtime | MVP | planned | |
| SR-2 | Exact per-step token/cost accounting, visible before a run | MVP | planned | |
| SR-3 | Per-bot compact-now and fresh-session controls | Later | later | |
| SR-4 | Outward-sending tools always ask, regardless of sticky allows | MVP | planned | |
| SR-5 | Small models: thinking off, per-turn token cap, loop detector | MVP | planned | |
| SR-6 | In-app help generated from or tested against real routes | Later | later | |
| SR-7 | Every run shows its parent bot or plan | MVP | planned | |
| SR-8 | Provider fallback chain | MVP | planned | |
| SR-9 | Failed streaming request retried once without streaming | MVP | planned | |
| SR-10 | Bubblewrap-wrapped shell on Linux | Later | later | |
| SR-11 | Hash-chained event log | Later | planned *(pulled forward)* | |
| SR-12 | Risk tier per bot (medium asks, high blocked) + per-command rules | MVP | planned | |
| SR-13 | Command parser fuzz-tested | MVP | planned | |
| SR-14 | `doctor` command | MVP | planned | |

## Performance

| ID | Requirement | Proposed target | Phase | Status | Where |
|---|---|---|---|---|---|
| PF-1 | Byte-identical system prompt + tool list across a run | cached-token share per run | MVP | planned | |
| PF-2 | Per-tool output limit; full output saved as artifact | configurable per tool | MVP | planned | |
| PF-3 | Prompt includes only the bot's allowed tools | — | MVP | planned | |
| PF-4 | Compaction before the context limit | ~75% of context | Later | later | |
| PF-5 | Scheduler sleeps until next due run or event; no polling | near-zero idle CPU | MVP | planned | |
| PF-6 | Playwright and provider SDKs imported lazily | CLI status < 300 ms | MVP | planned | |
| PF-7 | SQLite WAL, one writer, batched event inserts, run+seq index | 1,000 events/s | MVP | planned | |
| PF-8 | Browser launches on first use, closes when idle | idle close 5 min | MVP | planned | |
| PF-9 | Coalesced live updates, paginated transcripts | usable at 10,000 events | MVP | planned | |
| PF-10 | Small router model stays loaded | — | Later | later | |
| PF-11 | Per-step timing: model wait, tool time, Hutch overhead | overhead < 50 ms/step | MVP | planned | |
| PF-12 | Benchmark suite in CI; fails on 20% regression | — | MVP | planned | |
| PF-13 | Idle daemon small | < 150 MB resident | MVP | planned | |

## Build order and gates

| # | Phase | IDs | Gate | Gate status |
|---|---|---|---|---|
| 1 | Engine baseline | PF-5, PF-6, PF-7, PF-11, PF-12, PF-13 | tests pass offline; benchmarks record a baseline | planned |
| 2 | Run view and control | UI-1…6, UI-12, SR-7 | ten concurrent runs stream, connection cut, transcript resumes with no missing events | planned |
| 3 | Local model layer | LM-1…6, SR-1, SR-14 | self-check passes; swap latency measured for two model pairs | planned |
| 4 | Reliability harness | LM-11, LM-13, SR-5 | ≥ 3 models profiled on the dev machine | planned |
| 5 | Presets, escalation, budgets | LM-7, 9, 10, 14, 15, SR-2, 8, 9, 12, PF-1…3 | escalation respects caps in tests | planned |
| 6 | Collaboration | CO-1…11 | demo plan finishes on mock + one local model; misbehaving specialist is stopped by the engine | planned |
| 7 | v0.1 release | UI-7…9, UI-14, SR-4, SR-13, docs, site | README quickstart runs verbatim on a clean Linux machine | planned |

## Additions beyond the draft (driven by the Dots / Grok Bot research)

| Item | Why | Status |
|---|---|---|
| Dashboard CSRF / DNS-rebinding defence (Host allow-list, Origin + Fetch-Metadata, CSRF token, non-loopback bind refusal) | Local approval endpoints are drivable from any web page ([research §3](research/offerings-and-failures.md)) | planned |
| **Rehearse** (dry-run) mode: mutating actions simulated and logged | Grok Bot: "no dry-run mode; testing performs real work" | planned |
| Role templates (sales, PM, marketing, analytics) in the gallery | Team Bots ships role templates | planned |
| Approval webhook notification | Dots / Grok are reachable when you are away | planned |
| Pulled forward from *Later*: UI-10, UI-11, UI-13, SR-11 | Memory opacity, spend opacity, mobile, and audit are the loudest complaints about the two reference products | planned |

## Out of scope (unchanged)

A Rust rewrite, messaging channels (Discord, Telegram, Slack, Teams), hardware peripherals, peer-to-peer bot
chat, shared memory between bots, a vector database, multi-user accounts, and a mobile app.

## Open questions from the draft

- [ ] Does the current code match the finalized plan's layout? — *Reviewed 2026-10-07: yes, the v0.1 tree matches the plan; differences are listed in [architecture.md](architecture.md).*
- [x] Main development machine — AMD Ryzen 3 5300U (4C/8T), 22 GiB RAM, integrated Radeon (no ROCm/CUDA), Linux. Sets the CPU-only preset tier.
- [ ] Embedding model, if any — not needed; no vector memory in scope.
- [ ] Vision model for the browser tool vs DOM control — DOM control kept; vision preset exists but is optional.
- [ ] Performance targets realistic? — answered by the recorded baseline in [performance.md](performance.md).
- [x] Is "Hutch" free on PyPI? — checked during the rename (see [research/naming.md](research/naming.md)).
- [ ] **Hosted SaaS vs self-hosted** — the product *shape* mirrors Dots / Grok Bot, but this release is self-hosted and single-user per the draft's out-of-scope list. A hosted multi-tenant offering needs accounts, billing, isolation and a different threat model; it is not started.
