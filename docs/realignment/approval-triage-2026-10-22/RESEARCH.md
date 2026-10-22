# RESEARCH — approval triage (accessed 2026-10-22)

Scope: how owners scan and decide a backlog of pending approvals and uncertain action outcomes, on desktop and phone-width web, without missing a deadline or approving the wrong action. Research was done before planning; implementation will do a fresh Track-D lookup for the exact CSS/HTML features used.

## A. What works

### A1. Prioritize and group; counts belong on the queue

- **NN/g, “Alert Fatigue in User Interfaces” (2022-12-16)** — dashboards should guide attention to critical values, not emit endless unprioritized alerts. <https://www.nngroup.com/videos/alert-fatigue-user-interfaces/>
  - Implication: a flat chronological queue is not triage. The queue needs a priority order and a visible summary, not more decoration per card.
- **Visa Product Design System, “Notification tray”** — “Prioritize and group notifications with the most important first”; “place the most urgent or highest priority action-based messages first”; include timestamps and section titles. <https://design.visa.com/patterns/notification-tray/> (accessed 2026-10-22)
  - Implication: show counts per priority/urgency group and keep the highest-consequence items first. A count is not enough by itself; the list order must agree with it.
- **Smashing Magazine, “Design Guidelines For Better Notifications UX” (2025-07-07)** — notification fatigue is the most frequent complaint in usability testing; fewer, better, grouped notifications beat a stream. <https://www.smashingmagazine.com/2025/07/design-guidelines-better-notifications-ux/>
  - Implication: do not add another interruption or auto-open modal. Improve the queue the owner deliberately opens.

### A2. Reduce decision overhead without removing control

- **arXiv 2510.05307, “When Should Users Check? Modeling Confirmation Frequency in Multi-Step Agentic AI Tasks” (2026-09-15)** — 48-participant study; 81% preferred intermediate confirmation over confirm-at-end; completion time fell 13.54%; users described a Confirmation–Diagnosis–Correction–Redo pattern. <https://arxiv.org/html/2510.05307>
  - Implication: approvals are valuable checkpoints, but each one must be quick to place in context. Do not solve fatigue by removing the gate; make the queue scannable.
- **arXiv 2607.13718, “How Agents Ask for Permission”** — commercial agents rely heavily on user-in-the-loop enforcement, producing high overhead and “privacy fatigue”; users then ignore warnings or over-grant. <https://arxiv.org/pdf/2607.13718.pdf>
  - Implication: preserve per-action decisions, but reduce the cost of each decision with clear priority, consequence, and exact scope.
- **The Register, “Humans in the loop miss a third of dangerous AI coding agent requests” (2026-08-06)** — 40,000+ plays, 409,000 approve/deny decisions; average player missed 1 in 3 threats; fatigue set in within 60 seconds; Anthropic telemetry cited ~93% approval rate. <https://www.theregister.com/ai-and-ml/2026/08/06/humans-in-the-loop-miss-a-third-of-dangerous-ai-coding-agent-requests/5284236>
  - Implication: do not add bulk approve. Reduce noise and make high-consequence requests unmistakable; a faster queue must not become a rubber stamp.

### A3. Shipped inbox patterns: priority tabs, compact rows, explicit order

- **Linear, “Inbox” docs + screenshot** (accessed 2026-10-22) — “Priority” and “Other” tabs carry counts; rows show title, reason, timestamp, unread/status mark; display options expose ordering (“Newest”), grouping, badge count, and priority inclusion. <https://linear.app/docs/inbox> · screenshot <https://webassets.linear.app/images/ornj730p/production/b442b340278740de70919c868dce1afca4335fe7-3600x2080.png>
  - Observed in the image: 4 compact rows fit in one panel; “Priority 4 / Other 12” is the first thing under the title; each row has one line of context and one timestamp.
  - Implication: a **priority split with counts** and **explicit ordering** is a proven way to make a backlog scannable without hiding the rest.
- **Linear, display-options screenshot** — “Enable priority inbox”, “Ordering: Newest”, “Group unreads by”, “Badge count”, “Show unread first”. <https://webassets.linear.app/images/ornj730p/production/2decf1f92f20b31e8a917d8e8c8c7e819ea1d8c3-1324x897.png>
  - Implication: give the owner a small, visible control over order/priority instead of one hidden default. For Hutch the safety-relevant default is **soonest deadline first**, not newest.
- **Atlassian Jira, notifications drawer screenshot** (public blog asset, 2024-11) — “Notifications” header, “Only show unread” toggle, “Direct / Watching” tabs, “TODAY / OLDER” groups, compact rows with actor/action/time and unread dots, “Mark all as read”. <https://atlassianblog.wpengine.com/wp-content/uploads/2024/11/notifications-drawer-in-jira1.png> · context <https://support.atlassian.com/atlassian-cloud/kb/overview-of-in-app-notifications-in-atlassian-cloud-products/>
  - Observed: 4 rows fit in a 643px-tall crop; grouping by time is visible but not noisy; the unread toggle is in the header.
  - Implication: group by meaningful time/priority bands, keep the header fixed, and keep row metadata short.
- **GitHub Docs, inbox triage + batch-selection screenshot** — reason labels/filters, unread/read, save/done, keyboard shortcuts; the screenshot shows a compact selection toolbar (“2 selected”, Done, Unsubscribe, More) above dense rows. <https://docs.github.com/en/subscriptions-and-notifications/concepts/about-notifications> · <https://docs.github.com/en/subscriptions-and-notifications/how-tos/viewing-and-triaging-notifications/managing-notifications-from-your-inbox> · image <https://docs.github.com/assets/images/help/notifications-v2/triage-multiple-notifications-together.png>
  - Observed: rows are ~70px tall at this crop; the unread dot, repository, title, and state are separate scan targets.
  - Implication: density is achievable without losing the object identity. **Not transferable:** GitHub’s batch “Done” action. Hutch must keep one decision per exact action.

### A4. Technical and accessibility ground truth

- **W3C WCAG 2.2 SC 2.4.11 Focus Not Obscured (Minimum), updated 2026-06-15** — focused components must not be entirely hidden by author content; sticky headers/footers and non-modal dialogs are typical causes; a properly constructed modal dialog passes because it takes and contains focus. <https://www.w3.org/WAI/WCAG22/Understanding/focus-not-obscured-minimum.html>
  - Implication: if a sticky header is added, keyboard focus must scroll clear of it (`scroll-padding-top` / C43). The drawer is a native modal `<dialog>`; keep it modal and contained.
- **W3C C43, using CSS scroll-padding to un-obscure content** — <https://www.w3.org/WAI/WCAG22/Techniques/css/C43>
- **W3C F110** — failure caused by a sticky header/footer completely hiding focused elements. <https://www.w3.org/WAI/WCAG22/Techniques/failures/F110>
- **WCAG 2.2 SC 1.4.10 Reflow** — 320 CSS px width; single-direction scrolling for non-excepted content. <https://www.w3.org/WAI/WCAG22/Understanding/reflow.html>
- **MDN `<dialog>`** — Baseline “Widely available”; native modal takes focus, makes the rest inert, closes on Esc; `closedby` adds light dismiss/platform back; an explicit close button is the robust mechanism. <https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/dialog>
  - Implication: a sticky in-dialog header with the close button is a standards-compatible fix for the measured “close control 5,984px above the viewport” state. Adding backdrop/light dismiss is a secondary improvement; feature-detect rather than relying on it.

## B. What failed

- **Sonos 2024 app rebuild** — shipped with missing features (sleep timers, queue/playlist editing, local library) and accessibility regressions; The Verge, Reuters, Ars Technica, and The Register document the backlash, apology, delayed products, and executive departure. <https://www.theverge.com/2024/5/9/24152675/sonos-new-app-bad-reviews-response-statement> · <https://www.reuters.com/technology/sonos-ceo-promises-reforms-after-may-app-release-failure-leaders-forgo-bonuses-2024-10-01/> · <https://arstechnica.com/gadgets/2024/07/pained-by-having-let-you-down-sonos-apologizes-for-app-failures/> · <https://www.theverge.com/2025/1/13/24342282/sonos-app-redesign-controversy-full-story>
  - Lesson for this lane: do not remove pagination, resolved history, receipts, always-allow, exact arguments, or keyboard exit to make the queue prettier. Parity is a hard gate.
- **Copilot CLI #1168, “authorization fatigue” (2026-01-28)** — one request produced >12 consecutive approval dialogs, including repeated prompts for the same path/category; users ask for batching/scoping. <https://github.com/github/copilot-cli/issues/1168>
  - Lesson: the problem is not only visual; repeated, low-context prompts train blind approval. This lane cannot change prompt frequency (backend/safety policy), but it can make the existing queue prioritize consequence and deadline instead of arrival time.
- **OpenClaw #58616, “approval flow is impractical / self-defeating” (2026-04-01)** — constant prompts, expired IDs, unclear cross-surface flow; “if you prompt constantly, people stop evaluating prompts.” <https://github.com/openclaw/openclaw/issues/58616>
  - Lesson: expired/urgent requests must be visibly first, and the decision surface must not hide its exit.
- **Feedbackbench, “Tool approval prompts and autonomy modes” (2026)** — silent prompts stall unattended runs; users build dashboards just to see which session is waiting; fatigue pushes users to yolo/full access. <https://feedbackbench.com/criteria/work.permission_prompts.md>
  - Lesson: “Needs you” is the dashboard for waiting sessions. A contradictory empty state or a buried request breaks the only recovery path.
- **Agent permission-fatigue game / The Register (2026-08-06)** — see A2. Humans miss dangerous requests under time pressure; scope violations and typosquats are missed most.
  - Lesson: keep exact scope and risk visible on every request; do not let density erase the “leaves machine”/high-risk signal.

## C. What users complain about (kept only if front-end-fixable)

| ID | Complaint (source) | Front-end-fixable? | Mapped finding |
|---|---|---|---|
| C-1 | Urgent/expiring approvals are effectively invisible in a long chronological list; runs sit waiting or expire (Feedbackbench; OpenClaw #58616; NN/g alert fatigue) | Yes — order and summarize the queue | F-01, F-04 |
| C-2 | A long modal/drawer loses its close control; phone users must scroll back to escape (measured here; MDN dialog guidance; WCAG 2.4.11 discussion) | Yes — sticky header + close; light dismiss fallback | F-02 |
| C-3 | “No pending approvals” while an uncertain action still needs review; the badge says 1 but the drawer says 0 (measured here) | Yes — truthful combined status | F-03 |
| C-4 | Cannot see scope or filter a backlog; scanning 50 cards (Linear/Jira/GitHub patterns; NN/g) | Yes — counts, priority order, filters | F-04 |
| C-5 | Internal IDs and repeated metadata crowd the decision (measured; Jira/Linear keep rows compact) | Yes — move ID to details | F-05 |
| C-6 | “1:27 left” is ambiguous (1 h 27 m vs 1 m 27 s); timestamps help relevance (Visa tray; Linear/Jira) | Yes — unambiguous countdown | F-06 |
| C-7 | Too many prompts / repeated approvals / yolo-mode pressure (Copilot #1168; The Register; OpenClaw #58616) | **No** — policy/auto-review/backend; out of scope | Parked |
| C-8 | Provider/OAuth approval screens, push delivery, billing | **No** — third-party/back-end | Parked |

## D. Figma Community research status (disclosed blocker)

The local gate prefers Figma Community. In this environment:

- Community pages (`https://www.figma.com/community/file/…`) return an **AWS WAF JavaScript challenge**, and the `og:image` CDN (`s3-alpha.figma.com`) returns **HTTP 403**. We did not attempt to bypass the bot challenge or sign in.
- Candidate files found via search but **not inspected**: “Refyn — Affiliate Dashboard UI Kit” (includes an Approval Queue screen), “Dogear — Human-in-the-loop UI kit: approval gates…”, “Novu Inbox — Notification Center UI-Kit”, “Notification Center modal”. They remain leads, not evidence.
- Per the gate’s fallback, actual online interfaces were inspected instead: Linear Inbox + display options, Atlassian Jira notifications drawer, GitHub notifications inbox/batch selection (sections A3). These are shipped-product screenshots or official documentation images; they are inspiration, not proof of usability for Hutch.
- Mobbin was unavailable (HTTP 429; paid-plan requirement), so it was not used.

## E. Rejected ideas and why

- **Bulk approve / bulk deny** — rejected. Research shows fatigue already produces blind approval; batching consequential actions would increase the chance of a wrong outward action, and Hutch’s navigation decision explicitly says “There is no bulk approve.” Add filters, not bulk authority.
- **Hide low-risk approvals in a separate tab by default** — rejected as the only change. It can hide a low-risk request that expires sooner than a high-risk one. Priority order + counts + filters keeps everything reachable.
- **Auto-approve “safe” categories** — rejected; changes the safety model and belongs in policy/backend, not this front-end lane.
- **Infinite scroll** — rejected. It loses the footer/receipts and makes the backlog unbounded; use a bounded “Show more” with a total.
- **Master/detail table with one-line rows only** — not chosen as the primary route. It improves density but adds a click before the consequence/exact scope is visible, which is the opposite of what a safety surface needs.
- **Red/amber everywhere for urgency** — rejected; alert fatigue and color-only status. Use one priority order, counts, words, and existing semantic tokens.
- **Global token/theme changes** — unnecessary; the approval surface already uses the shared tokens.

## F. Research-to-plan traceability

- F-01/F-04 → A1 (prioritize, counts), A3 (Linear/Jira), B (fatigue failures), C-1/C-4.
- F-02 → A4 (dialog, 2.4.11, C43), C-2.
- F-03 → A1/A3 (truthful status), B (silent prompts), C-3.
- F-05/F-06 → A3 (compact rows, timestamps), C-5/C-6.
- Parity/rejected bulk actions → B (Sonos), E.
