# Findings register — measured UI audit, 2026-10-22

Base: `main@ceb9d36b`. Fixture: isolated synthetic `mock/demo` state (12 assistants incl. an
80-character name, Arabic, Japanese, emoji and one-letter names; 41 runs with 220-character,
long-URL and mixed-script prompts; two pending approvals). No provider calls, no operator state.
Measurement: `ui-audit.mjs` (self-test PASS, CSP-safe axe-core 4.14.0), Chromium 1243 / Playwright
1.63, plus targeted probes (`scratchpad/tools/*.py`, summarized in RUNLOG.md).

Labels: **Confirmed** = measured and seen on a screenshot; **Probable** = measured, not yet seen;
**Needs human check** = cannot be settled in this environment. Severity follows the pipeline:
S0 blocks a core task or fails WCAG A/AA on a core flow; S1 major friction; S2 minor; S3 polish.

| ID | Sev | Status | Where | What (evidence) | Root cause | Fix direction / level |
|---|---|---|---|---|---|---|
| F-01 | S0 | Confirmed | Every SPA route, all widths | Primary/ghost/danger/small buttons and `a.primary/a.ghost` show **no focus indicator**: computed `outline-style: none` while `:focus-visible` matches; focused vs blurred crops pixel-identical (e.g. **Allow once**, Review, Deny, Refresh, New assistant). ui-audit `focus-invisible` on 13 routes. WCAG 2.4.7. | Legacy-button rule (`style.css` "legacy element tags…") uses `all: unset` at specificity (0,1,1), which beats the global `:focus-visible` ring (0,1,0). Present since 2026-10-08. | Shared component: give that rule its own `:focus-visible` ring, matching the per-component idiom used throughout `style.css`. |
| F-02 | S0 | Confirmed | ≤900 CSS px (phones, tablets, laptops at ≥160 % zoom) | With the navigation sheet open, Tab cycles **Close menu ↔ brand** forever; Chats, Needs you, More and assistants are unreachable by keyboard (probe log, 30 Tab presses). WCAG 2.1.1. | Extra `#ws-close` keydown handler sends Tab to the first `a, button` in `#workspace`, which is the brand link *before* the close button. | Remove the handler; the sheet's existing wrap trap already handles first/last. |
| F-03 | S0 | Confirmed | ≤900 CSS px, every SPA route | Closed off-canvas sheet (`translateX(-102%)`) keeps ~20 controls in the tab order; each is focused off-screen (ui-audit `focus-obscured` high at 320/375/768 on all routes). "Open menu" is Tab stop 22. WCAG 2.4.11, 2.4.3. | Hidden with `transform` only. | `inert` on `#workspace` while narrow and closed (matchMedia on the CSS breakpoint). |
| F-04 | S0 | Confirmed | 641–900 px, chat | "N approvals need you" bar is fixed at `top: 66px` and covers the wrapped header's second row (conversation switcher, Search chats, chat options); focus on chat options entirely hidden at 768. WCAG 2.4.11 + pointer occlusion. | The bar's fixed `top: 66px` assumed a one-row header; the header wraps at ≤900 px. | From 641 px the reminder shares the main view's grid cell, aligned to the top: it sits just below the header however many rows it has, moves with the page (no separate jump) and stays under the navigation sheet. Phones keep their in-flow row. (Two earlier versions — in-flow at 641–900 px, then a fixed dock at the measured header height — were replaced after they raised CLS.) |
| F-05 | S0 | Confirmed | ≥901 px, page routes (Work history, Activity, Skills, Manage assistants) | Floating reminder **entirely covers the focused "Show 17 more tasks"** button at the end of Work history (element at its centre is `#attention-bar`; scroller already at end). Other last items 30–80 % hidden. WCAG 2.4.11 on the paging path. | No clearance reserved for the floating layer in `.page-scroll`. | `scroll-padding-bottom` + `padding-bottom` while the reminder floats (W3C C43). |
| F-06 | S1 | Confirmed | 901–1440 px, chat header | At 1280–1440 the conversation switcher covers the "Waiting for you" chip; at 901–1100 the avatar sits on the switcher, the title disappears, and "2 waiting · 1 queued" is painted over **Review** and **Stop**. | `.ctx-meta` (status chip) has `min-width: 0` and shrinks to 0 px; the header never wraps above 900 px, so non-shrinking actions overflow into the status cluster. | Keep the chip at its size, let the header wrap actions under the identity when they do not fit; dock the chat reminder under the *measured* header height. |
| F-07 | S2 | Confirmed | Apps & AI tiles near their 228 px minimum (e.g. 768 px) | Service names wrap one letter per line ("G/m/a/i/l"); `h3` 11 px wide. DESIGN.md: keep complete product names visible. | Fixed `48px | 1fr | auto` grid leaves ~10 px for the name beside the state badge. | Container query on the tile: stack the badge under the name when the tile is narrow. |
| F-08 | S2 | Confirmed | Work history, 768 px | CLS **0.562** on every load: "Loading past work…" wraps to a second toolbar row, then "42 results" fits on the first and the whole list jumps 44 px. | Count text width changes between states inside a wrapping toolbar. | Give the count its own stable row. |
| F-09 | S2 | Confirmed | `/models`, `/usage` ≤1024 px | axe `scrollable-region-focusable` (serious): horizontally scrolling table wrappers cannot be reached by keyboard in browsers without focusable scrollers (Chrome ≥130 adds this; WebKit does not). WCAG 2.1.1. | `.table-wrap` has no tabindex/name. | `tabindex="0"`, `role="region"`, `aria-label` on the wrappers. |
| F-10 | S2 | Confirmed (iOS behaviour: Needs human check) | Phones | Five fields render at 13–14 px (conversation switcher, assistant search, identity name, pair code, skill import path); iOS Safari zooms the page on focus below 16 px. | Shared form controls inherit 14 px. | 16 px floor for text fields/selects on coarse pointers. Never disable zoom. |
| F-11 | S2 | Confirmed | Activity on direct load | "Needs you" rows show storage slugs (`emoji-helper`, `fleet-helper-2`) or display names depending on load timing (pixel diff of simultaneous loads). DESIGN.md keeps storage IDs out of visible titles. | `/api/overview` rows carry only `bot_name`; the page renders before the roster cache fills. | Wait for the roster when the cache is empty before the first render (front end only; no API change). |
| F-12 | S3 | Confirmed | `/models` | axe `empty-table-header` on the actions column. | Empty `<th>`. | Visually hidden header text. |
| F-13 | S3 | Confirmed | All SPA routes with a reminder | axe `region`: reminder sits outside landmarks. Arrival is already announced via `#live-status` (4.1.3 met). | Plain `div`. | Labelled `aside` (complementary landmark). |
| F-14 | S3 | Confirmed | Server pages under `dir=rtl` | Skip link at `left: -999px` creates 999 px of horizontal overflow (scrollWidth 1319 at 320). | Physical off-screen offset. | Hide off the top with a logical inline start, like the SPA skip link. |
| F-15 | S3 | Probable | Forced colors | After F-01 most "no indicator" stops should resolve; remaining `forced-color-adjust: none` on cards (inherited) keeps author colours inside cards under a user high-contrast theme. | Design choice in `@media (forced-colors)` block. | Re-measure; palette decision is a follow-up (Needs human check). |
| F-16 | S3 | Confirmed | `/models`, `/usage` | 11 px table headers and 11.5 px meter labels, below DESIGN.md's 12 px app floor. | Server-page stylesheet. | Follow-up (polish). |
| F-17 | S3 | Confirmed | Marketing proof image, 480–639 px | 390 px bitmap shown at 446 px (soft). | `srcset` lacks a larger candidate. | Follow-up. |
| O-01 | — | Opportunity | Chat, keyboard | Reaching the composer from load takes 44 Tab stops on desktop (43 phone). | Composer follows the whole feed in DOM order. | Follow-up for product decision (e.g. a "Skip to message box" link); not changed here. |

## Candidates rejected after confirmation

- `#/approvals` overlap/occlusion rows: controls behind the **Needs you** `<dialog>` opened with
  `showModal()`; the background is inert by design.
- Marketing hero collisions: intentional illustration layering (decorative, no text or controls covered).
- Sticky-header overlaps on the marketing site and `/usage` at intermediate scroll positions: no
  focused element was obscured in the keyboard walk.
- "Light scheme differs": the pixel difference was F-11 (timing), not theming; computed colours of
  every element were identical in light and dark (the product is dark-only by design).
- `label-content-name-mismatch` under pseudo-localization: tool artifact (visible text rewritten,
  `aria-label` not).
- 22 px tool-line targets under the text-spacing override: produced by the override's forced
  line-height; WCAG 1.4.12 requires no loss of content, which was met.
- `#chat-prompt` `focus-invisible`: the ring is drawn on `.composer-box:focus-within`, outside the
  measured crop; seen on screenshot.

## Design-level review (added at the user's request: component fit, streamlining, colour and
## other disabilities, alignment/arrangement, text load, breathing room and processing time)

Instrument: `scratchpad/tools/design_review.py` (per screen at 1440 and 390 px: first-viewport words,
helper words, controls, disclosure depth, text density, sibling gaps, near-miss left edges, mixed
control heights in one row, toggle-like/pressed/checkbox/select inventory) and
`scratchpad/tools/cvd_palette.py` (rendered status colours through Machado 2009 protan/deutan/tritan
matrices and achromatopsia, ΔE in OKLab). An early run counted text inside collapsed, overflow-clipped
panels (Assistant settings appeared to show 1,653 words); the instrument was corrected to exclude
clipped content and those numbers were discarded.

| ID | Sev | Status | Where | What (evidence) | Fix direction / level |
|---|---|---|---|---|---|
| F-18 | S1 | Confirmed | Every route with the reminder | Keyboard focus on the reminder's **Review** button is lost after 4.5 s and lands on `<body>`: `renderAttention()` rebuilds the bar's HTML on every status poll. WCAG 2.4.3; also removes the time people need to read and act. | Rebuild only when the message changes; restore focus if a rebuild happens. |
| F-19 | S1 | Confirmed | Runtime (all widths; also other in-text links) | axe `link-in-text-block`: "Review in Needs you" inside running text is distinguished by colour only. WCAG 1.4.1 (A). The SPA underlines links only inside `.answer`. | System rule: underline class-less links in running text (`p, li, dd, td, .hint`). |
| D-01 | S2 | Confirmed | Skills, Models, Runtime | Helper/description text runs 135–164 characters per line, against DESIGN.md's Measure Rule (~72ch). | Cap helper text at 72ch (shared rule in `style.css` and `hutch.css`). |
| D-02 | S2 | Confirmed | Scheduled work, Runtime, composer menu | Immediate binary states are a status sentence plus a button whose label flips ("Scheduled work is on" + "Pause scheduled work"; "Pause/Resume automation"); "Enter sends" is a persistent, immediate preference shown as a checkbox. NN/g and WAI-ARIA APG: a switch states and changes an immediate on/off setting in one control. Scheduled work and Runtime change the *same* state (`/v1/schedules/control`) under two names. | New shared `.switch` component (button `role="switch"`, `aria-checked`, track + thumb + On/Off text) for these three. |
| D-03 | S2 | Confirmed | Work history filter; identity colour/shape pickers | Single-choice groups built as `aria-pressed` toggle buttons (4 and 8 tab stops); screen readers announce independent toggles, not one choice. | Work history: native radio group styled as the same segmented control (one tab stop, arrow keys). Identity pickers: follow-up. |
| D-04 | S2 | Confirmed | Settings | "Effects" and "Default routing" are 3-option selects in a Save form, hiding the choices. | **Recommendation, not changed:** in a Save form a select is acceptable; radios would lengthen the page. Revisit with the Settings owner. |
| D-05 | S2 | Confirmed | Needs you | Empty "Action outcomes to check — No uncertain action receipts." section always shown; DESIGN.md: hide empty buckets. | Hide when empty. |
| D-06 | S2 | Confirmed | Toasts | Success notices vanish after a fixed 4.2 s regardless of length, even while hovered or focused (errors already persist). | Length-based duration (≥5 s) and pause while hovered/focused. |
| D-07 | S2 | Confirmed | Manage assistants | 12 identical emerald **Open** buttons compete with the page's primary action (New assistant); every card also repeats "Ready when you are." and a "Details · Settings and activity" row. | Per-card Open as a secondary (ghost) button; repeated filler copy flagged for product decision. |
| D-08 | S2 | Confirmed (protan) | Status chips | Under protanopia "Failed" and "Done" chip colours are ΔE_ok 0.03 apart (indistinguishable); all states use the same round dot, though DESIGN.md specifies `✕ failed`. Words are present, so 1.4.1 passes. | Failed chips use the ✕ glyph from DESIGN.md (shape redundancy). |
| D-09 | S3 | Confirmed | Skills header and import panel | `.page-title-row` has no style, so Refresh stacks under the title; the subtitle touches the panel (0 px); sample-install buttons touch; "Install from folder" is 26 px beside a 39 px field. | Title row with trailing action, spacing tokens, button row gap, matched control height. |
| D-10 | S3 | Confirmed | Chat message head; server topbar (390) | Mixed control heights in one row: Stop 26 px beside View work details 36 px; server brand link 25 px beside 38 px menu button. Crumb → form gap 4 px on Assistant settings. | Match heights in the row; spacing token for the crumb gap. |

### Flagged for a product decision (not changed)

- **Approval timing (WCAG 2.2.1):** approvals expire (countdown "5:11 left"); there is no way to
  extend. Expiry may be a deliberate safety limit (essential exception), but people who need more
  processing time can lose a pending request. Options: an "Extend 10 minutes" action, or a longer
  default with the same server check.
- **"Always allow for this bot" next to "Allow once"** in the same row on phones invites a mis-tap
  on the broader, persistent grant. Options: order Allow once · Deny, then the persistent grant
  separated or behind the details disclosure.
- **Approval ID in every card** and in each action button's description: useful for cross-device
  matching, but screen readers hear a random ID on every Allow/Deny. Option: keep it inside
  "Review details" and out of `aria-describedby`.
- ~~Two names for one state~~ — resolved in D-02: both switches are labelled "Automatic starts"
  (the fence covers scheduled starts and watched-source admissions). Easy to rename if the product
  prefers another term.
- **Persona controls:** four 3–4-option selects inside the conversation menu and binary
  "Inherited/Custom" selects in Assistant settings; binary choices would read better as checkboxes
  in that Save form, but the menu should stay compact.
- **Manage assistants filter:** a select, while Work history uses a segmented filter; unify once
  the segmented control has proven itself on phones.
- **Filler copy** ("Ready when you are." on every idle card).
- **Workflow counts at 901–1000 px:** "2 waiting · 1 queued · 2 need you" takes ~230 px of the header,
  so run detail and Scheduled work must wrap (one-time CLS ≈ 0.2 at exactly 901 px). A compact form
  (e.g. only "N need you") at that width would keep one row.
- **O-01** skip-to-composer (unchanged).
