# Agents, bots and conversations: plan

Date: 2026-10-30. Branch: `agents/bots-conversations`, forked from `main` at `02cf968b`.

## Why this work exists

Hutch already has a durable conversation model, an atomic completion contract, a governed
whole-Bot deletion path and a bounded delegation preview. Two independent lines of evidence agree
on what is actually missing:

- The external research (`research-notes/grok-codync.md`, `openclaw.md`, `nanoclaw-failures.md`)
  shows the failure that recurs across products is not "too few features" but identity and
  lifecycle ambiguity: a retired assistant that keeps working, an identity key that silently
  changes, work that survives its owner's decision to stop it.
- The repository inventory (`research-notes/hutch-inventory.md`) finds exactly one completely
  missing lifecycle state: there is no way to retire an assistant and keep its history.

Tonight's absence is specific. An owner has three options and no fourth:

- `sidebar_hidden` - display only; the assistant still answers, still runs schedules.
- `paused` - "schedules skipped while paused" (`docs/bot-config.md:110`); interactive chat still works.
- `hutch bot delete` - governed, irreversible erase of the assistant and its managed files.

There is no reversible retirement. That is the gap this work closes.

## Non-goals

- No group chat, no multi-owner sharing, no hosted execution. Hutch is single-owner and local-first;
  the research on Grok Bot and Codync groups concluded that shared rooms add a permission surface
  this product does not have, and the assignment permits documenting that decision instead.
- No new persistent entity. `archived` is a field on the existing `Bot` document; no table, no
  join, no second registry.
- No change to the conversation completion, event projection, idempotency or delegation contracts.
  Those are covered by existing tests and are not modified here.
- No live-model claims. The available local inference is an OpenCode-hosted route; where a scenario
  needs a model call, the report says which route was used and what remained unverified.

## Domain decisions

`Bot` is the persistent assistant identity and configuration. `Run` is one execution attempt.
`Conversation` is the durable transcript. `archived` describes the *assistant's* lifecycle, never a
conversation, a run or a session:

- Archiving refuses **new** work at admission. It does not kill work already running; an owner who
  archives while a run is active is told to stop it first. Silently killing work would make the
  action a destructive one under a reversible name.
- Archiving keeps every conversation, message, run, event and memory record. That is the whole
  point: history outlives the retirement.
- Archiving removes the assistant from the active roster and from specialist eligibility, so it
  cannot be selected for delegated work.
- Archiving does not delete schedules and does not replay missed windows. The scheduler skips an
  archived assistant in the same transaction that admits an occurrence, exactly as it already does
  for `paused` (`docs/bot-config.md:292-295`), so a stale due-time snapshot cannot slip through.
- The workspace coordinator cannot be archived. It is the product's first-run entry point; the
  owner is told to make another assistant main first, which mirrors the existing rule that the
  coordinator "stays visible and outside specialist sections".

## Slices

Each slice is independently verifiable and committed separately.

1. **Persistence and admission** (`models.py`, `store.py`, `tests/test_bot_lifecycle.py`).
   `Bot.archived`, one store command with idempotency and a live-run refusal, and one shared
   admission predicate called by every path that can create work for a Bot.
2. **HTTP surface** (`server/app.py`, `tests/test_api.py`).
   `POST /api/v1/bots/{ref}/archive` with an idempotency key; `archived` in `bot_view`;
   archived assistants excluded from specialist eligibility.
3. **CLI** (`cli.py`, `tests/test_cli.py`).
   `hutch bot archive` / `hutch bot restore`, reporting the same refusals as the API.
4. **Application UI** (`server/static/app.js`, `server/static/studio.css`, `tests/e2e/`).
   Archive and restore from the roster and the assistant settings page; a distinct archived
   section; a composer that explains why it will not send instead of failing after the fact.
5. **Documentation and marketing** (`docs/bot-config.md`, `docs/architecture.md`,
   `docs/marketing-site.md`, `website/index.html`, `README.md` where inaccurate).
   Documented states, refusals and limits; public claims limited to what ships.

## Acceptance criteria

- An archived assistant refuses a new conversation message, a legacy run, a scheduled occurrence
  and specialist eligibility, each with a distinct, testable error.
- Archiving with an active run is refused and names the run.
- Conversation history for an archived assistant remains readable and exportable.
- Restore returns the assistant to the roster with its history and schedules intact, and does not
  admit work that was refused while archived.
- Two identical archive commands with one idempotency key produce one state change.
- Archiving a fresh database and upgrading an existing one both work; the change is additive and
  needs no schema migration because `archived` lives in the existing Bot document.
- `npm run check:agent` passes; focused suites for every touched behaviour pass.

## Risks

- Every admission path must be covered or the guarantee is cosmetic. The shared predicate is the
  mechanism; the tests assert each caller.
- The SPA caches the roster; archive/restore must invalidate it the same way hide/pin already do.
- The archived state must not leak into delegation: an archived specialist must be refused at
  assignment time, not only at dispatch time.
