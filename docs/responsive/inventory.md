# Responsive Adaptation - Phase 0.5 Scored Inventory

Date: 2026-10-29. Scope: Hutch working tree at commit 2a89909a plus the
another-session uncommitted brand/dashboard changes that are present in the
working tree (read-only). Method: enumerate source files only, score by
path/name heuristic, read the highest-risk files and the mandated entry points,
then stop once the stack, CSS strategy, breakpoint tokens, global-style homes,
navigation homes and densest data views are established. No source file was
modified. Generated CSS was excluded from inventory and reading per AGENTS.md.

## Bounded-discovery cap applied

- Enumerated: 86 source files (25 CSS sources including the marketing
  stylesheets, 31 Jinja templates, 24 static JS/HTML files, 3 remaining
  marketing sources, 3 build/config/entry files), plus AGENTS.md and package
  scripts.
- Scored: all 86.
- Read: 34 files as primary or range reads (17 CSS sources, 7 templates, 5
  static JS/HTML files, all 3 remaining marketing sources, 2 of 3
  build/config/entry files), plus focused grep/line-range passes over 8 more.
- Not read: 52 lower-scored files (24 templates, 19 static JS/HTML, 8 product
  CSS sources, app.py). Backlog below.
- Generated or build-output CSS deliberately not read: src/hutch/server/static/ui.css,
  src/hutch/server/static/model-switcher.css, website/app.css,
  website/styles.min.css, website/tokens.css.

## Stack summary (stop condition met)

- Framework: FastAPI + Jinja2 server-rendered pages with HTMX upgrades
  (src/hutch/server/pages.py:1-6; templates/base.html) and a second,
  hash-routed SPA dashboard served by the same app
  (src/hutch/server/static/index.html; src/hutch/server/static/app.js, 14,345
  lines).
- CSS strategy: two coexisting systems. (1) Tailwind v4 + daisyUI component
  layer compiled from app/src/input.css into ui.css, whose unlayered shell
  rules are then overridden by the legacy hand-written sheets loaded after it;
  (2) hand-written, token-driven component sheets in
  src/hutch/server/static/*.css. Both share brand tokens generated from
  website/tokens.json (website/tokens.css and static/brand-tokens.css). Server
  pages skip ui.css/style.css and load a smaller subset
  (templates/base.html:14-30). Marketing is Tailwind v4 + daisyUI
  (website/src/input.css) plus website/styles.css; app.css and styles.min.css
  are generated.
- Global styles: layout shell and shared components in
  src/hutch/server/static/style.css (SPA) and src/hutch/server/static/hutch.css
  (server pages); form system in hutch-forms.css + hutch-form-controls.css +
  hutch-select.css; composer in hutch-composer.css +
  hutch-composer-context.css; transcript messages in hutch-messages.css;
  marketing in website/styles.css.
- Breakpoint tokens: none declared as tokens. Values are literal px in each
  stylesheet. Across the 25 CSS sources audited (product and marketing) there
  are 23 distinct width values:
  359, 360, 420, 480, 520, 521, 560, 561, 600, 620, 640 (36 uses), 641, 720,
  760, 800, 900, 901, 940, 1000, 1001, 1023, 1100, 1400. Height-based queries
  exist only in studio.css (max-height 760 and 520). Container queries exist in
  app/src/input.css (18rem/16rem), studio.css (container firstrun/settings) and
  style.css service tiles.
- Navigation: server pages render nine top-level links
  (src/hutch/server/pages.py:37-47) in templates/base.html:40-61, with the
  collapse/overlay behaviour in hutch.css:328-343 and hutch.js:184-219; SPA
  uses a sidebar + drawer (src/hutch/server/static/index.html:51-114,
  style.css:380-408 and 1680-1692, app.js:2500-2552); marketing uses a sticky
  navbar + native dialog drawer (website/index.html:234-288,
  website/styles.css:275-297, website/site.js:46-65).
- Densest data views: SPA conversation transcript with tool groups and
  approval gates (hutch-messages.css, studio.css) and the SPA runs/usage
  views rendered by app.js; server-rendered densest views are the runs table
  (templates/_runs_table.html) and the usage dashboard
  (templates/usage.html:12-76) with four tables, plus models tables
  (templates/models.html:33-104). Marketing's densest block is the availability
  table (website/index.html:805-830).

## Scored inventory - CSS sources

Score: H = layout/nav/header/sidebar/shell/modal/drawer/dialog/form/table/grid/
card/hero/marketing naming; M = component sheet with layout potential or
runtime-positioned surface; L = token/utility/config-like. Read: Y = read in
this pass, P = partial/line ranges, N = not read (backlog).

| Path | Score | Why | Read |
|------|-------|-----|------|
| app/src/input.css | H | Tailwind source for SPA shell, rail width, connections/settings components; container queries | Y |
| app/src/model-switcher.css | H | Composer model menu sizing/positioning at 560/640 and coarse pointers | Y |
| src/hutch/server/static/style.css | H | SPA shell (sidebar/topbar/chat scroll/composer seat), modals, drawer, tables, all SPA breakpoints | P |
| src/hutch/server/static/studio.css | H | SPA header wrapping, short-height queries, palette dialog, first-run layout, model menu | P |
| src/hutch/server/static/hutch.css | H | Server-page shell: topbar, nav breakpoints, tables, run sticky header, overlays | Y |
| src/hutch/server/static/hutch-pages.css | H | Server-page connections grid, auth panels, models/usage table collapse | Y |
| src/hutch/server/static/hutch-composer.css | H | Composer seat replacement, safe-area padding, touch targets | Y |
| src/hutch/server/static/hutch-forms.css | H | Form root/two-up grid and field stack (part 1) | P |
| src/hutch/server/static/hutch-form-controls.css | H | Two-up collapse at 1000, inline bars at 720, coarse pointer density | Y |
| src/hutch/server/static/hutch-select.css | M | Select skin and 44px coarse step; progressive picker | P |
| src/hutch/server/static/controls.css | H | Shared fixed-position popup anatomy, sheet layout, coarse row height | Y |
| src/hutch/server/static/hutch-messages.css | M | Transcript message responsive rules and coarse targets | P |
| src/hutch/server/static/widgets.css | M | Widget cards/charts/table wrappers at 480 and coarse | P |
| src/hutch/server/static/computer.css | M | Computer-use panel, 60vh image cap, 480 actions | P |
| src/hutch/server/static/skills.css | M | Skill grid/picker menu at 720 | P |
| src/hutch/server/static/tasks.css | L | 17 lines, no media queries | N |
| src/hutch/server/static/hutch-composer-context.css | M | Composer context strips; 640/coarse rule | N |
| src/hutch/server/static/brand.css | L | 19-line wordmark lockup | N |
| src/hutch/server/static/brand-tokens.css | L | Generated token mirror | N |
| src/hutch/web/styles/hutch-tokens.css | L | Shared token layer; only reduced-motion query | N |
| src/hutch/web/styles/hutch-surfaces.css | M | Button/approval/run-transcript surfaces incl. 640/coarse rules | N |
| src/hutch/web/styles/hutch-bot-card.css | M | Bot card responsive and coarse rules | N |
| src/hutch/web/styles/hutch-theme-overrides.css | L | Theme scopes | N |
| website/styles.css | H | Marketing hero/nav/drawer/sections/table/footer + all site media queries | Y |
| website/src/input.css | M | Marketing Tailwind/daisyUI config, shared radius tokens | Y |

## Scored inventory - Jinja templates (server pages)

| Path | Score | Why | Read |
|------|-------|-----|------|
| templates/base.html | H | Viewport meta, stylesheet/script order, topbar and nav | Y |
| templates/_form.html | H | Form primitives used by every server form | Y |
| templates/run.html | H | Sticky run header, transcript and meters | Y |
| templates/usage.html | H | Densest tables, meters grid, two-column panels | Y |
| templates/runs.html | H | Filter bar and paginated results table | Y |
| templates/_runs_table.html | H | Data table + overflow wrapper + hide-sm columns | Y |
| templates/bot_new.html | H | Two-up create form | Y |
| templates/bot.html | H | Two-col settings, inline forms, memory/allows | N |
| templates/bots.html | M | Card grid and inline pause/resume forms | N |
| templates/models.html | H | Three wrapped tables and price form | N |
| templates/connections.html | H | Largest form surface, many inline forms | N |
| templates/home.html | M | Home grid (three columns) | N |
| templates/_home_lists.html | M | Run/bot list rows and inline forms | N |
| templates/login.html | M | Auth panel form | N |
| templates/pair.html | M | Device pairing panel | N |
| templates/approvals.html | H | Approval queue cards | N |
| templates/_approval_list.html | M | Approval list rows | N |
| templates/_approval_card.html | H | Approval decision forms | N |
| templates/_approval_resolved.html | L | Resolved row | N |
| templates/_wait.html | M | Wait banner | N |
| templates/_wait_fragment.html | L | Fragment | N |
| templates/_events.html | H | Event list rows and resume form | N |
| templates/_events_more.html | L | Fragment | N |
| templates/_events_fragment.html | L | Fragment | N |
| templates/_message.html | M | Message macro | N |
| templates/_meters.html | M | Meter bars (inline widths) | N |
| templates/_fact_purge.html | L | Purge form | N |
| templates/_icons.html | L | Inline SVG macros | N |
| templates/error.html | L | Error page | N |
| templates/bot_delete.html | M | Confirmation form | N |
| templates/bot_delete_pick.html | M | Bot picker | N |

## Scored inventory - static JS/HTML

| Path | Score | Why | Read |
|------|-------|-----|------|
| src/hutch/server/static/index.html | H | SPA document head (viewport-fit), app shell markup, drawer, dialogs | Y |
| src/hutch/server/static/app.js | H | Shell/drawer breakpoints, sidebar docking, popup anchoring callers, runs rendering, paired-phone renderer | P |
| src/hutch/server/static/hutch.js | H | Server-page nav overlay controller (1400px matchMedia) | P |
| src/hutch/server/static/controls.js | H | Fixed popup placement with visualViewport/sheet fallback | Y |
| src/hutch/server/static/composer.js | M | Auto-grow/IME keyboard semantics for the composer | N |
| src/hutch/server/static/palette.js | M | Command palette dialog behaviour | N |
| src/hutch/server/static/widgets.js | M | Widget cards/charts/tables (wrapped tables) | P |
| src/hutch/server/static/tasks.js | M | Task views and board | N |
| src/hutch/server/static/skills.js | M | Skill picker menu | N |
| src/hutch/server/static/computer.js | M | Computer-use preview | N |
| src/hutch/server/static/connection-browser.js | M | Connection directory flow | N |
| src/hutch/server/static/channels.js | M | Channel setup forms | N |
| src/hutch/server/static/persona.js | M | Persona settings | N |
| src/hutch/server/static/hutch-forms.js | M | Form validation/described-by wiring | N |
| src/hutch/server/static/hutch-select.js | M | Select picker | N |
| src/hutch/server/static/model-switcher.js | M | Model menu | N |
| src/hutch/server/static/markdown.js | L | Renderer | N |
| src/hutch/server/static/fact-purge.js | L | Purge dialog | N |
| src/hutch/server/static/bot-deletion.js | L | Delete flow | N |
| src/hutch/server/static/campaign-report.js | M | Report form/table | N |
| src/hutch/server/static/passkey-login.js | L | Auth | N |
| src/hutch/server/static/pair.js | L | Auth | N |
| src/hutch/server/static/redesign-preview.html | L | Preview artifact | N |
| src/hutch/server/static/redesign-preview.js | L | Preview artifact | N |
| src/hutch/server/static/vendor/* | L | Vendored htmx/uPlot | N |

## Scored inventory - marketing and config/entry

| Path | Score | Why | Read |
|------|-------|-----|------|
| website/index.html | H | All marketing sections, sticky navbar, drawer dialog, availability table | P |
| website/styles.css | H | Site layout, hero, tables, responsive and motion rules | Y |
| website/src/input.css | M | Tailwind/daisyUI site build config | Y |
| website/site.js | M | Drawer, tabs, reveal, pointer agent | Y |
| website/tokens.json | L | Token source (44px target, radii, typography) | Y |
| package.json | L | Build scripts (Tailwind CLI targets) | Y |
| src/hutch/server/pages.py | H | Page entry, NAV list, template context | P |
| src/hutch/server/app.py | M | App/router entry (7,256 lines); page routes registered in pages.py | N |

## Files actually read, with purpose

- AGENTS.md - hard rules, directory map, generated-CSS exclusions.
- package.json - build pipeline for app and site CSS; confirms sources vs
  generated outputs.
- src/hutch/server/templates/base.html - server-page head, viewport meta,
  stylesheet order, topbar/nav/footer.
- src/hutch/server/static/index.html - SPA head (viewport-fit=cover), shell,
  sidebar, dialogs, script order.
- app/src/input.css - Tailwind v4 + daisyUI source; shell rail width at
  1001px; container queries; connections/channel components.
- app/src/model-switcher.css - menu sizing and 560/640/coarse rules.
- src/hutch/server/static/hutch.css - server shell, nav overlay at 1400,
  tables, responsive block, coarse rules.
- src/hutch/server/static/hutch-pages.css - connections/auth/models/usage
  responsive rules.
- src/hutch/server/static/hutch-form-controls.css - form grid collapse and
  coarse density.
- src/hutch/server/static/hutch-composer.css - composer seat, safe-area
  bottom, touch target rules.
- src/hutch/server/static/controls.css - fixed popup shell and sheet layout.
- src/hutch/server/static/style.css (ranges 1-260, 350-620, 1660-2200,
  2380-2732 plus all media lines) - SPA shell, responsive block, drawer,
  bottom-sheet modals, touch targets, viewport units, final media queries.
- src/hutch/server/static/studio.css (ranges 430-569, 616-663, 730-829,
  940-1015 plus all media lines) - header wrapping, short-height rules,
  palette, first-run, model menu, coarse targets.
- src/hutch/server/static/hutch-forms.css (100-391) - form root/field/control
  contract used by all server forms.
- src/hutch/server/static/hutch-messages.css (285-318) - transcript responsive
  and coarse targets.
- src/hutch/server/static/widgets.css (425-456) - widget coarse/480 rules.
- src/hutch/server/static/computer.css (45-91) - computer-use visual caps.
- src/hutch/server/static/skills.css (90-108) - skill picker responsive.
- src/hutch/server/static/hutch-select.css (240-284) - select coarse/forced
  colors.
- src/hutch/server/static/app.js (ranges 2490-2620, 7820-8000; plus greps for
  tables, viewport APIs, popups, phone mode) - drawer/docking breakpoint,
  dialog focus restore, popup callers, runs card list, paired-phone renderer.
- src/hutch/server/static/hutch.js (180-269) - server nav overlay controller.
- src/hutch/server/static/controls.js - popup placement, visualViewport
  listeners, sheet fallback, controls.js:50-73/185-188.
- src/hutch/server/static/index.html / app.js backed by greps for
  `<table`, `visualViewport`, `matchMedia` etc.
- src/hutch/server/pages.py (1-120) - page entry and NAV list.
- website/index.html (ranges 1-90, 220-330, 355-465 plus greps) - head,
  navbar/drawer, hero, receipts section, availability table wrapper.
- website/styles.css - complete marketing custom layer and media queries.
- website/src/input.css - site Tailwind/daisyUI config.
- website/site.js - drawer/tabs/reveal/pointer-agent enhancement.
- website/tokens.json - size/target/typography tokens.

## Not-read backlog (lower scored; read next if a Phase 1 lead needs depth)

- Server templates: bot.html, bots.html, models.html, connections.html,
  home.html, _home_lists.html, login.html, pair.html, approvals.html,
  _approval_list.html, _approval_card.html, _approval_resolved.html,
  _wait.html, _wait_fragment.html, _events.html, _events_more.html,
  _events_fragment.html, _message.html, _meters.html, _fact_purge.html,
  _icons.html, error.html, bot_delete.html, bot_delete_pick.html.
- Static component scripts: composer.js, palette.js, tasks.js, skills.js,
  computer.js, connection-browser.js, channels.js, persona.js, hutch-forms.js,
  hutch-select.js, model-switcher.js, campaign-report.js, markdown.js,
  fact-purge.js, bot-deletion.js, pair.js, passkey-login.js,
  redesign-preview.*.
- CSS: tasks.css, hutch-composer-context.css, brand.css,
  src/hutch/web/styles/hutch-tokens.css, hutch-surfaces.css,
  hutch-bot-card.css, hutch-theme-overrides.css.
- src/hutch/server/app.py (route registration verified indirectly through
  pages.py; no layout content expected).
- Generated/build CSS and vendored assets intentionally excluded.
- Runtime rendering: no browser, Playwright or screenshot pass was performed
  in this phase; all findings are static-source findings.
