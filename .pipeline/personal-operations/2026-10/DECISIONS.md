# Decisions

Dated: 2026-10-31. Evidence base: repository code inspection (schema v81), the repo's own dated research in
\`docs/research/complaints.md\` and \`docs/research/offerings-and-failures.md\`, and the external research set
produced in this pipeline directory. Hard-to-reverse choices are recorded here; routine edits are not.

## D-01 One writer for schema and API

The Lead owns \`store.py\` migration registration, the new \`personal\` package, \`personal_api.py\`, and the
shell wiring. Teammates write research/audit/verification artifacts only. Rationale: migrations and route
registration are the shared contract surface; concurrent writers are the documented cause of repository
corruption in the coding-agent failure research.

## D-02 A new commitments domain instead of overloading \`Task\`

\`Task\` is a dispatch row (one bot prompt); \`workspace_tasks\` is a specialist assignment; \`conversation_task_state\`
is chat continuity. A user commitment has a due date, provenance, dependencies, a scope and a completion
verification path. Adding those columns to \`tasks\` would conflate execution with promise-keeping and break
existing projections. New tables; no schema change to existing ones.

## D-03 Assistant captures are proposed until the owner confirms

The model cannot assert that the user promised something. Assistant tool calls create \`confirmation='proposed'\`
rows that appear in Today as "Suggested", not as commitments. Only the owner API path creates confirmed rows.
This is the application-level floor; prompt instructions are not the boundary.

## D-04 Completion is reported, then verified

Model tools record completion with \`completion_kind='unverified'\`; the owner's complete/verify endpoint records
\`owner_confirmed\`. The UI shows the difference and never renders a reported completion as verified work.
A future receipt-backed kind can be added without rewriting history.

## D-05 Shared spaces scope data, not credentials

\`spaces\`/\`space_members\`/\`bot_space_grants\` are the only sharing surface. Integrations, credentials, run
evidence and memory remain per-bot/per-owner and are not movable into a space. Space access for an assistant is
an explicit, revocable grant evaluated on every tool call.

## D-06 Today is deterministic

No model call, no generated prose, no inference. \`build_today\` projects persisted rows with their sources and
explicit exclusions. This avoids the documented "generic summary/agent claimed completion" failure and makes
every line auditable. A future narrative layer must be labelled and show its inputs.

## D-07 IANA zone fail-closed

An unknown timezone returns 422 rather than silently defaulting to UTC, matching the scheduler's
\`InvalidScheduleZone\` decision. Local-day boundaries are converted to UTC per boundary so 23/25-hour DST days
are correct.

## D-08 UI: one new primary destination, no new framework

Today joins the existing primary nav; Shared joins More. No second SPA, no build step for new JS, no new design
tokens. This preserves the established navigation model tested by \`tests/test_navbar_consistency.py\`.

## D-09 Migration is additive and rollback-safe

v82 creates only new tables/indexes/triggers. Existing rows and columns are untouched. Old binaries refuse a
newer database instead of downgrading, and the existing pre-upgrade backup path applies. The feature can be
disabled by reverting the wiring; leftover tables are inert.

## D-10 Scope boundaries for this initiative

Implemented and validated in this pass: commitments, spaces + grants, Today aggregation + UI, capture/list/
report tools, focused tests, visual evidence, docs, marketing update. Explicitly deferred with reasons in
\`HANDOFF.md\`: multi-user authentication, live calendar/mail aggregation, event/webhook automation triggers,
autonomous multi-agent coding supervision changes, and full mobile app work.
