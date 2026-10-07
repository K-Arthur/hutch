# Bot configuration reference

A **bot** is a stored configuration; a **run** is one execution of it. Bots are managed via CLI,
dashboard, or the REST API, and live in `hutch.db`.

## Fields

| Field | Type | Default | Meaning |
|---|---|---|---|
| `name` | slug | — | lowercase `[a-z0-9-]`, unique; names the workspace dir too |
| `description` | str | "" | one-liner shown in dashboards |
| `instructions` | str | "" | standing system-prompt guidance, prepended every run |
| `model` | provider/model | `mock/demo` | see model specs below |
| `base_url` | str? | null | override endpoint for OpenAI-compatible providers |
| `runtime` | enum | `builtin` | `builtin` · `mock` · `pi` · `opencode` |
| `tools` | list | `["shell","files","memory"]` | allowlist; groups expand (see below) |
| `schedule` | obj? | null | `{cron, timezone, catch_up}` — omit for on-demand |
| `limits` | obj | see below | hard caps |
| `approval_mode` | enum | `ask` | `ask` · `auto` |
| `memory_enabled` | bool | true | inject remembered facts into the system prompt |
| `paused` | bool | false | schedules skipped while paused |

## Model specs

```
mock/demo                 deterministic offline runtime (tests, demos, first-run)
openai/gpt-4o-mini        OpenAI API (needs OPENAI_API_KEY)
ollama/llama3.2           local Ollama  (http://localhost:11434/v1)
lmstudio/qwen2.5-7b       local LM Studio (http://localhost:1234/v1)
openai-compatible/<name>  any endpoint — set bot.base_url or HUTCH_BASE_URL
```

Any `mock/*` model routes to the mock runtime regardless of the `runtime` field.

## Tools

Group names expand: `files` → `read_file, list_files, write_file`; `memory` → `remember, recall`;
`browser` → `browser` (needs `pip install "hutch[browser]"`). Concrete names may be listed
individually. Everything runs through the policy engine (`docs/safety.md`).

## Schedules

- `cron`: standard 5-field expression, evaluated **in the bot's timezone**
- `timezone`: IANA name (`Europe/Berlin`, `America/New_York`, `UTC`)
- `catch_up`:
  - `coalesce` *(default)* — if windows were missed (asleep machine, daemon down), run once and
    tag the run `missed_windows=N`
  - `skip` — only run if the newest window is < 30 min old; otherwise record a visible skip

A bot never has two live runs (single-instance lock). All storage is UTC-with-offset.

## Limits

| Key | Default | Effect |
|---|---|---|
| `max_steps` | 24 | agent turns per run; exceeding aborts (`steps_exceeded`) |
| `timeout_seconds` | 900 | wall clock; the run is killed and marked failed (`timeout`) |
| `daily_token_cap` | 200,000 | per-bot daily budget (measured or estimated); next model call aborts (`token_cap`) |

## Examples

Weekly research bot on a local model, approvals on:

```bash
hutch bot create weekly-research \
  --template research-briefing \
  --model ollama/llama3.2 \
  --tools web_fetch,files,memory \
  --cron "0 9 * * 1" --tz Europe/Berlin \
  --approvals ask
```

Trusted cleanup bot, auto-approve within policy:

```bash
hutch bot create tidy \
  --template tidy-downloads \
  --model openai/gpt-4o-mini \
  --approvals auto \
  --max-steps 12 --timeout-seconds 300 --daily-token-cap 50000
```

Inspect what a bot remembers and what it's been allowed to do:

```bash
hutch bot show tidy          # memory + sticky allows + recent runs
hutch bot forget tidy        # wipe memory and sticky allows
```

## Templates

Seeded by `hutch init` (`src/hutch/templates.py`):

- **research-briefing** — weekly web research → `report.md`, dedupes via memory (scheduled Mon 09:00 UTC)
- **repo-sweeper** — on-demand TODO/FIXME sweep of the workspace repo, reports only
- **tidy-downloads** — sorts workspace files; deliberately `ask` mode so you can watch approvals work
