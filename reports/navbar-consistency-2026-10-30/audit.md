# Navbar consistency audit - 2026-10-30

Status: audit complete, implementation in progress.
Scope: every top-level navigation surface that renders Hutch's application
chrome. Marketing site (navy sticky navbar) and the desktop startup splash are
separate product surfaces and are out of scope; the legacy/preview artifacts
under `src/hutch/server/static/redesign-preview.html` are not routes.

## 1. Where navigation is rendered or controlled

| File | Role |
|---|---|
| `src/hutch/server/templates/base.html` | Shared layout for **every** Jinja page. Renders `header.topbar`, `nav#primary-nav` (nine links from `NAV`), `#nav-toggle`, `#topbar-right` (Stop-all + live pill), skip link, footer. |
| `src/hutch/server/pages.py:37-47` | `NAV` - the single item list used by the server navbar (key, href, label, icon). |
| `src/hutch/server/static/index.html` | SPA app shell served at `/` and `/legacy`: `aside#workspace.workspace` sidebar (`.ws-brand`, `nav.ws-nav`, `.ws-roster`, `.ws-foot`), contextual header `header.app-top`, `#nav-toggle`, `#ws-scrim`. |
| `src/hutch/server/static/hutch.css:85-101,291-348` | Server navbar skin: `.topbar`, `.brand`, `.nav`, `.nav a.active`, `.topbar-right`, `.pill`; `@media (max-width:1024px)` full-screen overlay; `@media (max-width:720px)` wrapped topbar. |
| `src/hutch/server/static/hutch.js:183-226` | Server navbar behaviour: open/close overlay, inert, Escape, focus loop, resize. |
| `src/hutch/server/static/no-js-nav.css` | No-JS fallback: reveals `#primary-nav` inline below 1025px. |
| `src/hutch/server/static/responsive.css:173-181` | Publishes `--topbar-h` and sticky offsets; assumes a wrapping server topbar. |
| `src/hutch/server/static/responsive.js:30-45` | Measures `.topbar` height into `--topbar-h`. |
| `src/hutch/server/static/style.css:231-471` | SPA shell: `.app-shell` grid, `.workspace`, `.ws-*`, `.app-top`, drawer rules at 900px. |
| `src/hutch/server/static/studio.css:368-461` | Parked-session visual layer over the SPA sidebar/header. |
| `src/hutch/server/static/app.js:2450-2547` (+ 2191-2199) | SPA sidebar drawer, dock/collapse, and `aria-current` active-route detection. |
| `src/hutch/server/static/brand.css` | Shared 22px Visor Hutch mark + Bricolage wordmark lockup for `.topbar .brand` and `.ws-brand .brand`. |
| `src/hutch/server/templates/_icons.html` | `icon(name, size)` SVG wrapper; all nav glyphs come from here on server pages. |

Routes that render the **server navbar** (full pages, `chrome` true, `nav` non-empty):
`/models`, `/usage`, `/bots/delete`, `/bots/{name}`, `/bots/{name}/delete`, `/legacy/connections`.
Routes that render the chrome with an **empty item set** (no active item):
`/login`, `/pair`, error pages (`/models` 404s etc).
Chrome-less: all `/onboarding*` pages (`chrome=False`), fragments, redirects.
The SPA sidebar renders only at `/` (and `/legacy`, same document).

Verdict on Step 1: the navbar is **shared, not duplicated per page**; every
server page extends `base.html`. The real duplication is **two navigation
surfaces for one app**: a nine-link horizontal navbar on standalone server pages
and a twelve-destination sidebar in the SPA shell.

## 2. Consistency matrix

### Server-rendered pages that show the navbar

All rows share the same `base.html` markup, so item set/controls/brand/
responsive/theme cells are only repeated where behaviour differs.

| Page (route + template) | Item set | Active-state treatment | Controls present | Control styling | Brand / logo | Responsive behaviour | Focus order & keyboard | Theme |
|---|---|---|---|---|---|---|---|---|
| `/models` - `models.html` | 9 links, order: Chats, Activity, Assistants, Work history, Needs you, Models, Usage, Apps & AI, Delete bot | `.active` class + `aria-current="page"` on Models; emerald text + 9% emerald wash; no weight/indicator | Stop-all confirm (form), live pill, menu toggle | `.btn danger small` from `hutch.css`; ad-hoc `.pill`; icon via `icon()` macro | `.brand` link `/`, 22px Visor Hutch SVG + `hutch` wordmark, `aria-label="hutch home"` | `<=1024px` full-screen overlay via `#nav-toggle`; `<=720px` topbar wraps to 2 rows (no-JS only, because the overlay hides it); nav is horizontally scrollable 1025-1439px with icons hidden | Skip link -> `#main`; tab: brand, 9 nav links (toggle injected before nav in DOM after brand), stop-all, live pill; overlay traps Tab, Escape closes, focus returns to toggle | Fixed dark only |
| `/usage` - `usage.html` | same | same, Usage active | same | same | same | same | same | same |
| `/bots/delete` - `bot_delete_pick.html` | same | same, **Delete bot** active (destructive destination promoted to top-level nav) | same | same | same | same | same | same |
| `/bots/{name}` - `bot.html` | same | same, Assistants active (nested route: correct) | same | same | same | same | same | same |
| `/bots/{name}/delete` - `bot_delete.html` | same | same, Delete bot active (nested route: correct) | same | same | same | same | same | same |
| `/legacy/connections` - `connections.html` | same | same, Apps & AI active | same | same | same | same | same | same |
| `/login` - `login.html` | none (no `nav`) | no item active (pre-auth page) | Stop-all + live pill still shown | ad-hoc | brand only | navbar area empty, topbar 54px | skip -> brand -> stop-all -> content | Fixed dark |
| `/pair` - `pair.html` | none | none | Stop-all + live pill still shown | ad-hoc | brand only | same | same | Fixed dark |
| error pages - `error.html` | none | none | Stop-all + live pill | ad-hoc | brand only | same | same | Fixed dark |

### SPA app shell at `/` (sidebar is the app's primary navigation)

| Page (route + template) | Item set | Active-state treatment | Controls present | Control styling | Brand / logo | Responsive behaviour | Focus order & keyboard | Theme |
|---|---|---|---|---|---|---|---|---|
| `/` (and `/legacy`) - `static/index.html` + `app.js` | Primary: Chat, Tasks, Needs you (+badge). "More" disclosure: Conversation history, Activity, Scheduled work, Work history, Runtime, Skills, Models, Usage, Manage assistants. Footer: Apps & AI, Settings | JS sets `aria-current="page"` on the matching `.ws-nav a[data-nav]` (`app.js:2191-2199`); CSS = white text + 8% white wash + emerald icon; no weight/indicator | Search (Ctrl K), sidebar collapse, close (drawer), New assistant, roster search + roster rows, contextual header (title/status/daemon pill) | SPA primitives (`icon-btn`, `.btn` from ui.css, `.ws-*` classes) | `.brand` link `#/chat`, 22px mark + wordmark, `aria-label="hutch - open main chat"` | `<=900px` left drawer plus labelled toggle in contextual header (`app.js:2450-2500`); `>=901px` persistent 304px rail; collapse to 64px icon rail | Skip `.skip-link` -> `main#view[tabindex=-1]`; drawer: focus first link, Tab trap, Escape closes + returns focus, scrim click closes | Fixed dark only |

## 3. Inconsistency list (grouped)

Status legend: **fix** = change in this pass, **intentional** = deliberate
difference preserved, **deferred** = real but out of this pass' safe scope.

### Duplication
- **D1 (fix).** Two complete navigation surfaces for one app: `base.html:57-80`
  topbar navbar vs `static/index.html:56-115` sidebar. Same destinations are
  expressed twice with different labels/order/styling. Fix: make the sidebar the
  one primary navigation and render it from one shared server macro on every
  full page; delete the topbar navbar.
- **D2 (fix).** `pages.py:37-47` `NAV` is an independent item list with no
  shared source or drift test against the SPA sidebar (index.html). Fix: move the
  nav model into `src/hutch/server/nav.py`, render it through
  `templates/macros/sidebar.html`, and add a test that parses the SPA sidebar and
  fails when item order/labels/hrefs drift.
- **D3 (fix).** Nav skin duplicated: `.topbar/.nav` in `hutch.css:85-101,327-348`
  vs `.ws-nav` in `style.css:265-295`/`studio.css:387-401`. Fix: one
  `static/hutch-nav.css` loaded by both shells defines the nav row/active/footer
  component from semantic tokens; delete the old server navbar CSS.
- **D4 (intentional).** Marketing navbar (`website/index.html`) and desktop
  startup splash are different products/surfaces; not merged.

### Item-set drift
- **I1 (fix).** Server navbar omits Tasks, Conversation history, Scheduled work,
  Runtime, Skills and Settings, all primary destinations in the SPA sidebar.
- **I2 (fix).** Server navbar promotes **Delete bot** to a top-level destination.
  `bot_delete_pick.html` is a destructive settings page; it is not primary
  navigation (design-system: deletion must not compete with ordinary navigation).
- **I3 (fix).** Labels differ for the same destination: "Chats" vs "Chat",
  "Assistants" vs "Manage assistants". Order differs: "Needs you" is 5th in the
  navbar but second in the sidebar; "Apps & AI" is in the bar on server pages and
  in the footer on the SPA.
- **I4 (intentional).** Server pages expose no assistant roster, search palette or
  collapse control: those need live SPA state/handlers. They keep the same
  navigation rows and footer links.

### Active-state drift
- **A1 (fix).** Same page shows its current destination differently between
  surfaces: server = emerald text + emerald wash; SPA = white text + neutral wash
  + emerald icon. Canonical treatment: `aria-current="page"` + 600 weight + 3px
  emerald indicator + neutral wash, in the shared nav sheet, so it is not
  colour-only.
- **A2 (fix).** `aria-current` is present on server pages but the active *look*
  depends on a parallel `.active` class (`base.html:64`) that can drift from
  `aria-current`; keep one source: the class is gone, `[aria-current="page"]` is
  the only selector.
- **A3 (fix).** Nested routes are correct today for `/bots/{name}` (Assistants)
  and `/bots/{name}/delete` (Delete bot) because `pages.py` passes `nav`; the new
  model keeps explicit keys and adds tests for nested routes (`/models?price=1#prices`
  keeps Models active; `/bots/{name}/delete` keeps Manage assistants active).
- **A4 (intentional).** `/login`, `/pair`, error pages and `/onboarding*` have no
  active destination; they are not app destinations. Pre-auth pages keep no
  primary navigation at all (see R5).
- **A5 (fix, SPA).** Deep hash routes keep their parent journal active today
  (`schedules/runs` etc. share a `data-nav`); run detail `#/run/{id}` sets
  `runs` active. Verified by `tests/e2e/test_browser.py` and kept unchanged; the
  shared sheet must not break the collapsed-rail override.

### Control drift
- **C1 (fix).** Brand accessible name differs: server "hutch home" vs SPA
  "hutch - open main chat". Canonical: server `aria-label="hutch - open main chat"`,
  both link to the workspace home.
- **C2 (fix).** Navber icon-only toggle is 38px (`hutch.css:328-329`) vs the
  SPA 44px phone standard and `DESIGN.md` 44px floor; fix to 44px at coarse
  pointers/phones in the shell sheet.
- **C3 (intentional, deferred).** Stop-all keeps `.btn danger small` +
  confirm_form primitive and the live pill keeps the shared `.pill`; both are
  utility controls wired to existing handlers, not primary navigation. The SPA
  button/select/icon primitives are compiled from ui.css and not loaded on server
  pages; converting the server page button tier is a separate pass (button
  primitive). No select/workspace selector exists in either navbar, so there is
  nothing to consume the select primitive from.
- **C4 (fix).** `.nav a.active` uses hard-coded `rgba(52, 211, 153, .09)` and
  `.nav-toggle[aria-expanded]` uses `rgba(...,.42)`; the new nav/shell sheets use
  semantic tokens only.

### Responsive defects
- **R1 (fix).** Two different navigation models on the same device: server navbar
  collapses to a full-screen overlay at `<=1024px`; the SPA sidebar becomes a
  drawer at `<=900px`. One strategy: sidebar drawer + labelled toggle at
  `<=900px` on every page.
- **R2 (fix).** Server topbar height jumps: 54px at wide widths, auto/wrapped
  (2 rows) at `<=720px` without JS; the SPA header is a stable 56px. New shell:
  fixed 56px contextual header on every page, no wrapping.
- **R3 (fix).** Server navbar's nine links are horizontally scrollable with
  hidden scrollbar between 1025px and 1439px (`hutch.css:90-94` + responsive
  task 02 tradeoff) - overflow with no affordance. A sidebar has no such state.
- **R4 (fix).** No-JS fallback reveals an inline wrapped navbar under the topbar;
  the new fallback keeps the sidebar navigation visible inline above content, so
  every destination remains reachable without JavaScript.
- **R5 (fix).** Pre-auth pages (`/login`, `/pair`) render Stop-all + live pill
  from the app chrome; navigation/utility controls are irrelevant before sign-in.
  Mark them chrome-less like onboarding (`chrome=False`), preserving their layout.

### Accessibility defects
- **X1 (fix).** Server skip link targets `#main` but `<main>` is not focusable,
  so focus is not moved past the bar; the SPA target has `tabindex="-1"`. Add
  `tabindex="-1"` to the server `main`.
- **X2 (fix).** The active item relies on colour-only in both shells; fixed by
  A1 (weight + 3px indicator + aria-current).
- **X3 (fix).** Server nav overlay's first Tab stop ordering: DOM places
  `#nav-toggle` after the nav despite being the trigger (visual position is
  left). New shell orders toggle -> brand/close -> nav rows, and the shared drawer
  JS returns focus to the toggle and traps Tab (mirrors `app.js:2485-2498`).
- **X4 (fix).** Server navbar links do not mark the current page with
  `aria-current="page"`? They do today and keep doing so; the new nav keeps one
  attribute and adds tests. (Verified as correct; kept.)
- **X5 (fix).** Overlay trigger had `aria-controls="primary-nav"`; the new
  drawer is `aria-controls="workspace"` + `aria-expanded`, matching the SPA.
- **X6 (intentional).** SPA "More" uses a native `<details>` disclosure
  (keyboard-operable, no custom JS); the server sidebar reuses the same
  `<details>` so keyboard behaviour matches without new JS.
- **X7 (fix).** Dock/collapse is SPA-only and hidden from the server shell; no
  keyboard trap is introduced.

### Theme defects
- **T1 (fix).** Hard-coded nav colours (see C4) and `.brand`/topbar values that
  bypass semantic tokens; new sheets consume `--color-semantic-*`, `--radius-*`,
  `--motion-*` from `brand-tokens.css` (loaded by both shells).
- **T2 (intentional).** Hutch ships a fixed dark theme
  (`docs/design-system.md`: "Hutch intentionally ships a fixed dark theme"); the
  generic light/dark matrix column is N/A. Both shells declare
  `color-scheme: dark`; no light palette is claimed or added.

## 4. Is the navbar necessary? (decision)

No - not as a second primary navigation surface. The app already owns a
sidebar that is richer, always reachable inside the workspace, and is the
documented shared shell for Chats, Apps & AI, Models, Usage and settings
(`docs/design-system.md` "Apps, activity, and settings"). The nine-link topbar
duplicated a subset of it with different labels/order, made standalone pages
look like a different product, and forced a second responsive model.

Decision: **one navigation surface = the app sidebar.**

- Render that sidebar server-side from `templates/macros/sidebar.html` (one
  item model in `src/hutch/server/nav.py`) on every full server page.
- Keep a slim, fixed-height **contextual header** for controls the page owns:
  drawer toggle, Stop-all, live status. This replaces the navbar row; it is not
  primary navigation.
- Delete the topbar navbar markup, its CSS, its JS and `no-js-nav.css`.
- Preserve every route path and handler. Nav destinations point at the same
  destinations the app sidebar uses; old server routes (`/overview`, `/bots`,
  `/runs`, `/approvals`, `/connections`) stay valid redirects.
- Intentional differences: no roster/search/collapse in the server-rendered
  sidebar (needs live SPA state; deferred until those pages move inside the
  shell); marketing and desktop splash untouched.

## 5. Verification plan

- Template/route: focused pytest for pages, onboarding chrome-less assertion,
  token guard, plus a new nav-parity test (server nav model vs SPA sidebar DOM).
- Browser: `/models`, `/usage`, `/bots/delete`, `/bots/{name}`,
  `/bots/{name}/delete`, `/legacy/connections`, `/login`, `/pair`, `/` at
  1440x900, 1366x1024, 1180x820, 1024x768, 900x1024, 768x1024, 390x844,
  320x720: no horizontal overflow, 56px header on every route, one drawer
  strategy <=900px, active item has `aria-current="page"`, drawer Escape/focus
  return, no console errors.
- Grep gate: no `#primary-nav` topbar, `.nav-toggle` overlay CSS, `.nav a`
  server rules, or `no-js-nav.css` references left behind.
- `npm run check:agent` / site-token guard after CSS changes.

## 6. What was implemented

Decision executed: the sidebar is the one primary navigation surface; the
topbar navbar was deleted.

| File | Change |
|---|---|
| `src/hutch/server/nav.py` (new) | One item model: primary rows (Chat, Tasks, Needs you), the More disclosure (9 rows), footer rows (Apps & AI, Settings); `normalize()` maps page keys (`deletion` -> `bots`, `connections` stays) and `more_open()` decides the disclosure state. |
| `src/hutch/server/templates/macros/sidebar.html` (new) | The one server-rendered sidebar: brand lockup, primary rows, More disclosure, footer links, approval badge. Emits the same classes/ids/`data-nav` as the SPA sidebar; every icon comes through `icon()`. |
| `src/hutch/server/templates/base.html` | Renders the sidebar shell on every full page, then a fixed 56px contextual header (drawer toggle, Stop all, live status), flash region, focusable `main#main[tabindex=-1]`, footer. Chrome-less pages (`chrome=False`) keep the bare layout. |
| `src/hutch/server/pages.py` | Feeds `nav_active`/nav groups into the template; `login`+ `pair` are chrome-less; item list moved out to `nav.py`. The plain-form reader moved to `forms.py` so the frozen file shrank 744 -> 719 lines. |
| `src/hutch/server/static/hutch-nav.css` (new) | One navigation component sheet for **both** shells (loaded last by `index.html` and `base.html`): row metrics, hover, `[aria-current="page"]` = text + weight 600 + 3px brand inset rail + neutral wash + brand icon, footer pills, badge, focus, coarse-pointer 44px, forced-colors, reduced motion. Semantic tokens only. |
| `src/hutch/server/static/hutch-shell.css` (new) | Server app shell: 304px sticky rail, 56px sticky `.app-top`, <=900px drawer + scrim with the SPA's layer order (drawer 50 > scrim 46 > header 2 > page), stable header height, scroll/focus offsets, sidebar surface derived from `--color-semantic-bg` (DESIGN.md `surface-sidebar` #070709). |
| `src/hutch/server/static/hutch-shell.js` (new) | Server drawer: labelled toggle, scrim, inertness while closed, Tab containment, Escape, focus return; mirrors `app.js`'s `openWorkspace/closeWorkspace`. |
| `src/hutch/server/static/hutch.css` | Deleted the topbar/navbar skin, wrapped-topbar rules, overlay-nav rules and hard-coded nav colours; run-header/scroll offsets now use `--app-top-h`. |
| `src/hutch/server/static/hutch.js` | Deleted the old overlay-nav IIFE. |
| `src/hutch/server/static/no-js-nav.css` | Rewritten: without JavaScript the rail becomes an inline navigation list (closed More rows still visible), every destination reachable, no overflow. |
| `src/hutch/server/static/responsive.css` | Removed topbar/wrapped-topbar and 1024px nav-model rules; sticky offsets use `var(--app-top-h, 56px)`. |
| `src/hutch/server/static/index.html` + `app.js` | SPA loads the shared nav sheet; missing `data-nav` hooks added for Models/Usage; active-state loop now includes footer links and opens More for nested routes (chats/skills etc.). |
| `src/hutch/server/static/brand.css`, `hutch-popovers.css` | Removed dead `.topbar` / old overlay-nav selectors. |
| `src/hutch/server/templates/_icons.html` | Added `checklist`, `settings`, `more` icons for the shared sidebar rows. |
| `src/hutch/server/templates/bot.html` | The deletion picker (previously a destructive primary-nav row) is linked from the assistant danger zone instead. |
| `tests/test_navbar_consistency.py` (new) | Parses the SPA sidebar and fails on label/order/href/row drift; renders every chrome route and asserts exactly one `aria-current` with the right destination, no `.active`, no topbar, focusable skip target. |
| `tests/test_models_page.py` | Active assertion uses `aria-current="page"` instead of the removed `.active` class. |
| `tests/e2e/test_browser.py` | Server navigation e2e rewritten for the sidebar: 304px rail >900px, labelled drawer <=900px, active Usage, Tab trap/Escape/focus return, 56px header, no-JS reachability on /usage and /legacy/connections, text-spacing, forced-colors, reduced motion. |
| `tests/e2e/test_bot_deletion_ui.py` | Deletion discovery test now uses the assistant danger-zone link (primary nav has no destructive row). |
| `tests/test_site_tokens.py` | Token guard now checks the server nav/shell sheets too. |
| `docs/design-system.md`, `docs/responsive/tasks/02-*.md`, `docs/responsive/README.md`, `docs/overlays/inventory.md` | Document the single navigation surface, the permanent contextual header, the 900px drawer, the no-JS fallback and the superseded topbar overlay. |

## 7. Verification evidence

- Matrix/template tests: `tests/test_navbar_consistency.py` (4) +
  `tests/test_models_page.py` + `tests/test_onboarding_page.py` +
  `tests/test_site_tokens.py` + `tests/test_studio_markdown.py` +
  `tests/test_outputs_integration.py` + `tests/test_widgets_static.py`:
  **96 passed, 1 skipped**. Independent auditor run of 12 focused files:
  **137 passed / 0 failed**.
- Browser e2e: `test_server_page_navigation_uses_the_shared_sidebar`
  (**passed**), `test_assistant_danger_zone_links_to_the_deletion_picker`
  (**passed**); affected suites (deletion UI, WCAG fixes, radius scale) run in
  `e2e-affected.log`.
- Measured in Chromium against the real app: rail 304px, sticky `.app-top` 56px
  on /models, /usage, /bots/delete, /legacy/connections; active row computed
  `box-shadow: rgb(52,211,153) 3px 0 0 inset`, weight 600, `aria-current="page"`;
  drawer z 50 / scrim 46 / header 1 (header not clickable behind the drawer,
  drawer brand+Close on top, modal above the rail); at 390px closed drawer is
  inert with 0 horizontal overflow; no-JS shows all 12 destinations at
  390/768/900 with 0 overflow; no console or page errors.
- Gates: emoji clean; tool contracts pass; constitution passes; agent map
  regenerated and passes; context hygiene shows only 5 pre-existing parked-tree
  violations (bot_deletion.py, cli.py, store.py, two test files) - the
  pages.py and test_browser.py violations this change would have added are gone
  (pages.py 744 -> 719; test_browser.py at its frozen budget).
- Evidence directories: `reports/navbar-consistency-2026-10-30/`
  (`audit-rows.md`, `test-impact.md`, `review.md`, `post/`, `baseline/`,
  `e2e-affected.log`, `final-focused.log`).

### Final verification numbers

- Cross-page matrix (`post/matrix.md`, `post/matrix.json`): **72 cells**
  (9 pages x 8 viewports: /, /models, /usage, /bots/delete,
  /legacy/connections, /login, /pair, /bots/nav-bot,
  /bots/nav-bot/delete), **0 failures**. Server chrome pages: header 56px, rail
  304px docked >900px, off-canvas inert drawer <=900px that opens from the
  labelled toggle, one `aria-current="page"` with the expected label, 0
  horizontal overflow, drawer Escape returns focus. The SPA "/" keeps its own
  contextual header that wraps to 86-90px at <=900px (pre-existing SPA
  behaviour, not a navigation surface; the sidebar/drawer matches).
- Independent capture (`post/capture.json`, `post/summary.md`): 72 cells +
  2 no-JS cells, 172 screenshots, **12/12 checks PASS**, 0 console/page/HTTP
  errors.
- Final focused gate: 98 passed / 1 skipped, including
  `tests/test_navbar_consistency.py` (4), `test_models_page.py`,
  `test_onboarding_page.py`, token/static guards, the rewritten server-sidebar
  e2e and the deletion-discovery e2e.
- `tests/e2e/test_bot_deletion_ui.py` + `test_wcag_fixes.py` +
  `test_radius_scale.py`: 22 passed, 3 failed - all three are **pre-existing
  parked-tree drift, not this change**: `test_wcag_fixes` expects a
  `.settings` wrapper that the parked `bot.html` template removed (HEAD
  `bot.html:67` had `class="settings"`, worktree has none), and
  `test_radius_scale` flags a `999px` literal in the parked, untracked
  `static/tasks.css:11`. Neither file's failure path touches the new shell.
- `node --check` passes for `hutch.js`, `hutch-shell.js`, `responsive.js`;
  emoji clean; tool contracts + constitution pass; agent map regenerated and
  passes; token guard now scans the new server sheets and passes.


## 8. Status ledger (fixed / intentional / deferred)

| ID | Status | What was done |
|---|---|---|
| D1, D3 | fixed | Topbar navbar markup, CSS, JS and no-JS sheet deleted; one sidebar macro + one nav sheet serve both shells. |
| D2 | fixed | Single item model in `nav.py`; parity test fails on drift. |
| D4 | intentional | Marketing navbar and desktop splash stay separate products. |
| I1, I2, I3 | fixed | Server nav now equals the SPA sidebar (12 destinations + 2 footer); destructive Delete-bot row removed, deletion linked from the assistant danger zone. |
| I4 | intentional | Server sidebar omits roster/search/collapse/new-assistant (needs live SPA state/handlers); documented in design-system.md. |
| A1, A2, A3, A5 | fixed | One non-colour-only active treatment; `aria-current` is the only active selector; nested routes tested; SPA footer/nested active state fixed. |
| A4 | intentional | Login/pair chrome-less; error pages have no active destination. |
| C1, C2, C4 | fixed | Brand name matches the SPA, drawer toggle 44px on coarse pointers, nav colours token-only. |
| C3 | intentional/deferred | Stop-all keeps the server button tier + confirm_form; no select/bot selector exists in either navbar to consume. |
| R1-R5 | fixed | One 900px drawer strategy; stable 56px header; no scrolling/hidden nav; no-JS inline fallback; pre-auth pages chrome-less. |
| X1-X7 | fixed | Focusable `main`, non-colour active state, drawer focus order/trap/Escape, `aria-controls`/names, native More disclosure, no dock trap. |
| T1, T2 | fixed / intentional | Token-only nav/shell CSS; Hutch stays a fixed dark theme by design (no light palette claimed). |
| F1/F2 (review) | fixed | Drawer/scrim layer above the header; rail/header no longer above overlay layers. |
| F3 (review) | deferred, intentional | Two drawer implementations remain (`app.js` for the SPA, `hutch-shell.js` for server pages) because the SPA shell is parked/uncommitted work; both follow the same interaction contract and are covered by the shared e2e model. |
| F5 (review) | intentional | Server "Needs you" is a link into the app's approvals alias; the SPA keeps its in-place drawer button (capability difference, same destination). |
| F6 (review) | deferred | `page()` does not hard-fail a future chrome page that forgets `nav=`; the parity test pins today's routes. |
| Responsive harness (`scripts/responsive/*`) | deferred | Still asserts the removed topbar; documented at the top of docs/responsive/README.md so a harness run is not mistaken for current evidence. |

## 9. Not reproducible / untouched

- The premise "different pages render different navbars" is not reproducible in
  this tree: all server pages already extended `base.html`. The real divergence
  was the second navigation surface (topbar vs sidebar) and the two responsive
  models - both fixed here.
- `desktop/web/index.html` is the Tauri startup splash and has no navigation;
  untouched. The marketing navbar and `static/redesign-preview.html` are separate
  surfaces/artifacts and are out of scope.
- Light-theme defects are not reproducible: Hutch intentionally ships a fixed
  dark theme (`docs/design-system.md`); no light palette was added.
- No bot/workspace selector exists in either navbar, so there was no select
  primitive to consume; nothing was invented.
- The parked session's uncommitted shell/SPA work was preserved; this change
  only added to it (one CSS link, `data-nav` hooks, two active-state lines) and
  did not revert or reformat unrelated edits.

