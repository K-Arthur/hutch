# Run quiet validation

Use for the default inner loop: focused, failures-only commands that fit the
session budget. Escalate to broad runs only when the change warrants it and the
task says so.

## When

- Before reporting any code or docs change complete.
- Checking one behaviour while iterating.
- Re-verifying after a rebase or a concurrent change.

## Required context

- [Agent workflow and context economy](../../docs/agent-workflow.md) - quiet
  verification, test lanes, scratch-tree pruning.
- [Repository instructions](../../AGENTS.md) - the always-loaded command list
  and hard rules.
- The changed files and their tests; read ranges, not whole large files.
- `scripts/prune_validation_tmp.py` - scratch reclamation, dry run by default.

## Steps

1. Run the focused tests for each touched behaviour.
2. Run the default gate: `npm run check:agent`.
3. Prefer the project wrappers so `uv run --frozen --no-sync` and the quiet
   flags stay consistent; a direct pytest call keeps
   `-q --no-header --tb=line`.
4. Exclude `tests/e2e/` and Playwright by default; run browser checks only when
   the change is visible in the browser.
5. Reuse one scratch root per task; after unusual or interrupted runs, prune
   with the dry run first, then `--apply`.
6. Report exact commands and their results; quiet success is one line.

## Commands

```bash
npm run check:agent
npm run test:agent -- tests/test_tool_contracts.py
uv run --frozen --no-sync pytest -q --no-header --tb=line tests/test_x.py
python scripts/prune_validation_tmp.py          # dry run
python scripts/prune_validation_tmp.py --apply  # delete stale scratch trees
```

## Definition of done

- `npm run check:agent` passes.
- Focused tests for every touched behaviour pass; the exact commands and results
  are reported.
- No full suite, Playwright, native build, or dependency install ran without an
  explicit reason in the task.
- Scratch trees are reclaimed or intentionally reused, not left littered.

## Do not

- Run the full suite or Playwright "just in case".
- Run bare `pytest`, `pip install`, `uv sync`, or `npm install` in the inner
  loop.
- Paste long passing logs into the report; report failures only.
- Use `--apply` pruning while a run may still be writing a tree.

## Canonical docs

- [Agent workflow and context economy](../../docs/agent-workflow.md)
- [Tool-calling contract and evidence](../../docs/realignment/tool-calling.md)
- [Repository hygiene](../../docs/repository-hygiene.md)
