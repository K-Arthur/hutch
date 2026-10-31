# Handoff: agenda and notifications (2026-10-31, second pass)

Read this with `ac5e6f04`'s three predecessors, `RUNLOG.md`, `ACCEPTANCE.md` and the 2026-10 set
(`HANDOFF.md`, `GAP-REGISTER.md`, `DECISIONS.md`). Working tree caveat first: another session is
committing and leaving uncommitted work in this checkout, so always check `git status` and stage
only what you reviewed.

## What shipped (local main, no push)

| Commit | Scope |
|---|---|
| bb992832 | G01: read-only agenda builder + adapters + routes + Today card + tests + browser evidence |
| 614c331f | G05: notifications schema + outbox generalization + supervisor delivery + read API + tests |
| 4a95f39e | docs, site section, marketing claims, pipeline session record |
| ac5e6f04 | the review fixes: immediate revocation, JSON-guarded triggers, `not_queued`, deleted-assistant filtering, bounded calendar label |
| 5a835791, 227b1c89, 40663956 | the pipeline record: session, run log, acceptance, handoff, and the gate measured at the committed tip instead of in the shared tree |
| 48de6899, 33ef4461 | the second review round: schema v87 trigger repair, key-independent grant eviction, bounded source-list name, and the split that keeps the test file under the cap |

## Status by capability

- Agenda (G01): implemented as a pure builder over injected readers with one calendar and one
  mailbox chosen from existing grants. Every source and item shows its label, read time and
  staleness; grant reasons always yield `unavailable`; only a provider failure reuses a snapshot,
  and never past an hour. Tested with fixed clocks and expired grants; browser-validated at four
  widths with keyboard order. **No live provider account.** Do not describe it as live-verified.
- Notifications (G05): triggers write a content-free row in the same transaction as the fact;
  delivery reuses the one channel supervisor, outbox, lease and reconciliation. Duplicate
  suppression and the uncertain-never-resent rule are tested. **No live Telegram bot.**

## Limits and non-claims (do not weaken these)

- The agenda never calls a model, never writes provider text to SQLite, and is not part of
  `build_today`. Keep it that way; its separate route is what makes its limits statable.
- A grant reason (`grant_missing`, `grant_expired`, `mail_requires_local`) must discard any cached
  snapshot in the same request. An independent reviewer caught the opposite and it was a real
  trust bug, not a style issue; a second round caught that the first fix could not match the key
  of a removed grant. Eviction matches on assistant and kind, not on the exact cache key.
- A trigger body can only be replaced by dropping it. If you correct one of the notification
  triggers, add a migration step that drops and recreates it; editing `CREATE TRIGGER IF NOT
  EXISTS` in an already-applied migration changes nothing on a live database. Schema v87 exists
  for exactly that reason and its test is the template.
- Mailbox previews require a Local-inference assistant. Preserve that when adding Outlook or any
  second mail source.
- There is no second delivery path and no exactly-once claim. An uncertain send is only resolved by
  the owner recording what they saw.
- Alert text carries no prompt, action arguments, fact values or provider content. Adding a field to
  it is a privacy decision, not a formatting one.

## Environment and reproduction

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run --frozen --no-sync pytest -q --no-header --tb=short \
  tests/test_personal_agenda.py tests/test_notifications.py
HUTCH_TEST_ARTIFACTS_DIR=$PWD/.pipeline/personal-operations/2026-11/evidence \
  UV_CACHE_DIR=/tmp/uv-cache uv run --frozen --no-sync pytest -q --no-header \
  tests/e2e/test_personal_today_agenda.py
npm run check:agent
```

Use a disk-backed `TMPDIR`. `/tmp` is a 12 GB tmpfs on this host and a full non-e2e run exhausted
it once, producing 434 failures and errors that were all fixture writes, not product defects. The
`~/.hutch-tmp/<name>` directories are the working pattern.

## Next priorities (from GAP-REGISTER, unchanged ordering)

1. G02 coding handoff verification gate and worktree lifecycle (`hutch code verify/prune`) with
   receipts.
2. G03 automation revision history, approval checkpoints and bounded conditions.
3. G04 inbound webhook/event triggers admitted through the existing admission policy.
4. G06 per-routine automation observability (the data already exists; only presentation is missing).
5. G07 an ADR for real multi-participant authentication before any family-account promise.
6. G08 commitment to calendar reminder, G09 mail/calendar content to a proposed commitment with
   provenance. G09 now has a real source to bind to: the agenda's item identity is a natural
   provenance reference, but it must be validated server-side against a real prior read, exactly as
   the 2026-10 GAP-REGISTER entry says.

## Known gaps this pass leaves open

- `GET /api/v1/notifications` computes `counts` over the returned page rather than over all rows.
- The 422 for a malformed assistant-id selection has no direct test.
- A pre-existing site test failure (`test_dynamic_workflow_marketing_is_truthful_and_responsive`)
  belongs to another session's commit `2ba2f7eb`, which changed site copy without the test.
- `npm run check:agent` is blocked by four frozen files grown by that other session's uncommitted
  work. It passes at a clean worktree of HEAD.
- `tests/test_emoji_audit.py` fails only because the agent runtime keeps state in
  `.codewhale/state/`, which is untracked and self-ignored but not in the audit's `SKIP_DIRS`. If
  that becomes a nuisance, the fix is one line in `scripts/audit_emoji.py`, not a change to any
  content.
- The full non-e2e suite is green except six attributed failures; see `RUNLOG.md` before treating
  any of them as new.
