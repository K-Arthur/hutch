# Hutch agent playbooks

Index of reusable playbooks in `.ai/skills/`. Read `AGENTS.md` first, then load
only the entry that matches the task; loading everything defeats the context
economy the rules protect.

## Playbooks

| Playbook | Load it when |
| --- | --- |
| [add-tool.md](add-tool.md) | Adding or changing a model-callable tool, its canonical schema, catalog/groups, readiness or UI tool settings |
| [change-approval-boundary.md](change-approval-boundary.md) | Changing policy verdicts, approvals, permissions, provider/account reach, or data sharing |
| [split-god-file.md](split-god-file.md) | A source file approaches or exceeds 400 lines, or a frozen over-cap file needs to shrink |
| [run-quiet-validation.md](run-quiet-validation.md) | The default inner loop: focused checks before reporting any change complete |

## Shared conventions

- At most 80 lines per playbook; no emoji.
- Sections: When, Required context, Steps, Commands, Definition of done, Do not.
- Exact repository paths, runnable commands, and links that resolve from
  `.ai/skills/` (canonical docs are two levels up, under `docs/`).
- Guidance only: `AGENTS.md`, the canonical docs and the guard scripts decide.
- Keep the always-loaded `AGENTS.md` small; detail belongs in a playbook or a
  canonical doc linked from one.

## How to add a playbook

1. Create `.ai/skills/<verb>-<object>.md` following the conventions above.
2. Add a row to the table here with a truthful "load it when" condition.
3. Verify every relative link resolves and run `npm run check:agent`.

## Related docs

- [Repository instructions](../../AGENTS.md)
- [Agent workflow and context economy](../../docs/agent-workflow.md)
- [Tool-calling contract and evidence](../../docs/realignment/tool-calling.md)
- [Repository hygiene](../../docs/repository-hygiene.md)
