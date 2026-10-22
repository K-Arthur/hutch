# DECISION — is a front end needed?

**Yes.** The task is a high-frequency human decision queue. The measured failure is not missing backend capability: the data and per-action decision endpoints already exist. The owner cannot see which request is about to expire or leave the machine, cannot close the drawer after scrolling on phone, and is told “no pending approvals” while an uncertain action waits. These are presentation/flow defects.

**Which front end?** Improve the existing screen: the `#/approvals` “Needs you” drawer, sharing the card component with inline chat approvals. No new route, no new app surface, no API change.

**Interaction style.** Direct manipulation for each decision (approve/deny/always allow), a priority queue for triage, and progressive disclosure for exact arguments. This fits both occasional owners and experts processing a backlog: one glanceable priority order with counts, filters for narrowing, and the full consequence text still on the card. It deliberately avoids:
- a command palette or natural-language triage (weak for novel risky actions, and would add a new interaction layer);
- a master/detail table (extra click before consequence, wrong for a safety surface);
- bulk approval (safety decision; research shows fatigue already causes blind approval).

**Multi-layer fit.** Default view: soonest-deadline first, with high-risk/outward cards marked. Expert layer: filters and “Show more,” plus the existing exact-arguments disclosure. Novice layer: plain-language action, bot, risk, deadline, and one primary decision.

**Do not lose.** All existing per-card decisions, always-allow rules, resolved history, receipts, pagination access, polling/focus restoration, cross-device conflict handling, and the no-bulk-approve rule. See `RECON.md` feature-parity inventory.

**Out of scope.** Reducing prompt frequency, auto-approval policy, provider/OAuth approvals, push/browser notification delivery, and provider billing. These need backend/policy work and are parked in `RESEARCH.md`.
