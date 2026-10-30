# Split a god file (400-line budget)

Use when a source file approaches or exceeds 400 lines, or when a frozen file
needs to shrink. Split along a named seam; never grow an over-cap file.

## When

- A file is 350-400 lines and the next change would push it over.
- `npm run audit:context` reports a new over-cap file or a frozen file that grew.
- A file listed in `.file-size-baseline.json` is being edited.

## Required context

- [Agent workflow and context economy](../../docs/agent-workflow.md) - file-size
  policy and baseline lifecycle.
- `scripts/audit_context_hygiene.py` - scan rules, `--report`, `--update`.
- `.file-size-baseline.json` - sorted, compact path-to-lines map; shrink-only.
- `tests/test_context_hygiene.py` - policy regression tests.
- The module's public imports and callers; extract along a real boundary.

## Steps

1. Confirm the current count with `wc -l` and read policy context with
   `scripts/audit_context_hygiene.py --report`.
2. Choose a seam: one responsibility, one import surface, one test file. Keep
   public names stable or update every caller in the same task.
3. Move code into new modules that stay well under 400 lines; split at
   350-400 lines instead of growing a hub.
4. Keep the old module as the facade where callers depend on it; do not duplicate
   state.
5. Only after an intentional split, run the baseline update and review its diff:
   entries removed or counts lowered only.
6. Run the focused policy tests and the tests for the moved behaviour.

## Commands

```bash
wc -l path/to/file.py
uv run --frozen --no-sync python scripts/audit_context_hygiene.py --report
uv run --frozen --no-sync python scripts/audit_context_hygiene.py --update
npm run audit:context
npm run test:agent -- tests/test_context_hygiene.py tests/test_moved.py
```

## Definition of done

- Every touched source file is 400 lines or fewer; frozen files did not grow.
- The baseline diff contains only removals or lowered counts; no new over-cap
  file was grandfathered.
- Behaviour is unchanged for callers: focused tests and `npm run check:agent`
  pass; the 3-File / 1-Seam rule was respected or the task was split.
- New modules are explained by the directory map or a doc update.

## Do not

- Grandfather a new over-cap file or raise a frozen count.
- Split mechanically into fragments with no seam; a facade over a bag of helpers
  is not a split.
- Edit generated CSS or evidence trees to make a count pass.
- Rewrite another session's uncommitted work during the move.

## Canonical docs

- [Agent workflow and context economy](../../docs/agent-workflow.md)
- [Tool-calling contract and evidence](../../docs/realignment/tool-calling.md)
- [Repository hygiene](../../docs/repository-hygiene.md)
