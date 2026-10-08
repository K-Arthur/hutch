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

*Status column last updated: Phase 3 built (local model layer), Connections, and the chat model switcher.*

## Dashboard and app

| ID | Requirement | Phase | Status | Where |
|---|---|---|---|---|
| UI-1 | Home shows Needs you / Running now / Stale | MVP | done | `views.home_state` served at `/`: Needs you / Running now / Stale, each with cause and fix; `tests/test_views.py`, `tests/test_dashboard.py` |
| UI-2 | Stop all in every header; per-run Stop kills child processes | MVP | done | Stop all in every header (plain POST + confirm); engine kills process groups; tested incl. forked helper |
| UI-3 | Run detail streams over SSE and resumes gap-free via event sequence | MVP | done | SSE seq cursor + Last-Event-ID replay from SQLite; gate + real-Chromium TCP-cut test |
| UI-4 | Run detail: steps, elapsed, spend, context vs caps | MVP | done | `views.run_meters`: steps, elapsed, spend, tokens, context vs caps, plus absolute model/tool/Hutch timing |
| UI-5 | Approvals inbox: parsed segments, rule, once/always/deny, countdown | MVP | done | approval card: parsed segments, rule, once/always/plan/deny, live countdown; outward never offers always |
| UI-6 | Every waiting state names its cause and a fix | MVP | done | `views.explain_run`, `explain_outcome` and the stale cause: every wait names a cause and a fix |
| UI-7 | New bot: template gallery → purpose, model preset, permissions+budget; YAML view | MVP | planned | |
| UI-8 | First run: mock demo / local model that fits / API key; seeded demo bots | MVP | planned | |
| UI-9 | Schedules page: next runs in each bot's zone, coalesced misses, pause all | MVP | planned | |
| UI-10 | Memory page with provenance, edit, delete, export | Later | partial | bot page lists memory with the run that wrote it, delete; edit/export + dedicated page pending |
| UI-11 | Usage page: spend by bot/provider/day; escalation log | Later | done | `/usage`: spend and tokens by day (local day), model and bot, today against each bot's caps, plan allowances, cache share, and the fallback/escalation/allowance-stop log |
| UI-12 | Server-rendered templates + HTMX, no build step; stop/approve are plain POSTs | MVP | done | Jinja2 + htmx 2.0.4 vendored, no build step; every action is a plain POST; CSRF + Host/Origin checks |
| UI-13 | Approvals inbox usable at phone width | Later | done | approvals inbox verified at 390px in Chromium (full-width, thumb-sized actions) |
| UI-14 | Localhost app run by a user-level systemd service; Tauri shell after v0.1 | MVP, then later | planned | |

## Local models and presets

| ID | Requirement | Phase | Status | Where |
|---|---|---|---|---|
| LM-1 | Ollama provider uses native chat API, always sets context size | MVP | done | `providers/ollama.py`: native `/api/chat`, `num_ctx` always sent; the `/v1` path is never used for Ollama |
| LM-2 | Startup self-check: fact at top of a long prompt must be recalled | MVP | done | `context.run_selfcheck` (cached per model/window/template); `hutch doctor --deep` |
| LM-3 | Warn before a run when prompt + tools exceed effective context | MVP | done | `context.py` pre-run prompt + tools check; the run fails with the fix instead of truncating |
| LM-4 | Hardware probe: RAM, GPU memory, Apple Silicon, installed runtimes | MVP | done | `hardware.probe`: RAM, GPU memory, Apple Silicon, installed runtimes |
| LM-5 | Models page: fits / tight / won't fit + actual context | MVP | done | `/models` page and `hutch models list`; [models.md](models.md) |
| LM-6 | Models are scheduled resources; batching; cold load is a visible state | MVP | done | `slots.py` (batching, slot gate, fairness, visible wait reason); cold load is the `loading_model` state. Swap latency measurable with `hutch models swap-test`; not yet measured on real models |
| LM-7 | Task presets: router, research, extraction, coding, planner, vision | MVP | partial | six presets resolve per machine, shown on `/models` and `hutch models presets`; picking one in bot creation arrives with the wizard (UI-7) |
| LM-8 | Different presets for planner/executor/summarizer roles | Later | later | |
| LM-9 | One-step escalation on malformed calls / loop / overflow, within spend cap | MVP | done | `runtime/ladder.py`: one-rung escalation inside the spend guard; tests |
| LM-10 | Local-default bots ask before first hosted call | MVP | done | ask before the first hosted call for a local-default bot, even in auto mode; a hosted model picked in the chat switcher is explicit consent for that message |
| LM-11 | Reliability harness per model/quant/runtime/template | MVP | done | `reliability.py` + `hutch models bench`: five tool probes + long-prompt recall, keyed by model/quant/runtime/template/digest/window, shown on `/models`, used by doctor. Verified against scripted models only; not yet run on real local models |
| LM-12 | Re-measure when runtime or model file changes | Later | later | |
| LM-13 | Tool-call repair; ≤ 8 tools by default | MVP | partial | `runtime/toolrepair.py` coerce/validate/one retry; `hutch doctor` warns above 8 tools; the 8-tool default is not enforced at bot creation |
| LM-14 | Editable hosted price file with verified-on date in UI | MVP | done | price table with source and verified date on `/models`; edit, reset; 90-day stale flag |
| LM-15 | API key access; subscription only via vendor CLI behind a terms warning; no token extraction | MVP | partial | API keys and connection terms notices done ([connections.md](connections.md)); the `pi` / `opencode` vendor-CLI adapters do not yet show a terms warning |
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
| SR-1 | One runtime/model crash affects only its own runs; health per runtime | MVP | done | orphan recovery, shutdown, per-run isolation and per-runtime health (`health.py`, Models page, doctor) |
| SR-2 | Exact per-step token/cost accounting, visible before a run | MVP | done | per-step accounting, spend guard before every hosted call, plan note at run start, and a worst-case ceiling before a run: bot page, `hutch bot estimate`, `GET /api/bots/<name>/estimate`, the chat switcher (`estimate.py`) |
| SR-3 | Per-bot compact-now and fresh-session controls | Later | later | |
| SR-4 | Outward-sending tools always ask, regardless of sticky allows | MVP | partial | shell: `git push`, `ssh`/`scp`/`rsync`/`ftp` always ask and are never sticky, an allow rule or the trusted tier cannot suppress them (tested); network uploads are denied. Browser actions that submit forms are not classified yet |
| SR-5 | Small models: thinking off, per-turn token cap, loop detector | MVP | done | `think:false` only for thinking-capable models, per-turn token cap, loop detector that refuses a third identical call (`tests/test_providers.py`, `tests/test_runtime_builtin.py`) |
| SR-6 | In-app help generated from or tested against real routes | Later | later | |
| SR-7 | Every run shows its parent bot or plan | MVP | done | every run shows who started it: schedule, you (cli, dashboard or api), or a plan |
| SR-8 | Provider fallback chain | MVP | done | ordered fallback chain on unreachable model, missing model and mid-run outage, announced in the run (`tests/test_runtime_builtin.py`) |
| SR-9 | Failed streaming request retried once without streaming | MVP | done | a stream that fails mid-flight is retried once without streaming, never after Stop (`tests/test_providers.py`) |
| SR-10 | Bubblewrap-wrapped shell on Linux | Later | later | |
| SR-11 | Hash-chained event log | Later | done | hash chain in `store.py`, `Store.verify_chain`; tamper/delete tests (CLI/UI surface pending) |
| SR-12 | Risk tier per bot (medium asks, high blocked) + per-command rules | MVP | done | `safety.PolicyEngine(tier, rules)`: readonly, supervised or trusted, plus per-command `allow`, `ask` or `deny` globs, seen through wrappers and substitutions; hard denies and outward sends cannot be overridden; bot page, API, CLI (`--risk-tier`, `--rule`); [safety.md](safety.md) |
| SR-13 | Command parser fuzz-tested | MVP | done | `shellparse.py` reads the line like a shell (substitutions, `bash -c`, wrappers, heredocs, `&`, newlines, redirects) and denies what it cannot read; hypothesis-fuzzed in `tests/test_shellparse.py` |
| SR-14 | `doctor` command | MVP | done | `hutch doctor` (`doctor.py`): every problem prints its fix; `--deep`, `--online`, `--json` |

## Performance

| ID | Requirement | Proposed target | Phase | Status | Where |
|---|---|---|---|---|---|
| PF-1 | Byte-identical system prompt + tool list across a run | cached-token share per run | MVP | done | frozen prompt prefix hash recorded on every step (`tests/test_runtime_builtin.py`) |
| PF-2 | Per-tool output limit; full output saved as artifact | configurable per tool | MVP | done | per-tool output limit (configurable per bot); full output saved as an artifact (`runtime/steps.py`) |
| PF-3 | Prompt includes only the bot's allowed tools | — | MVP | done | only the bot's allowed tools reach the prompt (`tests/test_runtime_builtin.py`) |
| PF-4 | Compaction before the context limit | ~75% of context | Later | later | |
| PF-5 | Scheduler sleeps until next due run or event; no polling | near-zero idle CPU | MVP | done | `engine.run_loop`/`next_wakeup`, `wake.py`; `tests/test_engine_loop.py`; 0.0 s/h idle CPU |
| PF-6 | Playwright and provider SDKs imported lazily | CLI status < 300 ms | MVP | done | lazy `httpx`/provider imports; `hutch status` 275 ms (was 820 ms for `version`) |
| PF-7 | SQLite WAL, one writer, batched event inserts, run+seq index | 1,000 events/s | MVP | done | `store.py` writer thread + WAL; ~52k events/s; `tests/test_store_events.py` |
| PF-8 | Browser launches on first use, closes when idle | idle close 5 min | MVP | planned | |
| PF-9 | Coalesced live updates, paginated transcripts | usable at 10,000 events | MVP | done | the run page renders the last 200 events and paginates; a 10,000-event run is tested (`tests/test_dashboard.py`) |
| PF-10 | Small router model stays loaded | — | Later | later | |
| PF-11 | Per-step timing: model wait, tool time, Hutch overhead | overhead < 50 ms/step | MVP | done | `runtime/steps.py`; 0.25 ms/step (mock); recorded as `step` events |
| PF-12 | Benchmark suite in CI; fails on 20% regression | — | MVP | done | `benchmarks/run.py`, `baselines/local.json`, `.github/workflows/ci.yml` (CI not yet run remotely) |
| PF-13 | Idle daemon small | < 150 MB resident | MVP | done | 39 MB daemon / 56 MB serve idle |

## Build order and gates

| # | Phase | IDs | Gate | Gate status |
|---|---|---|---|---|
| 1 | Engine baseline | PF-5, PF-6, PF-7, PF-11, PF-12, PF-13 | tests pass offline; benchmarks record a baseline | **passed** — 101 tests offline; baseline in `benchmarks/baselines/local.json` |
| 2 | Run view and control | UI-1…6, UI-12, SR-7 | ten concurrent runs stream, connection cut, transcript resumes with no missing events | **passed** - `tests/test_sse_resume.py` (10 runs x 2 real cuts, real sockets) and `tests/e2e` (Chromium, TCP cut, DOM verified) |
| 3 | Local model layer | LM-1…6, SR-1, SR-14 | self-check passes; swap latency measured for two model pairs | **built and tested; gate not met** - self-check and swap measurement pass against scripted servers (`tests/test_slots.py`, `tests/test_models_layer.py`); no real local models on the dev machine, so swap latency for two real pairs is **not measured** |
| 4 | Reliability harness | LM-11, LM-13, SR-5 | ≥ 3 models profiled on the dev machine | **harness built and tested; gate not met** - three scripted models (good / needs repair / never calls tools) are ranked correctly in `tests/test_reliability.py`; **no real models were profiled** because the dev machine has ~3 GiB free and no Ollama. Run `hutch models bench <model>` on a real machine to meet it |
| 5 | Presets, escalation, budgets | LM-7, 9, 10, 14, 15, SR-2, 8, 9, 12, PF-1…3 | escalation respects caps in tests | planned |
| 6 | Collaboration | CO-1…11 | demo plan finishes on mock + one local model; misbehaving specialist is stopped by the engine | planned |
| 7 | v0.1 release | UI-7…9, UI-14, SR-4, SR-13, docs, site | README quickstart runs verbatim on a clean Linux machine | planned |

## Additions beyond the draft (driven by the Dots / Grok Bot research)

| Item | Why | Status |
|---|---|---|
| Dashboard CSRF / DNS-rebinding defence (Host allow-list, Origin + Fetch-Metadata, CSRF token, token auth for `--allow-remote`) | Local approval endpoints are drivable from any web page ([research §3](research/offerings-and-failures.md)) | done - `server/security.py`; refusal of non-loopback bind without a token lands with the CLI work |
| **Rehearse** (dry-run) mode: mutating actions simulated and logged | Grok Bot: "no dry-run mode; testing performs real work" | planned |
| Role templates (sales, PM, marketing, analytics) in the gallery | Team Bots ships role templates | planned |
| **Model switcher** in the chat composer + all-models dialog, per message (never edits the bot) | A chat product switches models from the composer; ChatGPT shows deprecation notes there, Hutch shows fit, cost and what is missing | done - `modelchoices.py`, `static/model-switcher.js`, [models.md](models.md); real-browser tested, desktop + phone |
| Approval webhook notification | Dots / Grok are reachable when you are away | planned |
| Pulled forward from *Later*: UI-10, UI-11, UI-13, SR-11 | Memory opacity, spend opacity, mobile, and audit are the loudest complaints about the two reference products | planned |

## Connections and integrations (added at the product owner's request, 2026-10-07)

Subscription plans such as OpenCode Go and the Xiaomi MiMo Token Plan, and the integration breadth that Dots
(4,000+ plugins) and Grok Bot (Slack, routines) advertise. Details: [connections.md](connections.md).

| ID | Requirement | Status | Where |
|---|---|---|---|
| CN-1 | Named connections, each with its own key, usable as `<connection>/<model>` | done | `connections.py`, `providers/connection.py` |
| CN-2 | Keys from an env var or a 0600 file; never in the database, transcript, page or API | done | `ConnectionBook.key`; test greps pages + DB for a planted secret |
| CN-3 | Required headers: own User-Agent and a stable per-run session id | done | `ChatRequest.session_id`, both HTTP providers |
| CN-4 | Billing modes: per-token (priced), subscription / free (flat, still ledgered) | done | `PriceBook.flat_providers`, `usage` table |
| CN-5 | Declared allowance enforced before the call; warning at 80% | done | `SpendGuard.quota_refusal`, `quota` log |
| CN-6 | Terms notice acknowledged before first use; re-ack when it changes | done | `ConnectionBook.ack_status`, runtime fails fast with the fix |
| CN-7 | Protocol per model (openai-chat / anthropic); Responses API rejected clearly | partial | Responses protocol not implemented |
| CN-8 | Test a connection without spending tokens | done | `check_connection`, `hutch connections test` |
| CN-9 | Consumer-plan OAuth sessions explicitly unsupported (vendor terms) | done | policy, documented in connections.md |
| IG-1 | MCP client (stdio): bots can use MCP tools, all behind the approval gate | planned | |
| IG-2 | Inbound webhook trigger for a bot | planned | |
| IG-3 | Outbound notifications (approval needed, failure, result) to a webhook | planned | |
| IG-4 | "Save this run as a bot" (routine capture without a recorder) | planned | |
| TP-1 | Role templates (sales, PM, marketing, analytics, support, ops) | planned | |
| TP-2 | Bot customization: persona/tone, reusable skills, delivery target | planned | |

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
