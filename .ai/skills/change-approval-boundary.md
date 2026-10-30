# Change an approval, permission, or data-sharing boundary

Use when a change alters what a tool may do, when a run pauses for approval,
which provider or account it reaches, or what data leaves the machine. The
local-first, explicit-approval model is a product promise, not an implementation
detail.

## When

- Policy verdicts, sticky approvals, action receipts, budgets, or approval UI
  change.
- A tool gains a new effect, a broader argument surface, or a new credential or
  account scope.
- A provider, model route, or tool protocol change alters where prompts, files,
  or tool output are sent.
- A connection, grant, or workspace action expands the reachable accounts or
  actions.

## Required context

- `src/hutch/safety.py` and `src/hutch/approvals.py` - policy engine, verdicts,
  and approval gate.
- `src/hutch/tools/base.py` - `effect` and `recorded_arguments`.
- `docs/safety.md` and `docs/approvals.md` - the documented user-facing model.
- [Agent workflow and context economy](../../docs/agent-workflow.md).
- [Tool-calling contract and evidence](../../docs/realignment/tool-calling.md) -
  every generation mode converges on the same dispatcher and local validation.

## Steps

1. State the exact boundary in the task: who approves what, for which Bot and
   account, and what data moves. If the feature does not require it, do not
   change it.
2. Keep deny/ask/allow defined in one place; never edit a provider grammar,
   prompt, or UI path to bypass the local `validate_call` and policy check.
3. Route new external effects through the existing approval gate and action
   receipt; record an intent row before the effect runs.
4. Persist only safe arguments (override `recorded_arguments` for secrets) and
   keep data-sharing disclosures accurate.
5. Add focused tests: allowed path, ask path (pauses then resumes), deny path,
   and unauthorised or invalid arguments refused before any effect.
6. Update the canonical safety or approval doc with the behaviour change and the
   evidence that supports it.

## Commands

```bash
npm run test:agent -- tests/test_safety.py tests/test_approval_cas.py
npm run test:agent -- tests/test_file_approval.py
npm run check:agent
```

## Definition of done

- The boundary change is explicit in the diff, docs, and tests; no incidental
  expansion of tools, permissions, provider access, or data sharing.
- Refused calls never execute and never mutate state; approvals are recorded
  once and cannot be replayed.
- Quiet verification passes and the report names the exact commands run.

## Do not

- Broaden authority to make a test, model, or provider integration pass.
- Treat a grammar or structured-output mode as the approval decision.
- Log or persist secrets, raw sensitive arguments, or private account data.
- Change `.gitignore` or ignore files to hide new runtime state.

## Canonical docs

- [Agent workflow and context economy](../../docs/agent-workflow.md)
- [Tool-calling contract and evidence](../../docs/realignment/tool-calling.md)
- [Repository hygiene](../../docs/repository-hygiene.md)
