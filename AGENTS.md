# Repository Guidelines

## Project Structure

Hutch is a Python package under `src/hutch/`, organized around the CLI, server, providers, tools, and runtime. Product defaults and bundled skills live in `src/hutch/data/`. Python tests are in `tests/`; browser and visual checks are in `tests/e2e/`. User and architecture documentation, including numbered architecture decision records, is under `docs/`. The landing page is in `website/`, while dashboard styles are sourced from `app/src/` and served from `src/hutch/server/static/`.

## Build, Test, and Development

- `uv sync --extra dev` creates or updates `.venv` and installs the package with test dependencies; it safely reuses an existing environment.
- `uv run pytest --ignore=tests/e2e` runs the fast local suite without requiring browser binaries. Run `uv run pytest -q` for the full suite used in CI; browser tests may require Playwright browsers.
- `uv run hutch init && uv run hutch serve` initializes local state and starts the dashboard at `http://127.0.0.1:8787`. Prefix project commands with `uv run` unless `.venv/bin` is on `PATH`.
- `npm install && npm run build:css` builds both the marketing-site and dashboard CSS. Use `npm run watch:css` or `npm run watch:css:app` while editing the corresponding styles.

## Coding Style and Naming

Use Python 3.11+ and follow the surrounding code: four-space indentation, `snake_case` for modules/functions/variables, and `PascalCase` for classes. Keep tests named `test_*.py` and test functions named `test_*`. No formatter or linter is configured in `pyproject.toml`; keep changes consistent with nearby code. Keep website and dashboard styling in their source files, not generated CSS outputs.

## Testing Guidelines

Add or update focused pytest coverage for behavior changes. Use fixtures in `tests/fixtures/` for persisted-state compatibility and `tests/e2e/` for browser-visible flows. Run the relevant focused tests first, then `pytest --ignore=tests/e2e`; run browser tests when the change affects the UI or browser behavior. CI runs `pytest -q` on Python 3.11, 3.12, and 3.13.

## Commits and Pull Requests

Recent commits use concise imperative summaries (for example, “Add skills API…” or “Fix template identity…”); follow that style and keep each commit focused. PRs should explain the behavior change, link relevant issues or design/ADR documents, and report checks run. Include screenshots for visible UI changes and update user or architecture documentation when behavior or safety boundaries change.

## Architecture and Safety

Read the relevant documentation in `docs/` and existing ADRs before changing cross-cutting behavior. Preserve Hutch’s local-first, explicit-approval model: do not broaden tools, permissions, provider access, or data sharing as an incidental part of a feature. Update tests and evidence alongside changes to safety or execution boundaries.
