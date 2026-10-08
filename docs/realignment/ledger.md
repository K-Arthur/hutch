# Continuation ledger

The live record of the realignment: who owns what, what has landed, what is verified, what is open. Update it in the
same commit as the change it describes.

## Coordination and ownership

Another session was committing to `main` and editing the shared checkout at the same time (observed 2026-10-07: new commits
`27a73ed`, `846f3f9`; uncommitted `cli.py`, `server/app.py`, `templates.py`, `.gitignore`). To avoid staging each other's changes,
this work lives on **branch `realign/platform`** in a separate git worktree (`.worktrees/realign`, excluded locally through `.git/info/exclude`).
Integration into `main` is a rebase/merge done only after the other session's tree is committed; see "Integration".

| Area | Owner | Rule |
|---|---|---|
| `server/static/*`, `server/pages.py`, `templates.py`, `tests/test_dashboard.py`, `tests/test_templates.py`, website visuals, design docs | Frontend / design session | Not edited here. API contracts that the UI needs are in `contracts.md`. |
| `engine.py`, `store.py` (schema v5+), `lifecycle.py`, `worker.py`, `sandbox.py`, `netguard.py`, `runtime/*`, `providers/*`, `tools/*`, `approvals.py`, `scheduler.py`, `compat.py`, `docs/adr/*`, `docs/realignment/*` | This work | |
| `models.py`, `server/app.py`, `cli.py`, `safety.py` | **Shared** | Additive hunks only; re-read the file immediately before editing; keep hunks small so rebases are mechanical. |
| Claims in `README.md`, `docs/safety.md`, `docs/architecture.md`, `docs/research/*`, `website/index.html` text | This work for *claims*; design session for *visuals* | Claim edits are minimal and text-only. |

## Integration

* Baseline for this branch: `b3e4b15` (see `baseline.md`, "Why not `main` HEAD").
* To integrate: `git fetch` nothing needed (local repo) -> in this worktree `git rebase main` once `main` is green, run the full suite, then fast-forward `main` from the main checkout (`git merge --ff-only realign/platform`). **Not done automatically** because `main` currently has uncommitted work in the shared tree and an inconsistent HEAD.
* Nothing in this work was pushed. `origin/main` is 50+ commits behind local `main` and the GitHub repository is private; pushing is not authorised by this assignment.

## Slices

| # | Slice | Invariant | Status |
|---|---|---|---|
| S0 | Baseline, evidence ledger, ADRs, claims audit | Every public claim maps to evidence or is qualified | in progress |
| S1 | Credential routing and SSRF (`registry.py`, `netguard.py`) | A key is only ever sent to the host it belongs to; no URL form reaches a private address | **landed** |
| S2 | Schema v5, lifecycle state machine, atomic claims, leases, fencing, schedule occurrences, tool receipts, cross-process Stop | One valid execution claim per run and per occurrence; a stale owner cannot write or start an action | **landed** |
| S3 | Owned worker processes, process-group teardown verified, recovery of a crashed owner's processes, commit-time event sequencing | Stop works from any process; no descendant in the run's group outlives a terminal run | **landed** (limit: a fully detached daemon is unreachable without the S4 sandbox) |
| S4 | OS sandbox, structured-tool boundary, approval CAS and identity binding | The shell cannot read `~/.ssh` or reach the network unless granted; one approval resolves once | **partial**: approval CAS + action fingerprint + expiry landed (`tests/test_approval_cas.py`, 9 pass). Sandbox (`sandbox.py`, bubblewrap) implemented and wired into the shell tool, bot field `sandbox`, fail-closed; `tests/test_sandbox.py` **11 pass, 3 FAIL** (`only_the_workspace_is_writable_and_tmp_is_private`, `no_network_without_a_grant...`, `a_file_size_limit...`) - not yet diagnosed; may be test bugs, may be real. **The full suite was NOT re-run after the S4 changes.** |
| S5 | Runtime adapters (OpenCode, Pi) against captured contracts; compatibility matrix; offline mode | No `--auto` by default; model/session propagated; offline makes no non-loopback connection | planned |
| S6 | Conversations, messages, stable workspaces, artifacts, scoped memory, bounded delegation | A follow-up sees prior context across restart; deletion semantics as ADR-0002 | planned |
| S7 | Browser ownership and real human handoff | Bots never share a profile unless granted; automation is paused while a human holds control | planned |
| S8 | `/api/v1` contract, event stream, pairing and remote auth | A paired phone can supervise; stale input is dropped; off-loopback needs auth | planned |
| S9 | End-to-end integration, benchmarks vs baseline, docs and website alignment | Budgets hold; every claim has evidence | planned |

## Commits (this branch)

_Filled in as slices land._

## Verified behaviour

| What | Command / evidence | Result |
|---|---|---|
| Six processes race for one schedule occurrence | `python docs/realignment/race_schedule.py <src> <python>` | baseline b3e4b15: **6 runs**; this branch: **1 run** |
| Six processes race to claim one run; and one bot's two queued runs | `tests/test_claims.py` (real subprocesses) | exactly one claim wins in each |
| `stop` from another process ends a run it does not own | `tests/test_cancel.py` (programmatic and through the real `hutch stop-all`) | run reaches `stopped`, owner exits 0, within 10 s; baseline left it running |
| A stalled worker whose lease lapsed cannot rewrite history or start an effect | `tests/test_cancel.py::test_a_worker_that_lost_its_lease...` | status/transcript unchanged; its `write_file` refused at admission |
| `kill -9` after an effect, before its receipt | `tests/test_cancel.py::test_a_crash_after_an_effect...` | run ends `outcome_unknown` naming the action; the effect happened once; a restarted supervisor starts nothing |
| A schema-v4 database written by the baseline upgrades | `tests/test_migration.py` (fixture generated by b3e4b15) | bot ids, schedules, memory, allows, usage, transcripts and their hash chains survive; backup written; legacy orphan recovered |
| SSRF forms and DNS answers | `tests/test_netguard.py`; live fetch of https://example.com and refusals of `localtest.me`, `127.0.0.1.nip.io` | all hostile forms refused; pinned-TLS fetch succeeds |
| Control-plane cost | `python -m benchmarks.run` vs `benchmarks/baselines/pre-realign.json` | step overhead 0.17 ms (was 0.24), 59.6k events/s (was 58.0k), idle RSS 41/60 MB (was 41/66) |
| Live dashboard: run, stop, stop-all | `hutch serve` on a private port + curl (script in the commit message) | worker is a separate pid and session leader; API Stop ends it in about a second, group gone; `hutch stop-all` from another process stops a second run; `verify` reports the hash chain intact (it was broken before the commit-time sequencing fix); 0 leftover workers |
| A worker survives a dead supervisor | `tests/test_worker.py::test_a_worker_outlives_a_dead_supervisor...` | the run keeps its lease past three lease periods, a new supervisor leaves it alone, approval completes it |
| Cost of the process executor | `python docs/realignment/bench_worker.py` | dispatch to terminal for a 4-step mock run: **216 ms** median with a worker process vs **6 ms** in-process; a worker waiting on an approval holds **38 MB** RSS. Dormant bots hold nothing. Regression budget: process-mode start-up under 400 ms on this host. |
| Control-plane benchmarks after S3 | `python -m benchmarks.run` | 75.6k events/s (baseline 52.1k; hashing moved to the writer), 0.053 ms/step (0.246), idle RSS 41/61 MB (39/56), idle CPU unchanged |
| Whole suite | `pytest --ignore=tests/e2e` | **879 passed** (baseline 637) |

## Not started (S5-S9) and other open work

OpenCode/Pi adapters against captured contracts and no default `--auto` (S5), compatibility matrix and offline mode (S5), conversations/messages/workspaces/memory/delegation (S6), browser ownership and real human handoff (S7), `/api/v1` contract, pairing and remote auth (S8), end-to-end integration, marketing/doc alignment for S4+ (S9). Integration into `main` (rebase after the other session commits `cli.py`, `server/app.py`, `templates.py`) is not done; nothing was pushed.

## Unresolved risks and limits (carried)

* Live provider, live Ollama, live Pi and live Playwright runs were not possible on the baseline host (no Ollama, Pi, or browser binaries installed; no paid-provider budget authorised). Anything that depends on them is reported as "contract-tested offline", never "verified live".
* The frontend is another session's work. Contracts are specified here, not implemented in the UI.
* OS sandbox is Linux/bubblewrap only.

## Reproducible commands

```bash
cd .worktrees/realign
uv venv --python 3.13 .venv && uv pip install -e ".[dev,browser]"
.venv/bin/python -m pytest -q --ignore=tests/e2e        # baseline: 637 passed
.venv/bin/python -m benchmarks.run                       # control-plane numbers
bash docs/realignment/journeys.sh                        # baseline user journeys against a throwaway state dir
```
