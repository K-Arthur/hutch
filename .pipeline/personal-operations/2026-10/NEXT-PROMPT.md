# Next prompt

Continue the Hutch personal-operations initiative from .pipeline/personal-operations/2026-10/.
Read HANDOFF.md, CURRENT-STATE.md, GAP-REGISTER.md, DECISIONS.md and RUNLOG.md first; the
repository working tree may also contain another session's uncommitted frontend work, so check
git status and stage only files you have reviewed.

Objective for the next session: close G01 (a read-only, grant-gated calendar/mail agenda
projection for Today) and G05 (outbound notifications for needs-you, failures and results) without
adding external effects that lack approval binding or reconciliation. Keep Today deterministic:
the agenda projection must mark each item with its source, fetch time and staleness, and must not
let email or page content become instructions. Any outbound notification must reuse the existing
channel outbox and uncertain-delivery handling; do not add a second delivery path.

Definition of done for that session:
1. A pure agenda builder plus a read-only API route, unit-tested with fixed clocks and expired
   grants, and Today showing the source label and stale/unavailable states.
2. Notification delivery through the existing channel supervisor with tests for duplicate
   suppression and uncertain outcomes; no silent resend.
3. Browser validation at 1440/834/390/320 plus keyboard, with evidence committed under a new
   pipeline directory.
4. Focused tests, npm run check:agent, updated docs/commitments.md + operations.md + marketing
   claims, and focused commits.
5. Independent read-only verification with per-row command output before claiming completion.

Do not claim multi-user isolation, exactly-once external effects, or live model-driven capture:
those remain blocked/deferred as recorded in ACCEPTANCE-CRITERIA.md.
