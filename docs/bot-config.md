# Bot configuration reference

`memory_enabled: false` omits memory tools from new runtime tool lists and refuses recall/proposal
through existing tool objects after the persisted setting changes. It does not hide saved facts from
human management or retract prior provider input. `remember` proposes a reference fact within its
chat (or isolated attempt); `recall` returns only reviewed facts in that scope plus references explicitly
shared with this bot's chats. A revision requires a new review. Keys/values are bounded to 120/2,000
characters. Legacy unscoped facts need an explicit sharing decision. Archive retains versions, earlier
prompts and backups. Store credentials through configured connections, never reference facts.

Bot settings keep memory management beside the Bot. The owner can review proposals, create immutable
revisions, archive records, inspect history and manage exact cross-Bot snapshots there. **Download
memory JSON** exports all fact revisions and scopes, review/archive decisions, and incoming/outgoing
share snapshots with current status. It is limited to 10,000 fact revisions, 5,000 shares in each
direction and 2 MiB of source data. It is unencrypted plaintext; fact values and review notes may contain
personal or sensitive information. The export excludes conversations, credentials, run events, action receipts, workspace
files and artifact bytes. Permanent deletion is not implemented; archive retains history and backups.

A **bot** is a stored configuration; a **run** is one execution of it. Bots are managed via CLI,
dashboard, or the REST API, and live in `hutch.db`.

## Conversation-driven Bot setup

In Studio, **Make a bot** on a user message seeds the four-step setup with that exact request. The owner may select up to eight
earlier user messages from the same conversation as saved background; assistant replies, later requests and other chats stay
excluded. New Bot setup suggests a professional display name and stable address locally from the purpose. Both remain editable,
and updating the purpose refreshes only suggestions the owner has not edited.

From a built-in workspace coordinator chat, the owner may request a tool-free refinement of the current purpose. Each request
returns one proposal using the exact source message, current editable purpose and only the selected earlier user messages. The owner
can edit the purpose and request another response; there is no multi-turn clarification exchange. Refinement uses normal model
route, fallback and budget controls, but the run has no tools and cannot create a Bot or change its authority. The owner must apply
the suggestion and then review the complete Bot setup before saving. Hosted providers may retain submitted text under their terms;
the suggestion quality has not been verified against a live provider.

The advanced setup flow also offers an optional task focus. The owner can change it later under Bot settings → **Model & connection**.
It changes local context sizing and residency only; it does not verify model capabilities, and the user still chooses the
model/provider route separately.

### Review, download and import the setup as YAML

The final setup review can build a YAML preview and download it as `hutch-<bot-address>.yaml`. The server runs the same
configuration validation used by Bot creation, but previewing does not save a Bot, start a run, or grant a connection. The
document uses `apiVersion: hutch.ai/v1`, `kind: BotConfig`, and a `spec` containing the reviewed instructions, route, tools,
schedule and limits. **Load a saved YAML setup** at the first setup step to validate a compatible file and copy it into the
current unsaved draft. The wizard then presents those values across its ordinary review steps, with the normal final **Create bot**
confirmation still required. Importing never creates a Bot or starts a run by itself.

Import accepts at most 64 KiB of YAML, rejects aliases, duplicate keys, unsafe tags, unknown fields, and configurations with
unsupported authority (including auto approval, trusted risk, local-folder workspaces, endpoint URLs, or command rules the wizard
cannot review). It accepts only the `hutch.ai/v1` `BotConfig` document. Files are parsed on the server and returned as a sanitized
unsaved configuration; the response is `Cache-Control: no-store`. A file is untrusted input: review its model route, identity,
tools, limits, schedule, and permissions before choosing **Create bot**. Import checks route syntax and policy, but does not require
credentials or acknowledged terms on this machine; final creation still requires the selected route to be usable in Connections.

The YAML excludes provider endpoint URLs, local folder paths, and chat-source identifiers. Credentials, OAuth grants, messages,
memory, artifacts and run history are not part of the document. Selected chat context becomes part of saved instructions, so that
text is present in the preview and downloaded file. YAML is plain text: review it before sharing or committing it. The preview
response is marked `Cache-Control: no-store`.

## Fields

| Field | Type | Default | Meaning |
|---|---|---|---|
| `name` | slug | — | lowercase `[a-z0-9-]`, unique; names the workspace dir too |
| `description` | str | "" | one-liner shown in dashboards |
| `instructions` | str | "" | standing system-prompt guidance, prepended every run |
| `persona_profile_version` | int | current version | version of the saved response-style profile; unversioned legacy profiles are read as version 1, while invalid/future profiles are isolated to that bot |
| `persona_override` | sparse object | inherited | owner's saved wording preferences for this bot; see [response style](architecture.md#response-style-persona). It never grants tools or changes task, safety, evidence or output requirements |
| `model` | provider/model | none | choose a configured real route before creating or running a bot |
| `preset` | task profile? | null | optional configured focus (`router`, `research`, `extraction`, `coding`, `planner`, or `vision`); tunes local context/residency without selecting a model or provider. The vision focus does not enable image input; Hutch chat currently accepts text only |
| `inference_mode` | enum | `hybrid` | `hybrid` permits local and hosted routes; `local` restricts model routes to classified local providers while tools may still use the network; experimental `offline` requires fresh host-verified Linux network/PID namespaces, loopback model routes through Hutch's private Unix-socket broker, and strict shell containment when shell is enabled. |
| `base_url` | str? | null | override endpoint for OpenAI-compatible providers |
| `runtime` | enum | `builtin` | `builtin`; legacy values `mock`, `pi` and `opencode` are retained for migration but fail closed as unsupported |
| `tools` | list | `["shell","files","memory"]` | allowlist; groups expand (see below) |
| `tool_limits` | map | `{}` | Per-tool maximum characters shown to the model; omitted tools default to 12,000, `0` disables clipping, and positive values are capped at 10,000,000. Clipped full output is retained as a verified run artifact, up to 4 MB per artifact and 16 MB per run. |
| `schedules` | list | `[]` | Up to 100 named recurring tasks, each `{id, name, cron, timezone, catch_up, prompt, created_at}`. Each task has its own timing and prompt; tasks share the bot's tools, workspace, limits and permissions. |
| `schedule` | obj? | null | Compatibility alias for the first item in `schedules`; older `cron`/`schedule_prompt` settings update this task. Omit `schedules` for on-demand bots. |
| `limits` | obj | see below | runtime limits and usage admission budgets |
| `approval_mode` | enum | `ask` | `ask` · `auto` |
| `memory_enabled` | bool | true | allow runtime fact proposal/retrieval tools; facts are never automatically injected |
| `workdir` | path? | null | a folder of yours the bot works in, run after run (see below); null = a fresh empty workspace per run |
| `local_browser_handoff` | bool | false | open this bot's browser as a visible Linux desktop window; a login wait holds one Hutch handoff/profile lease until the user resumes. Requires a live Linux display and Playwright Chromium; does not enable phone control. |
| `risk_tier` | enum | `supervised` | `readonly` · `supervised` · `trusted`: what happens to medium-risk actions ([safety.md](safety.md)) |
| `command_rules` | list | `[]` | `{match, verdict}` per-command `allow`/`ask`/`deny` globs ([safety.md](safety.md)) |
| `sandbox` | enum | `strict` for new bots | `strict` uses Linux bubblewrap for shell commands and fails closed if unavailable; `off` runs shell commands without OS containment |
| `paused` | bool | false | schedules skipped while paused |

Manage task streams independently with `hutch bot schedules list <bot>`, `add`, `update`, and
`remove`, or the per-task versioned API routes. Each stream's ID is globally unique and remains
reserved after removal, including when it was removed before its first run. Existing schedule IDs,
occurrence claims, runs and next-fire markers survive the schema v21 upgrade; the normal migration
path makes a SQLite backup before applying the upgrade. A bot still has at most one active run at a
time, so simultaneous tasks on that bot queue independently instead of overlapping.

Database restoration sets every saved bot to `paused` and revokes standing tool grants. A separate
installation-wide restore hold blocks new submissions and claims until local review is recorded.
Unpausing a bot does not bypass the hold; activating the restore does not unpause schedules or
resume old attempts. Review user-owned `workdir` paths separately because database snapshots do
not include the files they reference. See [Operations](operations.md#database-migration-and-restore).

Enable or disable the local browser handoff with `hutch bot update <name> --local-browser-handoff` or
`--no-local-browser-handoff`. Headless remains the default. If a run reaches a login challenge without
the option, it reports that no person can interact with the headless browser and does not enter a fake
human-wait state. When enabled, the same visible browser stays open while the run is paused; Hutch
rechecks the challenge after Resume and keeps waiting if it remains.

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
openai/gpt-4o-mini        OpenAI API (needs OPENAI_API_KEY)
ollama/llama3.2           local Ollama  (http://localhost:11434/v1)
lmstudio/qwen2.5-7b       local LM Studio (http://localhost:1234/v1)
openai-compatible/<name>  any endpoint — set bot.base_url or HUTCH_BASE_URL. Its key is HUTCH_API_KEY (or a connection);
                           OPENAI_API_KEY is only ever sent to api.openai.com
```

The versioned [provider compatibility matrix](realignment/provider-compatibility.md) describes
the request Hutch sends for each route and the evidence behind its status. A supported route is
fixture-tested at the protocol level; it does not establish that a particular endpoint/model can
use tools or report all usage. `hutch connections test` checks model-list access only. An owned,
usage-reserved Bot run may add a positive tool-call observation for its exact connection, account,
model and route revision; inspect these at `GET /api/v1/model-capabilities`. No observation means
unknown, and an observed tool call does not guarantee future behavior or grant action permission.

There is no production mock model route. Existing records that contain `mock/*` remain readable
for migration and audit, but attempts fail before starting an action with `model_unavailable`.
The deterministic test scenario runtime lives under `tests/` and is not included in built wheels.

Pi and OpenCode executor records also remain readable, but those external executors are unavailable
until Hutch can own their processes, broker permissions and reserve provider budgets. Settings can
move an idle legacy bot to Hutch's built-in runtime after its saved model route is usable. This
switch uses Hutch's model connection, tools and approval policy; credentials or sign-in state saved
by Pi or OpenCode are never imported. An active run or missing Hutch route blocks the switch.

Separately, an owner may prepare a reviewed coding task from a completed Studio answer when this Bot uses an existing Git
repository as its `folder` workspace. The original request and proposed brief are shown for editing; the exact brief must be
confirmed before a durable task appears in chat. The first time, run `hutch code login` from an interactive Linux terminal on
the Hutch host to connect a provider in a dedicated private profile; this does not import the regular OpenCode profile. Then
run the card's `hutch code run <task-id>` command. Choose the model in OpenCode; provider usage is outside Hutch's budgets. OpenCode's
permission prompts remain outside Hutch: commands approved there run with the Linux user's filesystem, process and network
authority and are not contained by Hutch's bubblewrap shell sandbox. Hutch creates a separate worktree at the reviewed commit and
does not change the source folder, commit, push, deploy or automatically apply the branch. Inspect it manually before use. Avoid
secrets in the task. OpenCode runtime selection remains disabled; see the [handoff research](research/opencode-coding-handoff-2026-10-09.md)
for the experimental boundary and verification gaps.

Set the route policy with `hutch bot create helper --model ollama/llama3.2 --inference-mode local`
or update it with `hutch bot update helper --inference-mode local`. The model must also be an
allowed local route; change the model and mode together when moving a bot. Local-route mode
blocks hosted per-message choices and fallback/escalation calls. It blocks currently recognized
Ollama cloud-tagged names, but cannot prove that a configured local model service never proxies
requests. Tools retain their own network policy. Use Hybrid for hosted model destinations, and
review the selected connection and tools before a run.

`offline` is a host-gated experiment, not a property inferred from a model name or `localhost` URL.
On Linux, Hutch runs a fresh bubblewrap network/PID namespace probe: both loopback and host-interface
TCP must be unreachable, only namespace processes should appear in `/proc`, and a private Unix socket
must remain reachable. A per-run Unix-socket broker forwards only to its configured numeric loopback
model endpoints. systemd user scopes apply memory/task caps, not network filtering. Offline routes
must use Hutch's builtin runtime and recognized local model providers. Hutch removes browser
and web-fetch tools, blocks hosted overrides/fallbacks, scrubs provider-key/proxy/custom-endpoint
environment variables, masks saved provider connection/key files from the worker, and requires
strict bubblewrap containment for shell tools. Thread/in-process execution is refused. See
`GET /api/v1/capabilities` for the host result. A local inference daemon runs outside Hutch's
worker boundary and may itself make network requests. On hosts where the check fails, create/update
and execution both refuse Offline; changing the bot back to Local or Hybrid remains available.

## Tools

Group names expand: `files` → `read_file, list_files, write_file`; `memory` → `remember, recall`;
`browser` → `browser` (needs `pip install "hutch[browser]"`). Concrete names may be listed
individually. `delegate_task` is an experimental, per-bot opt-in and works only through the
supervised builtin process executor in Strict Offline mode on a host whose Linux bubblewrap
network/PID checks pass. Every request requires fresh human approval, regardless of `approval_mode`.
The child receives only its task text, runs in a private workspace, and cannot use browser or memory
tools. It returns text to the parent; files stay attributed to the child. See
[bounded delegation](realignment/delegation.md) for limits and unsupported cases. Everything runs
through the policy engine (`docs/safety.md`).

Enable or remove the tool explicitly with `hutch bot update <name> --tools ...`; for example:

```bash
hutch bot update local-worker --inference-mode offline --sandbox strict --tools files,delegate_task
```

## Schedules

- A bot can have up to 100 independent named tasks. Each has a stable ID and `created_at`, a
  `name`, `cron`, `timezone`, `catch_up`, and an optional `prompt`.
- `cron`: standard 5-field expression, evaluated **in that task's timezone**
- `timezone`: IANA name (`Europe/Berlin`, `America/New_York`, `UTC`)
- `prompt`: optional task to perform at each occurrence, up to 4,000 characters. Blank keeps
  compatibility with existing bots by using their standing `instructions` (or the generic report
  task when instructions are empty).
- `catch_up`:
  - `coalesce` *(default)* — if windows were missed (asleep machine, daemon down), run once and
    tag the run `missed_windows=N`
- `skip` — only run if the newest window is < 30 min old; otherwise record a visible skip

Manage streams without replacing their siblings:

```bash
hutch bot schedules list weekly-research
hutch bot schedules add weekly-research --name "Security feed" --cron "0 8 * * 1" \
  --timezone Europe/Berlin --prompt "Check the security feed and summarize relevant changes."
hutch bot schedules update weekly-research schedule_abc123 --catch-up skip
hutch bot schedules remove weekly-research schedule_abc123
```

The legacy `schedule` config field, creation `--cron`/`--schedule-prompt` options, and
`hutch bot update` schedule flags address the first task. `--clear-cron` removes that first task;
any remaining task is promoted to the first position. All tasks on a bot share resources and the
one-live-run limit. A removed task ID stays reserved for run-history identity and cannot be reused.

The dashboard's **Scheduled work** page brings recurring tasks from every assistant into one
bounded, chronologically ordered overview. It leads with each task's next occurrence and keeps
the schedule expression, timezone, and missed-time choice under **Timing details**.
**Pause scheduled work** is a durable workspace setting: it prevents future scheduled admissions,
but does not stop work already queued or running. Resuming the workspace does not clear a Bot's
own pause; windows missed during the workspace pause then follow each task's `catch_up` policy.
The scheduler checks the workspace pause in the same transaction that admits an occurrence, so a
previously read due-time snapshot cannot slip through after pause is saved.

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

In the assistant settings page, task time is entered in minutes for easier
reading; Hutch converts it to the same `timeout_seconds` field used by YAML,
the API, and the CLI. Token and currency fields are estimates and do not replace
provider-side billing limits.

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

Give scheduled work its own task prompt instead of using the bot's standing instructions:

```bash
hutch bot create weekly-research \
  --model ollama/llama3.2 \
  --cron "0 9 * * 1" --tz Europe/Berlin \
  --schedule-prompt "Review new release notes and write a concise report."
hutch bot update weekly-research \
  --schedule-prompt "Check the weekly security feed and summarize relevant changes."
```

Clear `--schedule-prompt` with an empty value to return to the standing-instructions fallback.
Use `--clear-cron` to remove the first task. Use `hutch bot schedules remove` to remove any
specific task stream.

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
hutch bot show tidy          # bounded fact inventory + sticky allows + recent runs
hutch bot forget tidy        # archive all facts; revoke sticky allows; history remains
```

## Templates

Available from `hutch bot templates` (`src/hutch/templates.py`); `hutch init` creates no bots:

- **research-briefing** — weekly web research → `report.md`, dedupes via memory (scheduled Mon 09:00 UTC)
- **repo-sweeper** — on-demand TODO/FIXME sweep of the workspace repo, reports only
- **tidy-downloads** — sorts workspace files; deliberately `ask` mode so you can watch approvals work
