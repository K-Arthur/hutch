# Navbar consolidation — adversarial read-only review

Review of the implemented consolidation (server topbar removed; one app-shell sidebar on
every server page; shared navigation sheet for both shells). Date: 2026-10-30. Snapshot
taken at **02:52:34 PDT**; the working tree is under active concurrent edit (see caveat).
Read-only: no source file was modified; this file is the only artifact written. No server
was started, no pytest/e2e run, no network — findings are from reading current files plus
git status/grep/stat/sha256sum.

**Concurrency caveat.** Files changed while this review was in progress: app.js and
index.html at 02:47:17 (footer active-state + More auto-open + data-nav on Models/Usage),
pages.py at 02:51:44, hutch-nav.css + hutch-shell.css at 02:52:21 (SPA rail colour
side-effect removed; server rail colour derived from the token instead), tests at 02:48 and
02:51:28. Everything below reflects the SHAs at 02:52:34; re-verify hashes before merge and
re-run the updated e2e tests once edits stop.

| File | SHA-256 (snapshot) |
|---|---|
| src/hutch/server/nav.py | 637b1036466003fb529f8e04b6dd820d950f7366e7f7661a501bd3aba4b70e0b |
| templates/macros/sidebar.html | 5c2ad6a482ab9610a35aab4f50de0f3000e5ad616a1d33cd5bf059d264a0b2a4 |
| templates/base.html | 9af2bcfda44e8c3b74e29c712f3034f203856356ecfe237f101bcff3923c7f33 |
| static/hutch-nav.css | 7e3816702343903f2d8752941dc9557b5dbb1eefc7ce9d34723479df4f4c77e4 |
| static/hutch-shell.css | 2163803282c2d3bd0fffca8553c10b5f11a6e8a8683c24cfb53ca394b31609da |
| static/hutch-shell.js | d9fc19dae4238cf0230a668862c21d9fe2f10322a81d50606744685040a8c6bb |
| static/hutch.css | b5c5c5c06c5db109a23531b1ea8643354b52cb179203b124b81d1604a3d49b3f |
| static/hutch.js | e981433ffa0c5ca5f852b48f47748f3a94d1e06062913cf03157a615e82bfabd |
| static/responsive.css | 8000dd66716ed73259e84e6341e36b054f238e9cf08aa8d8e6e77301f4fe72ff |
| static/no-js-nav.css | 23e022e2e7324fd31fcf184ca14005ba311839112e12316dc885c2d6052d3b4e |
| static/index.html | 24814021ea7ef456f90fece227953306044b37384447fb50de628203106cc135 |
| static/app.js | 1f35c8bc521e5f66876f0525f50b09d60036d1d61d5ba227370fa779119b47e7 |
| pages.py | d6f9e06895c21f6b718f10b3111deeb74104160dc60dd3dbf00cf25ff08d7837 |
| tests/test_navbar_consistency.py | 72a94becd85ca81f847ec9164194ae12e66b4ade61966aaf22f7bed4dff6f5a2 |
| tests/e2e/test_browser.py | 84d28b9ea9eb4b81223ee109a6ec7587dcda38ad3fe4756d317430e4cb7ecbe8 |

## Verdict by area

| # | Area | Verdict | Notes |
|---|------|---------|-------|
| 1 | Every chrome page renders one sidebar with correct active destination (nested/Delete-bot) | PASS | Alias + server-side active verified for models, usage, connections, bot detail, delete picker/delete. Error pages render no active item (expected); login/pair/onboarding are chrome-less. See F6/F12. |
| 2 | No leftover topbar/.nav/#primary-nav old overlay CSS/JS | FAIL (low severity) | Core legacy code is gone, but stale references remain: hutch-popovers.css:183, responsive.js Topbar measurement, responsive.css fallback contract, brand.css:13, dead app.js selector. See F8. |
| 3 | Item order/labels/hrefs match SPA sidebar | PASS | nav.py and static/index.html agree on 13 anchors in the same order, data-nav included (index.html:79-118 vs nav.py:11-32); guarded by tests/test_navbar_consistency.py. Needs-you is a button in SPA vs link on server (accepted by the test) — see F5/F10/F11. |
| 4 | A11y (skip target, names, inert, keyboard, aria-current) | FAIL | Skip target focusable, names, inert/trap/Escape/aria-current/forced-colors are correct — but F1 makes the drawer open underneath the sticky header, so the first focused control (brand) is visually covered; F15 notes missing dialog semantics/background inertness. |
| 5 | Responsive (one 900px drawer, fixed 56px header, no overflow) | FAIL | 900px and 56px are implemented and e2e-covered; F1 and F2 are stacking defects at that breakpoint, F13 is a density risk. |
| 6 | Token usage in new/changed nav CSS | PASS | New nav/shell CSS has no hex/rgb/rgba values; all var() names resolve in brand-tokens/hutch-overlays/responsive or are runtime tokens with fallbacks. Minor literal nit in F9. |
| 7 | SPA side-effects / regressions | PASS with notes | Current SHA removed the shared sheet's .workspace override, so SPA rail colour is unchanged; active-row treatment change is intended. Residual risks F3, F4, F5, F6, F9. |

**Bottom line: do not merge as-is.** Fix F1 (High) and decide F2/F3 before merge; then clear
the low-severity legacy residue (F8) and re-run the updated e2e suite after concurrent edits
settle.

## Findings (ordered by severity)

### F1 [High] Server-page drawer and scrim stack underneath the sticky header (<=900px)
- hutch-shell.css:69-81 gives .app-top position sticky, z-index calc(var(--layer-nav,100) - 1) = 99.
- hutch-shell.css:139-151 gives the fixed .workspace drawer z-index var(--hutch-z-modal,50) = 50.
- hutch-shell.css:126-132 gives the fixed scrim z-index var(--hutch-z-popover,46) = 46.
- Overlay tokens: hutch-overlays.css:46-53 (tooltip 42, dropdown 44, popover 46, modal 50, toast 60, skip 70). SPA convention is the inverse: style.css:140 has --z-rail:40 and the SPA header is not positioned, so scrim/drawer paint over it.
- Effects on every server page at <=900px: the top 56px of the drawer (the entire .ws-brand row, including the Close button) is painted under the opaque header; the scrim does not dim the header, so Stop all and the live pill stay clickable over the modal scrim (safety hazard); openDrawer() focuses the brand link first (hutch-shell.js:33-34), so keyboard focus lands on a control that is visually hidden under the header (WCAG 2.4.7/2.4.11 concern). This makes the just-added Close button effectively unusable by pointer.
- Verify at 390x844 on /usage: click #nav-toggle, then
  `[...document.querySelectorAll('.hutch-shell > .workspace,.ws-scrim,.app-top')].map(e=>[e.id||e.className,getComputedStyle(e).zIndex])`
  -> workspace 50, scrim 46, app-top 99; and `document.elementFromPoint(150,28)?.closest('#workspace')` returns null
  (header wins). The e2e test (test_browser.py:7113+) screenshots this but asserts no z-order.
- Suggested fix: keep header below the drawer/scrim (e.g. .app-top z-index below scrim, or add
  .hutch-shell:not(.nav-open) .app-top z-index 40 and raise scrim above 40, leaving drawer above
  scrim); add a test assertion for elementFromPoint/closest('#workspace') after open.

### F2 [Medium] Desktop rail (and header) sit above every overlay layer
- hutch-shell.css:31 z-index var(--layer-nav,100) = 100 on the sticky rail; hutch-shell.css:72 header 99.
- All floating overlay tokens top out at 50/60 (hutch-overlays.css:46-53), and hutch-popovers.css:181-183 gives .workspace z 46 — but the shell rule wins by specificity. SPA precedent: rail --z-rail 40 (style.css:140), overlays 42-70 above it.
- Consequence on server pages: a select/picker/popover/dropdown anchored in content and overlapping the 304px rail renders beneath the rail; header-anchored floating surfaces render beneath the header. Static review only; verify by opening a hutch-select picker near the left edge of /models or the bot page and comparing rects/z-order, or evaluate computed z-index of .hutch-shell > .workspace (100) vs the open picker (46).
- Suggested fix: put the rail/header on the documented base layer (e.g. 40/39) and let overlay tokens sit above; keep the open drawer above the scrim (F1).

### F3 [Medium] Still two drawer implementations despite "one strategy"
- SPA: app.js:2458-2501 (openWorkspace/closeWorkspace, .workspace.open class, inert, Tab trap incl. inputs, Escape/focus restore, scrim).
- Server: hutch-shell.js:8-79 (mirror, .open + .hutch-shell.nav-open classes, trap without inputs, same Escape/focus return).
- Already-divergent details: SPA toggles .workspace.open and relies on style.css; server toggles .open and adds .nav-open for hutch-shell.css:151; SPA trap includes input:not([disabled]) (app.js:2491) while server's does not (hutch-shell.js:61-63); ids differ by shell (#primary-nav exists only on server).
- Risk: F1/F2 fixes and any future drawer change must be made twice; tests only cover each shell separately (e2e server test + SPA mobile test), so drift is silent. Verify with
  `grep -n "openWorkspace\\|openDrawer\\|nav-open" src/hutch/server/static/app.js src/hutch/server/static/hutch-shell.js`.
- Suggested fix: extract the drawer into one static module used by both shells, or at minimum
  cross-link the two implementations and add a shared behavioural checklist test.

### F4 [Medium] "Same app-shell sidebar" is true for destinations, not for contents
- Server macro renders brand + primary + More + footer only (sidebar.html:13-42). It has no roster, roster search, New assistant, search palette button, or sidebar collapse control; SPA has all of these at index.html:66-77 and 97-107.
- hutch-shell.css has no collapsed-rail implementation (only --shell-rail 304 and the <=900 drawer); server pages therefore cannot reflect a user's SPA collapsed preference and lose assistant switching/search while on /models, /usage, bot detail, etc.
- Not a regression (server pages previously had no sidebar), but the claim in hutch-shell.css:1-7 and nav.py:1-5 should be scoped; decide follow-up (server-rendered roster is possible from store.list_bots()) or explicitly document the reduced shell.
- Verify: `document.querySelector('#workspace #bot-search, #workspace #sidebar-toggle, #workspace .ws-roster')` -> null on any server page.

### F5 [Medium] "Needs you" is a destination on server, a dialog command in SPA — and its active key is unreachable
- SPA: <button id="needs-you-open"> with no href/data-nav (index.html:82); app.js:2678 uses it.
- Server: <a href="/#/approvals" data-nav="approvals"> (sidebar.html:24-27; nav.py:14).
- Clicking the server row loads the SPA and renderApprovals immediately rewrites the hash to #/chat (app.js:1889, 7938-7939), so app.js marks Chat current; nav.py's approvals key can never be aria-current in either shell (no server route renders nav="approvals"; SPA has no such element). The consistency test intentionally excludes approvals from anchor parity (test_navbar_consistency.py:106, 117-120) and only checks its label.
- This is defensible (same end state: approval dialog), but it is not "the same destination row": document it, or render the SPA row as an <a href="#/approvals" data-nav="approvals"> with a click handler that opens the dialog, and keep the key active until the dialog closes.
- Verify: from /usage click Needs you -> after load location.hash is #/chat and .ws-nav a[aria-current] is Chat.

### F6 [Medium] Server active destination is fail-open for new routes
- pages.py:70-77 computes `active = normalize_nav(nav)` from the page() argument, defaulting to "". The error handler calls page() with no nav (pages.py:149), so error pages render a sidebar with zero current destination; login/pair explicitly use chrome=False (pages.py:692,697).
- Any future full-page route that forgets nav= silently renders a shell with no aria-current. Only six routes are exercised by test_navbar_consistency.py:139-146.
- Suggested fix: derive the active key from request.url.path when nav= is empty (path-to-key map in nav.py), or assert in tests that every chrome page has exactly one aria-current (the test already asserts exactly one for its six cases).
- Verify: `grep -n "page(request" src/hutch/server/pages.py src/hutch/server/pages_models.py src/hutch/server/pages_usage.py` and check each call passes nav= (login/pair/onboarding/error are the intended exceptions).

### F7 [Low] Server contextual header is structurally empty
- base.html:69-83 renders header.app-top with nav-toggle, an EMPTY .app-top-context div (line 82) and .app-top-status (Stop all + live pill). No Jinja block and no server JS fills .app-top-context (grep templates: only base.html mentions it), so every server page shows 56px of dead space to the right of the toggle; page identity stays in the content h1/crumb.
- Not a functional regression, but "slim contextual header" is currently mostly blank; fill it with page title/breadcrumb or shrink it. Verify: `document.querySelector('.app-top-context').children.length` -> 0 on /models.

### F8 [Low] Legacy residue from the removed topbar
1. hutch-popovers.css:183 `#primary-nav { z-index: var(--hutch-z-modal); }` — old overlay rule; now targets the static sidebar nav (no position -> inert, but stale). Loaded by both shells (index.html:51, base.html:42). Remove.
2. responsive.js:30-32 and 42-44 still measure `document.querySelector(".topbar")` for --topbar-h; .topbar exists in neither shell now (base.html has no topbar), so --topbar-h is never published; header comment line 8 is stale.
3. responsive.css:152-153 retains the dead `var(--topbar-h, 54px)` fallback contract; hutch.css:103 .run-head also keeps `top: var(--app-top-h, 54px)` plus the hard-coded `rgba(5,7,10,.94)` background, while hutch-shell.css:167 overrides the effective top.
4. brand.css:13 `.ws-brand .brand, .topbar .brand` — .topbar selector is dead.
5. onboarding_pagekit.py:73 still passes the obsolete `"nav_items": []` context.
6. app.js:2680 `$('[data-nav="approvals"]')` is dead in the SPA (no such element; server shell does not load app.js).
7. onboarding.css:26 comment still speaks of "no topbar" (stale wording after the global removal).
Verify each with the cited line; all are cleanup, none functional. The rewritten sheets themselves are clean: no .nav a/.topbar/#primary-nav overlay rules remain in hutch.css/hutch.js/responsive.css/no-js-nav.css/base.html.

### F9 [Low] Token purity nit + confirm intended SPA visual deltas
- hutch-shell.css:37-40 derives the rail colour with `color-mix(in srgb, var(--color-semantic-bg) 82%, black)`. It reproduces DESIGN surface-sidebar #070709 and avoids a second palette literal, but `black` is still a literal colour keyword in new CSS (item 6 asked for no literals outside generated sheets). Consider promoting a `--color-semantic-sidebar` token so the SPA --sidebar literal (style.css:42) and this derivation share one source.
- Current SHA removed the shared sheet's .workspace background override (previous hutch-nav.css:14-17), so SPA rail colour is unchanged now; the remaining intended SPA deltas are the shared active row (3px brand inset + weight 600, hutch-nav.css:61-67 vs old studio.css:396-397) and footer/badge token surfaces. Confirm by screenshot; no functional impact found.

### F10 [Low] Icon parity drift between shells
- SPA renders empty <span class="nav-ico"> for More summary and Needs-you (index.html:82,84); CSS masks exist only for `a[data-nav=...]` (style.css:279-286), while server renders icon("more") and icon("shield") (sidebar.html:26,30; nav.py:11-14; _icons.html icons exist). Result: SPA shows a blank 16px icon column for those two rows; server shows glyphs. Tests only compare labels/hrefs/data-nav.
- Verify on SPA: `getComputedStyle(document.querySelector('#monitor-nav summary .nav-ico')).backgroundImage` -> "none".

### F11 [Low] Shared-component markup asymmetry
- Server nav has `id="primary-nav"` (sidebar.html:23); SPA nav has no id (index.html:79). Tests and e2e target #primary-nav on server pages only. Also brand aria-label differs ("hutch - open main chat" vs "hutch — open main chat"). Fold into the shared-component contract if the sheet is meant to be identical.

### F12 [Low] Error pages: shell with no active destination; auth/onboarding chrome-less
- pages.py:149 renders error.html through page() with no nav -> shell with no aria-current (intentional? acceptable for errors, but not tested/documented).
- login/pair use chrome=False (pages.py:692,697) and onboarding renders with chrome=False/nav empty (onboarding_pagekit.py:70-75), so the "every full server page renders the sidebar" claim is literally false for those three surfaces — presumably intentional (auth/setup should not expose app navigation); state it in the code comment so nobody "fixes" it later.

### F13 [Low] Content-density regression risk from the 304px rail on wide server tables/bars
- Page-level breakpoints are viewport-based while the shell consumes 304px. Example: hutch-pages.css:64 keeps .models-hw-bar at repeat(4,1fr) and only collapses at <=860px (hutch-pages.css:69). At viewports 901-1024 the content column is ~597-720px (rail + gutters), so four cells are ~130-160px wide. Verify /models at 1024x768 (computed grid tracks + no overflow); consider container queries or a slightly higher collapse breakpoint. The e2e test only asserts document overflow, not internal density.

### F14 [Low] Duplicated safe-area/chrome ownership
- responsive.css:41-45 and 132-137 still style .app-top and .workspace insets for "server pages", while hutch-shell.css:41-44 and 76-78 own the same properties for the server shell (shell loads later and wins). Harmless today, but two owners invite drift; consolidate in hutch-shell.css and leave responsive.css to SPA-only rules (as the comments now claim).

### F15 [Low] Drawer a11y remaining gaps (same class as SPA, worth fixing with F1)
- The drawer is not aria-modal/role="dialog" and the background .hutch-workspace is not inert while open (only the rail is inert while closed: hutch-shell.js:20-22; app.js:2462). Focus is Tab-trapped, Escape restores focus, and the toggle/close names are correct — but pointer/AT can still reach page content, and in the current stack (F1) the header stays interactive over the scrim. Fixing F1 by layering alone leaves the background reachable; add `.hutch-workspace.inert` or aria-modal semantics while open (mirror in app.js).
- Duplicate accessible name: while open both #nav-toggle and #ws-close are named "Close menu" (sidebar.html:20; hutch-shell.js:29-30). Acceptable, but a distinct "Close navigation" would be clearer.

### F16 [Info] Untracked deliverables
- `git status` shows the consolidation files are untracked: src/hutch/server/nav.py, static/hutch-nav.css, static/hutch-shell.css, static/hutch-shell.js, templates/macros/sidebar.html, tests/test_navbar_consistency.py. Ensure they are staged; this review's own artifact and reports/ are untracked as well.

## What was verified as correct (so it is not re-litigated)

- One sidebar on every chrome route, with aria-current as the only active signal (no `class="active"`): templates/base.html:63-98 + macros/sidebar.html:14-42; server-side active keys for /models (pages_models.py:62-67), /usage (pages_usage.py:20,64), /legacy/connections (pages.py:580-584), /bots/{name} (pages.py:286-290), /bots/delete (pages.py:248-251), /bots/{name}/delete (pages.py:295-298). Delete routes map to "bots" via nav.py:36-48 so Manage assistants is current (matches DESIGN "deletion is an assistants action").
- Item parity: nav.py:11-32 vs static/index.html:79-118 (13 anchors, same order/labels/data-nav; Models/Usage now carry data-nav, index.html:91-92); Needs-you label parity handled separately (test_navbar_consistency.py:101-120). Server-side More opens for every More key (page():76, nav.py:34-48).
- A11y plumbing: skip link target is focusable (base.html:62,91; main tabindex="-1"), server tests assert it (test_navbar_consistency.py:162-163); toggle/close accessible names and aria-expanded/aria-controls (base.html:71; sidebar.html:20; hutch-shell.js:29-30,43-44); inert while closed + Tab containment + Escape focus return (hutch-shell.js:20-22,33-34,57-72); reduced-motion and forced-colors blocks exist (hutch-nav.css:165-178, hutch-shell.css:159-161) and are e2e-covered.
- Responsive skeleton: single 900px drawer breakpoint (hutch-shell.css:139; SPA style.css:1658-1671 + app.js:2461), fixed 56px header (hutch-shell.css:13-17,69-81; asserted by e2e), no-JS fallback stacks the rail and hides controls (no-js-nav.css:9-31), --vvh fallback keeps drawer height sane.
- Tokens: new nav/shell CSS contains no hex/rgb/rgba literals (grep); every var() resolves to brand-tokens.css/hutch-overlays.css/responsive.css or is a runtime token with a fallback (--vvh, --hutch-z-*, --layer-nav, --safe-*). hutch-nav.css loads after studio.css in the SPA (index.html:48 after line 27) and after hutch.css in base.html (base.html:38-39), so cascade order is deliberate.
- SPA side effects checked: shared sheet no longer overrides .workspace surface in current SHA; hutch-nav.css is loaded last in the SPA and only touches .brand, .ws-nav*, .ws-foot*, .nav-ico, .ico — no roster/composer/layout selectors. The intended SPA visual change is the shared active-row treatment only.
- Legacy code removed cleanly from the rewritten files: no topbar markup in base.html, no .nav/.topbar overlay CSS in hutch.css, no nav IIFE in hutch.js (ownership note at hutch.js:183-185), no old overlay rules in responsive.css/no-js-nav.css.
- Tests are updated for the new shell: tests/test_navbar_consistency.py (parity + one-sidebar/active assertions, six routes), e2e test_browser.py:7113+ (12 nav links, 56px header at five viewports, inert/focus trap/Escape, no-JS, reduced motion, forced colors, text-spacing).

## Limits
Static review only. I did not run pytest, Playwright, or a server; z-order and visual claims are CSS/DOM reasoning with exact verification steps above. The tree changed under this review (latest observed edits 02:52:21-02:52:34), so re-check SHAs and re-run the updated e2e tests before merge.
