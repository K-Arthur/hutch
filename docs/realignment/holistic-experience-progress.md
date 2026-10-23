# Repo-wide experience work — active checkpoint

## Authority

User approved **Task-first pages** on 2026-10-23. Research, alternatives and approval:
[`../research/holistic-experience-2026-10-23.md`](../research/holistic-experience-2026-10-23.md).
Current `DESIGN.md`, `PRODUCT.md` and repo instructions govern; older square/brutalist
surface guidance is stale. Preserve tokens/identity, factual claims and permission boundaries.

Latest steering: screenshots are examples, **consistency across the entire repo** is
required. Cover every frontend family, including server-rendered and phone surfaces.
Do not call isolated screenshots or passing first-run checks repo-wide validation.

## Acceptance and coverage

| ID | Acceptance | Status |
|---|---|---|
| A1 | Inventory all authored frontend surfaces and shared components | In progress; source inventory below |
| A2 | Consistent layout/type/spacing/controls/icons with purposeful surface differences | Partial uncommitted app foundations; marketing overview committed |
| A3 | Long setup/configuration on task pages, dialogs for short decisions; preserve navigation/drafts | Setup moved to page, uncommitted; behavior tests/recovery review pending |
| A4 | Marketing follows same rules; expanded content works without stretching unrelated columns | Overview + FAQ verified/committed; icons uncommitted; other sections pending |
| A5 | Actual desktop/tablet/phone and loading/error/empty/focus/expanded-state inspection | Partial only; coverage matrix still needed |
| A6 | Meaningful regressions + relevant suite + necessary code review | First marketing 5 tests passed; remaining checks/review pending |
| A7 | Progressive commits and relevant documentation | First commit ef33bfc3; this checkpoint tracks remainder |
| A8 | Integrate into main/master, verify integration, remove task worktree/branch | Pending; do not integrate unfinished work |

## Source inventory / remaining review families

- SPA shell and routes: `static/index.html`, `app.js`, `style.css`, `app/src/input.css`.
  Chat/first-run, Chat library, Needs you, Activity, Scheduled work, Work history,
  Runtime, Skills, assistant manager/detail, run detail, Apps & AI, workspace settings.
- Additional widgets: `skills.{js,css}`, `model-switcher.{js,css}`, `widgets.{js,css}`,
  `computer.{js,css}`, `persona.js`. Inspect actual menus/pickers, not just closed controls.
- Phone views are rendered in `app.js`; pairing/login use `pair.js`, `passkey-login.js`.
- Server pages: `templates/base.html`, login/pair/error, models/usage, legacy connections,
  and bot/run/approval/home templates and partials. Identify active versus redirected
  routes before assuming each template is user-facing. Styles: `hutch.css`,
  `hutch-pages.css`; behavior: `hutch.js`. Do not edit vendor bundles.
- Marketing: `website/index.html`, `styles.css`, `src/input.css`, `site.js` and generated
  CSS. Remaining long technical disclosures, examples/icons, responsive nav/FAQ and proof
  captures must be checked together.

## Current implementation and evidence

Branch `feature/holistic-experience`, worktree
`/home/kevina/.local/share/opencode/worktree/5b4899/holistic-experience`.
The first commit was created on detached HEAD by the worktree tool; the named branch
now contains it. Original checkout has unrelated backend/test edits—preserve them.
Original research note also remains untracked there; reconcile only our own duplicate.

Committed `ef33bfc3`: marketing workflow explanations moved below compact overview;
body-size explanation text; missing FAQ class fixed; docs + keyboard/geometry regression.
Five focused pytest tests passed using existing Chromium 1248 launch override.

Uncommitted: input font normalized; select dark native options/44px height; helper weight;
Activity aligns widths and leads with active/empty state; Skills rows/compact empty state/
import layout and context-header Refresh; missing Runtime/Skills icons; operational
container 1040px; page titles deduplicated; programmatic heading focus ring removed;
native form controls use 16px/44px; marketing example icons unified and generic app icon
returned to brand color. Assistant setup now uses `#/assistant/new` with a retained page
object and full tab-scoped session persistence (250ms debounced save, restore notice,
Save draft and leave, Discard draft, clear on create). Reload recovery was reproduced in
an isolated server: restored step and model route plus notice. Fixed button/listener
arguments that previously passed click Events as template names. **Not yet verified:**
source/duplicate flows, create success in full suite after these changes, model-connect
return, in-flight navigation races. Tests changed: quick creation now expects page IDs,
reload/restore, discard, and a fresh form; workspace geometry now scrolls the page actions
and tolerates hover-transition channel drift (300ms settle + ±2). Template-gallery test now
leaves the page and waits for chat.
Disk: `/tmp` repeatedly reaches 100% from unrelated trees; use TMPDIR and
`--basetemp` under `/home/kevina/.local/share/opencode/hutch-tmp`. Temporary screenshots
moved to `/home/kevina/.local/share/opencode/hutch-shots/` after `/tmp` ENOSPC aborted two
test runs at trace writing (assertions had passed). Do not delete unrelated `/tmp/varve-*`
or other agents' temporary trees.

Inspected screenshots (temporary `/tmp/opencode/hutch-holistic-review/`): original app
chat/settings/site; changed marketing workflow at 1440/768/390; changed app Activity,
Skills, settings and setup at 1440. Later container changes invalidate those last app
captures. Mobile workflow captures caught transition opacity; recapture settled/reduced.

## Environment and next actions

- Existing Python environment: `/home/kevina/CodingProjects/hutch/.venv/bin/python`.
- Existing browser: `/home/kevina/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome`.
  Python Playwright expects unavailable revision 1243; use explicit executable_path,
  including a process-local BrowserType.launch override for pytest. No dependency install.
- node_modules is an **untracked symlink** to original checkout dependencies; never commit.
- `npm run build:css` works. Syntax: `node --check src/hutch/server/static/app.js` passed
  before latest small edits. Builds generate ui.css/site CSS and stamp site asset hashes.
- Worktree review servers: app 18891, website 8100; original review 18890/8099. App uses
  `/tmp/opencode/hutch-review-state`. Do not run real model/provider tasks for visual QA.
  Processes may die on host restarts. Use independent fixture state for mutations/tests.
- Next: finish source/route inventory and shared rules, harden/test the active setup-page
  slice (do not propagate an unverified navigation pattern), commit verified foundation
  work; then complete remaining frontend families and full validation/review/integration.
- Required final evidence refresh: marketing validation hashes in prior approval-triage
  evidence and proof screenshots when affected. Tests can rewrite tracked evidence; inspect
  generated churn and use HUTCH_TEST_ARTIFACTS_DIR where supported.
