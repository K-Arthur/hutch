# Next prompt

Continue the Hutch personal-operations initiative from .pipeline/personal-operations/2026-10/.
Read HANDOFF.md, CURRENT-STATE.md, GAP-REGISTER.md, DECISIONS.md and RUNLOG.md first; the
repository working tree may also contain another session's uncommitted or staged work, so check
git status and stage only files you have reviewed.

Since the previous next-prompt, G01 (read-only agenda), G05 (owner notifications), the first G06
slice (last-run outcome/attention) and G02 (coding handoff verification receipts and worktree
pruning, schema v89) have shipped. Do not rebuild them; see the RUNLOG for evidence and limits.

Objective for the next session: close G03 sub-slice 1 only, an append-only schedule revision
journal. Do not add the approval checkpoint or a condition language in this pass.

Definition of done:

1. A new additive migration (next schema version) creates `schedule_revisions` and observes bot
   document changes through SQL triggers, so both API and CLI schedule writes are recorded. Store
   the before/after extracted schedule arrays and an honest actor label (empty/unknown when the
   write path cannot supply one); derive hashes and per-schedule changed-field summaries in Python
   at read time rather than persisting model prose.
2. A bounded read-only `GET /api/v1/bots/{ref}/schedules/{id}/revisions` returns the revisions for
   that schedule only, with no host paths or unrelated bot data.
3. The schedules card exposes a keyboard-accessible History disclosure; no polling faster than
   30 s and no new always-on request loop.
4. Tests: a no-op save writes no row; changing one schedule writes exactly one immutable row;
   adding, deleting and disabling a schedule are recorded; UPDATE/DELETE on the journal is
   refused; the API and card render the history. Use a real temp SQLite store and the real routes.
5. Focused tests plus `npm run check:agent`, and an audit in a clean worktree if the shared
   checkout's index contains another session's staged changes. Update docs/operations.md, the gap
   register, run log, handoff and marketing claims where the behavior is actually shipped.
6. Focused commits only; never stage, revert or reformat the other session's work.

Do not claim multi-user isolation, exactly-once external effects, live model-driven capture, or a
live OpenCode coding run: those remain blocked/deferred as recorded in ACCEPTANCE-CRITERIA.md.
