# Overlay unification - completion

Status: complete for the audited product scope. Every blocking surface is a
**Modal** and every anchored surface is a **Popover/Dropdown/Tooltip** on one of
two primitives; deferred and unverified items are named at the bottom, not hidden.

## What shipped

| Layer | Artifact | Notes |
| --- | --- | --- |
| Token source | src/hutch/web/styles/hutch-tokens.css | z/scrim/elevation/motion/focus families added in place |
| Token slice | src/hutch/web/styles/hutch-overlay-tokens.css | split out at the 400-line budget; same namespace, one source of truth |
| Theme | src/hutch/web/styles/hutch-theme-overrides.css | light scope: scrim opacity 0.52, ink-alpha elevation |
| Shipped sheet | src/hutch/server/static/hutch-overlays.css | documented token mirror + modal primitive (server pages do not load ui.css) |
| Shipped sheet | src/hutch/server/static/hutch-popovers.css | popover/dropdown/tooltip primitives, native-review overrides, surface adoption |
| Runtime | static/hutch-overlay-{core,dialog,modal,popover,dismiss,tooltip}.js | one runtime for both shells; each file inside the 400-line budget |
| Markup | templates/macros/modal.html | modal() + confirm_form() (destructive forms) |
| Markup | templates/macros/popover.html | popover() + menu_item() for server-rendered panels |
| Spec | src/hutch/web/docs/overlays.md | elevation, scrim, motion, density, action placement, content, theme |
| Audit | docs/overlays/inventory.md, docs/overlays/audit.md | Step 1 and Step 2 deliverables |
| Harness | scripts/validate_overlays.py | boots the real app, writes committed evidence |
| Tests | tests/e2e/test_overlays.py, tests/e2e/test_overlay_layout.py | 12 browser contract tests |

### Native dialog vs custom implementation

The modal primitive uses the **native dialog element with showModal()**.
Chrome 37+, Safari 15.4+ and Firefox 98+ provide it; the browser owns the top
layer, modal focus containment, background inertness and Escape-on-topmost. The
runtime adds only what the element does not: initial focus, exact focus return,
backdrop policy, non-dismissible destructive confirmations, scroll lock with
scrollbar compensation, busy/error states and enter/exit motion. It replaces the
custom #modal-root div modal that previous code rolled by hand.

### Popover rendering strategy

Native popover top layer is used when available (Chrome 114+, Safari 17+,
Firefox 125+): the panel stays in its owning DOM, escapes overflow clipping and
remains inside an enclosing modal focus world. This preserves the approved
dropdown direction in docs/design-system.md:74-80. Without the API the panel is
portalled to document.body so an overflow:hidden ancestor cannot clip it; a panel
opened from inside a modal is never portalled there (the modal would make it
inert). The fallback path is covered by a test that stubs
HTMLElement.prototype.showPopover.

### z-index ordering (documented in both sheets)

base 0 < tooltip 42 < dropdown 44 < popover 46 < modal 50 < toast 60 < skip 70.
The gaps allow a category variant without renumbering neighbours; in the top
layer the browser owns order and the numbers are inert. No overlay stylesheet
declares a z-index literal.

## Migrated, by category

### 1. Destructive confirmations (highest risk first)

| Surface | Before | After |
| --- | --- | --- |
| data-confirm forms on server pages (6): stop-all, delete model route, reset price, disconnect ChatGPT, remove connection, delete assistant | Browser window.confirm, no title/verb/danger treatment | confirm_form macro -> non-dismissible modal, safe initial focus, verb labels, description, submit fallback works without JavaScript |
| confirmDialog() (29 call sites in app.js: schedules, assistants, credentials, calendar/mail grants, saved requests, fact shares, ...) | Custom div modal, dismissible by Escape/backdrop, initial focus on the destructive button | Primitive HutchOverlay.confirm, non-dismissible, initial focus Cancel, 120ms exit, exact focus return |
| app.js openModal with confirmClass danger | Same custom modal | Treated as destructive by the adapter: non-dismissible + safe focus |

Page-level deletion flows (bot_delete.html, fact purge) remain pages, not
overlays; their inline two-step confirmation is intentional and documented in
the inventory.

### 2. Form dialogs

All 45 openModal call sites keep their historical contract (title, body HTML,
async onConfirm that may return false, #modal-confirm, #modal-cancel,
#modal-close, .modal-card, .modal-body, .modal-footer, #modal-title) but now
render the primitive: native dialog, description support, explicit Tab cycle,
background scroll lock, busy state that disables every control and keeps label
width, inline role=alert error surface, success close, focus return through the
existing receipt/replaced-node fallbacks (moved to static/app-modal-focus.js to
keep the frozen bundle under its line cap).

### 3. Pickers, menus and popovers

controls.js is now a thin adapter over HutchOverlay.popover; every caller keeps
its API (hutchControls.popup({trigger, panel, kind, side, triggerKeys,
matchWidth, onOpen, onClose})) and its markup hooks. Upgraded families:

- model picker (.ms-menu, radio menu), roster action menu (portalled by app.js),
  assistant settings menu, conversation actions panel, fleet card menu,
  composer plus menu (dialog kind), skills picker (dialog kind, multi-select),
  datalist autocomplete (listbox), and the server-page disclosures.
- Flip + shift on all four edges, 8px viewport inset, re-anchor on window/
  container scroll and resize, topmost-only Escape, outside pointer/focus
  dismissal, menu Arrow/Home/End/typeahead, Tab closes and returns focus,
  one shared surface/radius/elevation/focus ring.

### 4. Tooltips

- New HutchOverlay.tooltip (role=tooltip, aria-describedby, pointer-events none,
  hover delay 420ms, focus immediate, Escape consumes while shown).
- Progressive enhancement of native title tooltips: the attribute is the
  accessible/no-JS fallback, temporarily removed while the themed bubble is up
  and restored on exit. This covers the 17 template tooltips plus programmatic
  titles without changing markup.
- No interactive tooltip existed; every current tooltip is descriptive on a
  focusable control, so none needed reclassification as a popover.
- Fixed a content defect: templates/_approval_card.html:60,63 no longer put raw
  code markup in a title attribute.

### 5. Remaining overlays

| Overlay | Result |
| --- | --- |
| Needs-you review drawer | Modal by contract, sheet by presentation: enhanced with the primitive (scroll lock, initial close focus, exact focus return, topmost Escape, token scrim) while keeping its 100dvh right-sheet anatomy and review layout |
| Command palette | Enhanced primitive wrapper: scroll lock, topmost Escape, focus return; keeps its combobox/listbox anatomy and 12vh position |
| SPA workspace drawer + server nav sheet | Already modal in behaviour (trap, Escape, focus return); now share the scroll lock, token scrim and z tokens. Their landmark aside/nav structure and the missing dialog semantics are deferred (see below) |
| Marketing nav dialog | Out of scope: separate editorial surface with no application popup JS (intentional) |

## Verification

### Commands and results

| Command | Result |
| --- | --- |
| python scripts/validate_overlays.py --label working-tree --light | **40/40 assertions pass**; 13 screenshots + summary.json + assertions.txt |
| pytest -q tests/e2e/test_overlays.py tests/e2e/test_overlay_layout.py | **12 passed** |
| pytest -q tests/e2e/test_dropdown_controls.py tests/e2e/test_popup_layout.py | **19 passed, 1 skipped** |
| pytest -q tests/e2e/test_browser.py -k "chatgpt_background_permission or opencode_coding_handoff or needs_you_drawer_preserves or bot_menu_downloads or multiple_scheduled_tasks" | **5 passed** |
| pytest -q tests/test_site_tokens.py tests/test_models_page.py | **24 passed** |
| pytest -q tests/e2e/test_design_system.py | 17 passed, 2 failed (pre-existing parked-work drift) |
| pytest -q tests/e2e/test_wcag_fixes.py tests/e2e/test_hutch_select.py tests/e2e/test_model_picker.py tests/e2e/test_studio_palette.py tests/e2e/test_bot_deletion_ui.py tests/e2e/test_fact_purge_ui.py | passed except the two pre-existing WCAG selector failures listed below |
| python scripts/audit_emoji.py | clean |
| python scripts/audit_context_hygiene.py | only the six pre-existing parked-file violations; no overlay file over budget |

### Edge-case checklist, item by item

**Focus and keyboard**

| Item | Status | Evidence |
| --- | --- | --- |
| Opening sets focus inside at the specified target | PASS | form-dialog first field, destructive initial focus Cancel, palette input, drawer close, menu first item |
| Tab cycles within the modal and cannot reach the background | PASS | explicit Tab cycle in the primitive; destructive dialog Tab loop |
| Escape closes only the topmost overlay | PASS | nested-dialog test; palette-refuses-over-drawer test |
| Closing returns focus to the trigger, including nested | PASS | dropdown, destructive confirm, nested dialog tests |
| Popover menus are arrow-key navigable; Home/End reach first/last | PASS | menu contract + browser tests |
| Every interactive control has a visible focus ring in both themes | PASS | shared --hutch-focus-ring; forced-colors uses Highlight; focus assertions in the existing WCAG suite |

**Dismissal**

| Item | Status | Evidence |
| --- | --- | --- |
| Backdrop click matches category and dismissible flag | PASS | destructive dialog ignores backdrop; dismissible dialogs behave per category |
| Destructive confirmations cannot be dismissed by outside click/Escape | PASS | server confirm + assistant delete tests |
| A popover closes on outside click and Escape, focus returns to trigger | PASS | dropdown contract test |

**Layout and positioning**

| Item | Status | Evidence |
| --- | --- | --- |
| Popovers flip near every viewport edge | PASS | test_overlay_layout (top/bottom/left/right anchored panels fit) |
| Stay attached on scroll and resize | PASS | inner-scroller re-anchor test; shared scroll/resize/visualViewport reposition path |
| Popovers inside a scroll container are not clipped | PASS | top-layer path plus fallback body portal test; existing native-dialog popup test |
| Long modals scroll internally without scrolling the page | PASS | long-review test: body scrolls, view scroll unchanged, wheel contained |
| 320px width and 200% zoom | PASS | 320x740 captures + 200% root text scenario (40/40 evidence) |
| Short viewports (laptop toolbar, phone landscape) | PASS | 844x390 + 1280x900 + 200% text |
| Two overlays stack in defined order; topmost owns focus/Escape | PASS | nested-dialog and palette-vs-drawer tests |

**States and async**

| Item | Status | Evidence |
| --- | --- | --- |
| Async dialog action shows loading, blocks double submit, keeps width | PASS | busy test: disabled + aria-busy, second click not delivered, min-inline-size held |
| Failed action shows inline role=alert error and keeps dialog open | PASS | primitive busy/error test |
| Successful action closes and produces visible confirmation | PASS | success close path + existing caller toasts/announcers preserved |
| Disabled controls cannot be triggered by keyboard or mouse | PASS | controls disabled in DOM while busy; Tab order skips them |

**Accessibility**

| Item | Status | Evidence |
| --- | --- | --- |
| Each dialog has an accessible name and a description when visible | PASS | aria-labelledby + aria-describedby asserted |
| Background inert to screen readers while open | PASS | native modal dialog; background not reachable by Tab/Escape or pointer |
| Icon-only close buttons have accessible names | PASS | "Close dialog", "Close <title>", "Close needs-you drawer" |
| Readable/operable in forced colors / high contrast | PASS | forced-colors scenario + explicit CanvasText borders and Highlight focus |
| Motion collapses under prefers-reduced-motion without losing state | PASS | 1ms durations, no travel; open/close state and focus still change |

**Theme**

| Item | Status | Evidence |
| --- | --- | --- |
| Scrim, elevation, focus ring render in light and dark | PASS (token scope) | 40/40 evidence includes light scope assertions; full-page light activation is a later step |
| No hard-coded colours or z-index in overlay CSS | PASS | only the documented token mirror declares literals; grep audit below |

**Repository checks**

- No HTML-snapshot or template-linting suite exists in this repo; the
  markup-pinning test that did exist (tests/test_models_page.py) was updated to
  the migrated confirmation markup and passes.
- Grep audit: no data-confirm remains in templates; no numeric z-index remains in
  overlay CSS; the legacy modal-backdrop/modal-card layout block is removed from
  style.css; only the shared close controls remain in the primitives
  (.hutch-modal__close, .hc-popup-close).
- npm run check:agent cannot pass in this checkout because its first gate is
  already failing on parked files (below); focused checks were run instead.

## Deferred

| Item | Why |
| --- | --- |
| Navigation drawer dialog semantics (A5/A6: role/aria-modal) | They are page landmarks (nav/aside) and the earlier pass pinned their structure; behaviour (trap, Escape, focus return, scroll lock, inert when closed) is preserved. Converting them to top-layer dialogs would change document semantics and is a separate review. |
| Async menu loading state (S6) | Model menu refresh is best-effort over cached data; palette already reports its loader. No overlay blocks on it. |
| Re-anchor during ancestor animation (P4) | No product trigger animates an ancestor under an open panel. |
| Toast internals (T5) | Toasts are explicitly out of scope for this pass; they now use the z/elevation tokens. |
| Marketing navigation dialog | Separate editorial surface, intentionally outside the product overlay system. |
| Full-page light-theme activation | Token scopes exist and are verified; activating data-hutch-theme belongs to a later theme step. |

## Unverified

| Item | Reason |
| --- | --- |
| Real Safari 16 / Firefox rendering | Only Chromium is installed in this checkout (WebKit revision missing); the no-Popover-API path is covered by stubbing. |
| Real Windows High Contrast | forced_colors="active" emulation only. |
| Real 200% browser zoom | Approximated with html font-size 200%; layout assertions pass. |
| Real touch devices | Pointer sizes/guard rails are token-based; no device pass. |
| Full tests/e2e/test_browser.py (13k lines) | Excluded by the repo quiet-verification rule; a 5-test modal/drawer subset passed. |
| Nested sheets / drag-to-dismiss | Explicitly out of scope for this pass. |

## Pre-existing failures in this checkout (not caused by this pass)

The tree carries another session's parked brand/dashboard work; these failures
predate the overlay work and reference parked files:

1. tests/e2e/test_radius_scale.py: .task-source uses border-radius 999px in
   untracked static/tasks.css.
2. tests/e2e/test_type_and_spacing_scale.py: 11px .models-hw-label and a 15px
   models heading from the parked models page/CSS.
3. Two test_wcag_fixes.py tests target the pre-restructure bot settings markup
   (no .settings container) and SPA setup selectors that the parked work moved.
4. Two test_design_system.py tests: the message-search control rename and a 40px
   persona-preview control from the parked persona work.
5. scripts/audit_context_hygiene.py: six violations in parked files
   (bot_deletion.py, cli.py, pages.py, store.py, test_bot_deletion.py,
   test_commit_attribution.py).

## Files touched (this pass)

New: docs/overlays/{inventory,audit,README,STATE,COMPLETION}.md,
docs/overlays/screenshots/working-tree/,
src/hutch/web/docs/overlays.md,
src/hutch/web/styles/hutch-overlay-tokens.css,
src/hutch/server/static/hutch-{overlays,popovers}.css,
src/hutch/server/static/hutch-overlay-{core,dialog,modal,popover,dismiss,tooltip}.js,
src/hutch/server/static/app-modal-focus.js,
src/hutch/server/templates/macros/{modal,popover}.html,
scripts/validate_overlays.py, tests/e2e/test_overlays.py,
tests/e2e/test_overlay_layout.py.

Modified: hutch-tokens.css, hutch-theme-overrides.css, app/src/input.css
(import only), templates/base.html, templates/models.html,
templates/connections.html, templates/bot.html, templates/_approval_card.html,
static/index.html, static/app.js (adapter only), static/controls.js (adapter),
static/hutch.js, static/palette.js, static/style.css, static/hutch.css,
static/skills.css, static/controls.css, docs/design-system.md,
tests/test_models_page.py, tests/e2e/test_dropdown_controls.py (form ancestor
selector for the parked field wrapper). Generated static/ui.css rebuilt.
