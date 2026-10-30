# Add or change a Hutch tool

Use when a model-callable tool is added, renamed, or its arguments or behaviour
change. Keep one canonical JSON Schema; a provider grammar never replaces the
local check.

## When

- Adding a tool class under `src/hutch/tools/`.
- Changing a tool's name, description, `parameters`, effect, approval policy,
  or recorded arguments.
- Wiring a grant-gated connection tool or changing tool-group membership.

## Required context

- `src/hutch/tools/base.py` - `Tool` protocol: `name`, `description`,
  `parameters`, `run`, `spec`, `effect`, `recorded_arguments`.
- `src/hutch/tools/__init__.py` - `_CATALOG`, `GROUPS`, `ALL_TOOL_NAMES`,
  `build_tools`.
- `src/hutch/integrations/catalog.py` - offline withheld list, browser special
  case, connection tools, capability snapshot enumeration.
- `src/hutch/readiness.py` - what the Bot readiness report promises.
- `src/hutch/toolcalling/{contracts,validate,schemas}.py` - canonical
  `ToolDefinition`, bounded 2020-12 validation, lowering diagnostics.
- [Tool-calling contract and evidence](../../docs/realignment/tool-calling.md).

## Steps

1. Declare `name`, `description` and a root `type: object` JSON Schema in
   `parameters`; keep it certifiable by the bounded validator (no unsupported
   keywords, no remote `$ref`, bounded depth and size).
2. Implement `run`; set `effect` (`fs`, `process`, `web`) for lasting effects
   and override `recorded_arguments` when arguments may carry secrets.
3. Register the class in `_CATALOG`; add it to every applicable `GROUPS` entry
   and keep `ALL_TOOL_NAMES` consistent.
4. Update every derived enumeration: offline withholding in
   `integrations/catalog.py`, readiness/capability snapshot, the display-only
   `TOOL_SETTINGS` list in `src/hutch/server/static/app.js`, and any
   grant-gated connection spec.
5. Add focused tests: a valid call is accepted, an invalid call is refused
   before dispatch, and `spec()` matches the canonical schema.
6. Update the evidence map in the canonical tool-calling doc when the contract
   changes.

## Commands

```bash
npm run audit:tool-contracts
npm run test:agent -- tests/test_tool_contracts.py
npm run check:agent
```

## Definition of done

- `npm run check:agent` passes with no new findings.
- Focused tests cover valid execution and pre-dispatch rejection.
- Catalog, groups, readiness, UI settings and docs agree; no second registry or
  validator exists.
- New or changed source files are within the 400-line budget.

## Do not

- Add a parallel registry, validator, schema dialect, or provider-specific
  argument shape.
- Narrow or widen authority as a side effect; see
  [change-approval-boundary.md](change-approval-boundary.md).
- Rewrite canonical schemas to fit a backend grammar; report diagnostics instead.
- Edit generated CSS or another session's uncommitted files.

## Canonical docs

- [Agent workflow and context economy](../../docs/agent-workflow.md)
- [Tool-calling contract and evidence](../../docs/realignment/tool-calling.md)
- [Repository hygiene](../../docs/repository-hygiene.md)
