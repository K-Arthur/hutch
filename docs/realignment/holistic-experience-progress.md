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
| A1 | Inventory all authored frontend surfaces and shared components | Complete inventory; active, alias and compatibility routes distinguished |
| A2 | Consistent layout/type/spacing/controls/icons with purposeful surface differences | Implemented; representative families opened and verified in the validation record |
| A3 | Long setup/configuration on task pages, dialogs for short decisions; preserve navigation/drafts | Implemented and tested, including pending/failed/replaced/reloaded drafts |
| A4 | Marketing follows same rules; expanded content works without stretching unrelated columns | Implemented; body-sized shared reading rows, real proof and evidence hashes verified |
| A5 | Actual desktop/tablet/phone and loading/error/empty/focus/expanded-state inspection | Representative family/state coverage recorded; physical-device/screen-reader/native-zoom checks remain unrun |
| A6 | Meaningful regressions + relevant suite + necessary code review | Complete with disclosed limitations: combined fast coverage 3260 passed, 5 failed nodes; four workflow reruns pass, storage benchmark reproduces baseline failure; computer-control baseline failures remain; two-pass self-review recorded |
| A7 | Progressive commits and relevant documentation | Six implementation commits through 1d9b58da plus 01afd3ca checkpoint; final validation recorded below |
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

Committed in `9280b251`: input font normalized; select dark native options/44px height; helper weight;
Activity aligns widths and leads with active/empty state; Skills rows/compact empty state/
import layout and context-header Refresh; missing Runtime/Skills icons; operational
container 1040px; page titles deduplicated; programmatic heading focus ring removed;
native form controls use 16px/44px; marketing example icons unified and generic app icon
returned to brand color. Assistant setup now uses `#/assistant/new` with a retained page
object and full tab-scoped session persistence (250ms debounced save, restore notice,
Save draft and leave, Discard draft, clear on create). Reload recovery was reproduced in
an isolated server: restored step and model route plus notice. Fixed button/listener
arguments that previously passed click Events as template names. Tests changed: quick creation now expects page IDs,
reload/restore, discard, and a fresh form; workspace geometry now scrolls the page actions
and tolerates hover-transition channel drift (300ms settle + ±2). Template-gallery test now
leaves the page and waits for chat.

Committed `050c585f`: setup generation guards, pagehide flush, stale timer cancellation,
discard cleanup, scoped success navigation, restored-source checks and memory state, scoped
status announcements, YAML runtime restoration, and no automatic OpenCode tool grants in
blank setup or runtime switching. Explicitly chosen templates retain their reviewed tools.
Replacing a draft from an example/source now requires a short confirmation.

Committed `7e46e858`: compact operational header actions now have icons/accessible names
and remain reachable at 320px; compact buttons use 32px/14px and coarse-pointer buttons 44px.
Assistant settings uses the 1040px rail and panel-width-aware field tracks; range inheritance
no longer squeezes its slider/value. Server pages share scalable body/title roles and section
type; phone message prose uses body sans rather than raw-event monospace. Source navigation
labels match the SPA; Models and Usage are discoverable in More. Marketing technical details
use body-sized shared-width rows rather than narrow equal-height explanatory columns.
Committed `b312a4d9`: marketing first-run and response-style proof assets have fresh actual-browser captures and
truthful dimensions. Phone proof explicitly uses an extended 390×1200 viewport; ordinary
390×844 and 320×740 captures remain separate. Asset provenance is in
`artifacts/no-mock-setup/marketing-assets.json`.

Latest verified: syntax check and CSS build passed. Six setup tests passed (71.27s): guided
configuration, YAML import, coordinator purpose refinement, immediate reload/tab isolation/
discard timers, loading-navigation guard, and create/validation cleanup. Earlier duplicate/name
tests passed (2); selected-source/context/default tests passed (4), with refinement subsequently
fixed and now included in the six passing checks. Quick creation, template gallery, responsive
workspace routes and the two corrected marketing disclosure/copy tests passed earlier.
The six lifecycle tests in `test_task_pages.py` now pass (94.48s), including replacement
Cancel/confirm, failed replacement loading retaining an editable draft, and delayed creation
staying on the user's next page. Distinct requirements and standards self-review found/fixed
silent draft replacement and failed replacement invalidating the retained draft. Full
design/browser batch: **34 passed, 2 failed, 4 errors**. The first-run failure was the newly
required replacement confirmation; its updated test subsequently passed. The computer-control
fixture error and process-worker failure were reproduced on pre-overhaul `f29b299b` sources,
but those runs had contaminated subprocess imports; this does not establish baseline product
defects. The fresh isolated comparison below now reproduces both failure classes.
No backend workaround or safety relaxation made.
Computer panel suite separately passed **10 tests** with synthetic-frame captures inspected.
Broader interaction batch: **14 passed**, one locator counted the newly added Models nav link;
scoping that assertion to the dialog passed. Website: **35 passed** excluding stale evidence
manifest; subsequent final checks below cover the proof/boundary changes. Settings-width and header checks
passed at 1440/1280/900/390/320 as applicable; typed widget transcript and paired supervision
checks passed. Server-page check correctly found a 22px narrow title override; normalized to
the shared 24px role and its rerun passed. `/legacy` is the SPA alias, not a second home template.

Earlier fast suites were interrupted or used a defective local runner. The external wrapper
now has a `__main__` guard (all four admission tests passed), exports the selected tree's
`src` and root through `PYTHONPATH` for workers, and uses short temporary paths. The old
long-path full run has failures involving schema v76 from the separate editable checkout,
AF_UNIX path limits, subprocess durability, and the now-fixed multiplication glyph in the
marketing caption. That superseded run completed with **9 failed, 3256 passed,
8 skipped, 6 xfailed** (1654.76s); its subprocess results cannot establish regressions.
With corrected isolation, CLI scenario, native containment and loopback-close tests all
passed (**3 passed**, 7.10s). The isolated `f1` run was also interrupted by a host
restart after printing 716 outcomes without failures. Stable collection contains
3278 runnable test nodes. Retain 715 outcomes from completed files; rerun the partial
boundary file and remainder in serial 80-test batches with per-test phase journals.
This is combined coverage, not one uninterrupted full-suite pass.
The remainder is now complete. Combined node outcomes: **3260 passed, 7 skipped,
6 xfailed, 5 failed** across 3278 nodes. This folds teardown errors into their test
nodes rather than counting them twice. Genuine aggregate output is retained at
`artifacts/holistic-experience-2026-10-23/fast-validation.json`; external raw phase
journal, batch logs and JUnit remain in `holistic-fast-validation/` as noted below.
One failing node is the disk-backed benchmark below. Four workflow API nodes timed
out or failed thread shutdown in batch 28 (3 call failures, 2 teardown errors).
Focused checks passed unchanged on both the pre-overhaul archive (**4 passed**, 13.71s)
and task tree (**4 passed**, 13.52s). The tests, workflow engine, supervisor and API
are byte-identical between trees. Root cause of the batch failures is unresolved;
do not erase the initial failures or call this a green uninterrupted full suite.
The remaining subprocess durability cases passed with isolation (**4 passed**): queued
event recovery, post-file-flush process death, and both effect-receipt crash boundaries.
The disk-backed throughput gate measured **530 events/s** in the changed tree and
**577 events/s** in the pre-overhaul archive. Both writer and test are byte-identical
between trees. Its existing RAM-backed benchmark option passed the unchanged >1000/s
threshold (**1 passed**, 3.77s), using a unique automatically cleaned directory under
the `/tmp` tmpfs. This identifies a storage/load-sensitive pre-existing failure in this
environment, not a UI regression or an optimized writer. No threshold or assertion changed.
Latest functional review fix: returning to setup during a create request must keep its fields,
Discard and Create disabled and expose Creating assistant…; added a fieldset and pending state
with a delayed-response regression. **All eight task-page/layout tests passed** after this fix.
Final route/token/persona checks: **3 passed** (80.91s). Final server matrix plus marketing
evidence completeness: **2 passed** (16.56s); the server matrix covers 7 surfaces at 4 sizes.
The long-URL overflow in compatibility Connections and squeezed estimate label were corrected,
not hidden with page clipping. Current site suite has 34 passing cases plus the corrected
approval/body-token case; that case, the three real-proof viewports and response-style case
then passed (**5 passed**, 26.60s). Fresh approval-triage captures and their genuine manifest
were copied only after inspection; evidence completeness passed. The reading token is 17px
on marketing, 16px in the app; the failed 16px marketing test assumption was corrected.
Final self-review fixes: canonical assistant identity now keys transcript avatars just as
the roster does; its regression passed (**1 passed**, 8.20s), and both captures were opened.
Duplicate-setup evidence now measures overflow rather than reporting a hard-coded zero;
its regression passed (**1 passed**, 13.99s). Proof chrome/caption now uses body sans;
the extended viewport caption uses ASCII “390 by 1200” to satisfy the inline-SVG icon audit.
Approval/proof/emoji checks passed (**11 passed**, 23.49s). Latest proof desktop/phone and
identity desktop/phone captures opened; genuine approval-triage output recopied and root
manifest regenerated from actual retained files. Evidence-completeness/site-token checks
passed (**9 passed**, 5.34s).
See [rendered coverage and review](holistic-experience-validation.md). Integration still pending.

Disk: `/tmp` repeatedly fills from unrelated work. Use short home-directory temporary paths;
do not delete other tasks' temporary trees. Retained current captures are under
`artifacts/holistic-experience-2026-10-23/` and `artifacts/no-mock-setup/`; earlier temporary
captures are historical, not current-state evidence. No further design/polish round planned.

## Environment and next actions

- Existing Python environment: `/home/kevina/CodingProjects/hutch/.venv/bin/python`.
- Existing browser: `/home/kevina/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome`.
  Python Playwright expects unavailable revision 1243; use explicit executable_path,
  including a process-local BrowserType.launch override for pytest. No dependency install.
- Verified local invocation: `/home/kevina/CodingProjects/hutch/.venv/bin/python
  /home/kevina/.local/share/opencode/hutch-run-tests.py -q
  --basetemp=/home/kevina/.hutch-tmp/<short-name> <tests>`; run from the selected source tree.
  Runner sets child `PYTHONPATH` and `TMPDIR=/home/kevina/.hutch-tmp`; directory must exist.
- node_modules is an **untracked symlink** to original checkout dependencies; never commit.
- `npm run build:css` and `node --check src/hutch/server/static/app.js` passed after the
  latest setup and technical-detail edits. Builds generate CSS and stamp site asset hashes.
- Worktree empty-state review server: app 18891, state in
  `/home/kevina/.local/share/opencode/hutch-visual-empty-20261023`. Do not run real
  model/provider tasks for visual QA. Use fixture servers for populated states.
  Processes may die on host restarts. Use independent fixture state for mutations/tests.
- Completed restart-safe remainder runner: shell `sh_16ae746210017r0gLHwi8jCR2m`.
  It validated a fingerprint of tracked product/test sources, kept completed nodes,
  and stored admission, per-phase reports, per-batch logs/JUnit and final result in
  `/home/kevina/.local/share/opencode/holistic-fast-validation/`. It does not change
  product behavior, assertions or benchmark mode. No more full-suite rerun planned.
  Isolated computer-phone (`c1`) returned
  1 failure and 4 fixture errors:
  no controlled session is created and the worker ends before the expected human wait.
  The representative pre-overhaul comparison (`b1`) reproduces the same fixture error
  and process failure (**1 failed, 1 error**, 24.52s), now using correct child imports and
  short socket paths. These are pre-existing failures in this environment, not proven UI
  regressions; their deeper cause is not diagnosed. Do not claim this path works. Copied
  evidence/site-token checks passed. No claim of successful live computer control.
- Next: commit the final validation record, fast-forward main,
  verify integration and all 12 unrelated file hashes, remove only the task worktree/branch.
  Main remains at f29b299b; preservation record:
  `/home/kevina/.local/share/opencode/holistic-main-before-merge.json`. Latest comparison
  confirmed all hashes unchanged and merge paths disjoint. The duplicate original-checkout
  task research note is archived at
  `/home/kevina/.local/share/opencode/holistic-original-research-note-2026-10-23.md`;
  its original remains in place until the fast-forward. It is a prefix of the tracked note.
  No merge or push yet. No independent subagent review was performed; review is self-review.
