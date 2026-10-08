# Models: switching, fit, slots, prices and `hutch doctor`

## Switching models in the chat

The Studio composer has a model pill beside Send. Its menu lists the bot's own model first (marked *default*, with a
check on the one in use), then what is usable right now, then **All models**. Each entry has one line of secondary
text that says something true on this machine:

| Entry | Secondary line |
|---|---|
| installed local model | `fits, 16k context` or `tight fit, 7k context` (the context the bot will really get) |
| hosted model | `$4 in / $20 out per 1M tokens`, or `needs ANTHROPIC_API_KEY` |
| connection model | `flat-rate plan` / `pay per token`, or what is missing (key, acknowledged terms) |

**All models** opens a searchable dialog with everything, grouped. Models that cannot be used are shown with the
reason and the fix (`the weights alone are 40 GiB against 3.5 GiB usable`, `set ANTHROPIC_API_KEY where hutch
starts`) instead of being hidden. Anything that sends the chat off the machine carries a **leaves this machine** tag.
A field at the bottom takes any `provider/model`, for connection models that are not listed.

Rules worth knowing:

- **Per message, never a silent edit.** The choice is stored on the run as `model_override`. The bot's own model is
  untouched, so scheduled runs keep using it. The choice is remembered per bot in your browser.
- **A hosted pick is your explicit consent for that message.** The "ask before the first hosted call" rule exists
  to stop a *local-first bot* drifting off your machine on its own; it does not fire when you picked the hosted model
  yourself. Spend caps and the exact per-call accounting still apply.
- **The runtime still protects you.** The override goes through the normal run path, so a model that cannot fit this
  machine is refused before it loads, and the run says so.
- **The server re-validates on send.** Unknown provider, missing key and an unacknowledged connection are refused with the exact
  fix. Bots saved with legacy `pi` or `opencode` runtime values create a visible failed run with an `unsupported` reason; those
  runtimes are disabled before an external process starts.

API: `GET /api/bots/<name>/models` returns `{default, models:[{spec,label,group,state,note,fix,default,hosted,detail}]}`;
`POST /api/bots/<name>/run` takes an optional `"model": "provider/model"` (409 = usable once set up, 422 = malformed
or unknown).

## The Models page (`/models`)

The "everything" view behind the switcher: runtimes and connections with state and fix, installed models marked
**fits / tight / won't fit** at 16k and 32k context, what each task preset resolves to on this machine (with the
install command when it is missing), measured swap costs, and the hosted price table.

`hutch models list` and `hutch models presets` print the same data in the terminal.

Fit is **arithmetic, not a benchmark**: weights plus KV cache against the memory budget, using the runtime's own
architecture numbers once a model is installed and catalog estimates before. It does not predict speed.

## Measuring tool reliability: `hutch models bench`

"Supports tools" on a model card does not tell you whether a model forms a valid call, gets argument types right,
picks the right tool among several, stops when it should, and uses what the tool returned. `hutch models bench
<model>` measures that on your machine:

| Probe | Passes when the model... |
|---|---|
| Forms a valid tool call | makes exactly one `read_file` call with the right file and schema-valid arguments |
| Gets argument types right | sends `quantity` as an integer and `urgent` as a boolean (`3`, `true`; not `"3"`, `"true"`) |
| Picks the right tool among five | chooses `list_files` for "list the files in reports" |
| Does not call a tool it does not need | answers "2 + 2" directly, without a tool call |
| Uses what a tool returned | answers from a tool result it was given instead of calling again |
| Recalls the start of a long prompt | repeats a code word placed at the top of a long prompt, at the measured window |

Each probe runs `--trials` times (default 3) at low temperature so a flaky model shows as flaky. Two numbers per probe:
**passed** (after Hutch's safe argument repair, which is what a bot will experience) and **unaided** (what the model
did right on its own). The verdict is *reliable*, *works, leaning on argument repair*, *unreliable* or *inconclusive*
(more than half the calls failed at the runtime, which says nothing about the model).

Profiles are keyed by model, quantisation, runtime, chat-template hash, file digest and window, so a changed file or
template is a different profile (the Models page flags "changed since measured") instead of a stale number.
`hutch doctor` warns when a bot with tools runs on a model measured unreliable, and notes models never measured.
This is a profile of one model on one machine, not a leaderboard score. It has been exercised only against scripted
models; run it on your own installed models to get real numbers.

## Model slots

A machine keeps one or two local models resident, and every swap costs seconds to minutes. The dispatcher therefore
treats a local model as a **slot**:

- runs that share the loaded (or in-use) model start immediately;
- a run that needs a different model starts only when a slot is free, and **says which model it is waiting for**;
- queued runs are batched by loaded model, so alternating bots do not swap on every run;
- a run that has waited over 15 minutes goes first, so nothing starves.

Slot count comes from the memory tier (1, or 2 on large machines); `HUTCH_MODEL_SLOTS=n` overrides it. Hosted and mock
runs are never constrained, and they cause no request to the runtime.

`hutch models swap-test <model-a> <model-b>` measures what alternating a pair really costs: cold load of A, load of B
on top, load of A again, and whether the runtime actually evicted A. It unloads and reloads your models and generates
no tokens, so run it when the machine is idle. Results appear on the Models page. *Until you run it, the page says
"not measured": Hutch does not guess swap cost.*

## What a run can cost, before it starts

Every bot page, `hutch bot estimate <bot> [--model X]` and `GET /api/bots/<name>/estimate` show a **ceiling**, not a
guess: every step re-sends the whole prompt and uses its full per-turn budget, which is exactly the arithmetic the spend
guard enforces, so the figure can never be exceeded. Typical runs cost far less. When the bot has its own per-run cap lower
than the worst case, the cap is stated as the maximum. A flat-rate plan says so (and that calls still count against your
allowance), a local model says "no per-token cost", and a hosted model **with no price on file has no ceiling and says
why**: Hutch never invents one. The chat switcher's dialog shows the same ceiling beside each hosted model.

## Usage

`/usage` answers "where did the money and the allowance go": spend and tokens by **local calendar day** (the same day the
daily caps use), by model and by bot; today against each bot's token and spend caps; each plan's allowance meter; the
share of prompt tokens served from cache; and a log of every time a run **fell back** (the model was unavailable),
**escalated** (it was not up to the job) or **stopped at a plan allowance**, newest first. Local models read "free
(local)" and flat plans read "flat plan" instead of a misleading `$0.00`.

## Hosted prices

`prices.json` rows carry a source and a **verified** date; rows over 90 days old are flagged. Correct a row on the
Models page and the new number is used immediately: it is written to `<state dir>/prices.json`, stamped today, and
**Reset** restores the bundled row. Local models cannot have a price row. A hosted model with no row **cannot run
under a spend cap**: Hutch refuses rather than guess.

## `hutch doctor`

```bash
hutch doctor              # every check, each problem with its fix
hutch doctor --deep       # also run each local bot's context self-check (uses CPU/GPU, no money)
hutch doctor --online     # authenticate connections (spends no tokens)
hutch doctor --json
```

Checks: Python version; database integrity, WAL and schema version; state-directory and key-file permissions;
runs orphaned by a dead process; the `hutch.service` user unit; each runtime (a stopped runtime is a failure only
when a bot depends on it); each local bot's model fit and the context it will actually get; connection keys and
terms; hosted bots with no spend cap; auto-approval combined with a shell. Exit status is non-zero only for a
**FAIL**; warnings do not fail it, so it can gate a script.

Per-runtime health (also on the Models page): each call's outcome is recorded; two consecutive failures mark a runtime
*degraded*, four mark it *down*, and a success clears it. One runtime's failures never change another's state.

## What is and is not verified

- Verified by tests against scripted servers: fit arithmetic, slot ordering and gating, swap measurement logic,
  override validation, the fit guard on an overridden run, price edits, doctor and health, and the switcher in a
  real browser (desktop and phone width).
- **Not verified on real models.** The development machine has about 3 GiB free and no Ollama, so swap latency,
  cold-load times and context self-check results on real local models have not been measured. The pages and commands
  report "not measured" rather than showing numbers that were not.
