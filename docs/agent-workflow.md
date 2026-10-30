# Agent workflow and context economy

This is the on-demand companion to [`AGENTS.md`](../AGENTS.md). It maps the five
repository-context defects from the 2026-10-28 review to Hutch rules, the guard
commands that keep them from drifting, and the seam rules for every agent session.
Commit policy is separate ([`docs/repository-hygiene.md`](repository-hygiene.md));
the LLM tool-calling contract lives in
[`docs/realignment/tool-calling.md`](realignment/tool-calling.md).

## The five defects, mapped to Hutch rules

| Defect | Symptom in agent sessions | Hutch rule | Guard |
| --- | --- | --- | --- |
| 1. God files | A 14.5k-line `app.js` or 12.6k-line `store.py` consumes the context window before real work starts | 400-line cap for new source; existing offenders frozen shrink-only; split at 350-400 lines along a named seam | `npm run audit:context` |
| 2. Unfiltered search scope | Searches return lockfiles, build output, 381 MB of evidence captures, and installed dependencies | Root `.ignore`/`.dshignore`/`.opencodeignore` plus targeted reads; never scan evidence or dependency trees | rg probes; see "Ignore policy" below |
| 3. Weak AGENTS.md | The inherited guidance lacked an exact directory map, quiet commands, seam rules and context-economy rules | `AGENTS.md` is a <=150-line index; detail lives here and in the docs it points at | `wc -l AGENTS.md` |
| 4. Verbose verification | Full pytest and browser runs dominate the session budget and hide the one relevant failure | Quiet focused commands only; full suite and Playwright are explicit escalation | `npm run test:agent -- <files>` |
| 5. Weak type boundaries | Provider wire shapes and execution handlers can drift from the reviewed tool schemas | Canonical JSON Schema is the execution contract, validated before dispatch; every registered tool is audited | `npm run audit:tool-contracts` |

## Guard commands

```bash
npm run check:agent        # context-hygiene + tool-contract + constitution + map audits
npm run audit:context      # file-size budget vs .file-size-baseline.json
npm run audit:tool-contracts  # every registered Tool schema + spec contract
npm run audit:constitution # rules, roles and their real enforcement targets
npm run audit:agent-map    # stable map drift check
npm run agent:map          # regenerate .ai/repo-map.generated.md after staging file changes
npm run test:agent -- tests/test_context_hygiene.py tests/test_tool_contracts.py tests/test_constitution.py tests/test_agent_map.py
```

The audits are quiet on success and exit 1 with a concise, capped finding list on
failure. They run through `uv run --frozen --no-sync` and never install anything.

## File-size policy

- **Hard cap: 400 lines for new source** - Python, JS/MJS, TS, Astro, and
  hand-maintained CSS (dashboard `static/*.css` sources, `app/src/` and
  `website/` site CSS). Split at 350-400 lines.
- **Existing over-cap files are frozen** in `.file-size-baseline.json`, a sorted,
  compact JSON map of path to current line count. A frozen file may shrink but
  never grow; a new over-cap file may not be added.
- **Not source, never scanned**: installed environments (`.venv`, `node_modules`),
  `.worktrees/`, every hidden tool directory, `desktop/` Rust build output
  (`target/`, `binaries/`, `gen/`), root `build/`/`dist/`/`var/`/`reports/`,
  documentation evidence trees (`docs/**/artifacts/**`), and generated CSS:
  `src/hutch/server/static/ui.css`, `model-switcher.css`, `website/app.css`,
  `website/styles.min.css`, any `*.min.css`, and `static/vendor/`.
  Hand-written CSS such as `static/style.css` is budgeted because the package
  scripts generate only the two files listed above.
- **Baseline lifecycle**: only after an intentional split, run
  `uv run --frozen --no-sync python scripts/audit_context_hygiene.py --update`,
  review the diff (it must only remove entries or lower counts), and commit it with
  the split. `--update` refuses to grandfather a new over-cap file or raise a
  frozen count; a checkout without a baseline bootstraps one on first update.
- **Reporting**: `--report` prints the scanned file count, frozen count and top
  offenders, and never fails. It is safe to run during triage.

## Quiet verification

```bash
npm run test:agent -- tests/test_x.py                       # focused, quiet
uv run --frozen --no-sync pytest -q --no-header --tb=line tests/test_x.py
npm run build:css --silent   # only when app/src or website CSS sources changed
```

- Focused tests only, then the fast suite when the change warrants it; CI owns the
  full suite on Python 3.11/3.12/3.13.
- `tests/e2e/` and Playwright are excluded from the fast lane; run them only when
  the change is visible in the browser, with the locked Playwright Chromium.
- Never run in the inner loop: full `pytest -q`, Playwright, full `cargo build`,
  native installer builds.
- Scratch trees: `python scripts/prune_validation_tmp.py` is a dry run, `--apply`
  deletes stale `hutch-*` trees, keeping the newest per family and anything
  recent or open. Reuse one scratch root per task.

## Tool-schema seam contract

Hutch already has one contract; enforce it rather than inventing a second one.

- Registration: `Tool` (`src/hutch/tools/base.py`) declares `name`,
  `description` and `parameters`; `src/hutch/tools/__init__.py` assembles the
  catalog, groups and grant-gated connection tools.
- Identity and snapshots: `ToolDefinition` (`toolcalling/contracts.py`) is the
  canonical view; `schema_revision` hashes the exact argument schema.
- Analysis and lowering: `toolcalling/validate.py` `analyze_schema()` must
  certify the schema (no unsupported keywords, no remote `$ref`);
  `toolcalling/schemas.py` lowers it for a generation backend while the canonical
  schema remains the execution contract.
- Execution: every call is decoded strictly, validated against the canonical
  schema before dispatch (`runtime/toolrepair.validate_args` ->
  `toolcalling.validate.validate_call`), and only then run. A provider grammar
  never replaces the local check.
- Regression: `scripts/audit_tool_contracts.py` fails on a duplicate, empty or
  malformed name/description, a non-object or uncertifiable `parameters`
  schema, a mismatched `spec()`, or a canonical schema that cannot complete the
  planning/lowering path. Tests: `tests/test_tool_contracts.py`.
- Adding or changing a tool means updating the catalog, any group allowlist,
  readiness/capability snapshots, UI tool settings, and focused tests (valid call
  accepted, invalid call refused before dispatch).

## Ignore policy and search scope

- The identical `.ignore`, `.dshignore` and `.opencodeignore` files exclude
  dependency trees, lockfiles, build output, runtime state and evidence trees from
  code search. `.ignore` is honored by ripgrep; this DSH build does not read
  `.dshignore` yet, and its `glob` tool does not apply ignore files at all, so
  pass explicit paths when using it.
- `.gitignore` remains the commit policy: `uv.lock`, `package-lock.json`,
  `desktop/Cargo.lock`, generated shipping CSS and reviewed evidence stay tracked
  even though search skips them. Do not confuse "ignored for search" with
  "untracked" or "disposable".
- Never search or read: lockfiles, `CHANGELOG.md`, generated CSS, docs evidence
  artifacts, `.worktrees/`, `.venv/`, `node_modules/`. Use exact paths and line
  ranges for everything large.

## Task discipline

- 3-File / 1-Seam: at most three source files plus one cross-cutting seam per
  task; split larger work into separate tasks before starting.
- Name exact paths in the first prompt (`@src/hutch/store.py:120-180`), not
  directories; read ranges, not whole large files. Fresh session after each
  completed task, under about 120K tokens, and report only failures.

## Reusable skills and editor settings

Reusable task playbooks live in `.ai/skills/`, indexed by
[`.ai/skills/README.md`](../.ai/skills/README.md); load only the one a task
matches. Each playbook is Markdown with When / Required context / Steps /
Commands / Definition of done / Do not sections, at most 80 lines, links to the
canonical docs above, and no emoji. They are maintainable working instructions,
not Hutch product skills (those are documented in [`docs/skills.md`](skills.md)).
Adding a playbook means adding one file to `.ai/skills/` and one row to its
README; verify every link and run `npm run check:agent`.

`.vscode/` is intentionally untracked in Hutch: keep personal editor settings
local and do not commit them or add `.gitignore` exceptions for them. Because
nested `.worktrees/` checkouts look like submodules, set
`"git.detectSubmodules": false` locally in VS Code settings to stop the editor
from scanning them. Do not change `.gitignore` to work around editor noise.

## Constitution and role files

`.ai/constitution.json` is the machine-validated registry of durable Hutch rules
and on-demand role files (schema `agent-constitution-v1`). It is deliberately not
auto-loaded by anything: `AGENTS.md` stays the only always-loaded index, the
canonical docs carry detail, a role file in `.ai/roles/` adds scope-specific
invariants, and at most one `.ai/skills/` playbook adds the procedure. Load order:
`AGENTS.md` -> canonical doc -> role file -> one skill.

Every rule maps to enforcement that already exists in this checkout: a
package.json script key, a repo-relative script, existing test paths, or a manual
checklist plus an existing review doc. `npm run audit:constitution` validates the
schema/version/repo, `CON-###` id uniqueness, severity values, unique role ids,
existing role files and scope paths, package.json check keys, every enforcement
target and every source doc path. A rule therefore cannot rot into decorative
prose: delete a guard script, rename a test or move a role file and the audit
fails. `tests/test_constitution.py` pins the failure classes and asserts this
checkout is clean.

The audit also enforces coverage. Every `.ai/roles/*.md` except `README.md` must be
registered exactly once in `roles[].file`, so a new role file cannot be added and
forgotten. Every rule `source` doc must be reachable from `AGENTS.md` within two
Markdown-link hops (AGENTS.md is depth 0, its docs depth 1, their docs depth 2):
the always-loaded index has to keep a short pointer chain, and a rule source is
not allowed to hide three links deep. External agent tooling (MCP servers,
code-graph tools) is covered by the manual `CON-013` rule: adoption needs
explicit approval, a pinned version, sandboxed access and output cross-checked
against the generated map.

Adding a rule: take the next unused `CON-NNN`, state a testable statement, set
`severity` and a `source` doc path (optionally with an anchor), and point
`enforcement` at real machinery. Manual rules must carry at least two checklist
items plus an existing review doc. Adding a role: add `.ai/roles/<name>.md` at or
below 80 lines with mission, scope, invariants, forbidden patterns, required
checks, definition of done and escalation, then register its `file`,
`applies_to` paths and package.json `required_checks` in the constitution. Both
changes end with `npm run audit:constitution` and `npm run check:agent`.

## Stable generated agent map

`.ai/repo-map.generated.md` is a deterministic structural map generated by
`scripts/generate_agent_map.py` from the committed/staged tree
(`git ls-files --cached`). It lists top-level, Python, test, desktop, dashboard
and website layouts with tracked-file counts, Rust crates found from
`desktop/*/Cargo.toml`, the agent entry-point table, and the largest frozen files
from `.file-size-baseline.json`. There are no timestamps and no source line
counts, so ordinary source edits do not change it; adding, removing or moving a
tracked file does. Output is capped at 120 lines.

The map reads the git index, not the working tree: stage file additions or
removals first, then run `npm run agent:map` (the same as
`python scripts/generate_agent_map.py --write`) and commit the map with them.
`npm run audit:agent-map` and `check:agent` fail when the map is missing or stale,
so a structural change cannot leave a misleading map behind. Read the map before
broad searches; it is a navigation aid, not a contract source. Its entry-point
table still names `.ai/skills/README.md` and `.ai/roles/README.md` even while those
paths are untracked, so regenerate after they are staged.

## Concurrent agents and worktrees

Parallel sessions use one checkout per task under `.worktrees/<slug>`, edit
generated and lock files through a single writer, and run the quiet gate instead
of duplicate full suites. The full operating model, merge protocol, single-writer
surface list and failure modes live in
[`docs/concurrent-agents.md`](concurrent-agents.md).

Before touching a shared checkout, run `npm run worktree:status`. Prune with the
dry run `npm run worktree:prune`, then `npm run worktree:prune -- --apply`; the
toolkit removes only clean, merged, old worktrees strictly under this
repository's `.worktrees/` and never external, current or nested-parent trees.




