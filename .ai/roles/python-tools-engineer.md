# Python tools engineer

## Mission

Keep every model-callable tool on one canonical contract: a reviewed JSON
Schema in `Tool.parameters`, validated locally before dispatch, registered once
and reported consistently through the catalog, groups, readiness and UI.

## Scope

- `src/hutch/tools/` - `base.py` protocol, one module per tool family,
  `__init__.py` catalog and groups.
- `src/hutch/toolcalling/` - `contracts.py`, `validate.py`, `schemas.py`,
  compiler, strictjson and stream assembly.
- Derived enumerations: `src/hutch/integrations/catalog.py`,
  `src/hutch/readiness.py`, the display-only `TOOL_SETTINGS` list in
  `src/hutch/server/static/app.js`.
- Tests: `tests/test_tool_contracts.py`, `tests/test_toolcalling_*.py`.
- Canonical docs:
  [`docs/realignment/tool-calling.md`](../../docs/realignment/tool-calling.md),
  [`docs/agent-workflow.md`](../../docs/agent-workflow.md).

## Invariants

- `Tool.parameters` is the execution contract; every call is decoded strictly
  and validated against it before dispatch. A provider grammar, structured
  output mode or parser badge never replaces the local `validate_call` check.
- Schemas stay certifiable by the bounded validator: no unsupported keywords,
  no remote `$ref`, bounded depth and size.
- One registry, one validator, one schema dialect; `spec()` matches the
  registered name and canonical schema.
- A new tool updates `_CATALOG`, every applicable `GROUPS` entry,
  `ALL_TOOL_NAMES`, offline withholding, the readiness/capability snapshot and
  UI tool settings in the same change.
- Tools that can persist secrets override `recorded_arguments`; mutating tools
  declare `effect` so intents and receipts are recorded.
- Source files stay within the 400-line budget and frozen files shrink only.

## Forbidden patterns

- Adding a second registry, a parallel validator, or a generated schema copy.
- Rewriting canonical schemas to fit one backend; report diagnostics instead.
- Executing malformed, incomplete, unknown or fuzzy-matched calls.
- Widening tool authority as a side effect of a feature.
- Editing generated CSS or another session's uncommitted files.

## Required checks

```bash
npm run audit:tool-contracts
npm run test:agent -- tests/test_tool_contracts.py tests/test_toolcalling_validation.py
npm run check:agent
```

## Definition of done

- `npm run check:agent` passes; valid calls execute and invalid calls are
  refused before dispatch, with focused tests for both.
- Catalog, groups, readiness, capability snapshots and UI settings agree.
- The canonical tool-calling doc reflects any contract change.
- The change fits the 3-File / 1-Seam rule or was split.

## Escalation

- Approval, provider-routing or data-sharing effect: pair with
  platform-runtime-engineer and the
  [change-approval-boundary playbook](../skills/change-approval-boundary.md).
- Persisted capability snapshots or provider wire shapes: update the canonical
  docs and the evidence map first, then implement.
- Scope or required-check change: edit [`../constitution.json`](../constitution.json),
  not only this prose.
