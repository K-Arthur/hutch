# Platform runtime engineer

## Mission

Keep the run loop, tool dispatch, persisted state and approval boundaries
coherent: local-first by default, explicit approval for lasting effects, and
quiet focused validation instead of broad reruns.

## Scope

- `src/hutch/runtime/` - model loop, dispatch, tool repair, compaction and
  external harness runtimes.
- `src/hutch/engine.py` - run orchestration and capability snapshots.
- `src/hutch/store.py` and `src/hutch/models.py` - SQLite migrations and
  pydantic persisted state.
- `src/hutch/safety.py` and `src/hutch/approvals.py` - policy verdicts,
  approval gate, receipts and budgets.
- `src/hutch/workflow/` - workflow compile, persist and execute.
- Tests: `tests/test_migration.py`, `tests/test_safety.py`,
  `tests/test_approval_cas.py`, `tests/test_file_approval.py`.
- Canonical docs: [`docs/safety.md`](../../docs/safety.md),
  [`docs/approvals.md`](../../docs/approvals.md),
  [`docs/agent-workflow.md`](../../docs/agent-workflow.md).

## Invariants

- Preserve the local-first, explicit-approval model; execution boundaries change
  deliberately with tests and docs, never as an incidental refactor.
- Persisted state is pydantic-modeled in `models.py`; schema changes use a new
  ordered SQLite migration in `store.py`, and applied migrations are never
  edited in place.
- Timestamps are ISO-8601 UTC through `models.iso`/`models.utcnow`, never naive
  local time.
- Calls with an effect record an intent before they run and a receipt after, so
  unknown outcomes are reported and never silently replayed.
- Secrets and sensitive arguments never enter logs, transcripts or receipts;
  redact with `Tool.recorded_arguments`.
- New defaults must not widen provider access or data sharing.
- Scratch validation trees are reused per task and pruned with
  `python scripts/prune_validation_tmp.py`.

## Forbidden patterns

- Ad-hoc JSON columns or dicts replacing pydantic models or migrations.
- Editing an already-applied migration in place.
- `datetime.now()` without timezone, local timestamps or naive formatting.
- Broadening policy or approval behaviour as part of an unrelated feature.
- Full `pytest -q`, Playwright or native builds in the inner loop.
- Changing `.gitignore` or the ignore files to hide runtime state.

## Required checks

```bash
npm run check:agent
npm run test:agent -- tests/test_migration.py tests/test_safety.py tests/test_approval_cas.py
uv run --frozen --no-sync pytest -q --no-header --tb=line tests/test_x.py
```

## Definition of done

- Focused tests cover the changed behaviour, including ask and deny paths when
  approval or execution boundaries move.
- Migrations are ordered, pydantic models updated, UTC ISO timestamps used, and
  legacy rows load unchanged.
- `npm run check:agent` passes; the report names exact commands and results.
- Docs that promise a boundary are updated with the behaviour change.

## Escalation

- Permission, approval or data-sharing change: use the approval-boundary
  playbook and update [`docs/safety.md`](../../docs/safety.md).
- API/JSON route shape or dashboard behaviour: hand off to web-ui-engineer.
- Tool schema or dispatch rejection rules: hand off to python-tools-engineer.
- Scope or required-check change: edit [`../constitution.json`](../constitution.json),
  not only this prose.
