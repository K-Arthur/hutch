# Changes — measured UI audit, 2026-10-22

Branch `agent/claude-wcag22m/measured-audit` on `main@ceb9d36b`. Each row is one commit; every
behaviour change has a test in `tests/e2e/test_wcag_measured_audit.py` that passes with the change
and was run against the previous code to confirm it fails there.

| Finding | Change (file: area) | Level | Evidence | Status |
|---|---|---|---|---|
| F-01 | `style.css`: focus ring restated for the `all: unset` legacy button variants | Shared component | `evidence/f01-allow-once-focus-{before,after}.png`; matrix `focus-invisible` 199 → 36 (remaining: container-ring and timing false positives, checked) | Fixed |
| F-02, F-03 | `app.js`: sheet `inert` while closed at ≤900 px (matchMedia, load and resize); removed the faulty Close-menu Tab handler; Needs you opened directly instead of `.click()` on an inert button | Shell | Probe log in RUNLOG/report; `evidence/f02-phone-sheet-open-after.png`; matrix `focus-obscured` high 387 → 0 | Fixed |
| F-04, F-05, F-06, F-13 | `style.css`, `app.js`, `index.html`: header wraps instead of overlapping; status chip keeps its size; reminder docked at the measured header height in chat from 641 px (in flow on phones), bottom clearance on page routes; follow-up commit 9c25bdbd removed the layout shifts the first version introduced; reminder is a labelled `aside` | Component + screen | `evidence/f06-chat-header-{901,1280}-{before,after}.png`, `f05-history-show-more-1024-*`, `f04-chat-reminder-768-after.png`; header overlap 9 widths → 0 | Fixed |
| F-07 | `style.css`: service tile container query | Component | `evidence/f07-gmail-tile-768-{before,after}.png` | Fixed |
| F-08 | `style.css`: fixed basis for the Work history count | Screen | CLS at 768 px 0.562 → 0.077 (remaining shift is the reminder appearing) | Fixed |
| F-09, F-12, F-14, F-16 | `models.html`, `usage.html`, `hutch.css`: named focusable table regions; visible Actions header; skip link hidden above the page; 12 px headers/meters; topbar scroll padding | Server templates/CSS | axe `scrollable-region-focusable` 5 → 0, `empty-table-header` 6 → 0; RTL overflow 999 px → 0 | Fixed |
| F-10 | `style.css`, `hutch.css`: 16 px floor for touch text fields | Shared form controls | `input-zoom-ios` at 320/375: 48 → 0 (iOS device check pending) | Fixed (device check pending) |
| F-11 | `app.js`: Activity waits for the roster when the cache is empty | Screen | Slug leaks 5/8 → 0/8 fresh loads | Fixed |
| F-18 | `app.js`: reminder rebuilds only when its message changes; focus restored | Component | Focus kept ≥25 s (was lost at 4.5 s) | Fixed |
| F-19 | `style.css`: underline class-less links in running text | System rule | axe `link-in-text-block` 6 → 0 | Fixed |
| D-01 | `style.css`, `hutch.css`: 72ch cap for hints and muted notes | System rule | Long-line paragraphs on Skills/Models 5 → 0 | Fixed |
| D-02 | `style.css`, `app.js`: shared switch; Automatic starts (Schedules, Runtime) and Enter sends; Runtime focus restore | New shared component | `evidence/d02-switch-states.png`; keyboard probe | Fixed |
| D-03 | `app.js`, `style.css`: Work history filter as native radios | Screen | `evidence/d03-history-filter.png`; keyboard probe | Fixed |
| D-05 | `index.html`, `app.js`: empty action-outcomes bucket hidden | Screen | Test | Fixed |
| D-06 | `app.js`: notice reading time and hover/focus hold | Component | Test | Fixed |
| D-07, D-08 | `app.js`, `style.css`: one primary on Manage assistants; ✕ for failed | Screen + component | `evidence/d07-assistants-1440-*`, `evidence/d08-status-chips-protan-deutan.png` | Fixed |
| D-09, D-10 | `style.css`, `skills.css`: shared `.btn-row` gap, Skills title row and spacing, matched control heights, crumb gap, chat head heights | System + screen | `evidence/d09-skills-header-1440-*` | Fixed |
| CLS follow-up (F-04, F-06) | `style.css`, `app.js`: header wraps only when title, chip and actions do not fit (subtitle `contain: inline-size`); reminder in the main view's grid cell from 641 px (a824292a) with conversation scroll padding; no reminder flash on the Needs you route | Component | CLS Scheduled work 1024 px 0.20 → 0.06, run detail 0.20 → 0.04, chat 768 px 0.13 → 0.06, Needs you 375 px 0.31 → 0.09 | Fixed (regression introduced and caught on this branch) |
| D-02 follow-up | `style.css`: the Automatic starts switch label may wrap on phones (6e1ff7dd) | Component | Pseudo-localized 320 px: 28 px overflow → 0 | Fixed (regression introduced and caught on this branch) |
| Verifier follow-up (F-10, F-07) | `style.css`: touch floor skips the 18px composer; tile badge stacks below 18rem (543a9d5e) | Component | Composer 16 → 18 px on touch; no tile name broken at 16 widths incl. 641–672 px | Fixed (found by independent verification) |
| Housekeeping | `style.css`: comment without a pictographic character (d26d6e3f); sheet test uses a function predicate under CSP (02b94328) | — | `test_emoji_audit` passes | Fixed |
| Full-suite follow-up (D-06, F-07) | `app.js`: notices hold on real pointer movement or focus, not when they appear under a resting cursor (168985b2); `style.css`: 18rem tile threshold only from 641 px, 16rem on phones (7c29b027) | Component | Coordinator, saved-requests and compact-phone card tests pass | Fixed (found by the full browser suite) |
| Tooling | `ui-audit.mjs`: axe under CSP, `axe-unavailable`, CSP self-test | Tool | Self-test passes; fails with the bypass removed | Fixed |
| D-04 | — | — | Recommendation | Not changed |
| F-15, F-17, O-01, flagged decisions | — | — | See FINDINGS | Follow-up |

Existing tests changed for intended behaviour: `test_browser.py` (Scheduled work switch role/name;
Work history radios; three notice waits 6 s → 10 s) and `test_runtime_page.py` (notice wording
"Automatic starts paused").
