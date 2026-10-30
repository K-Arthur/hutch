# Unmerged branch triage (2026-10-30)

Seven refs held commits that were not on `main`. Each was classified against current `main` by three
independent signals before anything was changed: a dry-run three-way merge
(`git merge-tree --write-tree`), file-level comparison against `main`, and, for files that exist on
both sides, the share of the branch's meaningful added lines (25+ characters) that are already present
in `main`'s version of the file. Subject-line matching was also tried and found nothing, because the
work was re-landed under new commits, so it is not used as evidence.

Every tip is preserved as a local annotated tag (`archive/*`, not pushed). Nothing in this table is
unrecoverable: `git switch -c <name> <tag>` restores a branch, `git worktree add <path> <tag>` a checkout.

| Ref (preserved as tag) | Commits | What the evidence shows | Action |
|---|---|---|---|
| `brand/plan` (`archive/brand-plan`) | 3 | Docs only: root `PROGRESS.md` and `docs/brand/00-PLAN.md`, the Phase 0 plan of 2026-10-28. Merges cleanly. The brand program continued in `.pipeline/brand/2026-10`, which is on `main`; a root progress log is transient. | Tagged. Branch and worktree removed. Not merged. |
| `brand/phase-1` (`archive/brand-phase-1`) | 4 | The three `brand/plan` commits plus one Phase 1 research WIP commit. The worktree also held 225 untracked capture files (competitor screenshots and scratch) that exist nowhere else. | Tagged. Untracked files archived off-repo (below), then branch and worktree removed. Not merged. |
| `computer-use/supervised` (`archive/computer-use-supervised`) | 18 | 96.2% of 4,276 meaningful added lines are already on `main`; the feature merged through `defa74ac` on a different line of history. 34 merge conflicts, all from `main` being newer. | Tagged. Branch and worktree removed. |
| `outputs-workspace` (`archive/outputs-workspace`) | 1 | 97.8% of 2,415 meaningful added lines are already on `main`; the feature merged through `7befddd8`. 8 conflicts. | Tagged. Branch and worktree removed. |
| `outputs/unified-stray-wip` (`archive/outputs-unified-stray-wip`) | 1 | Salvaged from a quota-interrupted run. Only 20.7% of added lines match, but the rest are earlier WIP versions of `kernel.py`, `render.py`, `manager.py` and `media.py`, which `main` has in finished form. All three documents it touches are already on `main`. 13 conflicts. | Tagged. Branch removed. Nothing to salvage. |
| `8db7f28e`, detached (`archive/marketing-s11`) | 3 | `README.md` gains one CI badge for `.github/workflows/ci.yml` (present on `main`) plus CI-run evidence records under `.pipeline/marketing/2026-10/`. Merges cleanly. | Merged into `main` as `332d44dc`. Worktree removed. Whether the badge shows a passing build depends on the remote CI run, which was not checked from this machine. |
| `3c5ce893`, detached in a Codex worktree (`archive/agent-connections-2026-10-11`) | 63 | Real, unintegrated work. Only 9.2% of 11,140 meaningful added lines in files that exist on `main` are present there; 200 of 435 touched files do not exist on `main`; 96 merge conflicts. See below. | Tagged only. The Codex-managed worktree outside this repository is untouched. Not merged. |

## agent-connections: what it contains and why it is not merged

All 63 commits are from 2026-10-11. They fall into seven themes. "On main" is a name-based search of
committed `main` (`git grep`), so a differently named equivalent could exist; treat "no match" as a
lead, not proof.

| Theme (branch commits) | On main? |
|---|---|
| Versioned effective bot configuration and run-configuration evidence | No match for the terms used |
| Assistant lifecycle: safe archive, persisted visual identity, reviewed settings reset, duplication boundaries | Archive has name matches in `store.py` and `server/app.py`; persisted identity: no match |
| Skills: bounded reviewed ZIP import, namespaced identity, Agent Skills format diagnostics, typed inputs and reviewed scripts, persisted on-demand versions, compact catalog within the prompt budget | A skills lifecycle exists (README); ZIP import and namespaced identity: no match |
| Credentials and OAuth: Secret Service adapter, ChatGPT tokens and model keys moved to the vault, serialized refresh and disconnect, Authlib | Vault and refresh serialization have name matches; Authlib: no match |
| Integrations and MCP: central tool catalog, reviewed account grants, endpoint network pinning, local OAuth setup API, run-scoped grants, contained stdio connections, setup UI | An `integrations/` package exists with Notion MCP and KDE Connect; general MCP stdio is a stated non-goal in the plan |
| Compaction of safe prior chat context before local runs | Compaction exists on `main` (README) |
| Benchmarks, a ten-minute soak and packaging evidence | `benchmarks/agent_scale.py` absent; `main` has a computer-use soak |

Why it cannot be merged as a branch:

- 96 conflicts across 233 files that both sides changed, including `store.py`, `app.js` and `skills.py`.
- Its schema migrations collide with `main`, which is at schema version 83 with the fact-purge (82)
  and whole-Bot deletion (83) migrations. Any ported migration must be renumbered after 83.
- Part of it overlaps lanes that did merge separately (skills lifecycle, security containment, MCP,
  integrations), so a wholesale merge would reintroduce older versions of code `main` has since changed.

Recommended path if any of it is still wanted: port one theme at a time from the tag as a patch series
on top of current `main`, each with its own migration number, tests and ledger entry. The most
self-contained candidates by this evidence are skill ZIP import with format diagnostics, then versioned
effective and run configuration. This is a product decision about whether those features are wanted;
nothing here assumes they are.

## Also found, not touched

Seven worktrees whose branches are merged still carry uncommitted changes, so a "merged" label there
says nothing about those edits: `.worktrees/outputs` (279 modified), `.worktrees/realign` (348 modified,
2 untracked), `.worktrees/mcp-s0` (15 modified, 2 untracked), `.worktrees/ui-run-wait` (2),
`.worktrees/persona-adaptive` (1), `.worktrees/runtime` (1 modified, 1 untracked) and the Codex worktree
`dynamic-workflows-completion` (491 modified, 3 untracked). Whether those edits are real or generated
noise was not examined.

## Off-repository archive

`~/hutch-quarantine-2026-10-30/` holds, each verified by file count before the originals were removed:

| Archive | Contents |
|---|---|
| `removed-untracked.tar.gz` | 34 files: the React/TypeScript preview harness and its fixture bundle, the `tree.json` and Apple HIG scrape dumps, `docs/prompts/` |
| `web-harness-deps.patch` | The npm dependency and script changes that harness needed |
| `bulk-captures.tar.gz` | 433 files, 74 MB: slice 7c raw verification captures and the navbar-consistency before/after screenshots |
| `brand-phase1-research-untracked.tar.gz` | 225 files, 32 MB: Phase 1 research captures and scratch from the brand-phase1 worktree |
