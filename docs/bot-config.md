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
| `runtime` | enum | `builtin` | `builtin` · `mock`; legacy values `pi` and `opencode` are retained but fail closed as unsupported |
| `tools` | list | `["shell","files","memory"]` | allowlist; groups expand (see below) |
| `schedule` | obj? | null | `{cron, timezone, catch_up}` — omit for on-demand |
| `limits` | obj | see below | runtime limits and usage admission budgets |
| `approval_mode` | enum | `ask` | `ask` · `auto` |
| `memory_enabled` | bool | true | inject remembered facts into the system prompt |
| `workdir` | path? | null | a folder of yours the bot works in, run after run (see below); null = a fresh empty workspace per run |
| `risk_tier` | enum | `supervised` | `readonly` · `supervised` · `trusted`: what happens to medium-risk actions ([safety.md](safety.md)) |
| `command_rules` | list | `[]` | `{match, verdict}` per-command `allow`/`ask`/`deny` globs ([safety.md](safety.md)) |
| `sandbox` | enum | `strict` for new bots | `strict` uses Linux bubblewrap for shell commands and fails closed if unavailable; `off` runs shell commands without OS containment |
| `paused` | bool | false | schedules skipped while paused |

### Working folder

Without a `workdir`, every run gets a fresh, empty workspace, so a bot cannot see your files. Set one and the run's
workspace *is* that folder: file tools resolve inside it, the shell starts in it, and a path that escapes it is denied.
Files persist from run to run, so a bot can sort `~/Downloads`, read a folder of CSVs, or keep a running report.

```bash
hutch bot create tidy --workdir ~/Downloads --risk-tier supervised
hutch bot update tidy --clear-workdir
```

Because the folder is yours and live it is validated hard: it must already exist (Hutch never creates it), be readable, and
not be a system location (`/etc`, `/usr`, `/proc`, ...), your whole home folder or a parent of it, Hutch's own state folder
(it holds transcripts, memory and keys), or a credentials location (`~/.ssh`, `.aws`, ...). Symlinks are resolved first, and
the check runs again at the start of every run: a folder that has vanished or become forbidden fails the run with the reason.
Two bots may share a folder; Hutch does not coordinate between them. **Rehearse** runs never change it.

## Model specs

```
mock/demo                 deterministic offline runtime (tests, demos, first-run)
openai/gpt-4o-mini        OpenAI API (needs OPENAI_API_KEY)
ollama/llama3.2           local Ollama  (http://localhost:11434/v1)
lmstudio/qwen2.5-7b       local LM Studio (http://localhost:1234/v1)
openai-compatible/<name>  any endpoint — set bot.base_url or HUTCH_BASE_URL. Its key is HUTCH_API_KEY (or a connection);
                           OPENAI_API_KEY is only ever sent to api.openai.com
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

## Shell containment

New bots request `sandbox: strict`. On supported Linux hosts Hutch mounts the workspace writable, uses a private temporary
directory and PID/network namespaces, scrubs inherited environment values, and applies per-command CPU, memory, process, file-size
and open-file limits. Strict shell networking is unavailable; use Hutch's address-checked `web_fetch` tool for public pages.
This boundary covers the shell only; it is not a hardened VM. Existing bots keep their pre-upgrade value (`off`) so their behavior
does not silently change.

Set it at creation or later:

```bash
hutch bot create helper --sandbox strict
hutch bot update helper --sandbox off       # explicit: shell is uncontained and runs as your Hutch user
hutch doctor                                # checks whether strict mode can run on this host
```

`HUTCH_SANDBOX=off` is an operator-wide rollback override. A `shell_network: true` request with strict mode is refused; Hutch does
not silently join the host network. Check [operations](operations.md) for requirements and recovery steps.

## Limits

| Key | Default | Effect |
|---|---|---|
| `max_steps` | 24 | agent turns per run; exceeding aborts (`steps_exceeded`) |
| `timeout_seconds` | 900 | wall clock; the run is killed and marked failed (`timeout`) |
| `daily_token_cap` | 200,000 | per-bot local-day budget; measured provider usage plus active/uncertain request reservations; the next request is refused if its estimate would pass the cap (`token_cap`) |

Hosted currency limits reserve a local price-based estimate before the request. They require a matching price record, and a capped route with
unknown pricing is refused. Provider billing can differ from Hutch's prompt-size estimate. See [Connections](connections.md) for shared
provider-account caps and reservation reconciliation.

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
