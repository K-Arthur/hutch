# Hutch role files

On-demand role context for agents working in a narrow part of Hutch. Load the
role that owns the paths you will touch, after `AGENTS.md` and the canonical doc
it points at, and at most one skill on top.

The machine-readable registry is [`../constitution.json`](../constitution.json).
It fixes each role's scope and required checks and maps every constitution rule
to real enforcement; `scripts/audit_constitution.py` fails when a role file,
scope path or package.json check key stops existing.

## Roles

| Role | Use when | Scope | Required checks |
| --- | --- | --- | --- |
| [python-tools-engineer.md](python-tools-engineer.md) | Adding or changing a model tool, its schema, registry, groups or readiness | `src/hutch/tools`, `src/hutch/toolcalling` | `npm run check:agent`, `npm run audit:tool-contracts` |
| [platform-runtime-engineer.md](platform-runtime-engineer.md) | Run loop, dispatch, persistence and migrations, approvals, scratch validation | `src/hutch/runtime`, engine/store/models, safety/approvals | `npm run check:agent`, `npm run test:agent -- <paths>` |
| [web-ui-engineer.md](web-ui-engineer.md) | Dashboard templates/static JS, server routes, Tailwind sources, marketing site | `src/hutch/server`, `app/src`, `website` | `npm run check:agent`, `npm run build:css` when sources change |

## Load order

1. [`../../AGENTS.md`](../../AGENTS.md) - the always-loaded index and hard rules.
2. The canonical doc for the area, linked from the role file.
3. The role file below.
4. At most one playbook from [`../skills/README.md`](../skills/README.md).

## Add or change a role

1. Add `.ai/roles/<name>.md` with the shared sections: mission, scope,
   invariants, forbidden patterns, required checks, definition of done,
   escalation; keep it at or below 80 lines.
2. Register it in [`../constitution.json`](../constitution.json) with a unique
   `id`, existing `file` and `applies_to` paths, and package.json script keys as
   `required_checks`.
3. Run `npm run audit:constitution`; every new relative link must resolve.

## Related docs

- [Repository instructions](../../AGENTS.md)
- [Agent workflow and context economy](../../docs/agent-workflow.md)
- [Reusable playbooks](../skills/README.md)
