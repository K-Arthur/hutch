# Computer use and automation design (2026-11-06)

Companion to `docs/realignment/computer-automation-research-ledger.md`. The ledger holds the
evidence; this document holds the decisions and the order of work.

## Problem

Hutch already delivers a real, bounded computer-use path (EIS input into a disposable KWin session,
AT-SPI semantic actions, integrity-checked frames, human takeover) and a real automation path
(cross-process supervisor election, occurrence uniqueness, workflow engine, effect receipts). The
research found defects that make those guarantees narrower than they look:

- a schedule can stop firing silently when its marker is rendered differently but denotes the same
  instant;
- supervisor leadership is advisory because the fence is never checked and a tick is unbounded;
- unattended workflows can mutate the machine without a human because Auto does not require
  `approval_mode == "ask"`, while channels do;
- unattended browser work starts and reads without approval, contrary to the computer-use doc;
- the computer tool can crash on `close`, is skipped by the tool-catalog validation suites, and its
  budget is never shown even though the doc says it is;
- semantic-tree truncation, write outcomes and worker error types are reported inaccurately;
- public claims about workflows and computer use have drifted from the shipped copy, and the
  website e2e suite currently fails on one claim.

The goal is to make the delivered boundaries true and testable before adding reach. No new
transport, no new channel type, no broader account access.

## Invariants

1. The canonical JSON Schema in `Tool.parameters` is validated before dispatch. A second validator
   or a provider grammar never replaces it.
2. Frozen over-cap files shrink only. New logic goes in new modules; a frozen file may gain at most
   a one-line call while losing at least as much elsewhere.
3. One task touches at most three source files plus one seam. Larger work is split.
4. Autonomous runs are more constrained than interactive runs, never less. Any change to an
   execution boundary is deliberate, documented and tested through
   `.ai/skills/change-approval-boundary.md`.
5. Verification uses the real stack: a real KDE Wayland session with KWrite and AT-SPI, real
   Chromium, a real SQLite file, the real `Engine.tick()`/`run_loop`, and real short wall-clock
   intervals. Pure-logic unit tests are allowed only for parsers, schedule math and validators, and
   each is paired with a recorded real run.
6. A fixture, mock or monkeypatched clock never stands in for the thing being claimed. If the real
   environment is unavailable, the result is `UNVERIFIED`.
7. No new files in `docs/**/artifacts/`; scratch evidence stays in the session scratchpad.

## Decisions

### D1. Correctness and authority boundary first, capability later

Order: scheduler claim truth, unattended workflow authority, computer contract/lifecycle,
supervision visibility, semantic/input truth, supervisor/heartbeat, browser unattended boundary,
workflow correctness, public claims.

Rejected: starting with portal input for the owner's existing desktop, more app toolkits or new
channels. Those widen reach while silent non-firing and unattended mutation remain open.

### D2. One schedule-marker normalizer, compared by instant

Add `src/hutch/schedule_marker.py` with `normalize_marker(value)` and `markers_equal(a, b)`. Parse
with `datetime.fromisoformat`, require a timezone, convert to UTC and render a canonical string.
An unparseable marker is an explicit `blocked` record, not a silent `created_at` fallback. Call it
from `Store.submit_scheduled` in one line. Move the not-ready/blocked marker writes onto the same
compare-and-set helper.

Rejected: an epoch column (migration on a frozen store, leaves old rows) and rewriting every writer
to a canonical string (does not fix existing rows or foreign writers).

### D3. Supervisor leadership is a fence, not a hint

Expose the observed `fence` from `supervisor_state`. Every supervisor-owned action that can
double-run (recovery claim, job/source pump, occurrence admission) passes that fence and
compare-and-sets on it. Between tick phases, renew the lease and re-check ownership; a demoted
leader stops before the next destructive phase.

Rejected: a longer lease. It relocates the window and does not survive suspend or a slow tick.

### D4. Unattended workflow authority matches channels

Require `approval_mode == "ask"` for an Auto start and for a schedule-linked Auto start. Re-apply
the compiled plan envelope at execution by narrowing the interpreter's tool dict to the envelope,
not the bot-wide set. This is a deliberate tightening: record it in `docs/safety.md` and
`docs/approvals.md`, and add allowed / ask / deny tests.

Rejected: treating `auto` mode as implicit consent for local mutations. It is the exact inversion
of the autonomy rule.

### D5. Split frozen files at named seams

- `server/app.py`: move the computer state, frame and control handlers into a new
  `server/computer_state.py`; `app.py` keeps one-line registration and must not grow.
- `tools/browser.py`: move the session-start approval into a new `tools/browser_approval.py`;
  `browser.py` stays at or below 1 714 lines.
- `scheduler.py`: move window enumeration and counting into a new `schedule_windows.py`; the old
  module keeps the public names as a facade.
- `workflow/engine.py`, `workflow/persistence.py`, `store.py`: helpers go in new modules and are
  called from one line.

Rejected: a baseline exception or grandfathering a new over-cap file.

### D6. Report what actually happened

Semantic truncation sets `truncated`; a subtree `total` is counted before truncation; `set_text`
returns `dispatched`; a malformed worker line raises `InputError`; the computer state exposes
`limits`; readiness warns when the selected tool cannot run. Each is a truthfulness fix, not a new
feature.

Rejected: documenting the current behaviour as a limitation. The panel and the doc already promise
the accurate version.

## Phase roadmap

Each phase is one task or a small set of tasks. Every task carries: a failing real-world
reproduction before the change, the change, the same reproduction passing after, focused tests,
`npm run check:agent`, a commit, and a ledger update. Stop after each phase.

### P1. Scheduler claim truth

Files: new `src/hutch/schedule_marker.py`; `src/hutch/scheduler.py`; `src/hutch/store.py` (one-line
call). Seam: `tests/test_scheduler.py` and `tests/test_schedule_durability.py`.

Reproduction before: real SQLite store with marker `2026-11-06T12:00:00+00:00`; a due claim whose
expected marker is `2026-11-06T12:00:00Z` for the same instant. Today: no run, no skip, no blocked
record. After: exactly one run, marker advanced to the occurrence instant.

Also in scope: cron give-up records `blocked`; capped window counts set `uncertain`; `catch_up=skip`
grace does not collapse to the whole period for intervals at or below 240 s; occurrence projection
is ordered by `claimed_at` and shows skipped windows.

Acceptance: the reproduction passes on the real store; a second identical claim creates no second
run; the four edge cases have real tests; `scheduler.py` did not grow.

### P2. Unattended workflow authority (boundary change)

Files: `src/hutch/workflow/routing.py`, `src/hutch/workflow/submit.py`,
`src/hutch/workflow/runtime.py`. Docs seam: `docs/safety.md`, `docs/approvals.md`.

Reproduction before: a bot with `workflow_mode=auto`, `approval_mode` other than `ask`, and a plan
whose first effect is a workspace write; drive `engine.tick()` with no human. Today: the run
proceeds and the write lands. After: admission is refused with a precise reason and no effect row
is written.

Also in scope: the interpreter's tool dict is narrowed to the compiled envelope, so an
out-of-envelope call is refused at execution even if the bot has the tool.

Acceptance: allowed / ask / deny tests; a real effect sink shows zero writes in the denied case; the
boundary docs state the behavior; `.ai/skills/change-approval-boundary.md` was followed.

### P3. Computer contract and lifecycle

Files: `src/hutch/tools/computer.py`, `src/hutch/tools/computer_contract.py`,
`src/hutch/tools/computer_dispatch.py`. Seam: `tests/test_computer_limits.py`.

Reproduction before: `ComputerTool().run({"action": "close"}, ctx)` returns
`computer error: 'ComputerTool' object has no attribute '_budget'`. After: returns success and the
session is cleanly shut down.

Also in scope: `_budget` and `_human` are initialised in `__init__`; `ACTIONS`, `STATEFUL` and the
dispatch branches derive from one table; a contract test asserts the sets are equal; the approval
label map includes `computer` (app.js is the seam, separate commit if needed).

Acceptance: close-first and close-after-observe both pass; a deliberately added action cannot be
half-wired without a failing test.

### P4. Supervision visibility

P4a, state endpoint: new `src/hutch/server/computer_state.py`; `src/hutch/server/app.py`
(registration only, net shrink); `src/hutch/server/static/computer.js`.

Reproduction before: `GET /computer` during a live run has no `limits`; the panel shows no budget,
stall or refusals although `docs/computer-use.md` says it does. After: the state carries
`limits {actions, limit, unchanged_actions, stalled, refusals}` and the panel renders it.

P4b, readiness and labels: `src/hutch/readiness.py`, `src/hutch/server/static/app.js`, and the
catalog seam (`src/hutch/tools/__init__.py`, `src/hutch/integrations/catalog.py` if needed).

Reproduction before: a bot with `tools=["computer"]`, `computer_apps=[]` reports readiness `ok`;
`_CATALOG["computer"]` raises `KeyError`. After: readiness names the missing apps and Playwright;
both tools resolve through the catalog and are included in validation/compiler suites.

Acceptance: real API shape test; real readiness report; catalog completeness test; no frozen file
grew.

### P5. Semantic and input truth

P5a, truncation and write outcome: `src/hutch/computer/native/a11y_worker.py`,
`src/hutch/computer/a11y_tree.py`.

Reproduction before: a real KWrite container with more than 60 children returns a tree marked
complete and a subtree `total` equal to the truncated count. After: `truncated` is true and `total`
is the real count.

P5b, input error typing and write dispatch: `src/hutch/computer/native/eis.py`,
`src/hutch/computer/native/a11y_worker.py`, `src/hutch/computer/accessibility.py`.

Reproduction before: a malformed worker line raises `JSONDecodeError`; a refused `set_text`
reports `dispatched`. After: `InputError`; `not_dispatched` when the application reports refusal.

Acceptance: real KWin + KWrite + AT-SPI run, plus parser unit tests for the pure clamping logic;
`docs/computer-use.md` corrected for the AT-SPI adapter and the 16 KiB statement.

### P6. Supervisor fence and heartbeat

Files: `src/hutch/engine.py`, new `src/hutch/supervisor_fence.py`, `src/hutch/models.py` plus one
line in `src/hutch/store.py`.

Reproduction before: two real engines, one with a deliberately slow tick; the follower steals the
lease and both perform supervisor work. After: the demoted leader stops before the next destructive
phase and no duplicate recovery occurs. Separately, backdating `heartbeat_at` while the lease is
valid surfaces `owner_stalled` before expiry.

Acceptance: two-engine test on a real SQLite file; no lease arithmetic mocked; `docs/operations.md`
updated.

### P7. Browser unattended boundary (boundary change)

Files: `src/hutch/tools/browser.py`, `src/hutch/tools/computer.py`, new
`src/hutch/tools/browser_approval.py`. Docs seam: `docs/computer-use.md`, `README.md`.

Reproduction before: an `auto`-mode bot with the browser tool starts a session and reads a page
with no approval. After: session start asks (or is refused in a context with no approver), matching
the computer tool and the documentation.

Acceptance: real Chromium with a real approval gate; allowed / ask / denied paths; `browser.py`
did not grow; the doc statement matches both tools.

### P8. Workflow correctness

Files: `src/hutch/workflow/engine.py`, `src/hutch/workflow/runtime.py`,
`src/hutch/workflow/persistence.py`, with helpers in new modules.

Reproduction before: crash-before-settle `publish` writes a second artifact; an empty node digest
renders `"Nodes: "`; an unparseable `created_at` resets the deadline; a CLI answer waits up to
300 s. After: each is fixed with a regression.

Also in scope if the 3-file budget permits in a follow-up: the `opened_steps` tuple/string guard,
the optimistic `drained`, and the missing save idempotency receipt.

Acceptance: real subprocess crash test for the artifact, real CLI wake test, real store for the
deadline; frozen files did not grow.

### P9. Public claims truth

Files: `website/index.html`, `tests/e2e/test_website.py`, `docs/marketing-site.md`,
`docs/realignment/claims-audit.md`.

Reproduction before: the workflow marketing e2e assertion fails on
`"live provider execution remains unverified"` while the page has newer wording. After: the suite
passes at the recorded widths.

Acceptance: website e2e green; the envelope distinguishes the owner's existing desktop from a
Hutch-started disposable one; scheduling has one status; the claims audit gains computer-use and
workflow rows each tied to a real test or artifact; `tests/test_claims.py` is not presented as a
marketing-claims suite.

## Evidence plan

| Layer | Tool | Where evidence goes |
|---|---|---|
| Schedule math, marker parsing, byte caps, digest text | pytest unit tests | test output in the phase report |
| Schedule claims, leases, occurrences, recovery | real SQLite file, real `Engine.tick()`/`run_loop`, short real intervals, short `HUTCH_LEASE_SECONDS` | scratch state directory under the session scratchpad |
| Workflow admission and effects | real `Engine`, real store, real subprocess crash | scratch state plus a real append-only effect sink |
| API surfaces | real `create_app()` + `TestClient` over the real store | test output |
| Browser | real Chromium through the pinned proxy | scratch, never `docs/**/artifacts/` |
| Native desktop | real KWin virtual session, KWrite, private AT-SPI bus, real EIS | scratch; screenshots only if needed |
| Claims | focused Playwright with an isolated evidence root | never rewrite reviewed evidence |

Reclaim scratch with `python scripts/prune_validation_tmp.py` (dry run first) after long runs.

## Boundary impact summary

| Phase | Boundary effect |
|---|---|
| P1 | None (correctness) |
| P2 | Tightens: unattended Auto needs `ask` mode; envelope enforced at execution |
| P3 | None (correctness) |
| P4 | None (observability and truthfulness) |
| P5 | None (truthfulness) |
| P6 | Tightens: a demoted supervisor stops instead of continuing |
| P7 | Tightens: unattended browser start/read obeys the same approval as computer |
| P8 | None (correctness) |
| P9 | None (public copy) |

## Open questions

1. P2 assumes schedule-linked Auto also requires `approval_mode == "ask"`, matching chat-router
   Auto. If the owner wants schedule-linked Auto to remain available under a different mode, that
   is a boundary decision and should be settled before P2.
2. `docs/realignment/claims-audit.md` is a dated document; P9 will append rows and preserve the
   dated findings rather than rewrite history. Confirm at P9.
3. Phase numbering here is P1-P9 because the originating prompt's section 3 was truncated. Rename
   before the first commit if a mandated numbering exists.
