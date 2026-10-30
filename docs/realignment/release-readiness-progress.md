# Release readiness: durables and slice log

Updated 2026-10-30. Read this first when resuming. Everything here was checked against the repository on
that date; recheck anything you rely on, and treat a changed file as invalidating its old evidence.

## Durables

**Goal.** A public, non-commercial release of Hutch whose frontend reads as the product it is: one shell, one
vocabulary, honest states, and no control that promises more than its backend does.

**Owner decisions (do not reopen).**

1. Merge Conversation history, Activity and Work history into one destination (default name "Activity",
   tabs Now / History / Conversations) unless screenshots show it is worse; keep `#/chats`, `#/overview`
   and `#/runs` working as redirects. Scheduled work stays separate.
2. Audit tooling is tracked, not deleted. Done.
3. No fixture-driven preview page is served from `src/hutch/server/static/`. Done, with a guard test.
4. Plan-wide approvals do not exist and no UI may offer them. Done.
5. The frontend does not yet read as the product Hutch is; coherence is a deliverable, not polish.
6. No other agent is active; the working tree and leftover worktrees are this work's responsibility.

**Authority.** Commit on `main` with explicit paths and no AI-attribution trailer. Never push, publish, tag
for release, deploy, add dependencies, sign, spend, or open any `*.db*` file, state directory or `.env*`.

**Canonical checks.**

```bash
npm run check:agent                 # context hygiene, tool contracts, constitution, agent map
.venv/bin/python -m pytest -q --no-header --tb=short -p no:cacheprovider tests/<file>.py
.venv/bin/python -m pytest -q --no-header --tb=line -p no:cacheprovider --ignore=tests/e2e   # ~21 min
npm run build:css --silent          # deterministic; a second run must change nothing
.venv/bin/python scripts/audit_emoji.py
.venv/bin/python scripts/worktree_tools.py prune        # dry run; --apply removes clean merged worktrees
```

The sandbox may block `uv` cache writes, so call `.venv/bin/python` directly. Browser: Playwright 1.63.0,
Chromium revision 1243. The agent map embeds tracked-file counts: stage every new file, regenerate
(`python scripts/generate_agent_map.py --write`), and commit the map with them.

**Hard-won cautions.**

- `tests/e2e` runs must not rewrite reviewed evidence. Two tests did; they now write to the isolated
  artifact root unless `HUTCH_ONBOARDING_EVIDENCE_DIR` or `HUTCH_DELETION_EVIDENCE_DIR` is set.
- Frozen over-cap files (see `.file-size-baseline.json`) may only shrink. New logic goes in new modules.
- The legacy `openModal` owns one dialog at a time; nested flows use `HutchOverlay.confirm`.
- Zsh does not word-split unquoted variables; use `bash` for loops over lists.

**Off-repository archive.** `~/hutch-quarantine-2026-10-30/` holds everything removed from the tree
(preview harness and fixtures, scrape dumps, bulk captures, brand research, re-captured evidence). Local
tags `archive/*` preserve every unmerged branch tip. Triage:
`docs/realignment/unmerged-branch-triage-2026-10-30.md`.

**Sources.** `docs/realignment/start-state-audit-2026-10-30.md` (findings S1-S9, fresh-state evidence,
comparison with Hermes Agent, OpenClaw and Grok Bot), `docs/realignment/long-horizon-prompt.md`,
`PRODUCT.md`, `DESIGN.md`, `docs/design-system.md`, `docs/overlays/COMPLETION.md`.

## Slice log

Status words: **verified** (checked by a command recorded here), **implemented** (code in, not independently
checked), **not run**, **open**.

| Slice | Status | Commits | Evidence |
|---|---|---|---|
| P0 reproducible repository: audit tooling, baseline, `.ai/` tracked; sdist allowlist; map within cap | verified | `d93ae7e2` `2dbe4787` `44ed5a2c` `8e663bc0` | fresh clone runs `check:agent` scripts and the README responsive command; emoji audit clean |
| P0 audit findings fixed by splitting, not by raising caps | verified | `70e4fa09` | `bot_deletion.py` 1067 -> 381 lines plus three layered modules; `cli.py` and `store.py` at or below their caps |
| P0 migration test fixture over-dropped tables | verified | `27d94414` | two upgrade tests that failed at clean HEAD pass; production migrations unchanged |
| P0 land the uncommitted work | verified | `79a37973` `29561b47` `332d44dc` `728e0b4f` `de4a84cd` | tree clean; focused browser suite 176 passed, 1 skipped, 0 failed (24 files) |
| P0 workflow currency ceiling (`budget.max_cost_usd`) | verified | `696b9f37` | 36 budget tests pass; ceiling cannot be raised or removed by amendment; frozen files below caps |
| P0 no preview or fixture file under `static/` | verified | this commit | `tests/test_static_has_no_demo_surfaces.py` fails on the old harness filename |
| P0 full non-browser suite green at a clean clone | see ledger | | recorded in `ledger.md` after the final run |
| P1 product spine (`product-spine.md`): definition, loop, canonical terms, navigation, contradiction list | verified | see git log | 36 contradictions in 9 groups (D, T, N, C, X, V, M, G, S), each with file and line and a phase or a keep-reason; line numbers re-read from the tree; two claims corrected after a wider search (C2 scope of "Stop all", X4 dead-template evidence). G1 (chat hides approval mode and spend) rests on source search, not a capture: decided by the P2 capture |
| P2 navigation and shell (merge, titles, one chrome) | not started | | |
| P3 start states and first success | not started | | S2, `hutch doctor` and service offer in first run |
| P4 UI promises versus backend sweep | partly done | `06887b15` `696b9f37` | see the table below |
| P5 README, site and docs truth | not started | | |
| P6 release readiness (build, install, smoke; never publish) | not started | | |

## UI promises versus backend (P4 seeds)

| Item | State |
|---|---|
| "For this plan" approval control that granted a single use | fixed, regression tests (`06887b15`) |
| Workflow spend ceiling specified by tests but unbuilt | built (`696b9f37`) |
| Models page says no route while first run says OpenCode is ready (S2) | open |
| Page titles `hutch — hutch`, `Models - hutch` (S3) | open |
| `/models` and `/usage` are separate server pages with different chrome (S4) | open |
| Overlapping history destinations (S5) | decided, not implemented |
| First run does not offer `hutch doctor` or the background service | open |
| `/legacy`, `/legacy/connections` and the dead body of `bots_page` | open; remove only after tests show nothing depends on them |
| Seven merged-branch worktrees still hold uncommitted edits | not examined |
| `agent-connections` themes (skill ZIP import, versioned effective configuration, persisted assistant identity, others) | product decision; tag `archive/agent-connections-2026-10-11` |
| No screen-reader or axe-core pass; no live-model first-task run | not run |

## Next

Start at P1: write `docs/realignment/product-spine.md` from `PRODUCT.md`, the README and `DESIGN.md`, list
every contradicting surface with file and line, then P2.
