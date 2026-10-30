# Overlay audit: matrix, gap list, and decisions

Date: 2026-10-30. Baseline commit 548a2d6e + parked design-system work. This document is the
gate before any overlay edit: tokens, primitives and migrations were held until the matrix
and gap list below existed. Every entry cites a file and line; every gap names how it will
be verified. Status starts as `open`; the final column is updated to `fixed`,
`intentional`, `deferred` or `unverified` at completion.

## 1. Audit matrix

Legend: T = trap, IF = initial focus, FR = focus return, Esc = Escape, OC = outside click,
SL = scroll lock, A11y = accessible name, States = loading/error/disabled.

| Overlay | Category | Trigger | Focus trap | Initial focus | Focus return | Escape | Outside click | Scroll lock | Stacking | Positioning | Motion | A11y name | Theme | States |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A1 openModal | Modal | JS call | Manual Tab wrap, incomplete (F1) | First input else confirm (F2) | Yes, many fallbacks (F3) | Yes | Backdrop mousedown closes | None (X5) | Fixed z 50 vs native top layer (Z2) | Centred, bottom sheet <=640 | Enter only, no exit (C4) | aria-labelledby only (X1) | Hard-coded scrim/shadow (T2/T3) | Per call site; no factory busy/error (S1/S2) |
| A2 confirmDialog | Modal (destructive) | JS call | Inherits A1 | Destructive confirm button (F2) | Inherits A1 | Yes, even for destructive (D1) | Backdrop closes, destructive too (D1) | None | Inherits A1 | Inherits A1 | Enter only | aria-labelledby only; body not described (X2) | Inherits A1 | No busy while API runs (S5) |
| A3 needs-you | Modal (sheet) | #needs-you-open | Native dialog | Close button | Explicit stored target + visible fallback | Yes (cancel prevented, manual close) | Backdrop rect check | None (dialog is fixed; page scrolls) | Native top layer | Right sheet, 100dvh | None | aria-labelledby, close labelled; hint not described (X6) | ::backdrop literal (T4) | Loading, error, retry present (good) |
| A4 palette | Modal | Ctrl/Cmd+K | Native dialog | Search input | Explicit trigger restore | Yes (input + native cancel) | Backdrop click | None | Native top layer | Centred 12vh top | palette-in; exit none; reduced covered | aria-label "Jump to" | Literal backdrop (T2) | Async list loader has status; no busy on actions |
| A5 SPA drawer | Modal (nav sheet) | #nav-toggle | Manual over a/button/input/summary | First link | To toggle | Yes | Scrim click | None | z calc(var(--z-sheet)+1) (Z1) | Left drawer <=900 | Slide enter, no exit | No dialog role/aria-modal; toggle labelled (X8) | Scrim literal (T2) | n/a |
| A6 server nav | Modal (nav sheet) | #nav-toggle | Manual over links | First link | To toggle | Yes | None (no backdrop; full page) | None | z 120 literal (Z1) | Full-screen top sheet <=1400 | transform/opacity enter; reduced covered | No aria-modal; toggle labelled | Opaque bg, no scrim token | n/a |
| A7 window.confirm | Modal (destructive) | Form submit | Browser | Browser (OK) | Browser | Cancels | No | Browser | Browser chrome | Browser | Browser | Browser text | Browser | No custom busy/error; success invisible |
| A8 restored-history | Modal | Banner button | A1 | A1 | A1 | A1 | A1 | A1 | A1 | A1 | A1 | A1 | A1 | A1 |
| A9 document preview/versions | Modal | Doc actions | A1 | A1 | A1 | A1 | A1 | None | A1 | A1 | A1 | A1 | A1 | Async loaders present |
| A10 React Modal prototype | Modal (unwired) | Props | No | No | No | No | Scrim click only | No | No z family (Z1) | Inline | None | aria-labelledby/description in markup | Tokens only (good) | No busy/error |
| B1 controls.popup | Popover / Menu / Listbox | Caller trigger | n/a (non-modal) | Checked item, else first non-header control | Yes on explicit close | Yes, top of stack | Yes (closes all) | Native page scroll | Native top layer else z 160 (Z1) | Flip vertical + clamp horizontal; no left/right placement (P2) | None (C4) | Panel aria-label or trigger label; no labelledby (X9) | Token border/bg, literal shadow (T3) | Caller-owned |
| B2 roster menu | Dropdown menu | [data-bot-options] | n/a | First item | Esc -> trigger | Yes | Yes | n/a | Manual body portal + z toast+5 (Z1) | Anchored above (side top) | None | role=menu + aria-label | Literal shadow/bg legacy | Items disabled while busy |
| B3 model menu | Dropdown menu | .ms-btn | n/a | Checked item | Yes | Yes | Yes | n/a | Top layer | Anchored above | None | role=menu aria-label; menuitemradio | Legacy tokens in studio.css | Async refresh no loading state (S6) |
| B4 assistant settings menu | Dropdown menu | summary | n/a | First item | Yes | Yes | Yes | n/a | Top layer | Anchored | None | role=menu + label | Legacy | n/a |
| B5 conversation actions | Dropdown menu / Popover | #studio-conversation-options | n/a | First action | Yes | Yes | Yes | n/a | Top layer | Anchored; sheet at short heights | None | role=dialog/menu currently | Legacy | n/a |
| B6 composer menu | Popover (dialog) | #composer-menu-btn | n/a | First control | Yes | Yes | Yes | n/a | Top layer | Anchored / sheet (P2) | None | role=dialog aria-label | Token surface via controls.css | Mixed form; nested details Escape handled |
| B7 skills picker | Popover (dialog) | .skill-picker-btn | n/a | First checkbox | Yes | Yes | Yes | n/a | Top layer | Anchored above; narrow right-align | None | role=dialog aria-label | skills.css literals | Empty state present; async readiness hidden until loaded |
| B8 fleet card menu | Dropdown menu | details summary | n/a | First item | Yes | Yes | Yes | n/a | Top layer | Anchored | None | role=menu | Legacy | n/a |
| B9 datalist combobox | Popover (listbox) | input focus/click | n/a | DOM focus stays in input | n/a | Yes | Yes | n/a | Top layer | Match width, anchored | None | combobox/listbox semantics | Token surface | Status live region present (good) |
| B10 title tooltips | Tooltip | Hover/focus | n/a | n/a | n/a | n/a | n/a | n/a | Browser chrome | Browser | Browser | title text | Browser | Never interactive (good) |
| B11 React Menu prototype | Dropdown menu (unwired) | Props | No | No | No | No | No | No | No tokens | Inline absolute | None | Role menu in prototype | Tokens only | No busy/error |
| B12 React Tooltip prototype | Tooltip (unwired) | Hover/focus | n/a | n/a | n/a | Esc consumes | hover out | n/a | No z tokens | Absolute in wrapper (clips) | None | aria-describedby wired | Tokens only | n/a |

## 2. Gap list

### 2.1 Focus defects

| ID | Gap | Evidence | Verify | Target status |
| --- | --- | --- | --- | --- |
| F1 | Tabbing in A1 can skip controls the trap does not count: focusables are gathered from `button, input, select, textarea, a[href]` only, so `summary`, `[tabindex]`, contenteditable and media controls leak; `offsetParent` filtering also hides fixed-position controls. | app.js:1640-1652 | e2e: dialog containing a disclosure + focusable region, Tab sweep and assert activeElement stays inside | fixed |
| F2 | Destructive confirmations put initial focus on the confirm button: with no field, `firstField || #modal-confirm` focuses the destructive action. | app.js:1682, 1691 | e2e: delete-assistant confirm, read `document.activeElement` | fixed |
| F3 | Focus return relies on a long stack of `data-*` guesses and otherwise falls back to `#chat-prompt`; async re-renders can detach the trigger and silently move focus elsewhere. | app.js:1618-1665 | e2e: delete a schedule from the list, assert focus returns to that row action or a documented fallback | fixed (primitive stores exact element + connected check; call-site overrides preserved) |
| F4 | Nested dialogs are impossible: `openModal` replaces `#modal-root` innerHTML, so a dialog opened from an open dialog destroys its parent. | app.js:1594-1596, e.g. call site 3067 (edit saved request) | static: call chain 3038->3067; e2e open saved-request editor from its dialog | fixed (stacked native dialogs) |
| F5 | Drawer (A5) trap lists only `a, button, input, summary`; other focusables can escape. | app.js:2531-2548 | e2e: inject a `[tabindex]` control, Tab sweep | fixed via primitive layer |
| F6 | Server nav trap is link-only and the overlay has no dialog semantics, so assistive tech is not told the page is blocked. | hutch.js:204-215 | screen-reader tree inspection | deferred (nav landmark preserved; documented) |
| F7 | B1 menus do not set `aria-activedescendant`/roving tabindex consistently: `enhance()` sets `tabIndex=-1` and role only for its own selector; caller-built menus (model, roster) rely on their own markup. | controls.js:299-303, model-switcher.js:220+, app.js:1821-1825 | e2e: open each menu, Arrow/End, assert activeElement is an item | fixed in primitive |
| F8 | Popover focus return is skipped by the global outside-pointerdown path (`close(false)`), correct for pointer dismissal; keyboard dismissal (`Escape`) restores. No path restores focus after menu item navigation, which is correct for links but not for action buttons that stay on the page. | controls.js:75-85, 142-150 | e2e: click "Move to a section" item, assert focus lands in new dialog | fixed |

### 2.2 Dismissal defects

| ID | Gap | Evidence | Verify | Target status |
| --- | --- | --- | --- | --- |
| D1 | `confirmDialog` is dismissible by Escape and backdrop click even though it is destructive; the caller then proceeds as if the user declined, but the risk is accidental dismissal of a decision surface with no explicit choice. | app.js:1685-1695 + A1 backdrop/Escape handlers | e2e: open delete confirm, press Escape, assert it stays open unless marked dismissible | fixed (non-dismissible destructive dialogs) |
| D2 | Backdrop click closes every openModal dialog, including destructive and long form dialogs; behaviour differs from A3 (rect-check) and A4 (backdrop closes). | app.js:1672-1674 | e2e: backdrop press on form dialog and on destructive dialog | fixed (category rule: form dialogs dismissible, destructive not) |
| D3 | Server-page `data-confirm` forms use browser `window.confirm`; outside click/Escape semantics and copy are browser-owned and cannot be themed or tested. | hutch.js:41-45 | e2e: click delete on /models, assert a product modal opens | fixed |
| D4 | Two top-level handling paths disagree: needs-you intercepts `cancel` and closes manually, palette relies on native cancel, A1 uses a capture keydown. A single topmost rule does not exist; new overlays must guess. | app.js:7930-7938, palette.js:55,67, A1:1608 | static + e2e: Escape with popover inside modal closes only the popover (regression test exists) | fixed (one stack in primitive) |
| D5 | B1 outside pointerdown closes **all** live popups (reverse loop), not just descendants of the click, so a click on a second trigger can close panels that the new interaction did not otherwise dismiss. | controls.js:142-146 | e2e: two popovers open (menu + autocomplete), click second trigger | fixed (topmost-ancestor rule) |
| D6 | Mobile/SPA drawers close on Escape but have no topmost coordination with native dialogs or popovers open at the same time. | app.js:2519-2526, hutch.js:204-207 | e2e: drawer open + palette open, press Escape twice | fixed via shared Escape stack |

### 2.3 Positioning defects

| ID | Gap | Evidence | Verify | Target status |
| --- | --- | --- | --- | --- |
| P1 | Without the Popover API the panel stays inside its owner and is clipped by `overflow: hidden` ancestors; there is no body-portal fallback. This is a documented earlier decision (keep panels in owner) but the fallback path violates the clipping requirement. | controls.js:3-4, 21, 28-29; docs/design-system.md:76-78 | browser with `showPopover = undefined` + clipped ancestor fixture (test_action_menu_has_a_non_popover_api_fallback only covers an unclipped page) | fixed (body portal only in fallback; top-layer path preserves the documented no-portal rule) |
| P2 | Placement supports only `top`/`bottom` anchoring with a vertical flip and horizontal clamp; there is no left/right placement or full shift when both sides lack room, and the fallback max-height floor is 96px. | controls.js:48-74 | e2e: 320x480 with a 30-row menu at all four edges; assert bounds inside viewport | fixed (flip + shift in primitive; callers keep their preferred side) |
| P3 | The panel's width can exceed the viewport when `matchWidth` is false and a caller sets a fixed width (`.ms-menu` 348px, `.ms-all` dialog); narrow viewport relies on `maxWidth`. | controls.js:55-57, studio.css:812 | e2e: 320px width, open each menu, assert no horizontal overflow | fixed |
| P4 | Re-anchor listeners exist (resize, scroll capture, visualViewport) but panels in the top layer keep fixed coordinates while ancestors animate (drawer slide) - no re-anchor on transitionend/animationend. | controls.js:179-188 | e2e: open menu from a simulated animated ancestor, assert it tracks | deferred (no product trigger animates under an open popover) |
| P5 | Server-page native nav overlay is not anchored; no issue. Marketing drawer out of scope. | hutch.js:184+ | n/a | intentional |

### 2.4 State gaps

| ID | Gap | Evidence | Verify | Target status |
| --- | --- | --- | --- | --- |
| S1 | `openModal` has no busy/loading contract: every async dialog hand-rolls `confirm.disabled = true` (if it remembers), no `aria-busy`, no width stabilisation, and close/cancel stay live during the request. | app.js:1677-1681 and call sites (e.g. 823, 895, 2882) | e2e: slow onConfirm, double-click confirm, close during flight | fixed (factory busy state + disable) |
| S2 | Error surfacing is inconsistent: some dialogs write a local `#modal-error`/`role="status"` node, others toast outside the dialog and keep it open with no inline announcement. | app.js:823-830 vs 960; grep `modal-error` | e2e: force a 500 in a form dialog, assert `[role=alert]` inside dialog + dialog stays open | fixed (factory error slot, aria-live) |
| S3 | Success feedback is caller-dependent; several destructive flows close silently (only the toast, and toasts auto-dismiss). | app.js:3109-3117 vs 9208-9220 | e2e: revoke a share, assert visible confirmation | fixed (success announcement hook) |
| S4 | Action labels are mixed: "Delete request" (verb) is good, but "Done" as a close action and "Clear role" vs noun phrases appear; action order is consistent (cancel left) but danger is not visually separated. | app.js:3106, 8817, 1687 | static copy audit of every confirmText | fixed (copy + spec rule) |
| S5 | `confirmDialog` resolves before the destructive API call: the dialog closes and the loading/error path is invisible. | app.js:1685-1695 + call sites e.g. app.js:9208 | e2e: delete assistant, assert busy shutter + error path | fixed (confirm helper awaits action) |
| S6 | Async menu content has no loading state: model menu refresh after open paints over a stale list; palette conversation fetch uses a status line only. | model-switcher.js:100-105, palette.js:138-163 | e2e: throttle /v1/models, open menu | deferred (menu data is best-effort and already cached; status stays in palette) |
| S7 | Needs-you loading/error states are good (skeleton, role=alert, retry); no regression allowed. | app.js:7896, 8164 | e2e existing tests | intentional (preserve) |

### 2.5 Accessibility gaps

| ID | Gap | Evidence | Verify | Target status |
| --- | --- | --- | --- | --- |
| X1 | A1 dialogs have `aria-labelledby` but never `aria-describedby`; dialog descriptions are visual only. | app.js:1598 | DOM inspection on a dialog with a description | fixed |
| X2 | A2 confirm body is not linked as the description. | app.js:1691 | same | fixed |
| X3 | A background is not inert while A1 is open: the custom modal sets `aria-modal="true"` but the page stays in the tab order and the accessibility tree, and background scroll is unlocked. | app.js:1596-1610; style.css:1356-1381 | e2e: open dialog, Tab past last control, assert focus never leaves; wheel over backdrop, assert page scroll unchanged | fixed (native dialog + explicit inert fallback) |
| X4 | A5/A6 nav sheets expose no `aria-modal`/dialog role; screen readers are not told the page is blocked. | app.js:2500+, hutch.js:184+ | accessibility tree | deferred (structural nav landmark; behaviour trap preserved; documented) |
| X5 | No scroll lock for A1/A4/A5, so wheel/touch scroll moves the page under the modal and focus can scroll away. | style.css:1356+, app.js:1593 | e2e wheel/scroll test | fixed (scroll lock + scrollbar-width compensation) |
| X6 | Needs-you hint text is not referenced by `aria-describedby`; no token-driven backdrop. | index.html:159-160 | DOM inspection | fixed (attach layer adds describedby) |
| X7 | Icon-only close buttons are labelled in A1/A3, but popover close text is "Done" with an aria-label; no shared close-control contract or visual. | app.js:1601, controls.js:39-43 | static + screenshot | fixed (one shared close control) |
| X8 | Focus ring coverage is inconsistent: A1 buttons rely on the legacy global focus ring, popup rows have their own, roster items add another; no shared `--hutch-focus-ring` consumption in overlay CSS. | style.css:217, controls.css:46, style.css:1848, studio.css | e2e: Tab through every overlay control in both themes, assert `:focus-visible` outline | fixed |
| X9 | Popover panels are named by `aria-label` (often derived from the trigger) rather than `aria-labelledby`, and the trigger/panel relationship is only `aria-controls`. | controls.js:30-37, model-switcher.js:89 | DOM inspection | fixed |
| X10 | 320px and 200% zoom: A1 card `min(640px, 100%)` is fine, but fixed-width menus (348px) and the sheet rule are only partially covered; needs-you padding uses no safe-area inset. | studio.css:812, style.css:1855 | e2e at 320x740 and 200% zoom, assert no overflow and all controls reachable | fixed |
| X11 | Forced colors: only `.hc-popup` has a forced-colors block; modals, drawer and palette have none. | controls.css:88-92 | e2e forced_colors=active, assert borders/outlines visible | fixed |
| X12 | Reduced motion: modal-in/palette-in/drawer cover enter only; no overlay has exit motion, so there is no reduced-motion exit fallback to verify. | style.css:1371, 1419, studio.css:631-634 | e2e reduced_motion=reduce, assert open/close state changes instantly | fixed (enter/exit tokens collapse) |
| X13 | Screen readers are not explicitly told a custom div dialog opened; native dialogs are. | app.js:1596 | accessibility tree | fixed (native dialog) |

### 2.6 Stacking defects

| ID | Gap | Evidence | Verify | Target status |
| --- | --- | --- | --- | --- |
| Z1 | Hard-coded z-index: `160` (controls.css:32), `calc(var(--z-toast) + 5)` (style.css:1845, 703, 1186), `120` (hutch.css:336), `40` (skills.css:92). The documented scale is style.css:139-141 (`--z-rail:40; --z-sheet:45; --z-modal:50; --z-toast:60; --z-skip:70`). | as cited | grep overlay CSS for z-index after migration | fixed (z tokens only) |
| Z2 | Custom div modal (z 50) and native dialogs share no ordering: a native dialog opened while the custom modal is up sits in the top layer above it, even though the custom modal was opened later. Because the custom modal does not inert the page, a native dialog can be opened from behind it. | app.js:1596 + app.js:7925 + palette.js:173 | e2e: open form dialog, programmatically open needs-you, assert only topmost receives Escape/focus | fixed (all modals become native dialogs in one stack) |
| Z3 | Popover fallback z 160 is above the modal z 50, so a stale fallback popup floats over a later modal. | controls.css:32 | browser without showPopover + modal test | fixed (z tokens: popover below modal) |
| Z4 | Toast sits at z 60 above modal z 50 (correct order); roster menu at toast+5 (65) sits above toasts and modals - reverse of the intended hierarchy. | style.css:1845 | static z audit | fixed |

### 2.7 Consistency defects

| ID | Gap | Evidence | Verify | Target status |
| --- | --- | --- | --- | --- |
| C1 | Four close-control patterns: icon-btn x (A1), text "Done" button (B1 dialog), icon (A3), Esc hint (A4). | app.js:1601, controls.js:39-43, index.html:155, studio.css:642 | screenshots of all overlays | fixed (shared close contract; palette keeps its kbd hint) |
| C2 | Padding/radius/elevation diverge: modal 20/24 + sh-pop; popup 4/8/12 + popup-shadow; roster 4 + sh-pop; skills 8 + literal 0 12px 32px .4; palette 0/8. | style.css:1356-1381, controls.css:25-33, style.css:1845, skills.css:92-100, studio.css:626-659 | computed-style sampler | fixed |
| C3 | Danger action is not visually separated and sits next to Cancel; in A2 it is the default focus (F2). No divider or destructive-zone treatment. | app.js:1604-1607 | screenshot + Tab order | fixed (spec: cancel left, danger separated right, never default focus) |
| C4 | Motion differs: modal-in translate+scale, toast-in translate, palette-in, drawer transition; popovers have none; every one has no exit. | style.css:1371,1419, studio.css:631, style.css:1690 | reduced-motion e2e + frame inspection | fixed (motion tokens; enter/exit per category) |
| C5 | Modal title sizes/headers differ from popup headers; needs-you h2 is --fs-lg, popup header is font-weight 650, palette has no heading. | style.css:1376, controls.css:63, studio.css:626 | computed styles | fixed |
| C6 | A1 uses `aria-modal` div, A3/A4 native dialog, A5/A6 aside; three modal mechanics. | as cited | static | fixed for A1/A3/A4 (one primitive); A5/A6 intentional deferred |

### 2.7b Content defects found during inventory

| ID | Gap | Evidence | Verify | Target status |
| --- | --- | --- | --- | --- |
| C7 | Raw HTML inside a `title` tooltip renders as literal tags: `<code>{{ a.sticky_key }}</code>` and the plan label. | templates/_approval_card.html:60,63 | inspect rendered tooltip text; no `<code>` in the title attribute after fix | fixed |
| C8 | Six `data-confirm` forms have copy but no title, no verb label and no danger styling; the browser confirm gives OK/Cancel, not "Delete route"/"Remove key". | templates/base.html:61, models.html:159,542, bot.html:134, connections.html:39,54 | e2e: open each and read accessible name/action labels | fixed |

### 2.8 Theme defects

| ID | Gap | Evidence | Verify | Target status |
| --- | --- | --- | --- | --- |
| T1 | Overlay CSS does not consume the `--hutch-*` token layer; it uses legacy `--overlay`, `--sh-pop`, `--focus` and literal colours. A light theme scope exists in the token layer but never reaches shipped pages. | style.css:1356+, controls.css:25-33, studio.css:626+ | grep new overlay CSS for literals; set `data-hutch-theme="light"` and screenshot | fixed (tokens + light scope) |
| T2 | Scrim has four values: rgba(2,4,7,.72), rgba(0,0,0,.55) (x2), rgba(2,4,8,.6). | style.css:1359,1863; studio.css:632; style.css:458 | grep scrims | fixed |
| T3 | Shadows: `--popup-shadow: 0 12px 32px rgb(0 0 0/.45)` and literal `0 12px 32px rgb(0 0 0/.4)` bypass the elevation family. | controls.css:19, skills.css:96 | grep | fixed |
| T4 | Needs-you backdrop literal; no per-theme scrim token. | style.css:1863 | grep | fixed |
| T5 | Toast error border literal rgba(248,113,113,.55) (toast internals out of scope; overlay-triggered toast must use token if touched). | style.css:1414 | grep | deferred (toast internals out of scope) |

## 3. Intentional divergences preserved (do not flatten)

1. **Needs-you stays a right-side review drawer**, not a centred card. It is a modal by
   contract, a sheet by presentation; the primitive gains a `variant="sheet"` and the drawer
   keeps its bespoke content layout and 100dvh scrolling.
2. **Marketing site navigation dialog** stays outside the product overlay system. The public
   site deliberately does not load application popup JS or application menu roles
   (docs/design-system.md:68-72).
3. **Inline `<details>` disclosures** (FAQ, saved-request library, composer suggestions,
   template gallery) stay disclosures and are not converted into popovers/menus.
4. **Panels stay in their owning DOM when the native Popover API is available.** This is the
   approved dropdown direction (docs/design-system.md:74-80): the top layer escapes
   clipping without a body portal, and a popover opened from inside a modal stays inside
   that modal's focus world. A body portal is added **only** for browsers without the
   Popover API, where it is the only way to escape `overflow` clipping.
5. **Mobile rich panels become bottom sheets** (controls.js `place` sheet layout) rather
   than tiny anchored menus; this is a deliberate phone affordance and is kept.
6. **The roster action menu is manually portalled to body** by app.js (1826) so roster
   re-renders cannot orphan it; the primitive supports a pre-portalled panel and keeps it.
7. **Form dialogs focus the first field**, not the close button; only destructive dialogs
   move initial focus to a safe control. This asymmetry is intentional.
8. **Native browser tooltips (`title`)** remain the baseline for descriptive text; the
   tooltip primitive is progressive enhancement where it is worth the extra DOM, not a
   blanket replacement that would remove a working browser affordance.

## 4. Appendix: openModal and confirmDialog call sites

Open modal (`app.js` lines): 812, 917, 1048, 1136, 1687 (confirmDialog body), 1724, 1783,
1995, 2756, 2868, 2906, 2952, 3038, 3067, 3103, 3706, 3856, 4546, 5068, 5088, 5104, 5126,
5152, 5168, 5777, 5831, 6087, 6135, 8773, 8816, 8915, 8931, 8994, 9154, 9417, 10083, 10121,
10271, 11062, 11193, 11212, 11422, 11456, 13565, 13585, 14066.

Confirm dialogs (`confirmDialog(`): 9093 (remove scheduled task), 9208 (delete assistant),
10160, 10191, 10222, 10479, 10525, 10543, 10559, 10610, 10630, 10648, 10729, 10747, 10763,
10842, 10860, 10876, 10952 and the remaining revoke/disconnect variants in the same ranges.

Server-page `data-confirm` forms: `templates/base.html:61`, `templates/models.html:159,542`,
`templates/bot.html:134`, `templates/connections.html:39,54`.

## 5. Verification method for the whole pass

1. Static greps: no hard-coded `z-index` in overlay CSS; no colour literal in the new
   overlay sheet outside its documented fallback mirror.
2. Focused pytest: the token/design-system files touched by the token change.
3. Playwright e2e: existing `tests/e2e/test_dropdown_controls.py`,
   `tests/e2e/test_popup_layout.py`, `tests/e2e/test_wcag_fixes.py`,
   `tests/e2e/test_design_system.py`, `tests/e2e/test_hutch_select.py`,
   `tests/e2e/test_bot_deletion_ui.py`, `tests/e2e/test_fact_purge_ui.py` plus the new
   `tests/e2e/test_overlays.py` (every checklist item gets an assertion).
4. Local evidence run: `scripts/validate_overlays.py` boots the real app on loopback,
   exercises each overlay at 1440x960, 390x844, 320x740, phone landscape and 200% zoom,
   in both colour scopes and with reduced motion / forced colors, writes
   `docs/overlays/screenshots/<label>/{summary.json,assertions.txt,*.png}`.
5. Manual source review of the final diff for preserved handlers, form actions and data
   attributes.


## 6. Final status

Status at completion (2026-10-30). The target column above records the planned
status; this table is the audited outcome. Evidence lives in
docs/overlays/screenshots/working-tree (40/40 assertions) and the browser tests
in tests/e2e/test_overlays.py + test_overlay_layout.py (12 passed).

| Group | Fixed | Deferred | Intentional |
| --- | --- | --- | --- |
| Focus | F1, F2, F3, F4, F5, F7, F8 | F6 (nav landmarks) | - |
| Dismissal | D1, D2, D3, D4, D5, D6 | - | - |
| Positioning | P1, P2, P3 | P4 (animated ancestor) | P5 (nav overlay not anchored) |
| State | S1, S2, S3, S4, S5 | S6 (async menu loading) | S7 (needs-you states kept) |
| Accessibility | X1, X2, X3, X5, X6, X7, X8, X9, X10, X11, X12, X13 | X4 (nav drawer aria-modal) | - |
| Stacking | Z1, Z2, Z3, Z4 | - | - |
| Consistency | C1, C2, C3, C4, C5, C6, C7, C8 | - | - |
| Theme | T1, T2, T3, T4 | T5 (toast internals) | - |

Unverified items (see COMPLETION.md): real Safari/Firefox engines (not
installed), real Windows High Contrast (emulated), real browser zoom (200% root
font approximation), real touch hardware, and the full 13k-line test_browser.py
run (a 5-test modal/drawer subset passed).

Decision log kept intentionally:

1. Modal uses native dialog + showModal, not a custom trap. The custom div modal
   and its listener leak are removed.
2. Destructive confirmations trade outside-click convenience for safety: they
   are non-dismissible and never start on the destructive control.
3. Popovers keep the approved in-owner-DOM top-layer strategy and only portal in
   the no-Popover-API fallback, preserving docs/design-system.md:74-80.
4. Needs-you stays a right sheet; palette keeps its combobox anatomy; both are
   enhanced by the primitive rather than rebuilt as centred cards.
5. Navigation drawers keep their landmark markup; dialog semantics are deferred
   rather than changing the page's document structure in this pass.
6. The light colour scope is token-complete and verified in isolation; full-page
   activation is out of scope for this pass.

