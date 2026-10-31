# ADR-0025: Durable commitments, a deterministic Today and scoped shared spaces

Status: accepted (2026-10-31). Evidence: .pipeline/personal-operations/2026-10/
(ARCHITECTURE.md, DECISIONS.md, RESEARCH.md, FAILURE-ANALYSIS.md, CURRENT-STATE.md,
GAP-REGISTER.md, RUNLOG.md, ACCEPTANCE-CRITERIA.md, evidence/ screenshots);
tests/test_commitments.py, tests/test_spaces.py, tests/test_personal_api.py,
tests/test_commitment_tools.py, tests/e2e/test_personal_pages.py.

## Context

Hutch can execute durable work: runs with leases and honest outcomes, schedules with
IANA-zone firing and catch-up, workflows with immutable revisions, approvals bound to an
exact action, generated documents with hash-verified versions. It had no canonical record
of what the person promised to do. Task is a dispatch row, workspace_tasks are
specialist assignments and conversation_task_state is chat continuity, so none of them
can answer "what is overdue, what did I promise, and is it actually done?" without
conflating execution with commitment-keeping. The external research (same directory)
documents the failure pattern this addresses: agents claim completion and users lose
track of commitments across sessions.

## Decision

1. Add a durable commitments domain (schema v84) with immutable provenance, a
   confirmed/proposed distinction and reported/verified completion kinds. Assistant tools
   may only propose and report; owner routes confirm and verify. An append-only event
   table records every mutation; edits are revision compare-and-swap.
2. Add shared spaces as a data-scoping model: spaces, members with roles, and explicit
   per-assistant grants. Assistant visibility is enforced in store queries from current
   grants, and archiving revokes access. Spaces do not carry credentials and are not an
   authentication system.
3. Add a deterministic Today projection. No model call, no generated prose. Each section
   is a persisted-row projection with a source link, IANA-zone day boundaries that fail
   closed on unknown zones, and an explicit not-included list. UI states distinguish
   proposals, reported completions and verified completions.
4. Keep the existing scheduler, workflow, approvals and document systems unchanged; the
   new domain integrates with them by projection only.

## Alternatives rejected

- Add columns to Task: conflates dispatch with promise-keeping, breaks existing
  projections and migrations, and cannot carry dependencies or completion evidence.
- Let the model confirm commitments: repeats the documented false-completion failure and
  makes the model the authority for what the user promised.
- Model-generated briefing text: unverifiable and hard to audit; a later narrative layer
  must be labelled and show its inputs.
- Full multi-user household accounts in this slice: needs authentication, session and
  invitation design (GAP-REGISTER G07); recording members and roles now keeps the data
  model compatible without implying isolation that does not exist.

## Consequences

- Two extra durable tables and audit requests; Today becomes the natural landing view.
- Existing bots do not get the new tools until the owner grants them; no permission
  widening by default.
- Reported completion is visibly weaker than verified completion, which is intentional
  friction.
- Deferred: calendar/mail-derived agenda items, webhook/event triggers, multi-user
  authentication, and coding-orchestration changes (see HANDOFF.md).
