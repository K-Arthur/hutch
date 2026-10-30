# Concurrent agents: worktree operating model

Several agent sessions work on Hutch at once. The 2026-10-28 checkout had 25
registered worktrees: 6.3 GB under `.worktrees/` plus external `~/.codex` and
`~/.hutch-tmp` checkouts owned by other tools. This page keeps parallel sessions
from corrupting each other's tree, generated files and validation evidence.

## Workload categories

- Context and documentation: `AGENTS.md`, `docs/`, `.ai/`, constitution, map and baseline.
- Python backend: `src/hutch/` runtime, store, tools and tool-calling.
- Dashboard and website: `src/hutch/server/`, `app/src/`, `website/`, generated CSS.
- Desktop/native: `desktop/` Tauri/Rust host and its Cargo targets.
- Browser/e2e validation: Playwright and visual checks, the heaviest lane.
- Read-only investigation: audits, searches and reports that write nothing.

## Decision review

Adopted: one worktree per task, single-writer generated surfaces, quiet
validation. A task gets a checkout under `.worktrees/<slug>`, generated artifacts
have one writer at a time, and each session runs the quiet focused gate.

Rejected alternatives:

- OS-level claim daemons or lock services: a background process plus stale-lock
  failure modes, without controlling what other agents or people do.
- Union merges or shared dirty trees: interleaved writes make ownership untraceable.
- A shared `desktop/target`: concurrent Cargo locks corrupt or serialize builds.
- Full suites or duplicate Playwright runs per worktree: they saturate the machine
  and duplicate CI; escalate only for browser-visible changes.

## Isolation rules

- Create a checkout with `git worktree add .worktrees/<slug> -b <slug>` and work only inside it.
- `.worktrees/` is gitignored, excluded from audits and search; never commit it.
- Worktrees under `~/.codex/worktrees/` and `~/.hutch-tmp/` belong to other
  sessions and tools. Never edit, prune, lock or delete them, even when stale and
  merged.
- A worktree registered inside another is a nested child; its parent is never
  pruned while it has registered children.
- Remove worktrees with `git worktree remove`, never by deleting the directory.

## Single-writer surfaces

These files have one writer at a time. If another session owns one, wait for its
task dependency or hand the edit over; never edit a conflicting copy:

- `AGENTS.md`, `package.json`, `package-lock.json`, `uv.lock`, `desktop/Cargo.lock`.
- `.ai/constitution.json`, `.file-size-baseline.json`, `.ai/repo-map.generated.md`.
- Generated CSS: `src/hutch/server/static/ui.css`, `model-switcher.css`,
  `website/app.css`, `website/styles.min.css`.
- Reviewed evidence under `docs/**/artifacts/`.

## Generated-file conflicts

- Generated files are outputs, not hand-merge targets: take one side, then
  regenerate with `npm run build:css`, `npm run agent:map`, or the
  context-hygiene audit after an intentional split.
- Lockfiles are regenerated from the manifest (`npm install` / `uv lock`), never
  hand-merged; a lockfile conflict means the manifests diverged.
- The file-size baseline changes only after an intentional split (shrink-only, reviewed).
- Evidence artifacts are historical: pick one reviewed side or re-run the capture.

## Validation under concurrency

- Default gate: `npm run check:agent` plus `npm run test:agent -- <focused paths>`.
- Agent-context changes also run `npm run audit:constitution` and `npm run audit:agent-map`.
- Check `git status --porcelain` in your own worktree before trusting a diff; an
  unexpected dirty file may belong to another session's checkout.
- Never validate, clean, stage or reformat a worktree you did not create.
- Browser/Playwright runs are explicit escalation only, never duplicated across
  worktrees for the same revision.
- Do not run full `pytest -q`, full builds or native installer builds; CI owns those lanes.

## Merge protocol

1. Update the base first (`git fetch` when configured, otherwise rebase on the local base).
2. Resolve ordinary files first; resolve generated files last by taking one side and regenerating.
3. Re-run generation, focused tests and the quiet gate.
4. Merge sessions sequentially; re-run the focused tests on the merged result.
5. Do not force-push or rewrite another session's branch; report conflicts on the task board.

## Performance and storage

- Share the global uv/pip and npm caches; only resolved environments and build output
  are per worktree.
- Each worktree pays its own `.venv` and, for native work, `desktop/target`; that is
  the cost of isolation.
- Keep one scratch root per task and prune with `python scripts/prune_validation_tmp.py`.
- No duplicate full suites: quiet focused validation per session, broad checks in CI
  once per revision.

## Machine-wide validation queue (explicit opt-in)

Hutch can share the machine-wide admission and receipt queue used by the Varve
checkout. Adoption is **explicit**: the wrapper neither imports Varve code nor
assumes a sibling-checkout path.

```bash
export VARVE_QUEUE_CLI=/absolute/path/to/varve/scripts/quality/validation-queue.mjs

# Inspect the machine-wide holder/slots
npm run queue -- status

# Run a focused gate through the queue
npm run queue -- run --label "pytest: focused" --class shared -- \
  uv run --frozen --no-sync pytest -q --no-header --tb=line tests/test_x.py
```

`--queue-cli <path>` overrides `VARVE_QUEUE_CLI` for one invocation. With
neither set, the wrapper exits 2 and explains the opt-in. There is no implicit
cross-repository default.

Queue state and receipts are machine-wide, but receipt identity includes the
repository common directory and HEAD, so Hutch never reuses a Varve receipt and
Varve never reuses a Hutch receipt. Receipts are local cache evidence only,
never CI evidence. Browser/Playwright runs stay with the existing Hutch
escalation policy; the queue does not change that boundary.

Contract and tests: [`docs/validation-queue.md`](validation-queue.md),
`tests/test_validation_queue.py`.

## Toolkit

| Command | What it does | When |
| --- | --- | --- |
| `npm run worktree:status` | Lists registered worktrees, branch/HEAD age, dirty counts, merge state, external/nested classification and stale candidates | Start of a concurrent session, and before pruning |
| `npm run worktree:prune` | Dry run: reports removable stale worktrees, changes nothing | Review before pruning |
| `npm run worktree:prune -- --apply` | Removes clean, merged, old, repo-local worktrees leaf-first, then `git worktree prune` | After confirming the dry run |
| `git worktree add .worktrees/<slug> -b <slug>` | Creates one isolated task checkout | Starting a parallel task |
| `npm run check:agent` | Quiet default gate in your worktree | Before reporting a change |
| `npm run queue -- status` | Shows the machine-wide queue holder and shared slots | Before starting a heavy gate |
| `npm run queue -- run --label ... --class shared -- <command>` | Runs a focused gate through the explicit queue wrapper | Focused tests and audits |

The toolkit only considers worktrees strictly under this repository's
`.worktrees/`; external and nested-parent worktrees are reported and protected.

## Failure modes

- Stale worktrees accumulate until disk pressure forces a rushed cleanup; check status at session start.
- Two sessions edit one single-writer surface and one update is lost; the task dependency is the lock.
- A generated file is hand-merged and drifts until the next regeneration silently overwrites the fix.
- A baseline or map regeneration races another session; regenerate only from your own staged tree.
- `git worktree remove` refuses a dirty tree; clean or hand it off, never add `--force`.
- Pruning an external worktree breaks another session; the tool refuses paths outside `.worktrees/`.
- A stale `--base` marks unmerged work as merged; rebase and re-run status before pruning.
- Several full gates at once serialize the machine and time out like regressions; keep validation quiet.
