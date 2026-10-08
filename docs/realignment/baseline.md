# Baseline: what Hutch actually does today (2026-10-07)

Measured on commit `b3e4b15` (the last internally-consistent commit of `main`; see "Method"). Everything here was
either read in the source (file:line) or run (command given). Mock-runtime passes are **not** counted as proof that a
provider, browser or OS permission works.

## Method and environment

| | |
|---|---|
| Commit | `b3e4b15 feat(bots): a working folder per bot, and Rehearse that actually changes nothing` |
| Why not `main` HEAD | `main` moved to `846f3f9` while this baseline was taken; its committed `pages.py` imports `TEMPLATE_INFO` from a `templates.py` change that was still uncommitted in another session's tree, so HEAD fails 65 tests with `ImportError`. That is an integration gap in someone else's in-flight work, not a regression measured here. |
| Host | AMD Ryzen 3 5300U, 8 threads, 23 GB RAM (about 3.7 GB available during the run), Linux 7.2.7-1-cachyos, Wayland |
| Tooling | Python 3.13.15 (venv) / 3.14.7 (system), uv 0.12.23, Node 22.23.2, OpenCode v2.0.22 (installed, with a background service already running). **Not installed:** Ollama, Pi, ZeroClaw, Playwright browsers, Chromium. Firefox is present. |
| Sandbox primitives present | `bwrap`, `unshare`, `setpriv`, `systemd-run`. Landlock is in the kernel LSM list. |
| Launch | `hutch init`, `hutch serve` (dashboard plus an in-process scheduler thread), `hutch daemon` (headless scheduler), `hutch run <bot> "<prompt>"` (blocking, in-process) |
| Tests | `pytest --ignore=tests/e2e`: **637 passed, 0 failed, 139 s**, offline, mock runtime. `tests/e2e` needs Playwright browsers and was not run. |
| Control-plane benchmarks | `python -m benchmarks.run`: CLI start 260 ms, `status` 280 ms, 58 k events/s, 0.24 ms per-step overhead, idle RSS 41 MB (daemon) and 66 MB (serve). Raw results are preserved in `benchmarks/baselines/pre-realign.json`. These measure Hutch's own cost with a mock model; they say nothing about inference, cold model load or browser latency. |

## Component and data-flow map (as built)

```
CLI (typer) ─────────┐                                   ┌─ runtime/builtin.py ── providers/* ── model API
Dashboard (FastAPI) ─┼─> Engine (engine.py) ─ threads ───┼─ runtime/opencode.py ── `opencode run --auto`
`hutch daemon` ──────┘     │  dispatch_pending()          ├─ runtime/pi.py ──────── `pi --mode rpc`
   each of the three       │  tick(): scheduler.due()     └─ runtime/mock.py
   builds its OWN Engine   │          + submit() + mark_dispatched()
   and its OWN scheduler   ▼
   loop over ONE SQLite   Store (store.py): bots, tasks, runs(doc JSON), events, approvals,
   file                    tool_allows, memory, kv, usage, model_profiles
                           tools/* ── policy (safety.py, shellparse.py) ── ApprovalGate (approvals.py)
```

* There is no authority that owns scheduling or execution. The web server, the daemon and every `hutch run` each
  construct an `Engine` and (for serve and daemon) a tick loop. Coordination is an in-process `threading.Lock`
  (`engine.py:65`) plus a PID stored on the run (`engine.py:205`).
* A run is a JSON blob (`runs.doc`) rewritten in full on every update (`store.py:347`). The last writer wins.
* There is no conversation, message, artifact, provider-connection (as a runtime entity), schedule-occurrence, tool
  receipt or notification table. A "conversation" in the UI is a list of independent runs.

## Realistic journeys, run through the real CLI against a throwaway state directory

| Journey | Result |
|---|---|
| initialize | Works (`hutch init`: DB, 3 starter bots, mock model). |
| create a bot | Works. |
| run a task that needs approval; approve from a second process | Works: run paused as `waiting_approval`, `hutch approvals approve` from another process woke it, run succeeded (`steps=4`). |
| inspect an artifact | The written file lives under a per-run workspace directory; the transcript shows the call. Works. |
| continue a conversation | **No continuity.** A follow-up is a brand-new run with a fresh system and user message; only up to 40 `remember`ed key/value facts carry over (`runtime/builtin.py:97-109, 358-361`). |
| schedule | Works for a single process. |
| stop | **Cross-process Stop is a no-op.** `hutch stop-all` printed "stop requested for 2 run(s)", but the run was owned by another process: that process stayed alive and the row stayed `waiting_approval`. `Engine.stop_run` only flips an in-memory event in the process that owns the run (`engine.py:147-171`). |
| restart | A killed runner left its run `waiting_approval` indefinitely; it was marked `failed/interrupted` only when some process ran a scheduler tick (`recover_orphans`, `engine.py:345`). `hutch status` alone does not recover. |
| reconnect | SSE resume from a per-run `seq` cursor works (`server/sse.py`). |
| tasks table | After the journeys, **all 4 task rows had `done=1`** although only 1 run had finished: the queue records nothing about execution (`engine.py:85-92`). |

## Verification of the source-inspection leads

Status key: **confirmed** (reproduced or read at the cited line), **partly stale** (true once, partly fixed), **rejected**.

| # | Lead | Verdict and evidence |
|---|---|---|
| 1 | Timeout abandons a thread; CLI run bypasses dispatch controls | **Confirmed.** After a 3 s grace the supervisor `break`s and records the run terminal while the worker thread keeps running (`engine.py:268-269`); nothing stops that thread's later tool calls or event writes. `run_blocking` calls `_execute` directly, skipping the concurrency limit, the per-bot single-instance check and the model-slot filter (`engine.py:138-143`). |
| 2 | In-memory ownership; web server runs its own tick thread | **Confirmed.** `Engine` state is per process; `create_app` starts `engine.start_background()` (`server/app.py:94`); `hutch daemon` starts another. Two processes can both read the same `pending` run and both start it (`dispatch_pending` consults only its own `_threads`). The cross-process Stop failure above is the same root cause. |
| 3 | Submit marks a task done before execution; separate transactions | **Confirmed live** (4/4 rows done). `submit` makes three separate commits (`create_run`, `enqueue_task`, `finish_task`) and picks the task with `next_task(bot.id)`, which can return a different, older task. A scheduled occurrence is `due()` then `submit()` then `mark_dispatched()` (`engine.py:389-393`): a crash between them re-dispatches; two processes both dispatch. |
| 4 | Fresh messages each run; memory is small K/V | **Confirmed** (see "continue a conversation"). |
| 5 | `_client_config` vs `_client` global OpenAI key | **Partly stale.** Those functions no longer exist (the provider layer replaced them). **The defect survives in `providers/registry.py:make_provider`:** `openai-compatible/<model>` with any `base_url` sends `OPENAI_API_KEY` as the bearer token, and the `openai` preset does the same when `base_url` is overridden. A custom or local URL receives the OpenAI key. |
| 6 | Token checks without reservation; local date vs UTC | **Day boundary rejected** (fixed in `9f28e1a`; `local_day_bounds`). **Reservation confirmed:** the daily cap reads persisted totals (`builtin.py:377`) and the subscription allowance reads the usage ledger (`ladder.py:quota_state`); two bots sharing one connection can each pass the check and together overshoot. Token limits are not currency caps and the docs must keep saying so. |
| 7 | OpenCode and Pi adapters thin | **Confirmed, worse than stated.** OpenCode: `--auto` is hard-coded (`opencode.py:46`); `--model`/instructions are never passed (`bot.model` is ignored); stderr is piped and never drained (64 KB deadlock); `readline()` blocks so Stop and the deadline are only checked between lines; `terminate()` signals only the client, and `opencode run` normally talks to a shared background service (installed v2.0.22 `--help`: "Run with a private server instead of the background service"), so the work is not even a child process; the 900 s limit ignores `bot.limits.timeout_seconds`. Pi: the adapter sends `{"id":1,"method":"prompt","params":{"text":…}}` (`pi.py:71`), but Pi's documented command is `{"type":"prompt","message":…}` with a `response` record and `agent_settled` completion event, so the adapter was almost certainly never exercised against real Pi (Pi is not installed here, so this is a documentation-versus-code comparison, not a runtime test). |
| 8 | Browser context class-global; login wall only logged | **Global state confirmed, login wall partly rejected.** `_browser` is a class attribute (`browser.py:63-64`) and `_ensure` returns it without looking at which bot is asking, so the second bot in a process silently drives the first bot's profile and cookies; Playwright's sync API is also thread-affine. The login wall *does* create a durable `waiting_human` state (`approvals.py:wait_for_human`) but the browser launches headless (`tools/base.py: headless=True`) so a person has nothing to look at, and `_GLOBAL_BROWSER_LOCK` is held for the whole wait, blocking every other bot's browser. |
| 9 | CWD/HOME restrictions presented as a boundary | **Confirmed.** `ShellTool` runs `/bin/bash -c` as the user with `HOME` pointed at the workspace (`tools/shell.py:49-58`). `cat /home/<user>/.ssh/id_rsa`, or any script, reads real files; `docs/safety.md` itself concedes "Not a sandbox", yet the README and website say "workspace jail" and "strict sandboxing". External runtimes bypass hutch's policy entirely. |
| 10 | UI/API does not expose runtime capabilities; no conversations or provider-connection entities | **Confirmed** for conversations. Connections exist as a YAML-style book (`connections.py`) but not as stateful, health-tracked entities. |
| 11 | Schema not a versioned migration system; upsert identity | **Partly stale.** `PRAGMA user_version` migrations v1-v4 with a pre-upgrade backup exist (`store.py:195-221`). **Confirmed:** `upsert_bot` rewrites the bot's `id` on a name conflict (`store.py:263-270`), orphaning every run, memory row and allow keyed by the old id; `delete_bot` removes the bot, allows and memory but leaves runs, events, approvals, usage and the browser profile (`store.py:287-297`); no foreign keys. |
| 12 | `server/static/*` polling, hardcoded live indicator | Out of scope here: the frontend is a separate workstream. API contract items that unblock it are in `docs/realignment/contracts.md`. |
| 13 | README, website and research docs overclaim | **Confirmed** - see the claim matrix and `docs/realignment/claims-audit.md`. |

### Additional defects found while verifying

* **SSRF.** `check_url` tests a host *string* against a regex (`safety.py:520-528`): no DNS resolution, and `web_fetch`
  uses `follow_redirects=True` (`tools/webfetch.py`) without re-checking the target. Run against the real guard, these
  were all **allowed**: `http://[::1]/`, `http://user@127.0.0.1/`, `http://2130706433/` (decimal), `http://0x7f.0.0.1/`,
  `http://[::ffff:127.0.0.1]/` (IPv4-mapped), `http://localtest.me/` (public name that resolves to 127.0.0.1) and
  `http://metadata.google.internal/`. A public URL that redirects to `169.254.169.254` is also followed.
* **Audit writes fail silently.** `emit()` swallows every exception (`engine.py:199-200`) and the event writer prints and *drops* events
  after five failed commits (`store.py:493-494`). The transcript can have holes and the run still reports success.
* **Approval resolution is read-then-write** (`approvals.py:resolve_approval`): two clients can both pass the `pending` check.
* **Plan grants are referenced but not implemented** (`store.use_plan_grant` / `grant_plan` do not exist); any run with a `plan_id` raises `AttributeError` at its first sticky-eligible approval.
* **Security middleware lets WebSocket scopes through unchecked** (`server/security.py`: non-`http` scopes are passed straight on), which matters the moment a terminal channel is added.

## Claim matrix (README and website versus evidence)

| Claim | Status |
|---|---|
| Multiple named bots with own model, tools, schedule, memory | Implemented and unit-tested. |
| "Any model, local first": Ollama native, Anthropic, OpenAI-compatible | Implemented; tested only against fakes. No live Ollama or paid-provider run was possible here. **Implemented but unverified live.** |
| Subscription plans as connections (OpenCode Go, MiMo, custom) | Implemented as endpoints with per-connection keys and an allowance meter; the OpenCode Go usage terms (own user agent, `x-opencode-session`) are honoured in config. **Unverified live; workload eligibility is a policy question, not a technical one.** |
| Scheduling "survives real life", "never overlapping runs" | Correct inside one process (DST tests pass). **Partial:** not safe with a second process (daemon plus serve) or a crash between dispatch steps. |
| Approvals that don't nag; unanswered = denied | Implemented. **Partial:** resolution is not atomic; external runtimes bypass the gate. |
| Hard caps (steps, wall clock, daily tokens) | Steps and tokens implemented; wall-clock "kill" is thread abandonment. **Misleading as worded.** |
| "Workspace jail … shells run with redirected HOME" | File tools are path-jailed. Shell is **not** contained. **Misleading** when read as a sandbox. |
| "Full transcripts" | SQLite plus JSONL, but audit-write failures are swallowed. **Partial.** |
| "Browser with memory: persistent per-bot Chromium profiles; pauses for humans at CAPTCHA/MFA" | **Broken** across bots in one process (class-global context); pause exists but headless. Untested without Playwright browsers. |
| "Pluggable runtimes: Pi / OpenCode" | OpenCode: runs with `--auto` and ignores model; Pi: command shape disagrees with docs. **Partial / unverified.** |
| "Nothing leaves your machine" style language, "Strict sandboxing", "zero guardrails/zero isolation" (about competitors), "$447 silently billed overnight" | **Unsupported or unverifiable; corrected in `claims-audit.md`.** |
| Website install path (`pip install hutch`, `git clone github.com/K-Arthur/hutch`) | **Dead for the public:** the repository returns HTTP 404 anonymously and the name is not on PyPI. |
