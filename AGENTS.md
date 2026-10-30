# AGENTS.md - Hutch

Local-first, open-source multi-bot agent platform: "Your bots. Your machine.
Your rules." Python 3.11+ backend (FastAPI, SQLite, pydantic), Tailwind/daisyUI
dashboard, static marketing site, and a Tauri/Rust desktop host. Linux is the
primary dev OS. This file is the always-loaded index; detail lives in
[`docs/agent-workflow.md`](docs/agent-workflow.md),
[`docs/repository-hygiene.md`](docs/repository-hygiene.md) and
[`docs/realignment/tool-calling.md`](docs/realignment/tool-calling.md), loaded
on demand; reusable task playbooks live in
[`.ai/skills/README.md`](.ai/skills/README.md).

## Directory map (exact)

- `src/hutch/` - Python package. Entry point `cli.py`; run loop `engine.py`;
  SQLite persistence and versioned migrations `store.py`; pydantic models
  `models.py`; runtime config `config.py`; policy/approvals `safety.py`,
  `approvals.py`; skills `skills.py`.
- `src/hutch/server/` - FastAPI dashboard: `app.py` (app + REST routes),
  `pages.py` (server-rendered pages), JSON APIs `workflows_api.py`,
  `channels_api.py`, `skills_api.py`, `notion_api.py`, `kdeconnect_api.py`;
  SSE `sse.py`; auth `security.py`, `passkeys.py`; `static/` (hand-written
  vanilla JS/CSS; `app.js` is the main dashboard bundle, large) and
  `templates/`.
- `src/hutch/tools/` - `base.py` Tool protocol + registry; one module per tool
  family; `__init__.py` catalog, groups and `build_tools`.
- `src/hutch/runtime/` - model loop, dispatch and tool repair (`builtin.py`),
  compaction, OpenCode/Pi runtimes.
- `src/hutch/toolcalling/` - canonical LLM tool contract: `contracts.py`
  (ToolDefinition), `validate.py` (bounded Draft 2020-12 execution validation),
  `schemas.py` (analysis/lowering), compiler, envelope, strictjson, streaming.
- `src/hutch/workflow/` - workflow IR compile/persist/execute; `workspace/` -
  scratch workspace and account actions; `channels/` - delivery;
  `integrations/` - reviewable account grants; `providers/`, `grounding/`,
  `media/`, `synthesis/`, `documents/`, `computer/`, `actions/`,
  `platforms/`, `sources/`.
- `src/hutch/data/` - product defaults and bundled skill bodies.
- `app/src/` - dashboard Tailwind CSS sources; build to
  `src/hutch/server/static/ui.css` and `model-switcher.css`. Edit sources,
  never generated CSS.
- `website/` - static marketing site: `index.html`, `site.js`, `styles.css`,
  `src/input.css`; generated `app.css` and `styles.min.css`.
- `desktop/` - Tauri/Rust host: `src/main.rs`, `process-guard/` Rust helper,
  `icons/`, PyInstaller `backend.spec`/`backend_entry.py`; `target/`,
  `binaries/`, `gen/` are build output.
- `tests/` - pytest; `tests/e2e/` Playwright browser/visual checks (excluded
  from the fast lane); `tests/fixtures/` persisted-state compatibility inputs.
- `scripts/` - audits and build helpers, including `prune_validation_tmp.py`.
- `docs/` - `architecture.md`, numbered ADRs in `adr/`, `realignment/`
  ledgers/evidence, `qa/`, `research/`; about 381 MB including evidence.
  `benchmarks/` holds benchmark baselines.

## Quiet verification - default inner loop

```bash
npm run check:agent                     # context-hygiene + tool-contract audits
npm run test:agent -- tests/test_x.py   # focused pytest, quiet, no e2e
uv run --frozen --no-sync pytest -q --no-header --tb=line tests/test_x.py
npm run build:css --silent              # only when app/src or website CSS changed
```

- Prefer `uv run --frozen --no-sync`; run `uv sync --extra dev --extra browser`
  only when the environment genuinely needs a dependency change.
- Never by default: full `pytest -q` (CI runs it on 3 Python versions),
  `tests/e2e/`/Playwright/browser tests, full `cargo build`, native installer
  builds. Run focused tests first, then the fast suite only when the change
  warrants it. Browser tests require the Playwright Chromium revision.
- Run the focused tests for every touched behavior, then `npm run check:agent`,
  before reporting a change complete. Report exact commands and results.
- Long runs leave scratch trees under `~/.cache` and `~/.hutch-tmp`. Reclaim
  with `python scripts/prune_validation_tmp.py` (dry run; `--apply` deletes;
  skips recent directories and open handles). Reuse one scratch root per task.

## Hard rules

- Preserve Hutch's local-first, explicit-approval model. Do not broaden tools,
  permissions, provider access, or data sharing as an incidental part of a
  feature; execution boundaries change deliberately, with tests and docs.
- The canonical JSON Schema in `Tool.parameters` is the execution contract:
  every model tool call is validated against it before dispatch
  (`hutch.toolcalling.validate.validate_call`). A backend grammar or
  structured-output mode never replaces that check. Add contract tests for
  every new or changed tool.
- Persisted state is pydantic-modeled (`models.py`) with ordered SQLite
  migrations in `store.py` (`test_migration.py`, `tests/fixtures/`);
  timestamps are ISO-8601 UTC via `models.iso`/`models.utcnow`, never naive
  local time.
- Never commit secrets, tokens, `.env` files, runtime state (`*.db*`,
  `.state/`), or private account data. Redact sensitive tool arguments with
  `Tool.recorded_arguments`.
- No emoji in source, docs or UI (`scripts/audit_emoji.py`).
- Python 3.11+, four-space indentation, `snake_case` modules/functions,
  `PascalCase` classes; match nearby code (no formatter/linter is configured).
  Tests are `test_*.py` with `test_*` functions.
- Commits: concise imperative summaries, one focused change per commit, authored
  by the maintainer with no AI-tool attribution trailers or signatures. PRs
  explain the behavior change, link issues/ADRs, list checks run, and include
  screenshots for visible UI changes.
- Never revert, clean or reformat another task's uncommitted work; stage only
  files you reviewed.

## Do not modify

- Runtime state and secrets: `.state/`, `*.db*`, `.env*` (except placeholder
  examples), `.aws/`, `.ssh/`; never read, commit or rewrite them.
- Generated CSS: `src/hutch/server/static/ui.css`, `model-switcher.css`,
  `website/app.css`, `website/styles.min.css`; edit `app/src/` and
  `website/` sources and rebuild with `npm run build:css`.
- Reviewed evidence: `docs/**/artifacts/**`. Some artifacts are executable test
  fixtures; never prune, rewrite or untrack them.
- Frozen over-cap files in `.file-size-baseline.json`: shrink only, never
  extend; split instead (`npm run audit:context`).
- Another session's uncommitted work: never revert, clean, format or stage it.
- Ignore files and `.gitignore`: change them only as an explicit task; search
  scope is not commit policy.

## Tool seam rules

- Every `Tool` declares a unique non-empty `name`, a non-empty
  `description`, and `parameters` that is a JSON-Schema object; `spec()` must
  match the registered name and schema. `scripts/audit_tool_contracts.py`
  enforces this and that each canonical schema is certifiable (no unsupported
  keywords, no remote `$ref`).
- Reuse the existing machinery in `toolcalling/{contracts,validate,schemas,
  compiler}.py`; do not add a second registry, a parallel validator, or a
  bespoke schema dialect.
- A new tool means: catalog entry in `tools/__init__.py`, any group allowlist,
  readiness/capability snapshot, UI tool settings, and focused tests (valid
  argument accepted, invalid argument refused before dispatch).
- Contract and evidence map: `docs/realignment/tool-calling.md`.

## Context economy

- 3-File / 1-Seam rule: one task touches at most three source files plus one
  cross-cutting seam; split larger work into separate tasks before starting.
- Name exact `@path/to/file.py:120-180` paths in the first prompt, not
  directories. Read line ranges of large files instead of whole files.
- Never read lockfiles (`uv.lock`, `package-lock.json`, `Cargo.lock`),
  `CHANGELOG.md`, generated CSS, docs evidence artifacts, `.worktrees/`,
  `node_modules/`, or `.venv/`.
- Root `.ignore`, `.dshignore` and `.opencodeignore` keep generated,
  vendored and evidence trees out of search. `.ignore` is honored by ripgrep;
  this DSH build does not read `.dshignore` and its glob tool does not apply
  ignore files, so pass explicit paths. Git tracking policy is separate:
  `.gitignore` keeps reviewed lockfiles and evidence tracked.
- Fresh session after each completed task; keep a session under about 120K
  tokens and prefer quiet commands.
