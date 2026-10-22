# Recon — Hutch front end (main@ceb9d36b, 2026-10-22)

## Stack and rendering

- **SPA** at `/`: vanilla ES, hash-routed (`src/hutch/server/static/app.js`, ~12.4k lines;
  `index.html`), plus feature scripts (`skills.js`, `persona.js`, `widgets.js`, `computer.js`,
  `model-switcher.js`). No framework or bundler by product constraint (PRODUCT.md).
- **Server pages**: Jinja2 + HTMX templates (`src/hutch/server/templates/`) for login, pairing,
  models, usage and legacy routes, styled by `static/hutch.css` + `hutch-pages.css`.
- **Marketing site**: `website/` (separate surface, shared tokens).
- **Security**: strict CSP (`script-src 'self'`, no inline script). Any injected test script must
  bypass CSP in the test browser context only.

## Design system and sources of truth

- Token source: `website/tokens.json` → `scripts/build_site_tokens.py` → `static/brand-tokens.css`
  → daisyUI theme in `app/src/input.css` (compiled to committed `static/ui.css`) and the custom
  properties at the top of `static/style.css` (spacing `--s-1…8`, radii `--r-*`, z-index
  `--z-rail 40 / sheet 45 / modal 50 / toast 60 / skip 70`, durations, colours).
- Written spec: `DESIGN.md` (frontmatter tokens + rules: Measure Rule 72ch, One-Ink Rule, Amber Rule,
  Scale Rule, Measured Rule; status chip "dot + word", `✕ failed`).
- Theme: dark only by design (`color-scheme: dark`); no `prefers-color-scheme` or
  `prefers-contrast` handling; a `forced-colors` block exists in `style.css`.

## Conflict and drift scan (hand-written CSS)

| File | lines | hex | rgb/rgba | z ≥ 100 | `!important` |
|---|---|---|---|---|---|
| style.css | 2955 | 12 | 43 | 0 | 10 |
| hutch.css | 378 | 0 | 17 | 2 | 1 |
| widgets.css | 456 | 1 | 0 | 0 | 3 |
| hutch-pages.css | 94 | 0 | 2 | 0 | 5 |
| brand-tokens.css (generated) | 115 | 38 | 14 | 0 | 0 |

Raw z-index values outside the scale: `999` (3), `30` (3), `40` (2). Load order: `ui.css`
(all `@layer`) then unlayered `style.css`, so unlayered rules win regardless of specificity inside
layers. Eighteen `all: unset` resets in `style.css` (root cause of F-01). A generic `.btn-row` was
used 22 times with no style (D-09).

## Routes in scope

SPA: `#/chat`, `#/chat/<bot>`, `#/conversation/<id>`, `#/overview` (Activity), `#/schedules`,
`#/runs` (Work history), `#/runtime`, `#/skills`, `#/bots` (Manage assistants; full manager at ≥10
assistants), `#/connections` (Apps & AI), `#/bot/<bot>` (assistant settings), `#/run/<id>`,
`#/settings`, `#/approvals` (Needs you `<dialog>`). Server: `/login`, `/pair`, `/models`, `/usage`,
`/legacy/*` (titled 404). Site: `website/index.html`.

## Shared components and blast radius

Legacy button variants (`button.primary|ghost|danger|small`, `a.primary|ghost`) on every route; the
navigation sheet and pending-work reminder on every route; chat header (`.app-top`) on every chat
route; status chips (`.status`) on chat, Activity, Work history, run detail, assistant cards.

## Existing quality gates

`uv run pytest --ignore=tests/e2e` (fast), `tests/e2e/` Playwright suites incl.
`test_wcag_fixes.py`, `test_design_system.py`, `test_browser.py` (123 tests), `test_website.py`.
No CSS linter. Note: some e2e tests write screenshots into tracked
`docs/realignment/artifacts/ui-audit-2026-10-20/`; running them dirties the tree.

## Feature-parity inventory (must not lose)

Skip link; sidebar docking; phone sheet with Close/Escape; roster search, pin, options; Needs you
dialog (approve once / always allow / deny / open, review details, browser notifications, recently
decided); chat composer (send, stop, + menu with uploads, export, rehearse, Enter-sends, budget);
conversation switcher, search, options; Review and Stop in the header; Work history search, status
filter, paging; schedules pause/resume, run now, skip next, edit; runtime automation pause/resume and
source actions; Apps & AI tiles; assistant settings disclosure; Settings form; server page forms.
All remain after the change set (verified by the existing suites plus RUNLOG parity checks).
