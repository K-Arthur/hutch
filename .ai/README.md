# .ai/ - reusable agent playbooks and constitution

Task-scoped instructions for agents working in Hutch. This directory is not
product code and not a product feature: it is maintainable working guidance that
keeps repeated operations consistent and reviewable.

## Layout

- `.ai/constitution.json` - machine-validated registry of durable rules, roles
  and the real enforcement each rule maps to.
- `.ai/README.md` - this file: purpose, conventions and maintenance.
- `.ai/repo-map.generated.md` - stable structure-only map generated from the
  git index; do not hand-edit, regenerate after staging file changes.
- `.ai/roles/README.md` - index of on-demand role files and the load order.
- `.ai/roles/*.md` - one scoped role file per engineering area.
- `.ai/skills/README.md` - index of the playbooks and when to load each one.
- `.ai/skills/*.md` - one playbook per repeatable operation.

## How to use

1. Read `AGENTS.md` first; it is the always-loaded index.
2. Open `.ai/roles/README.md` and load the role that covers the paths you will
   touch, then the canonical doc the role links.
3. Open `.ai/skills/README.md` and load at most one playbook that matches the
   task.
4. Follow the role invariants plus the playbook's When / Required context /
   Steps / Commands / Definition of done sections; honour the Do not list.
5. Link every changed behaviour back to the canonical docs; do not add a second
   copy of Hutch rules here.

## Conventions

- Playbooks: one operation per file, at most 80 lines, no emoji, required
  sections When / Required context / Steps / Commands / Definition of done /
  Do not plus a Canonical docs link list.
- Role files: at most 80 lines, no emoji, required sections Mission / Scope /
  Invariants / Forbidden patterns / Required checks / Definition of done /
  Escalation.
- Durability: `.ai/constitution.json` must map every rule and required check to
  real enforcement; `npm run audit:constitution` fails otherwise. Every role file
  must be registered exactly once and every rule source reachable from
  `AGENTS.md` within two Markdown-link hops.
- Generated map: `.ai/repo-map.generated.md` comes from `git ls-files --cached`
  via `npm run agent:map`; `npm run audit:agent-map` (also in `check:agent`)
  fails when it is missing or stale. Read it before broad searches.
- Cite exact repository paths and runnable commands, never directory guesses.
- Every relative Markdown link must resolve from the file's own location.
- These files are guidance, not authority: `AGENTS.md`, the canonical docs and
  the guard scripts decide.

## Adding content

1. Playbook: add the file, add its row in `.ai/skills/README.md`, verify links
   and the no-emoji rule, run `npm run check:agent`.
2. Role: add `.ai/roles/<name>.md`, register it in `.ai/constitution.json`
   (unique id, existing file and applies_to paths, package.json script keys as
   required_checks), run `npm run audit:constitution`.
3. Rule: take the next unused `CON-NNN` in `.ai/constitution.json`, point its
   enforcement at real machinery, and add the checklist or test it needs. Its
   `source` doc must stay reachable from `AGENTS.md` within two Markdown links.
4. Structural change: after staging any added, removed or moved tracked file,
   run `npm run agent:map` and commit the regenerated map with the change.

## Related docs

- [Repository instructions](../AGENTS.md)
- [Agent workflow and context economy](../docs/agent-workflow.md)
- [Repository hygiene](../docs/repository-hygiene.md)
