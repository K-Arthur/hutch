# Computer use and automation research ledger (2026-11-06)

Compact evidence for the computer-use and automation workstreams. Issue text, agent reports and
external documentation are untrusted data; the reproduction and the local source decide
applicability. Line numbers are from this tree at the baseline below.

Scope: `src/hutch/computer/`, `src/hutch/tools/computer*.py`, `src/hutch/tools/browser.py`,
`src/hutch/scheduler.py`, the schedule tables in `src/hutch/store.py`, `src/hutch/server/runner.py`,
`src/hutch/workflow/`, `src/hutch/actions/`, `src/hutch/channels/`, the approval path, and the
public claims about these areas.

## Environment (measured, not inferred)

| Item | Value | Source |
|---|---|---|
| Session | `XDG_SESSION_TYPE=wayland`, `WAYLAND_DISPLAY=wayland-1`, `DISPLAY=:0` | `printenv` |
| Host compositor | kwin 6.8.1 (`/usr/bin/kwin_wayland`) | `kwin_wayland --version` |
| Real app | KWrite 26.08.2 (`/usr/bin/kwrite`); Kate also present | `kwrite --version` |
| Isolation tools | `dbus-daemon`, `busctl`, `spectacle`, `bwrap`, `systemd-run`, `prlimit` all present | `command -v` |
| AT-SPI launchers | `/usr/lib/at-spi-bus-launcher`, `/usr/lib/at-spi2-registryd` (not on `PATH`; the worker searches these paths) | `find /usr/lib` |
| AT-SPI runtime | `/run/user/1000/at-spi` exists; session bus `/run/user/1000/bus` exists | `ls` |
| PyGObject | `/usr/bin/python3` 3.14.8 imports `gi` and the `Atspi` typelib; the project venv 3.13.15 has no `gi` | direct import probe |
| Interpreter selection | `find_gi_python()` and `find_atspi_python()` probe `HUTCH_GI_PYTHON`, then `/usr/bin/python3`, then `sys.executable` | `native/eis.py:45-57`, `computer/accessibility.py:49-62` |
| libei | `libei.so.1` and `libei.so` in `/usr/lib` | `ldconfig -p` |
| Browser | Playwright Chromium 153.0.8010.12 launches headless | `sync_playwright` probe |
| Python | project `.venv` 3.13.15; `pytest`, `croniter`, `fastapi`, `PIL` present | `importlib.util` |
| Git | `main` at `6d9c5c46`; untracked `.commandcode/` and `docs/realignment/provider-expansion-2026-11/` belong to other sessions and are not touched | `git status` |

Consequence: the native EIS + KWin + KWrite + AT-SPI path is genuinely runnable on this host.
Physical phones, live Telegram and live hosted-provider calls are not available and will be recorded
`UNVERIFIED`.

## Evidence classes used below

- **reproduced** - a command in this session produced the stated failure on the real package.
- **source-confirmed** - the code path is unambiguous; the real reproduction is scheduled in the
  phase that fixes it.
- **real test** - an existing test drives the real process, database, browser or compositor.
- **UNVERIFIED** - not exercised here.

## Computer use

| ID | Sev | Evidence | Observed vs claimed | Reproduction / next real check | Regression |
|---|---|---|---|---|---|
| CU-01 | High | `tools/computer.py:41-52`, `:97-99`, `:335`, `:355-359` | `_budget` and `_human` are never initialised. `close` as the first action reaches `_shutdown` and raises `AttributeError`; the tool reports `computer error:`. **Reproduced**: `ComputerTool().run({"action":"close"}, SimpleNamespace(dry_run=False))` -> `False \| computer error: 'ComputerTool' object has no attribute '_budget'` | Same call in `tests/test_computer_limits.py` after the fix | A close-first test |
| CU-02 | High | `tools/__init__.py:60-84`, `:116`; `tests/test_toolcalling_validation.py:164` | `browser` and `computer` are absent from `_SPECS`; `_CATALOG[name]` raises `KeyError`. Compiler, validation and schema-cache suites silently omit the two largest schemas. **Reproduced**: `_CATALOG["computer"]` -> `KeyError 'computer'`; `_CATALOG["browser"]` -> `KeyError 'browser'` | Add a catalog test that enumerates both, then run `npm run test:agent -- tests/test_toolcalling_validation.py tests/test_toolcalling_compiler.py tests/test_toolcalling_schema_cache.py` | Catalog completeness test |
| CU-03 | High | `readiness.py:93-105`; `tools/computer.py:129-131` | Readiness never inspects `computer`, `computer_apps` or Playwright. A bot with the computer tool and no allowed app reports `ok`, then refuses at first use. | Real `readiness` report for a bot with `tools=["computer"]`, `computer_apps=[]` | Readiness warning test |
| CU-04 | High | `tools/browser.py:628-706`, `:1485`; `safety.py:585-593`; `docs/computer-use.md:319-323` | Unattended browser work is less constrained than documented: session start, `goto`, `read`, `observe`, `wait` and `tabs` need no approval; only `click`, `type`, `click_at`, `upload`, `download` ask. The doc claims browser behaves like computer when approval is needed. | Real `Engine` + real store + approval gate in `auto` mode; assert the first browser action | Auto-mode browser boundary test |
| CU-05 | Med | `native/a11y_worker.py:169-176`, `:262-267` | `MAX_CHILDREN` drops children without setting `truncated`; a subtree `total` is the truncated length, so an incomplete tree reads as complete. | Real KWrite tree with more than 60 children in one container | A11y truncation test (real + parser unit) |
| CU-06 | Med | `native/eis.py:181-188` | `json.loads(line)` is unguarded; a malformed worker line raises `JSONDecodeError`, not the documented `InputError`. | Feed a malformed line through a real `EisInput` worker pipe | Input error-type test |
| CU-07 | Med | `native/a11y_worker.py:327-329`; `computer/desktop.py:330-336` | `set_text` returns no `dispatched` key, so the "application reported that the action did not run" branch is unreachable for writes; a failed write is reported `dispatched`/`mismatch`. | Real KWrite editable element that refuses a write | Semantic write outcome test |
| CU-08 | Med | `docs/computer-use.md:185-192`; `server/app.py:5442-5458`; `static/computer.js:143` | The doc says every result carries `limits` and the panel shows it. The state endpoint returns no `limits` and the panel renders none. | `GET /computer` state during a live run | State shape + panel render test |
| CU-09 | Low | `computer/doctor.py:225`; `native/eis_worker.py:155` | Doctor probes `libei.so`; the worker dlopens `libei.so.1`. A host can pass the probe and fail at input start. | `hutch computer doctor --json` versus a real session start | Doctor agreement test |
| CU-10 | Low | `tools/computer_contract.py:11-28`; `tools/computer_dispatch.py:25-48`; `tests/test_computer_limits.py:115` | The action set is maintained three times with no equality test; a new action in one place yields "unhandled action". | Static comparison of `ACTIONS`, `STATEFUL` and dispatch branches | Contract equality test |
| CU-11 | Low | `computer/accessibility.py:214` | `assert self._latest is not None` is control flow and disappears under `python -O`. | Import and call with `-O` | No-assert build test |
| CU-12 | Low | `docs/computer-use.md:103`, `:267`, `:156`; `transport.py:18`; `static/app.js:8511` | Doc says "no AT-SPI semantic action adapter" while `activate`/`set_text` ship; says 16 KiB per command while the code uses 17 408 B; names a settings section that does not exist. | Doc truth review | Doc contradiction check |
| CU-13 | Low | `static/app.js:6993-7003` | The approval label map has `browser` but not `computer`, so desktop approvals use the generic label. | Pending desktop approval render | Label coverage test |

## Scheduler and persistence

| ID | Sev | Evidence | Observed vs claimed | Reproduction / next real check | Regression |
|---|---|---|---|---|---|
| SC-01 | High | `store.py:6751-6753`; `scheduler.py:484-494` | Marker CAS compares raw strings. Equivalent ISO renderings (`Z`, `+00:00`, microseconds) parse to the same instant but never equal, so the schedule is due every tick and creates no run, no `blocked` record and no `last_skip`. | Real SQLite: store marker `2026-11-06T12:00:00+00:00`, claim with expected `2026-11-06T12:00:00Z` for the same instant; assert one run after the fix | Normalized-marker claim test |
| SC-02 | High | `store.py:7024-7053`, `:7060-7067`; `engine.py:1646-1670`, `:1767` | Supervisor `fence` is incremented but never verified. Renewal happens only at loop top while `tick()` is unbounded; a tick over 30 s lets a follower steal leadership while the old leader keeps doing supervisor work. | Two real `Engine` instances, one with a deliberately slow tick; assert no duplicate recovery/pump | Fencing test |
| SC-03 | Med | `store.py:273`, `:6929`, `:6987`, `:2460-2461`; `models.py:660-666` | `heartbeat_at` is written but never read; a stalled owner is indistinguishable from a dead one until the lease expires. | Backdate `heartbeat_at` while the lease is still valid; assert the API reports `owner_stalled` | Heartbeat projection test |
| SC-04 | Med | `scheduler.py:496-499`; `engine.py:1483`, `:1517` | Not-ready/blocked workflow routine branches advance the marker with a non-CAS `kv_set`, bypassing the occurrence ledger and allowing rollback churn. | Real workflow schedule with a not-ready revision; assert no uncounted window | CAS-only marker test |
| SC-05 | Med | `scheduler.py:147-154`, `:366-368` | Cron newest-window search gives up after 8 croniter steps and returns `None`, treated as "not due" with no blocked/skip record. | Cron expression whose newest window is more than 8 steps back | Cron give-up test |
| SC-06 | Med | `scheduler.py:253-268`, `:376` | `_count_windows` can exhaust its scan bound with `count < 50` and still report `uncertain=False`, so `missed_windows` is presented as exact when it is a floor. | Long gap plus a pathological expression | Uncertainty flag test |
| SC-07 | Med | `store.py:2463-2464`, `:7006-7013` | `waiting_workflow` and `waiting_child` runs are excluded from liveness, so a dead owner of a parked run is never reported. | Parked workflow, kill owner, expire lease, recover from a second engine | Parked-run recovery test |
| SC-08 | Med | `scheduler.py:405-409`; `store.py:6767` | `buffer_one` is enforced against the newest 50 runs globally; a later occurrence can be admitted while one is pending. | Busy store with more than 50 newer runs | Buffer-one scope test |
| SC-09 | Med | `scheduler.py:288-292` | `catch_up=skip` grace collapses to the whole period for any interval <= 240 s, so past windows always run. | 60 s interval with a real short gap | Short-interval skip test |
| SC-10 | Med | `store.py:4107`; `server/app.py:3237` | Occurrence projection uses `ORDER BY occurrence DESC`, not `claimed_at`; after a marker rollback the UI can pair a stale occurrence. | Two occurrences with inverted claim times | Projection ordering test |
| SC-11 | Med | `store.py:537`, `:545`, `:282`, `:529`, `:574` | Migration v20 aborts on one corrupt bot document and reserves phantom IDs; the v5 occurrence table is never dropped. | `tests/fixtures/` pre-v20 input with one corrupt document | Migration resilience test |
| SC-12 | Low | `store.py:4098-4109` | No retention or prune path for `schedule_occurrences_v20`. | Long-lived state directory | Retention test |
| SC-13 | Low | `scheduler.py:447-453`, `:473-476` | `_windows_between` fabricates a "newest" that is not a fire instant; currently test-only. | Call directly with an interval anchor in the past | Window math test |
| SC-14 | Low | `engine.py:1496-1512` | Workflow-backed occurrences bypass `Store.submit_scheduled`, so durability tests do not cover the path most likely to drift. | Workflow schedule claim with two supervisors | Workflow-claim durability test |
| SC-15 | Low | `scheduler.py:296-335` | `next_fire` and `preview` ignore `enabled` and `bot.archived`, distorting wake computation. | Disabled schedule with a near next fire | Wake computation test |

## Workflow automation

| ID | Sev | Evidence | Observed vs claimed | Reproduction / next real check | Regression |
|---|---|---|---|---|---|
| WF-01 | High | `workflow/routing.py:101-126`; `channels/persistence.py:110-111`; `approvals.py:116-119` | Auto workflow start has no `approval_mode == "ask"` requirement, unlike channels. With `auto` mode answering non-outward asks as `bot_auto_permission`, local mutations run with nobody present. | Real bot with `workflow_mode=auto`, `approval_mode` other than ask, a plan that writes; assert refusal before any effect | Autonomy boundary test |
| WF-02 | Med | `workflow/runtime.py:54-56`; `workflow/engine.py:1109`; `workflow/compile.py:289` | The plan envelope is enforced at compile/submit but not re-applied at execution; the interpreter receives the bot-wide tool dict. | Plan with a narrow envelope on a bot with extra tools; assert an out-of-envelope call is refused | Envelope-at-execution test |
| WF-03 | Med | `workflow/engine.py:142`, `:1084`, `:1018-1021` | `opened_steps` stores `(site_id, instance_key)` tuples but is compared to a bare `instance_key`, so the missing-step guard can never fire. | Node row without a run, then re-enter | Dead-guard regression test |
| WF-04 | Med | `workflow/engine.py:483-487`; `workflow/persistence.py:1730-1743` | The interpreter asserts `first_success` is `drained` without checking child terminality, weaker than the supervisor gate; a never-dead child parks the workflow forever. | A discard child that never becomes verifiably dead | Drain gate test |
| WF-05 | Med | `runtime/artifacts.py:56-61`; `workflow/engine.py:495-508` | `publish` is append-versioned, so re-entry after crash-before-settle writes a second artifact; only the last path is recorded. | Kill between write and settle, then continue | Publish idempotency test |
| WF-06 | Med | `server/workflows_api.py:632-633`, `:658-671` | `POST /workflows` requires an idempotency key but persists no receipt; a retry creates another revision. | Repeat the same save with the same key | Save replay test |
| WF-07 | Med | `workflow/submit.py:364-384`; `store.py:4169-4180` | `status()` issues a raw `BEGIN` on the shared connection inside `store._lock`, while `Store._tx` uses `BEGIN IMMEDIATE`; a nested call can raise "cannot start a transaction within a transaction". | Submit inside a transaction-holding path | Nested transaction test |
| WF-08 | Low | `workflow/runtime.py:242` | Digest line precedence makes `or "none"` unreachable; an empty list renders `"Nodes: "`. | Empty node list digest | Digest text test |
| WF-09 | Low | `workflow/engine.py:43`, `:1115` | `MAX_RESULT_BYTES` is applied to a character slice, not bytes. | Multi-byte result over the cap | Byte-bound test |
| WF-10 | Low | `workflow/runtime.py:118-126` | An unparseable `created_at` yields `elapsed = 0`, silently resetting the instance deadline instead of failing closed. | Corrupt instance `created_at` | Fail-closed deadline test |
| WF-11 | Low | `workflow/persistence.py:1919-1976`; `cli.py:2218-2235` | `answer_question` never notifies the bus; HTTP and phone routes add it, the CLI does not, so continuation waits up to about 300 s. | Answer through the CLI with no tick | CLI wake test |
| WF-12 | Low | `workflow/persistence.py:1979-1989`; `workflow/holds.py:19-23` | Question expiry and archived-hold release depend on a supervisor tick; with no supervisor a workflow waits indefinitely, and an archived hold never expires. | Answer/expire with no supervisor | Expiry independence test |

## Public claims and validation

| ID | Sev | Evidence | Observed vs claimed | Reproduction / next real check | Regression |
|---|---|---|---|---|---|
| TR-01 | High | `tests/e2e/test_website.py:1038`; `website/index.html:973` | The test expects "live provider execution remains unverified"; the page says "workflow execution itself remains unverified beyond the two dated DeepSeek text checks". The website suite currently fails. | Focused Playwright run of the workflow marketing test | Updated claim pin |
| TR-02 | Med | `tests/test_claims.py:1` | The file is the DB ownership-lease suite, not a marketing-claims suite; the name misleads. | Read the module docstring | Rename or a new claims suite |
| TR-03 | Med | `docs/realignment/claims-audit.md` | The audit predates computer use and workflows; `T-RESERVE` and `T-BROWSER-REBIND` appear in no test file. | Search the audit gates across `tests/` | New audit rows |
| TR-04 | Med | `docs/marketing-site.md:59-60`; `website/index.html:987` | The envelope says "authenticated PTY/physical desktop control" is unavailable, while the site advertises a disposable Wayland desktop with accessibility control; the existing-desktop distinction is absent. | Compare the envelope with the availability row | Envelope correction |
| TR-05 | Low | `docs/marketing-site.md:58`; `website/index.html:603`, `:985` | Scheduling is "Supported" in the envelope but "Experimental" on the page, and the feature card carries no badge. | Read the three locations | Label agreement test |

## Already-verified capabilities (do not regress)

| Capability | Evidence |
|---|---|
| Real EIS input through a private `connectToEIS` socket into a disposable KWin session | `tests/e2e/test_computer_native.py` (real KWin + KWrite); `native/eis_worker.py:72-84` |
| Real AT-SPI read and semantic activation, with effect read back from disk | `tests/e2e/test_computer_semantic_native.py` (real KWrite + private bus) |
| Bounded, integrity-checked frames with run-scoped retention | `computer/frames.py:26-34`, `:151-216`; `tests/test_computer_frames_and_images.py` |
| Human takeover fencing, one-viewer rule, no replay, ephemeral text | `computer/human.py:89-103`, `:206-251`, `:316-317`; `tests/test_computer_human.py` |
| Cross-process supervisor election and occurrence uniqueness | `tests/test_claims.py:64,77,185` (six real processes) |
| Marker CAS and occurrence PK under canonical, identical rendering | `store.py:6751-6789`; `tests/test_claims.py:185,248` |
| Effect receipts with replay/unresolved semantics | `runtime/steps.py:60-148`; `tests/test_workflow_effect_receipts.py` |
| Telegram outbox uncertainty and reconciliation | `channels/telegram.py:72-89`; `channels/outbox.py:137-156`; `tests/test_notifications.py:147` |

## Rejected alternatives

| Alternative | Why rejected | Chosen response |
|---|---|---|
| Add portal input for the owner's existing desktop first | It widens the execution boundary while silent scheduler non-firing and unattended local mutation remain open | Fix delivered boundaries first; portal work stays out of scope |
| Store schedule markers as numeric epochs | Requires a migration on a frozen store and does not normalize existing rows | Parse and compare instants through one helper |
| Lengthen the supervisor lease instead of fencing | Moves the split-brain window without closing it; a suspended host still yields a stale owner | Verify a fence token and bound the tick |
| Treat `auto` approval mode as consent for local mutations | Makes autonomous runs less constrained than interactive runs | Require `approval_mode == "ask"` for unattended automation and re-apply the plan envelope |
| Add a fixture desktop, fake scheduler or demo channel to make tests pass | Forbidden by the task and hides the real failure | Real KWin/KWrite/AT-SPI, real SQLite and tick loop, real Chromium, real HTTP |
| Capture new evidence into `docs/**/artifacts/` | Reviewed evidence trees are not modified by this work | Write scratch evidence under the session scratchpad and cite commands |

## Baseline

- Branch `main`, HEAD `6d9c5c46`, working tree clean except untracked `.commandcode/` and another
  session's `docs/realignment/provider-expansion-2026-11/`.
- Schema: current migrations through the schedule identity tables (`store.py:282-309`, `:522-580`).
- Frozen files in scope: `store.py` (12 593), `scheduler.py` (523), `server/app.py` (7 461),
  `server/workflows_api.py` (1 312), `tools/browser.py` (1 714), `workflow/engine.py` (1 357),
  `workflow/persistence.py` (2 062), `workflow/plan.py` (393, under cap but over the guideline),
  `safety.py` (593), `sandbox.py` (641). None may grow.

## UNVERIFIED in this phase

- Physical phone input and any live iOS/Android behaviour.
- Live Telegram delivery and live hosted-provider execution.
- The owner's existing (non-Hutch) desktop and portal consent flow; not implemented.
- Non-KDE toolkits under AT-SPI (GTK, LibreOffice) and their tokenizers.
- Full native and browser e2e runs: they are the evidence for P3, P5 and P7, not for this phase.

## Phase log

| Phase | Status | Commit | Evidence | Notes |
|---|---|---|---|---|
| P0 research and design | Complete | `58c45c45` | this ledger; `docs/realignment/computer-automation-design.md` | Two real reproductions recorded: CU-01 and CU-02. All other findings are source-confirmed; each fixing phase starts with its own real reproduction. |

Verification actually run for P0:

```bash
npm run check:agent
# Context hygiene check passed (1040 source files; 117 frozen over-cap files).
# Tool contract check passed (47 registered tools; canonical schemas certifiable; specs match).
# Constitution check passed (3 roles, 14 rules; every rule maps to existing enforcement).
# Agent map check passed (119 lines; 2471 tracked files scanned).

.venv/bin/python - <<'PY'
from types import SimpleNamespace
from hutch.tools.computer import ComputerTool
print(ComputerTool().run({"action": "close"}, SimpleNamespace(dry_run=False)))
from hutch.tools import _CATALOG
_CATALOG["computer"]  # KeyError
PY
# CU-01 close-first: False | computer error: 'ComputerTool' object has no attribute '_budget'
# CU-02 catalog computer: KeyError 'computer'

uv run --frozen --no-sync python scripts/audit_emoji.py --root docs/realignment
# audit:emoji - clean (scanned 668 files, 0 waiver(s)).
```

Environment probe results are in the Environment table above; they were measured on this host, not
inferred from the repository.

Next phase: P1, scheduler claim truth. It starts with the real SQLite marker-rendering
reproduction and must not begin until a fresh session.

Open questions carried forward:

1. P2 assumes schedule-linked Auto also requires `approval_mode == "ask"`. Settle before P2.
2. P9 will append to `docs/realignment/claims-audit.md` rather than rewrite the dated findings.
3. Phase IDs are P1-P9 because the originating prompt's section 3 was truncated.
