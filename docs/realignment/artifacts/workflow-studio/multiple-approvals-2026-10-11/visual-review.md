# Paired-phone simultaneous approvals visual review — 2026-10-11

The review queue was exercised with two independent pending action approvals and answered in each order. Each card keeps its own bot name, action and durable approval ID. After the first decision, the other card remains visible and its approval remains pending; after the second, both approvals resolve and the queue empties.

At 390×844 CSS pixels the two cards stack with clear boundaries and side-by-side Allow once/Deny controls. At 320×780 they remain readable, the brand wraps without clipping, the review count stays visible, and each card stacks its action buttons vertically. Measured document overflow is 0px; all four action controls are at least 44px tall. The approved card disappears after refresh while the remaining request stays available.

The test uses two disposable local mock-model runs, local SQLite, and paired review permission. It makes no hosted model calls or external writes. Evidence includes both order traces and screenshots. This does not verify more than two concurrent approvals, OS-level screen-reader announcements, browser-chrome zoom, offline reconnection, or wider production queues.

Both Allow once and Deny controls reference the card's action and durable approval ID through `aria-describedby`. Browser assertions verify that both references resolve in owner chat and paired-phone cards. This verifies DOM accessibility metadata; it does not establish how a particular operating-system screen reader announces it.
