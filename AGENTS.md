# Repository Guidelines

## Project Structure

Hutch is a Python package under `src/hutch/`, organized around the CLI, server, providers, tools, and runtime. Product defaults and bundled skills live in `src/hutch/data/`. Python tests are in `tests/`; browser and visual checks are in `tests/e2e/`. User and architecture documentation, including numbered architecture decision records, is under `docs/`. The landing page is in `website/`, while dashboard styles are sourced from `app/src/` and served from `src/hutch/server/static/`.

## Build, Test, and Development

- `uv sync --extra dev` creates or updates `.venv` and installs the package with test dependencies; it safely reuses an existing environment.
- `uv run pytest --ignore=tests/e2e` runs the fast local suite without requiring browser binaries. Run `uv run pytest -q` for the full suite used in CI; browser tests require the Chromium revision the locked Playwright expects — install it with `uv run python -m playwright install chromium`. A shared `~/.cache/ms-playwright` holding only other revisions makes the product's own browser tool fail with `BrowserUnavailable` / missing-executable errors before most browser tests start (triaged 2026-10-25).
- `uv run hutch init && uv run hutch serve` initializes local state and starts the dashboard at `http://127.0.0.1:8787`. Prefix project commands with `uv run` unless `.venv/bin` is on `PATH`.
- `npm install && npm run build:css` builds both the marketing-site and dashboard CSS. Use `npm run watch:css` or `npm run watch:css:app` while editing the corresponding styles.

## Coding Style and Naming

Use Python 3.11+ and follow the surrounding code: four-space indentation, `snake_case` for modules/functions/variables, and `PascalCase` for classes. Keep tests named `test_*.py` and test functions named `test_*`. No formatter or linter is configured in `pyproject.toml`; keep changes consistent with nearby code. Keep website and dashboard styling in their source files, not generated CSS outputs.

## Testing Guidelines

Add or update focused pytest coverage for behavior changes. Use fixtures in `tests/fixtures/` for persisted-state compatibility and `tests/e2e/` for browser-visible flows. Run the relevant focused tests first, then `pytest --ignore=tests/e2e`; run browser tests when the change affects the UI or browser behavior. CI runs `pytest -q` on Python 3.11, 3.12, and 3.13.

### Validation scratch-tree hygiene

Long regression runs create large scratch trees: immutable tree snapshots (`~/.cache/hutch-tree-snapshot-v*`), per-batch pytest output (`~/.cache/hutch-pytest-snapshot-v*`), `pytest --basetemp` directories under `~/.hutch-tmp`, and one-off `~/.cache/hutch-*-validation-*` directories. Runs deliberately use a fresh versioned or suffixed name so they cannot clobber the previous run's evidence, so these accumulate across runs — tens of gigabytes is normal after a few full-suite passes.

To reclaim the space, run `python scripts/prune_validation_tmp.py` (dry run, reports only) and add `--apply` to delete. It keeps the newest directory per family, skips anything modified within the last 24 hours, and skips directories with open file handles, so a live or in-flight run is never removed. Unrelated tasks' scratch trees are not touched. Prefer reusing one scratch root per task over minting a new versioned directory each run, and remove a task's scratch trees when its validation work completes.

## Commits and Pull Requests

Recent commits use concise imperative summaries (for example, “Add skills API…” or “Fix template identity…”); follow that style and keep each commit focused. PRs should explain the behavior change, link relevant issues or design/ADR documents, and report checks run. Include screenshots for visible UI changes and update user or architecture documentation when behavior or safety boundaries change.

## Commit attribution

Do not add AI tools, assistants, agents, bots or model identities as commit
author, co-author, committer or generated-by attribution, and do not add
`Co-authored-by:` trailers for Claude, Devin, Copilot, Codex, ChatGPT, Gemini,
Cursor, Windsurf, OpenCode or other AI tools, unless the maintainer explicitly
requests it for a specific commit. Commits keep the configured human Git
identity. Tool and product references in documentation, code and commit-body
prose are legitimate and are not attribution.

The rule applies to new commits; preserved published history is not rewritten.
The managed `commit-msg` hook (`.githooks/commit-msg`, enabled with
`git config --local core.hooksPath .githooks`) and the CI commit-attribution
job enforce it for new work; hooks can be bypassed, so CI is the backstop. See
[docs/commit-attribution-policy.md](docs/commit-attribution-policy.md).

## Architecture and Safety

Read the relevant documentation in `docs/` and existing ADRs before changing cross-cutting behavior. Preserve Hutch’s local-first, explicit-approval model: do not broaden tools, permissions, provider access, or data sharing as an incidental part of a feature. Update tests and evidence alongside changes to safety or execution boundaries.
