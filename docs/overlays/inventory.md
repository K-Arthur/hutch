# Overlay inventory and classification

Date: 2026-10-30. Baseline commit 548a2d6e plus the parked uncommitted design-system work
(163 modified/untracked paths) already in this checkout. Read-only audit; no source file
was modified before this document existed.

Scope: every overlay in the two shipped frontend shells and the design-system tree:

- SPA shell: `src/hutch/server/static/index.html` + `static/*.js` (app.js is 14,373
  lines / 958 KB; inspected by targeted grep and line ranges, never dumped).
- Server-rendered shell: `src/hutch/server/templates/**` + `static/hutch.js`,
  `static/controls.js`, `static/fact-purge.js`, `static/bot-deletion.js`,
  `static/hutch-select.js`, `static/composer.js`, `static/onboarding.js`.
- Design-system tree: `src/hutch/web/components/ui/{Modal,Menu,Tooltip}.tsx` and
  `src/hutch/web/preview/` (presentational prototypes; not yet wired to the product).
- Marketing site is a separate, deliberately self-contained surface; its native
  `<dialog>` navigation drawer is inventoried but intentionally out of scope (see
  "Intentional divergences").

## Method

1. Repo-wide grep for `<dialog`, `role="dialog"`, `aria-modal`, `aria-haspopup`,
   `aria-expanded`, `aria-controls`, `popover`, `popovertarget`, and class names
   containing modal/dialog/overlay/popover/dropdown/menu/sheet/drawer/toast/popup/
   confirm, in HTML, Jinja, CSS and JS.
2. Read the overlay factories end to end: `app.js:openModal` (1593), `app.js:confirmDialog`
   (1685), `controls.js:popup` (17), `app.js` needs-you (7825-7946), `palette.js`
   (1-201), `hutch.js:setOpen` (184-219), `app.js` workspace drawer (2500-2552).
3. Enumerate every `openModal(` / `confirmDialog(` call site in app.js and every
   `hutchControls.popup(` consumer.
4. Classify each overlay into exactly one category. Ambiguous cases are flagged with
   the chosen category and the reason; no category is silently converted during
   migration.

## Classification rules used

| Category | Definition applied |
| --- | --- |
| Modal | Blocks the page, requires an explicit action to dismiss, owns focus while open. Destructive confirmations, form dialogs, settings sheets, review drawers. |
| Popover | Anchored, non-blocking, dismissed by outside click or Escape; may contain controls. Pickers, rich panels, listboxes, form popovers. |
| Dropdown menu | A popover whose content is a list of actions or links. Uses menu semantics when all rows are actions. |
| Tooltip | Descriptive only, hover/focus triggered, never interactive, never blocks. |
| Toast / status | Transient status; not migrated in this pass except where an overlay action triggers one. |

## A. Modals

| # | Overlay | File / line | Trigger | Content | Dismissal (current) | Focus (current) | Render |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A1 | `openModal()` generic dialog factory, ~45 call sites (workflow amendment, run start, files, export, sections, rename, templates, saved requests, facts, coding/task handoffs, connections, model budgets, phone pairing, document preview/versions, watched source, ...) | `static/app.js:1593-1690`; call sites listed in the audit appendix | `openModal({...})` from app.js | Form or review body built as an HTML string; header/body/footer | Escape, backdrop mousedown, close, cancel, confirm; `onConfirm` may keep it open by returning false | Focus trap (manual Tab wrap), initial focus = first input else `#modal-confirm`, return focus = caller override or `document.activeElement`, with many data-attribute fallbacks | Inline `#modal-root` (custom div, not native dialog) |
| A2 | `confirmDialog()` destructive confirmations, ~30 call sites (delete assistant, remove schedule, revoke/disconnect Google/Microsoft/Notion/ChatGPT access, delete saved request, revoke fact share, archive fact, ...) | `static/app.js:1685-1695`; call sites in audit appendix | `await confirmDialog({...})` | One paragraph (`.confirm-body`) | Escape, backdrop, cancel, confirm | Same as A1; with no form field, initial focus lands on `#modal-confirm` - the destructive action | Inline `#modal-root` |
| A3 | Needs-you review drawer | `static/index.html:152-173`; logic `static/app.js:7825-7946` | `#needs-you-open` (sidebar) and palette entry | Approvals overview, filters, cards, receipts, browser-alert controls, history | Close button, Escape (cancel prevented then closed manually), backdrop click measured against the panel rect, link activation, `closedby="any"` | Native `<dialog>.showModal()`; initial focus = close button; explicit return-focus stack with visibility fallback | Inline native `<dialog>` |
| A4 | Command palette | `static/palette.js:1-201`; CSS `static/studio.css:626-659` | Ctrl/Cmd+K, or palette action | Combobox over a grouped listbox of destinations/actions | Escape (input handler + native cancel), backdrop click, selection | Native `<dialog>.showModal()`; input focused on open; explicit trigger focus restored on close | Inline native `<dialog>` appended to body |
| A5 | SPA workspace/navigation drawer | `static/index.html:50-114`; JS `static/app.js:2500-2552`; CSS `static/style.css:1681-1711` | `#nav-toggle` | Full sidebar (nav, roster, footer links) | `#ws-close`, `.ws-scrim` click, Escape, link selection | Manual Tab trap over links/buttons/inputs/summaries; initial focus = first link; focus returns to toggle; rail inert when closed | Inline `<aside>` + scrim div |
| A6 | Server-page app sidebar drawer (the same navigation surface as A5, server rendered) | `static/hutch-shell.css` (<=900px drawer rules); JS `static/hutch-shell.js`; markup `templates/macros/sidebar.html` | `#nav-toggle` | Full app sidebar: 12 navigation destinations, More disclosure, Apps & AI / Settings footer (no live roster) | `#ws-close`, scrim click, Escape; the scrim covers the header while open | Manual Tab trap over links/buttons/summaries; initial focus = first rail item; focus returns to the toggle; rail inert while closed | Inline `<aside id="workspace">` + scrim div |
| A7 | Destructive confirmation via native `window.confirm`, 6 forms | `static/hutch.js:41-45`; triggers `templates/base.html:61`, `models.html:159,542`, `bot.html:134`, `connections.html:39,54` | Any form with `data-confirm` (submit) | Browser confirm text | Browser-owned: Escape/Cancel cancels; outside click does not dismiss; no backdrop | Browser-owned; OK is the default button | Browser chrome (no DOM) |
| A8 | "Restored history" review dialog (uses A1) | `static/app.js:2756` | `#restore-report-open` and execution-hold banner | Restored-state review, confirm text "Close" | A1 | A1 | Inline |
| A9 | Document preview / versions dialogs (A1) | `static/app.js:13565,13585` | Document actions | Async body with `role="status"` loaders | A1 | A1 | Inline |
| A10 | Design-system `Modal` prototype (unwired) | `src/hutch/web/components/ui/Modal.tsx:1-172` | Owner-controlled `open` prop; no product trigger yet | Title, description, body, footer | Only close button and scrim click call `onClose`; Escape and the Tab trap are delegated to the incumbent `openModal` | No trap, no initial focus, no return focus in the prototype | React DOM node (no portal) |

Superseded 2026-10-30: A6 no longer describes a topbar overlay. The server top
navigation bar was removed; every full server page renders the shared app
sidebar and reuses the A5 interaction model. A7 is stale too - the
`data-confirm` submit path was replaced by the modal primitive's
`data-hutch-confirm-form`; this inventory is kept for provenance.

## B. Popovers, dropdown menus and tooltips

| # | Overlay | File / line | Trigger | Content | Dismissal (current) | Focus (current) | Render |
| --- | --- | --- | --- | --- | --- | --- | --- |
| B1 | Shared popup controller `hutchControls.popup()` | `static/controls.js:17-139` | Caller-provided trigger | Caller panel | Escape (top of `live` stack), outside pointerdown, focusin outside, Tab for menus, caller close | Initial focus = checked/selected control, else first focusable outside the injected header, else panel; focus return on explicit close; menu roving arrows/Home/End/typeahead | Inline in owner DOM; native popover top layer (`popover="manual"`) when supported, otherwise in-flow fixed panel |
| B2 | Roster action menu | `static/app.js:1814-1883`; CSS `static/style.css:1845-1849` | `[data-bot-options]` button | Actions: section, template, duplicate, settings, pin, hide | B1 | B1 | Portalled to `document.body` manually (`position:fixed`) |
| B3 | Model picker menu | `static/model-switcher.js:88-90, 220+`; CSS `static/studio.css:802-864` | `.ms-btn` | Grouped radio menu (quick picks, local, hosted, all models, save default) | B1 | B1 | Inline `.ms-wrap`; top layer when supported |
| B4 | Assistant settings menu | `static/app.js` (search `assistant-settings-menu`); CSS `style.css:699+` | summary/options button in assistant views | Actions menu | B1 | B1 | Inline `<details>` |
| B5 | Conversation actions panel | `static/app.js:3580-3620`; CSS `style.css:699-712`, `studio.css:502-504` | `#studio-conversation-options` | Action list + "more" disclosure | B1 | B1 | Inline `<details>` |
| B6 | Composer "+" menu | `static/app.js:4354-4356`; markup `app.js:3580`; CSS `style.css:935-998` | `#composer-menu-btn` | Mixed form popover: suggestions, role select, file/report/export actions | B1 | B1 | Inline `.cmenu-wrap`; top layer |
| B7 | Skills picker | `static/skills.js:434-523`; CSS `static/skills.css:91-108` | `.skill-picker-btn` (`aria-haspopup="dialog"`) | Search + multi-select checklist of bound skills | B1 | B1 | Inline `.skill-picker` |
| B8 | Fleet card action menu | `static/controls.js:194` selector `.fleet-card-menu` | `<details><summary>` | Action menu | B1 | B1 | Inline |
| B9 | Datalist autocomplete combobox | `static/controls.js:196-288` | `input[list]` | Progressively enhanced listbox of model routes | Escape, Tab, outside click, selection | DOM focus stays in input; arrows move `aria-activedescendant` | Inline next to the input |
| B10 | Native hover/focus tooltips | `title=` attributes across templates and app.js (e.g. `templates/_approval_card.html:11,15,60,63`, `templates/base.html:64,66`, `app.js:4500,5529,5561`) | Hover/focus | One descriptive sentence | Browser-owned | None (not focusable) | Browser chrome |
| B11 | Design-system `Menu` prototype (unwired) | `src/hutch/web/components/ui/Menu.tsx:1-184` | Owner-controlled props | Menu/action rows | Close on Escape? (prototype only; no document listeners) | No trap/return; roving tab index in prototype | React inline |
| B12 | Design-system `Tooltip` prototype (unwired) | `src/hutch/web/components/ui/Tooltip.tsx:1-176` | pointerenter/focus | Short label + shortcut keys | pointerleave/blur; Escape consumes while shown | `aria-describedby` wired to bubble id | React inline, absolutely positioned inside wrapper |

## C. Ambiguous cases and the category chosen

| Overlay | Tempting alternative | Chosen | Why |
| --- | --- | --- | --- |
| Needs-you drawer (A3) | Popover (outside click closes) | **Modal (sheet variant)** | It blocks the page behind it, is a native modal `<dialog>`, owns focus, and dismisses only by an explicit close/backdrop action. The drawer presentation (right-side sheet) is an intentional variant of the centred modal primitive, preserved. |
| Workspace / server nav drawers (A5, A6) | Popover (navigation disclosure) | **Modal (navigation sheet)** | They cover the page, trap focus, and require an explicit close action. They stay inline landmarks rather than being moved into `#modal-root`; that structural divergence is intentional (documented). |
| Composer "+" menu (B6) | Dropdown menu | **Popover (dialog variant)** | It contains a form control (role select) and nested disclosures, not just actions; menu semantics would break form navigation. Rows are not all `menuitem`s. |
| Skills picker (B7) | Modal (role="dialog" today) | **Popover (dialog variant)** | Non-blocking, outside click dismisses, no backdrop; the role must be `dialog` because of the search field and checkboxes, not because it blocks the page. |
| Conversation actions (B5) | Modal (popup kind is "dialog" today) | **Dropdown menu** if content is only actions/links; **Popover (dialog)** if it keeps a settings form | Resolved per panel content in the audit; the current implementation mixes action links with a "More" disclosure, so the split is recorded per surface. |
| Marketing nav drawer | Modal | **Out of scope, intentional** | The public site deliberately ships a native `<dialog>` navigation drawer with its own editorial composition and no application popup JS (docs/design-system.md:68-72). |
| `window.confirm` forms (A7) | Out of scope browser UI | **Destructive modal (must migrate)** | They are the platform's only destructive confirmations on server pages and are reachable from every server page; they are browser chrome, not a contract we can leave in place. |

## D. Non-overlays recorded to avoid re-auditing

| Thing | File | Why it is not an overlay |
| --- | --- | --- |
| Bot deletion page (two-step preview/typed confirmation) | `templates/bot_delete.html`, `static/bot-deletion.js` | A page-level danger-zone workflow, not an overlay. It is upstream of A2-style confirmation and must stay a page. |
| Fact purge panel | `templates/_fact_purge.html`, `static/fact-purge.js` | Inline two-step panel; no backdrop or focus trap. |
| Toasts | `static/app.js:1175-1202`, `#toast-root`, `style.css:1402-1419` | Transient status. Out of scope except that migrated overlays must trigger the existing toast/announcer on success. |
| Inline `<details>` disclosures (FAQ, template gallery, cmenu sub-sections, needs-you history) | templates + app.js | In-flow disclosures, not floating overlays; the primitive must not convert them. |
| `#attention-bar`, `#live-status`, execution-hold banner | index.html:132-145 | Status/inline disclosure surfaces. |

## D2. Template-audit corroboration (audit-templates report)

The Jinja surface ships **zero overlay markup**: all 40 templates contain no `<dialog>`,
`role="dialog"`, `aria-modal`, `popover`/`popovertarget`, and no modal/popover/menu classes;
`templates/base.html` never loads `static/app.js`, so the SPA's `openModal`/`confirmDialog`
do not exist on server pages. The only overlay families on that surface are A6 (nav drawer)
and A7 (`data-confirm` -> `window.confirm`). Seven native `<details>` disclosures are
ordinary in-flow disclosures, not menus. Twelve native `.hutch-select` pickers keep the
native popup by design (hutch-select.js only skins/enhances).

Content defect found while inventorying tooltips: `templates/_approval_card.html:60,63` put
raw HTML (`<code>{...}</code>`) inside `title=` attributes, so the browser tooltip shows
literal tags. Fixed by moving the detail into the visible label/description or plain text.

Dead or redirecting templates: `home.html`, `bots.html`, `bot_new.html`, `runs.html`,
`run.html` and `approvals.html` 302 into the SPA (pages.py:191-199, 246-270, 421-436,
539-541); `connections.html` renders only at `/legacy/connections`. Their overlays are
therefore out of migration scope, and the live destructive-confirm forms are base.html:61,
models.html:159,542, bot.html:134 and connections.html:39,54.

## E. Counts

- Modal instances via A1/A2: 40 `openModal(` call sites + 29 `confirmDialog(` call sites in app.js
  (line list in the audit appendix; some are helpers wrapping repeated flows).
- Native `<dialog>` instances: 2 product (`#needs-you`, palette) + 1 marketing.
- Popover consumers: 9 product families listed in section B (B1 is the controller; B2-B9 are
  consumers); 2 design-system prototypes.
- Tooltip implementations: native `title` attributes only (B10); no custom interactive
  tooltip exists in the product.
- Overlay CSS homes: `style.css`, `studio.css`, `controls.css`, `hutch.css`, `skills.css`,
  `model-switcher.css`, `onboarding*.css`; token source `src/hutch/web/styles/hutch-tokens.css`.
