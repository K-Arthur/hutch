# Contributing

Hutch is in private preview: the repository is not public and no package or release is published,
so there is no external contribution queue today. If you are working in a source checkout, this is
the short version of how to build, test, and document a change. The full repository guidelines live
in [AGENTS.md](AGENTS.md).

## Setup

Requires Python ≥ 3.11 (Linux first) and [`uv`](https://docs.astral.sh/uv/).

```bash
uv sync --extra dev --extra browser   # .venv with test and browser dependencies
uv run playwright install chromium    # only needed for tests/e2e
uv run hutch init                    # create local state (no sample data is seeded)
uv run hutch serve                   # dashboard at http://127.0.0.1:8787
```

Frontend styles are built from their sources (`app/src/` for the dashboard, `website/src/` and
`website/styles.css` for the marketing site) with `npm install && npm run build:css`; use
`npm run watch:css` / `npm run watch:css:app` while editing. Edit the sources, never the generated
CSS outputs.

## Tests

```bash
uv run pytest --ignore=tests/e2e   # fast suite, no browser binaries needed
uv run pytest -q                   # full suite (what CI runs)
```

- Run the focused tests for the behavior you touched first, then the fast suite. Run the browser
  tests when the change is visible in the UI. Fixtures for persisted-state compatibility live in
  `tests/fixtures/`; browser flows live in `tests/e2e/`.
- CI (`.github/workflows/ci.yml`) runs the full suite on Python 3.11, 3.12 and 3.13, plus a
  benchmark-regression job with a runner-local baseline.
- Long regression runs leave scratch trees behind (tree snapshots, per-batch pytest output,
  `--basetemp` directories). Reclaim space with `python scripts/prune_validation_tmp.py` (dry run;
  add `--apply` to delete) — details in [AGENTS.md](AGENTS.md).

## Style and commits

- Python 3.11+: four-space indentation, `snake_case` for modules/functions/variables,
  `PascalCase` for classes; match the surrounding code (no formatter or linter is configured).
  Test files and test functions are named `test_*`.
- Commit summaries are concise and imperative ("Add skills API…", "Fix template identity…");
  keep each commit focused.

## Documentation and evidence

- Documentation is a claim that needs evidence: current behavior, a test, or a dated measurement.
  Do not present planned work as shipped; keep experimental status and verification limits
  explicit. Update [CHANGELOG.md](CHANGELOG.md) for user-visible changes.
- Read `docs/` and the numbered ADRs in `docs/adr/` before changing cross-cutting behavior, and
  preserve Hutch's local-first, explicit-approval model: do not broaden tools, permissions,
  provider access, or data sharing as an incidental part of a feature. Update tests and evidence
  alongside changes to safety or execution boundaries.
- Include screenshots for visible UI changes.

## Working in the tree

The checkout often carries in-flight work from other lanes (tracked in
`docs/realignment/ledger.md`). Inspect `git status` before staging, stage only the files your
change reviewed, and never discard, reset, clean, or rewrite unrelated work to make a task easier.
Pushing and publication are not authorized during the private preview.
