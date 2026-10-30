# Hutch navbar consistency audit — SPA sidebar vs server-page topbar

Read-only audit. Date: 2026-10-30. Repo: /home/kevina/CodingProjects/hutch (working tree). Scope: exactly the two navigation surfaces named in task-1. Generated CSS (ui.css, model-switcher.css) and lockfiles were not read; app/src/input.css is cited only through its source. No source file was modified; this file is the only artifact written.

Working-tree caveat: git status shows uncommitted parked-session work in `src/hutch/server/static/index.html`, `style.css`, `studio.css`, `app.js`, `hutch.css`, `hutch.js` and `templates/base.html` (all "M"). Every citation below is to the *working-tree* content, i.e. the shell that is actually served today; the parked diff must not be touched. `reports/` itself is untracked.

---

## A. Canonical SPA app-shell sidebar spec (served at `/` and `/legacy`)

Surface: `src/hutch/server/static/index.html` (205 lines), styles `style.css` + `studio.css` + `responsive.css` (loaded last, index.html:44), behaviour `app.js`, palette text `palette.js`. `/` and `/legacy` both return this file (pages.py:191-195, 179-184), so the SPA shell is a FileResponse, never Jinja chrome.

### A.1 DOM order of the sidebar (`aside#workspace`, index.html:56-115)

| # | Group | Label | href / action | data-nav | Icon source |
|---|-------|-------|---------------|----------|-------------|
| 1 | brand | "hutch" mark+wordmark | `#/chat` | — | inline SVG, fill `var(--brand)` (index.html:59-60) |
| 2 | utility | Search button `#ws-search` | opens palette | — | inline SVG (index.html:63-65) |
| 3 | utility | Collapse `#sidebar-toggle` (ws-dock) | collapses rail | — | inline SVG (index.html:67-69) |
| 4 | utility | Close `#ws-close` (hidden by default) | closes drawer | — | inline SVG (index.html:70-72) |
| 5 | primary | Chat | `#/chat` | `chat` | CSS mask `--i-chat` (style.css:279, 288) |
| 6 | primary | Tasks | `#/tasks` | `tasks` | inline SVG (index.html:77) |
| 7 | primary | Needs you (button, no href) | opens `dialog#needs-you` | — | CSS mask `--i-shield`; badge `#approval-badge` (index.html:78) |
| 8 | "More" `<details id="monitor-nav">` | More (summary) | disclosure | — | inline SVG/empty slot (index.html:79-80) |
| 8a | More | Conversation history | `#/chats` | `chats` | CSS mask `--i-clock` (style.css:280) |
| 8b | More | Activity | `#/overview` | `overview` | CSS mask `--i-dash` (style.css:282) |
| 8c | More | Scheduled work | `#/schedules` | `schedules` | CSS mask `--i-calendar` (style.css:283) |
| 8d | More | Work history | `#/runs` | `runs` | CSS mask `--i-list` (style.css:284) |
| 8e | More | Runtime | `#/runtime` | `runtime` | inline SVG (index.html:85) |
| 8f | More | Skills | `#/skills` | `skills` | inline SVG (index.html:86) |
| 8g | More | Models | `/models` (full page load) | none | inline SVG (index.html:87) |
| 8h | More | Usage | `/usage` (full page load) | none | inline SVG (index.html:88) |
| 8i | More | Manage assistants | `#/bots` | `bots` | CSS mask `--i-assistants`; hidden <10 bots (app.js:2282) |
| 9 | roster `section.ws-roster` | "Assistants" + New assistant `#topbar-new-bot` + search `#bot-search` + `#roster-list` | — | — | index.html:93-103 |
| 10 | foot `footer.ws-foot` | Apps & AI | `#/connections` | `connections` | inline SVG (index.html:106-109) |
| 11 | foot | Settings | `#/settings` | `settings` | inline SVG (index.html:110-113) |

Net SPA destination set: 14 destinations, grouped primary (Chat/Tasks/Needs you) → "More" disclosure (9) → roster → footer (2). `<nav class="ws-nav" aria-label="Primary">` index.html:75; roster landmark `section[aria-label="Your assistants"]` index.html:93; scrim `#ws-scrim` index.html:116.

### A.2 Active-state mechanism

- Set in JS, not markup: `route()` iterates `$$(".ws-nav a")` and compares
  `a.dataset.nav` to the route's nav key (app.js:2191-2198); sets/removes `aria-current="page"`. CSS keys off the attribute: style.css:273 (`.ws-nav a[aria-current="page"]`, `--brand-wash`), further refined by studio.css:396-397 (neutral `rgb(255 255 255 / 0.08)` fill + `--brand-hi` icon). Focus ring style.css:274.
- "More" auto-opens for `overview,schedules,runs,bots,runtime` only (app.js:2199);
  `#/chats` and `#/skills` leave the disclosure closed, so their active item is not visible.
- Never marked active: footer links (Apps & AI, Settings — the loop selects only
  `.ws-nav a`), the Needs-you button, and the More summary. The CSS for an active footer link exists but is unreachable (studio.css:446); no JS ever touches `.ws-foot-link` (grep `ws-foot` in app.js → 0 hits).
- Route→nav-key drift: `#/bot/<name>` and `#/assistant/new` map to `"chat"`/`"bots"`
  (app.js:1877, 1891); `#/approvals` maps to `"chat"` and `renderApprovals()` rewrites the hash to `#/chat` before opening the dialog (app.js:1889, app.js:7936-7945).

### A.3 Brand markup + accessible name

`a.brand` href `#/chat`, `aria-label="hutch — open main chat"` (index.html:58); 22×22 inline SVG `aria-hidden`, fill `var(--brand)` (index.html:59); wordmark `span.brand-name.brand-wordmark` "hutch" (index.html:60). Lockup geometry is shared with server pages in brand.css:10-19 (22px mark, 8px gap, Bricolage 800 18px wordmark), applied through `.ws-brand .brand, .topbar .brand { gap: 8px }` (brand.css:13). In the collapsed rail the brand becomes the expand control and the wordmark is hidden (style.css:381-404); its accessible name stays "open main chat" (see D-34).

### A.4 Utility controls (all in `header.ws-brand`, index.html:57-73)

| Control | id | role/type | Accessible name | Wiring |
|---|---|---|---|---|
| Search | `ws-search` | button | "Search assistants, chats and pages", `aria-keyshortcuts="Control+K Meta+K"`, title "Search (Ctrl K)" (index.html:63) | click → palette.open (app.js:13359-13362); Ctrl/Cmd+K listener in palette.js:196-202 (matches the shortcut claim) |
| Collapse | `sidebar-toggle` | button | "Collapse sidebar" ↔ "Expand sidebar", `aria-controls="workspace"`, `aria-expanded` toggled (index.html:67; app.js:2526-2538) | `.app-shell.collapsed`, localStorage `hutch:sidebar-collapsed`; persisted |
| Close | `ws-close` | button, `hidden` | "Close menu" (index.html:70) | revealed on drawer open (app.js:2467), closes with focus restore (app.js:2483) |
| New assistant | `topbar-new-bot` | button | "New assistant", title (index.html:96) | click → promptNewBot (app.js:13345) |

### A.5 Contextual header (`header.app-top`, index.html:118-139)

- Mobile menu toggle `#nav-toggle` first: aria-label "Open menu" ↔ "Close menu",
  `aria-expanded`, `aria-controls="workspace"` (index.html:119; app.js:2465-2466, 2477-2478).
- `#app-top-context` is empty in HTML and filled per view by `setTopContext()`
  (index.html:124; app.js:2228-2234). Chat view content: avatar + `h1` assistant name + subtitle role + coordinator/paused chips in `.ctx-id`, and `.ctx-actions` holding the conversation selector, search, and an options `<details>` (app.js:3434-3465; other views e.g. Activity app.js:6989, Settings app.js:2119).
- `#app-top-status`: `#workflow` (hidden unless there is activity, index.html:129),
  `#daemon-pill` (href `#/runtime`, data-state connecting, hidden when live — index.html:130-133, app.js:2555-2566), and `#execution-hold` restored-history banner (`role="status"`, index.html:135-138).
- View content: `main#view tabindex="-1"` (index.html:141); skip link first child of body
  `a.skip-link[href="#view"]` (index.html:51); status announcer `#live-status` role=status aria-live=polite (index.html:154); attention strip `aside#attention-bar` aria-label "Pending work" (index.html:148); `dialog#needs-you` labelled by `#needs-you-title` (index.html:155-176).

### A.6 Responsive strategy (SPA)

- Breakpoint: **900px** — `@media (max-width: 900px)` turns the sidebar into a fixed
  off-canvas sheet `width: min(300px, 86vw)`, translateX(-102%), `.workspace.open`, shows `#ws-close` and `#nav-toggle`, collapses the grid to one column (style.css:1658-1671). JS uses the same threshold: `matchMedia("(max-width: 900px)")` (app.js:2459).
- Sidebar widths: base 272px (style.css:235), **304px at ≥901px** (input.css:44-48 at
  ≥1001 overridden/aligned by responsive.css:128-132 at ≥901; the 272px base never shows because ≤900 is single-column and ≥901 is 304 — see D-28), collapsed **icon rail 64px at ≥901** (style.css:380-405), drawer `min(300px, 86vw)` ≤900 (style.css:1663).
- Drawer behaviour: open adds `.open`, removes `inert`, shows scrim `#ws-scrim`, locks
  scroll via `HutchOverlay.lockScroll()` (app.js:2461-2470; lock impl. hutch-overlay-core.js:63-81 sets `html[data-hutch-scroll-locked]`), focuses the first `#workspace a` (the brand link, app.js:2469); close restores focus to `#nav-toggle` (app.js:2471-2481); Escape and a Tab trap over `#workspace a, button:not([hidden]), input:not([disabled]), summary` (app.js:2485-2498); scrim click closes with focus return (app.js:2484); resize listener closes when crossing back above 900 (app.js:2499).
- Safe-area/viewport: responsive.css:55-59 (app-top insets), responsive.css:110-121
  (`--vvh`, keyboard), responsive.js publishes `--vvh`/`--keyboard-inset`/`--topbar-h`.
- Collapse rail: `.app-shell.collapsed` at ≥901, labels set to `font-size:0`, roster/ids
  hidden, `.ws-dock` hidden and the brand becomes the expand control (style.css:379-405); JS toggle/persist at app.js:2523-2547.

### A.7 Theme (SPA)

Fixed dark. `<html lang="en" data-theme="hutch">` (index.html:2), `<meta name="color-scheme" content="dark">` and `theme-color #09090b` (index.html:7-8); style.css:38 sets `color-scheme: dark`; daisyUI theme `hutch` is declared `color-scheme: dark` (input.css:185-222). Product statement: "Hutch intentionally ships a fixed dark theme. It does not currently add a separate `prefers-contrast` palette; this is a product decision" (docs/design-system.md:333-336), and "Keep the dark theme as the shared visual contract" (docs/design-system.md:166-167). A parked light counterpart exists keyed on `:root[data-hutch-theme]` (input.css:28-31; hutch-theme-overrides.css:14-27, 55, 183), and hutch-overlays.css:114-134 already carries a `:root[data-hutch-theme="light"]` `color-scheme: light` block — but **no page sets `data-hutch-theme`**, and the overrides file states "No attribute means no change … Activation of the attribute belongs to a later step" (hutch-theme-overrides.css:27-31). So: dark-only today; two attribute names (`data-theme` for daisyUI, `data-hutch-theme` for the parked tier), one dormant.

### A.8 Keyboard/focus notes (SPA)

Skip link `#view` (index.html:51) targets the focusable main (index.html:141); focus is rescued to the view `h1` after a hash route re-render when it orphans to `body` (app.js:2202-2210). Drawer focus entry is the brand link, not the first nav item (app.js:2469 — differs from server, see D-32). Collapse removes the collapse button itself from the tab order and moves the expand action onto the brand link (style.css:402-404); the brand click both expands and follows `#/chat` because the handler does not `preventDefault()` (app.js:2541-2546). Roster rows are real buttons with focus rings (style.css:337-346). No contentinfo landmark: `footer.ws-foot` is nested inside `aside#workspace` (index.html:105-114), so it is not exposed as `contentinfo`.

---

## B. Server-page chrome inventory

### B.1 Shared chrome contract (`templates/base.html`)

`{% if chrome|default(true) %}` (base.html:56) → `header.topbar` (base.html:57): `a.brand[href="/"][aria-label="hutch home"]` with 22px SVG fill `var(--accent)` + `span.brand-wordmark` (base.html:58-61); `nav#primary-nav[aria-label="Primary"]` loops `nav_items` and sets `class="active"` + `aria-current="page"` only when `nav == key` (base.html:62-68; badge for key `approvals`, base.html:65); hamburger `#nav-toggle` aria-label "Open menu" aria-expanded aria-controls (base.html:69); `div.topbar-right` with the **Stop all** `confirm_form` macro (base.html:70-77; macro markup macros/modal.html:68-92, trigger `btn danger small` + `aria-label="Stop all runs now…"`) and `<span id="live-pill" class="pill" role="status" aria-live="polite">live</span>` (base.html:78). The nav, toggle, controls and footer render **only when `nav` is truthy** (base.html:62, 70, 91); `chrome=false` removes the whole topbar (base.html:56, 81) but keeps the skip link and `main#main.container` (base.html:55, 88-90). Footer text: "hutch {{ version }} - local-first - {{ state_dir }}" (base.html:91). `<html lang="en">` has no theme attribute (base.html:4); hutch.css:21 sets `:root { color-scheme: dark }` and maps semantic brand tokens (hutch.css:20-53); no `<meta name="theme-color">`/`color-scheme` meta (base.html:5-14 vs index.html:7-8).

### B.2 Routes that render a full server page with chrome

| Route | Template | nav= | Active item |
|---|---|---|---|
| GET `/models` (pages_models.py:62-67) | models.html | `models` | Models |
| GET `/usage` (pages_usage.py:20, 64) | usage.html | `usage` | Usage |
| GET `/legacy/connections` (pages.py:605-612) | connections.html | `connections` | Apps & AI |
| GET `/bots/{name}` (pages.py:311-318) | bot.html | `bots` | Assistants |
| GET `/bots/delete` (pages.py:273-276) | bot_delete_pick.html | `deletion` | Delete bot |
| GET `/bots/{name}/delete` (pages.py:320-323) | bot_delete.html | `deletion` | Delete bot |
| GET `/login` (pages.py:714-716) | login.html | "" (default) | none — brand-only topbar, no controls, no footer |
| GET `/pair` (pages.py:718-721) | pair.html | "" | none — same |
| unmatched 404/405/500 with `Accept: text/html` (pages.py:165-175) | error.html | "" | none — same |
| GET `/onboarding` (onboarding_api.py:219-221 via onboarding_pagekit.py:68-75) | onboarding.html | "" + `chrome=False` | no topbar at all |
| GET `/onboarding/ai-service` (onboarding_chooser_api.py:187-189, same pagekit render) | onboarding_ai_service.html | "" + `chrome=False` | no topbar at all |

`NAV` itself is pages.py:37-47, DOM order: Chats `/`, Activity `/overview`, Assistants `/bots`, Work history `/runs`, Needs you `/approvals`, Models `/models`, Usage `/usage`, Apps & AI `/connections`, Delete bot `/bots/delete`; icons chat/home/bot/list/shield/cpu/ chart/layers/trash all resolve in _icons.html (2-42). Only **5 of the 9 keys are ever passed to `page()`** (`models`, `usage`, `connections`, `bots`, `deletion`), so Chats, Activity, Work history and Needs you can never render as an active server-nav item.

### B.3 Routes that are not chrome pages

- **FileResponse (SPA)**: `/` (pages.py:191-195) and `/legacy` + `/legacy/`
  (pages.py:179-184) serve `static/index.html`; no Jinja chrome.
- **302 redirects into the SPA**: `/overview` → `/#/overview` (pages.py:197-199), `/bots`
  → `/#/bots` (pages.py:246-266), `/bots/new` → `/#/bots` (pages.py:268-270), `/runs` → `/#/runs` (unless `?fragment`, pages.py:421-431), `/runs/{run_id}` → `/#/run/{id}` (pages.py:433-436), `/approvals` → `/#/approvals` (pages.py:539-541), `/connections` → `/#/connections` (pages.py:599-603). POST handlers answer 303 via `go()` (pages.py:118-124).
- **Fragments (no chrome)**: `/_home` (pages.py:201-203), `/_badge` (234-236),
  `/_approvals` (543-545), `/runs/{id}/events` (438-454), `/runs/{id}/meters` (456-462), `/runs/{id}/wait` (464-471); `/stream/live` and `/runs/{id}/stream` are SSE (pages.py:238-242, 473-490); `/api/overview` JSON (205-232).
- **chrome=false**: the two onboarding pages (pagekit context has `"nav": "", "nav_items":
  [], "chrome": False`, onboarding_pagekit.py:70-75).
- **Dead templates still present** (extend base.html but no route renders them):
  `home.html`, `bots.html`, `run.html`, `runs.html`, `bot_new.html`, `approvals.html` (grep of template names in `src/hutch/server/**/*.py` → 0 hits). They are leftover chrome renderers and will confuse any "which template owns which nav state" work.

### B.4 Nested-route active detection

Detection is **key-based, never URL-based** (base.html:64 compares `nav == key`), so a nested route is "correct" only if its handler passes the intended key: `/bots/{name}` → `bots` (pages.py:315) and `/bots/{name}/delete` → `deletion` (pages.py:323). Consequences: (1) `/bots/{name}/delete` does not mark Assistants, and the pair is communicated only by a hand-written crumb that says "Permanently delete a bot" (bot_delete.html:7) while `/bots/{name}`'s crumb says "Bots" (bot.html:10) and `/bots/delete` says "Assistants" (bot_delete_pick.html:7) — three labels for the same region. (2) There is no prefix-matching or parent-trail logic anywhere, so adding a nested route without knowing the `nav` argument silently loses the active state. (3) The redirect routes above would have been active states but never render.

---

## C. Consistency matrix

| Page (route + template) | Item set | Active-state treatment | Controls present | Control styling | Brand/logo | Responsive behaviour | Focus order & keyboard | Theme |
|---|---|---|---|---|---|---|---|---|
| SPA `/` + `/legacy` (static/index.html; app shell, FileResponse) | Sidebar 14 destinations: Chat, Tasks, Needs you, More(9), roster, Apps & AI, Settings; "More" collapses 9 | app.js:2191-2198 sets `aria-current="page"` on `.ws-nav a` only; CSS style.css:273, studio.css:396-397; footer/button/summary never marked; More auto-opens only for overview/schedules/runs/bots/runtime (app.js:2199) | ws-search (Ctrl/Cmd+K), sidebar collapse, drawer close, New assistant, daemon pill, workflow cluster, execution-hold banner | Token-driven `--brand-wash`/`--brand-hi`; primitives in style.css + studio.css; search/collapse are `.icon-btn` | `a.brand` `#/chat`, aria-label "hutch — open main chat", SVG fill `var(--brand)`, Bricolage wordmark (index.html:58-60; brand.css:10-19) | 304px ≥901 / 64px collapsed / drawer ≤900 `min(300px,86vw)`; Escape+scroll-lock+Tab trap; skip link → focusable `main#view` | skip-link → brand → header buttons → nav links → roster → footer; drawer focuses brand; focus restored to `#nav-toggle`; Tab trapped (app.js:2485-2498) | Fixed dark: `data-theme="hutch"` + `color-scheme` meta (index.html:2,7-8); parked `data-hutch-theme` light tier unwired |
| `/models` (models.html; nav=models) | NAV 9 flat: Chats, Activity, Assistants, Work history, Needs you, Models, Usage, Apps & AI, Delete bot | Models `aria-current="page"` + `class=active` (base.html:64); CSS hutch.css:94 | Stop all (confirm form), live pill | `btn danger small` primitive via macro (macros/modal.html:68-92); `.pill` hutch.css:97-100; topbar hutch.css:86-101 | `a.brand` "/" aria-label "hutch home", SVG fill `var(--accent)` (base.html:58-61) | Sticky 54px topbar; overlay nav ≤1024 (hutch.css:333-345, hutch.js:183-226); icons hidden 1025-1439 (responsive.css:65-69); wrap ≤720 with toggle order bug (D-25) | skip → brand → 9 nav links → [hamburger ≤1024] → Stop all → main; `main#main` lacks `tabindex` (base.html:88) | No theme attr; hutch.css:21 color-scheme dark; semantic tokens; no theme-color meta; no light |
| `/usage` (usage.html; nav=usage) | same NAV 9 | Usage active; page-local period nav `.seg` uses `aria-current="true"` (usage.html:10) — second active-state vocabulary on one page | same | same | same | same | same | same |
| `/legacy/connections` (connections.html; nav=connections) | same NAV 9 | Apps & AI active | same | same | same | same | same; `<h1>` says "Connections" not "Apps & AI" (connections.html:5,7) | same |
| `/bots/{name}` (bot.html; nav=bots) | same NAV 9 | Assistants active | same | same | same | same | same; crumb "Bots" (bot.html:10) | same |
| `/bots/delete` (bot_delete_pick.html; nav=deletion) | same NAV 9 | Delete bot active (a destructive destination promoted to primary nav) | same | same | same | same | same; crumb "Assistants" (bot_delete_pick.html:7) | same |
| `/bots/{name}/delete` (bot_delete.html; nav=deletion) | same NAV 9 | Delete bot active; Assistants not indicated | same | same | same | same | same; crumb "Permanently delete a bot" (bot_delete.html:7) | same |
| `/login` (login.html; nav="") | none — `{% if nav %}` false (base.html:62) | none | none (no Stop all, no live pill; nav-toggle absent) | n/a | brand-only topbar, 54px | only ≤720 wrap rule; no nav toggle; no JS nav behaviour | skip → brand → form field → passkey button; brand is the only way to leave | same |
| `/pair` (pair.html; nav="") | none | none | none | n/a | brand-only topbar | same | same; brand link only | same |
| HTTP error 404/405/500 (error.html; nav="") | none | none | none | n/a | brand-only topbar | same | skip → brand → "Back to Home" (error.html:6); no `tabindex` on main | same |
| `/onboarding` (onboarding.html; chrome=false) | none — no topbar/footer | none | none | n/a | none | plain document, onboarding.css mobile rules | skip → first field; no nav/toggle | same (hutch.css tokens) |
| `/onboarding/ai-service` (onboarding_ai_service.html; chrome=false) | none | none | none | n/a | none | same | same | same |

Not matrix rows (verified non-chrome): `/`, `/legacy`, `/overview`, `/bots`, `/bots/new`, `/runs`, `/runs/{id}`, `/approvals`, `/connections` (FileResponse/302), `/_home`, `/_badge`, `/_approvals`, `/runs/{id}/events|meters|wait` (fragments), `/stream/live`, `/runs/{id}/stream` (SSE), `/api/*`.

---

## D. Inconsistency list (with verification)

### D.1 Item-set drift
1. **Two unrelated item lists with no shared source.** Server NAV=9 flat
   (pages.py:37-47) vs SPA 14 grouped (index.html:75-114). Only 4 keys overlap (Activity, Apps & AI, Work history, Manage assistants/Assistants); SPA has Chat/Tasks/Scheduled work/Runtime/Skills/Settings/Delete-assistant-context that the topbar lacks; topbar has Delete bot top-level that the SPA routes only via a page. Verify: `sed -n '37,47p' src/hutch/server/pages.py` vs `sed -n '75,114p' src/hutch/server/static/index.html`.
2. **Label drift for the same destination.** Chat vs Chats (index.html:76 vs
   pages.py:38); Manage assistants vs Assistants (index.html:89 vs pages.py:40); Apps & AI nav label vs page `<h1>Connections` (connections.html:5,7); "Assistants" nav vs page crumb "Bots" (bot.html:10). Verify with the selector `document.querySelector('#primary-nav a.active')?.textContent`.
3. **Order drift.** Needs you is SPA item 3 but server item 5; Models/Usage are
   SPA-"More" items but server top-level; Settings exists only in SPA; Tasks/Runtime/ Skills/Scheduled work/Conversation history exist only in SPA. Verify: diff the two ordered lists above.
4. **Delete bot is a primary topbar destination** (pages.py:46), contradicting the
   design-system rule "Put secondary navigation and destructive actions in one labeled **Assistant options** menu; deletion should not compete visually with ordinary page navigation" (docs/design-system.md:240-242). Looks unintentional.
5. **SPA "More" mixes shell routes and full-page loads.** Models `/models` and Usage
   `/usage` are plain hrefs that leave the SPA (index.html:87-88; same jump from palette palette.js:92-93), so the sidebar is not a closed navigation model. Likely intentional until those pages migrate.
6. **`#fleet-nav` (Manage assistants) hidden below 10 assistants** (app.js:2282) while
   the server topbar always shows "Assistants" (pages.py:40) — same destination with different discoverability rules.

### D.2 Active-state drift
7. **Same concept, two visual treatments.** SPA active = neutral wash + brand icon
   (studio.css:396-397) on `--brand-wash`; server active = emerald text + hard-coded `rgba(52, 211, 153, .09)` wash (hutch.css:94). Verify side by side: `.ws-nav a[aria-current]` computed `background-color` vs `#primary-nav a.active`.
8. **SPA footer routes never get active state.** `.ws-foot-link[aria-current="page"]`
   styling exists (studio.css:446) but the only JS writer loops `.ws-nav a` (app.js:2194); `grep -n 'ws-foot' src/hutch/server/static/app.js` → 0 hits. On `#/connections` and `#/settings` nothing in the sidebar is highlighted. Verify: `document.querySelectorAll('[aria-current]')` on `#/settings` → only roster rows.
9. **SPA "More" hides the active item.** On `#/chats` and `#/skills` the More disclosure
   is closed (app.js:2199 excludes them), so the current location is invisible. Verify: open `#/chats`, `document.querySelector('#monitor-nav').open === false`.
10. **SPA route keys point at the wrong item.** `#/bot/<name>` and `#/assistant/new` mark
    Chat (app.js:1891,1877); `#/approvals` rewrites to `#/chat` and marks Chat (app.js:1889,7936-7938). The "Needs you" button has no active/aria-expanded state. Verify: navigate to `#/bot/<bot>` → `.ws-nav a[aria-current]` text is "Chat".
11. **4 of 9 server NAV keys can never be active** because their routes redirect before
    rendering (pages.py:191-199, 421-431, 539-541; only 5 keys reach `page()`). Verify: `grep -n 'nav="' src/hutch/server/pages.py src/hutch/server/pages_models.py src/hutch/server/pages_usage.py`.
12. **Two aria-current vocabularies on one server page:** topbar uses
    `aria-current="page"` (base.html:64); usage period segment uses `aria-current="true"` (usage.html:10); SPA roster uses `"true"` (app.js:2398, 2419). Consistent in spirit, inconsistent in string.
13. **Nested-route context loss:** `/bots/{name}/delete` marks Delete bot only; Assistants
    loses the trail (pages.py:323, base.html:64). Intentional? The explicit `nav=` argues yes, but the three conflicting crumbs (bot.html:10, bot_delete_pick.html:7, bot_delete.html:7) argue the label set was not settled.

### D.3 Control drift
14. **Status/liveness controls differ by surface.** Server: always-visible
    `#live-pill` "live" (base.html:78; hutch.js:97-110). SPA: `#daemon-pill` is hidden when healthy (app.js:2565) and a separate `#workflow` cluster appears only with activity (index.html:128-134). Verify: on a healthy SPA, `#daemon-pill.hidden === true`; on `/models`, `#live-pill` is visible.
15. **Danger control only on server chrome.** Stop all runs is in the topbar
    (base.html:70-77) but has no SPA sidebar equivalent; SPA run controls live in the contextual header. Verify: `document.querySelector('#primary-nav')` vs `document.querySelector('.ws-nav')` for a danger button.
16. **Search is a header button on both but behaves differently.** SPA `#ws-search`
    opens the global palette (app.js:13359-13362); server pages have no search control at all (base.html has none; grep `search` in base.html → only form inputs). Verify: `document.querySelectorAll('.topbar button')` on `/models`.
17. **Two drawer toggles with different names/semantics.** SPA `#nav-toggle` opens
    `aside#workspace` (≤900) and `#ws-close` closes it; server `#nav-toggle` opens `nav#primary-nav` and has no close button (Escape only). Verify selectors `#workspace.open` vs `#primary-nav.open`.
18. **Stop-all confirmation is a primitive; the live pill is ad-hoc.** `confirm_form`
    composes the modal primitive correctly (macros/modal.html:68-92) but the live pill is a hand-rolled `.pill` with its own `::before` dot (hutch.css:97-100) and its JS state machine lives beside the stream reconnection logic (hutch.js:97-110); the SPA daemon pill re-implements the same idea separately (style.css:412-422, app.js:2555-2566).

### D.4 Duplication
19. **Four encodings of the navigation item set:** `NAV` (pages.py:37-47), SPA sidebar
    markup (index.html:75-114), palette "Go to" list (palette.js:79-101), and `ROUTE_TITLES` (app.js:2154-2166). None imports another; adding one destination means editing up to four places. Verify: search for "Scheduled work" / "Work history" hits in all four.
20. **Two independent overlay implementations** for the same "nav sheet": app.js drawer
    (app.js:2450-2500 + style.css:1658-1671) and hutch.js overlay (hutch.js:183-226 + hutch.css:327-348), each with its own Escape/Tab/inert logic.
21. **Two shell stylesheets with the same concepts:** `header.app-top` / `header.topbar`,
    `aside#workspace` / `nav#primary-nav`, `.skip-link` / `.skip`, `#live-status` / `#live-pill`, `--brand` (style.css:63) / `--accent` (hutch.css:35). Verify: `grep -n '\.topbar\|\.app-top' src/hutch/server/static/*.css`.
22. **Six dead chrome templates** (`home.html`, `bots.html`, `run.html`, `runs.html`,
    `bot_new.html`, `approvals.html`) still extend base.html; grep of `src/hutch/server` Python for those filenames → 0 hits. They shadow the real redirect routes and should be deleted or clearly marked (looks like leftover migration work).
23. **Duplicate skip-link CSS:** `.skip-link` (style.css:209-215) vs `.skip`
    (hutch.css:81-82) — same behaviour, different names.
24. **Two theme attribute names**, `data-theme` (index.html:2) and `data-hutch-theme`
    (input.css:28-31, hutch-overlays.css:117), plus a third mechanism `prefersdark` in the daisyUI theme (input.css:188).

### D.5 Responsive defects
25. **Server hamburger can render before the brand below 720px.** hutch.css:302-307 gives
    `.brand{order:1}`, `.topbar-right{order:2}`, `.nav{order:3}` but gives `.nav-toggle` no order (order 0), and the topbar wraps at ≤720 (hutch.css:304). Verify at 600px: `document.querySelector('#nav-toggle').getBoundingClientRect().x` < `document.querySelector('.topbar .brand').getBoundingClientRect().x`.
26. **Cross-surface breakpoint mismatch:** SPA turns the sidebar into a drawer at
    **≤900px** (style.css:1658, app.js:2459); server pages switch to the nav overlay at **≤1024px** (hutch.css:333, hutch.js:188). responsive.css:9-16 documents a 768-1024 tablet band, and responsive.css:61-64 explains the 1024px choice for nine server destinations, so the 1024 choice looks intentional — but at 901-1024 the SPA already has a full sidebar while server pages show a full-screen nav sheet. Verify: at 950px compare `.workspace` computed position (`fixed` drawer ≤900 only) vs `#primary-nav` (`position:fixed` ≤1024).
27. **Icon strategy inverts across surfaces at the same width.** 1025-1439px: server nav
    *hides* all icons (responsive.css:65-69) because nine labels must fit; SPA sidebar at those widths keeps icons+labels at 304px. Verify: `getComputedStyle(document.querySelector('#primary-nav a svg')).display` at 1100px → `none`.
28. **272px value is dead in the cascade.** style.css:235 still declares 272px, but ≤900 is
    single-column and ≥901 is forced to 304px by responsive.css:128-132, which itself exists only to align style.css with input.css:44-48. Verify at 950px: `getComputedStyle(document.querySelector('.app-shell')).gridTemplateColumns` starts `304px`; 272px appears in no computed layout. (Comment at responsive.css:123-127 is still accurate about the two owners, but the 272 value should be deleted.)
29. **Server topbar height vs SPA header height:** 54px sticky (hutch.css:86) vs 56px
    (style.css:236); responsive.css:31-44 patches only the server page for safe areas and responsive.css:55-59 only the SPA. Verify: `offsetHeight` of `.topbar` vs `.app-top` at 1440px.
30. **No-JS fallback exists only for server pages.** base.html:37-38 links
    `no-js-nav.css` inside `<noscript>` (36 lines: hides toggle, wraps nav); the SPA has no no-JS story at all (index.html:180-203 scripts only). Intentional (SPA is an app) but it is a real parity gap for the "one navbar" goal.
31. **SPA ≤640 shell row reflow is patched twice** (style.css:1937-1941 and
    studio.css:520-532, 557-559) with different attention-bar models (grid row vs static banner); at 641-900 the behaviour differs from ≤640. Verify: resize 700→600 and watch `#attention-bar` position (`static` vs grid row 2).

### D.6 Accessibility defects
32. **SPA drawer focus entry lands on the brand, not navigation.** app.js:2469 focuses
    `#workspace a` which is `a.brand` (index.html:58); server overlay focuses the first nav link (hutch.js:199). With 14 destinations, SPA open-focus should be Chat. Verify: open the drawer at 390px, `document.activeElement.className` → `brand`.
33. **Neither overlay is announced as a modal.** SPA: `aside#workspace` has
    `aria-label="Workspace"` only (index.html:56); server: `nav#primary-nav` aria-label Primary (base.html:62); both become full-screen overlays (style.css:1660-1668, hutch.css:335-343) and neither sets `aria-modal`/`role="dialog"` nor inerts the page behind (only the overlay itself gets `inert` when closed: app.js:2460, hutch.js:194). Verify: with drawer open, `document.querySelectorAll('main a, main button')` are still focusable behind the scrim.
34. **Collapsed rail removes the expand control from the tab order.** style.css:402 hides
    `.ws-dock` when collapsed and style.css:403-404 makes the brand the expand affordance, but the brand keeps aria-label "hutch — open main chat" and its click also navigates (`#/chat`); app.js:2541-2546 does not `preventDefault()`. Keyboard user who collapses loses an explicit Expand control. Verify: at 1200px click `#sidebar-toggle`, then Tab → `#sidebar-toggle` is `display:none`; Enter on brand both expands and changes hash.
35. **Skip-link targets are not equivalent.** SPA `main#view tabindex="-1"`
    (index.html:141); server `main#main` has no tabindex (base.html:88), so "Skip to content" does not reliably move focus in the server shell. Verify: `document.querySelector('main').tabIndex` → SPA -1, server default; run the skip link and check `document.activeElement`.
36. **Hamburger is focusable only in the mobile overlay; no aria-current on the More
    summary** and no `aria-expanded` state on `details#monitor-nav` is managed by JS (native only) while SPA implicitly relies on native `<details>`. Minor; verify `#monitor-nav` attributes at `#/runs`.
37. **Server topbar Stop all sits in the tab order before page content and opens a
    non-dismissible dialog** (macros/modal.html:75-80 `data-dismissible="false"`); on phone widths the order is brand → [hamburger] → Stop all → content (base.html:57-79). Risk of accidental activation on mobile. Verify with the keyboard walk; no measured defect, flagged for review.

### D.7 Theme defects
38. **No light theme, by decision, but two dormant hooks disagree on the attribute.**
    Fixed-dark statement: docs/design-system.md:333-336. Parked tier keys `data-hutch-theme` (input.css:28-31; hutch-theme-overrides.css:14-31, 55, 183; hutch-overlays.css:117) while the SPA root uses `data-theme="hutch"` (index.html:2). Server base.html uses neither. Verify: `getComputedStyle(document.documentElement).colorScheme` and `document.documentElement.getAttributeNames()`.
39. **Server chrome colors bypass the semantic token tier.** hutch.css:94 and :330
    hard-code emerald `rgba(52, 211, 153, …)`; hutch.css:114 hard-codes `rgba(5, 7, 10, .94)` for `.run-head`. The SPA equivalent consumes `--brand-wash` (style.css:68,273). If the parked light tier ever activates, server nav/active states stay dark-tinted. Verify: `grep -n 'rgba(52, 211, 153\|rgba(5, 7, 10' src/hutch/server/static/hutch.css`.
40. **Missing mobile theme metadata on server pages.** SPA has `theme-color` #09090b and
    `color-scheme: dark` meta (index.html:7-8); base.html has neither (base.html:5-14), so mobile browser UI (address bar, form controls before CSS) can differ per surface. Verify: view-source of `/models` head.
41. **Server shell hard-codes `color-scheme: dark`** (hutch.css:21) and loads no daisyUI
    theme; SPA inherits daisyUI `hutch` (`prefersdark: true`, input.css:185-189). Today both dark, but they are two independent declarations of the same decision.

Intentional-looking: item 5 (Models/Usage bridge); the redirect routes to the SPA (B.3; documented migration, pages.py:182-184, 192-194); item 11 (4 keys unreachable); item 26's 1024 server breakpoint (responsive.css:61-64); item 30 (SPA requires JS by design); item 39's literals may predate the token pass but are still a theme hazard.

---

## E. Necessity review — is the server topbar navbar necessary given the sidebar?

**Verdict: the topbar *chrome* is necessary; its 9-item primary navbar is not, and is the main source of drift.**

Evidence:
1. **The sidebar does not exist on server-rendered pages.** They are separate Jinja
   documents (base.html), do not load index.html/app.js, and the SPA is served only by FileResponse at `/` and `/legacy` (pages.py:179-195). Rendered server pages that need a way out are `/models`, `/usage`, `/legacy/connections`, `/bots/{name}`, `/bots/delete`, `/bots/{name}/delete`, `/login`, `/pair`, error pages. Without a topbar these would be orphan documents with no path back to the app or between server pages. The **brand link + a small "back to app" + Models/Usage/Apps&AI + Stop all/live** would cover every real need.
2. **Most of the navbar is a redirect bridge.** 6 of the 9 NAV destinations
   (Chats, Activity, Assistants, Work history, Needs you, Apps & AI) resolve to a 302 or FileResponse into the SPA (B.3); only Models, Usage and Delete bot stay in server chrome. Clicking the active "Assistants" item on `/bots/{name}` (pages.py:315, nav item pages.py:40) immediately drops the user into `/#/bots` (pages.py:246-266), so the topbar advertises destinations it does not own. Inverting that: a plain `<a href="/#/chat">` would work from any server page without a 9-item list.
3. **The list diverges from the canonical sidebar** (items 1-6) and includes a
   destructive destination as primary navigation (item 4), contradicting docs/design-system.md:240-242. Design-system already states the target model: one shared "workspace sidebar, contextual header" (docs/design-system.md:270-273); the topbar nav is a second information architecture living beside it.
4. **The item set cannot be reconciled by copy-editing.** SPA has Tasks, Runtime, Skills,
   Scheduled work, Settings, conversation history and a roster that the topbar has no room for at 1025-1439 (responsive.css:61-69 hides icons *because* nine labels need ~1055px). Adding parity in the topbar is not viable; the honest options are (a) shrink the topbar to a bridge/minimal chrome, or (b) give server pages the real sidebar shell — which is parked shell work.

**What blocks removing/inlining the navbar today:**
- **Full-page documents**: server pages are separate HTML documents with no sidebar, so
  the topbar is the only cross-page navigation. Remove it first, not after.
- **href/route constraints**: 6 of 9 nav items are redirects into hash routes
  (B.3) and `/` is a FileResponse; converting them to in-page links requires deciding where those destinations live (server pages vs SPA) and whether `/models`, `/usage` and `/legacy/connections` migrate behind the SPA shell. The palette already duplicates the same decisions (palette.js:79-93).
- **Uncommitted parked-session shell work**: `src/hutch/server/static/index.html`,
  `style.css`, `studio.css`, `app.js`, `hutch.css`, `hutch.js` and `templates/base.html` all carry uncommitted "M" changes (`git status --short -- <paths>` above). Touching the sidebar/topbar now would either collide with that work or force a revert of it, which AGENTS.md forbids. This is the hard blocker for any implementation task that follows this audit.
- **Auth pages deliberately render brand-only topbars** (`nav=""` → no controls/footer,
  base.html:62-91): any "one navbar" design must keep a chrome-less variant for `/login`, `/pair`, error pages and onboarding (`chrome=false`, onboarding_pagekit.py:70-75) — those are not candidates for sidebar adoption.
- **Theme coupling**: server chrome hard-codes dark RGBA and `color-scheme: dark`
  (items 38-41); a shared shell needs the semantic token tier first, or the parked light tier stays broken on server pages.

**Recommendation (audit-only, no code):** keep the topbar for server pages but reduce it to brand + "Back to app" + the three server-owned destinations (Models, Usage, Apps & AI via `/legacy/connections`) + existing Stop all/live primitives; demote Delete bot out of primary navigation; then, once the parked shell work lands, decide whether `/models`/`/usage` move inside the SPA shell. Any change must wait for the uncommitted shell diff to be resolved.

---

### Method / limits
Read-only inspection with read/grep/glob; `git status` and `wc -l` only. No server was started, no test or e2e run, no network, no source edits; only this file was created. Generated `ui.css` / `model-switcher.css` and lockfiles were not read (app/src/input.css cited as the source). Where a claim is a CSS-cascade inference it names the selector and measurement a browser check should use; where it is direct evidence it cites file:line.