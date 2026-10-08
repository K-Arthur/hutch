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
| S1 | Credential routing and SSRF (`registry.py`, `netguard.py`) | A key is only ever sent to the host it belongs to; no URL form reaches a private address | planned |
| S2 | Schema v5, lifecycle state machine, atomic claims, leases, fencing, schedule occurrences | One valid execution claim per run and per occurrence; a stale owner cannot write | planned |
| S3 | Cross-process cancel, owned worker processes, verified cleanup | Stop works from any process; no descendant outlives a terminal run | planned |
| S4 | OS sandbox, structured-tool boundary, approval CAS and identity binding | The shell cannot read `~/.ssh` or reach the network unless granted; one approval resolves once | planned |
| S5 | Runtime adapters (OpenCode, Pi) against captured contracts; compatibility matrix; offline mode | No `--auto` by default; model/session propagated; offline makes no non-loopback connection | planned |
| S6 | Conversations, messages, stable workspaces, artifacts, scoped memory, bounded delegation | A follow-up sees prior context across restart; deletion semantics as ADR-0002 | planned |
| S7 | Browser ownership and real human handoff | Bots never share a profile unless granted; automation is paused while a human holds control | planned |
| S8 | `/api/v1` contract, event stream, pairing and remote auth | A paired phone can supervise; stale input is dropped; off-loopback needs auth | planned |
| S9 | End-to-end integration, benchmarks vs baseline, docs and website alignment | Budgets hold; every claim has evidence | planned |

## Commits (this branch)

_Filled in as slices land._

## Verified behaviour

_Filled in with commands and results as slices land._

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
