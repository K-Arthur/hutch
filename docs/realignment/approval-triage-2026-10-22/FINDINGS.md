# FINDINGS — approval triage (baseline 2026-10-22)

Method: isolated Hutch server on port 8810, seeded synthetic approvals (14 realistic; 52 stress) in a temporary state dir. DOM measured with Playwright at 1440×960, 1024×900, 390×844, 320×740; screenshots inspected. Raw data: `measure-before/measure.json`, `measure-stress/stress.json`, `measure-stress/stress-320*`, `close-check`, `receipts-only/state.json` (copied to `evidence/` at verification time). No provider calls, no real data.

Severity: S0 blocks a core task / legal or data loss · S1 major friction or frequent error · S2 minor · S3 polish.

---

## F-01 · S1 · Confirmed · FIFO order buries urgent, outward requests

- **What:** The queue renders `GET /api/v1/actions/approvals` in server order (`ORDER BY created_at, id` — oldest first). Newest/urgent requests are at the bottom and on the last page. There is no priority order, no urgency summary, and no filter.
- **Evidence (52 pending, 1440×960):** page 1 = 50 cards, `scrollHeight` **12,869 px**, pagination at **12,640 px**, “1–50 of 52 requests · Next”. The urgent outward payment (TTL **1:26**) is the **51st** item on page 2; the other outward payment (TTL **3:27**) is card 50 at **12,298 px**. (`measure-stress/stress.json`, `stress-bottom.png`, `stress-page2-urgent.png`)
- **Evidence (52 pending, 320×740):** page 1 = **20,584 px** tall, pagination at **20,363 px**; page 2 urgent payment at 615 px. Reaching it costs ~**20,978 px ≈ 28 viewport heights**. (`measure-stress/stress-320`, screenshot `stress-320-bottom.png`, `stress-320-page2.png`)
- **Evidence (14 pending, 1440):** the 1:35 context-summary request sits at 1,837 px and the 2:35 `git push` at 2,419 px; the first card has 23:35 left. (`measure-before/measure.json`)
- **User impact:** default-deny deadlines pass while the owner reviews low-consequence older requests; an outward payment or `rm` can expire unseen. This is the exact failure class in RESEARCH C-1/B (silent waiting, approval fatigue, missed scope violations).
- **Rubric:** G3 attention (prioritize; ≤2 intensity levels), P2 task-frequency ordering, P4 error prevention, U1 speed/error rate, Nielsen “visibility of system status.”
- **Root cause:** the queue uses arrival order and server pagination as if this were a log. Triage needs consequence/deadline order.
- **Fix direction:** fetch the pending set (bounded), sort by soonest deadline with high-risk/outward tie-breaks, show counts, keep everything reachable. No API change; no bulk actions.
- **Blast radius:** `#/approvals` drawer; inline chat cards keep their per-conversation order and are not re-sorted.

## F-02 · S1 · Confirmed · Close control is unreachable after scrolling on phone

- **What:** The drawer header is not sticky. At 390×844, after `scrollTop = 6000`, the close button is at **top −5,984 px** (fully off-screen); tapping the content does not close, there is no backdrop area on phone, and the native dialog does not light-dismiss (`closedby` unset). Only Esc (keyboard) or scrolling ~6,000 px back to the top closes it.
- **Evidence:** `close-check` run: `{closeVisible:false, closeTop:-5984, open:true}` before and after a tap; 52-card page is 20,584 px at 320. Screenshot `stress-320-bottom.png` shows the bottom of the drawer with no header/close.
- **User impact:** touch users are effectively trapped in a long queue; MDN’s dialog guidance says provide a close mechanism that works on devices without a physical keyboard. Combined with F-01, the phone supervisor cannot quickly leave or recover.
- **Rubric:** WCAG 2.2 2.4.11 context, MDN `<dialog>` “closing dialogs,” P4 “user in control,” C-2.
- **Root cause:** header is a static block inside a 100dvh scrolling dialog; no `position: sticky`, no light dismiss, no platform back handling.
- **Fix direction:** sticky compact header containing the title, live counts, and close; add `scroll-padding-top` equal to its height so focused cards are not obscured (C43); add `closedby="any"` with a backdrop-click fallback for browsers without it.
- **Blast radius:** drawer only; inline cards unaffected.

## F-03 · S2 · Confirmed · Drawer says “No pending approvals” while an uncertain action is waiting

- **What:** With 0 pending approvals and 1 unresolved action receipt, the drawer leads with a large success check and “No pending approvals. Requests appear in their conversation and here.” The “Action outcomes to check” section and its receipt appear **below** (top ≈ 300 px at 390). The sidebar badge says 1. The top-level status contradicts the actual work.
- **Evidence:** route-intercepted receipts-only state at 390×844 (`receipts-only/state.json`, `receipts-only-390.png`): order is `approvals-pending` (empty check) → `receipt-queue-title` → receipt.
- **User impact:** an owner opens “Needs you” for the badge, sees a positive empty state, and closes — leaving an outward action whose outcome is unknown. Matches RESEARCH C-3 and the “silent waiting” failure.
- **Rubric:** Nielsen “visibility of system status,” WCAG 4.1.3 status messages, F3 empty states, P5 error prevention.
- **Root cause:** the approvals empty state is rendered unconditionally and is not aware of receipts; the drawer has no combined “items needing review” summary.
- **Fix direction:** one truthful top-level status (“N approvals · M action outcomes”); when approvals are empty but receipts exist, lead with the receipts and use a neutral line instead of a success check. Keep both sections and their pagination.
- **Blast radius:** drawer only; badge/announcements already count both.

## F-04 · S2 · Confirmed · No queue-level summary or filters for backlog scanning

- **What:** The only count is the pagination line at the bottom of the list (“1–50 of 52 requests”). There is no “due soon / high risk / leaves machine” summary and no filter. At 50 cards the owner must scan every card face; the header only says “Needs you.”
- **Evidence:** DOM measurements above; screenshots `stress-top.png`, `stress-bottom.png`. Source: `refreshApprovals()` renders only `approvalCardHtml` list + pagination.
- **User impact:** the 200/hour goal fails on scan cost even before F-01; the owner cannot answer “is anything about to expire or leave the machine?” without scrolling. Linear/Jira/GitHub patterns (RESEARCH A3) all expose counts/filters/unread before the list.
- **Rubric:** G2 users control display (sort/filter), G3 attention, P1 expert efficiency, U1 speed.
- **Root cause:** the drawer is a single flat list with server pagination and no view state.
- **Fix direction:** sticky summary with counts derived from the loaded set + filter toggles (`All`, `Due soon`, `High risk`, `Leaves machine`), accurate per current data; keep per-card decisions.
- **Blast radius:** drawer only; data contract unchanged.

## F-05 · S3 · Confirmed · Internal approval ID on every card face

- **What:** Each card prints `Approval ID apr_…` in a 14 px hint line (21.7 px tall) between the action and “Review details.” With 50 cards that is ~1,085 px of repeated internal identifiers (8% of the 12,869 px page; 5% at 320).
- **Evidence:** `measure-before/measure.json` (`idHeight: 21.7`, id text `apr_220165d5d875`); screenshots.
- **User impact:** scan noise on the safety surface; the ID is useful only for support/reconciliation and belongs inside review details.
- **Rubric:** G2 terminology/display (no need to remember; display format matches use), craft floor hierarchy.
- **Fix direction:** move the ID into the existing Review details rows (and keep the `aria-describedby` relationship on buttons). No ID is removed from the DOM or API.
- **Blast radius:** inline cards and queue share `approvalCardHtml`; both get the compaction.

## F-06 · S3 · Confirmed · Countdown format is ambiguous

- **What:** TTL renders as `m:ss` (`1:27 left`, `26:17 left`). `1:27` can read as 1 h 27 m or 1 m 27 s; the product’s deadline is default-deny, so misreading urgency matters. There is no absolute expiry time.
- **Evidence:** `measure-before/measure.json` TTL values; `stress-page2-urgent.png` (`1:27 left`).
- **User impact:** the owner underestimates or overestimates time left; especially at 320 where the countdown wraps to its own line and is easy to miss.
- **Rubric:** G2 display/entry consistency, Nielsen “match with the real world,” RESEARCH C-6.
- **Fix direction:** format as `1m 27s left` (<1 h) and `1h 27m left` (≥1 h); keep updating each second; do not add a second timestamp line.
- **Blast radius:** shared `updateTtls()`; applies to inline and queue cards.

---

## Dependency, not a finding in this lane

- **Button focus rings on main are missing** (WCAG 2.4.7): `button.primary/ghost/danger/small { all: unset }` clears the global `:focus-visible` outline. The concurrent WCAG lane fixes this in commit `a403a598` (F-01). This lane will not duplicate the fix; the after-matrix will re-verify it after rebase.
- `ui-audit.mjs` `fixed-layer-overlap`/`occluded-control` hits behind the open modal are expected modal behavior (background is inert); confirmed false positives, not findings.

## Residual risks / needs human check

- **Needs human check:** screen-reader announcement order for the new summary/filters (no NVDA/VoiceOver available here). Keyboard and DOM only.
- **Needs human check:** whether “Due soon” should be 10 or 15 minutes. Baseline default TTL is 600 s; 10 min matches the default. Revisit if real usage shows longer TTLs.
- **Probable:** at >200 pending approvals a single `limit=200` fetch would truncate. Plan handles this by paging with a documented cap and a visible notice; exact threshold to confirm with the owner.
