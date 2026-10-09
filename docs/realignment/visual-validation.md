# Visual validation record

## Searchable pinned Bot roster and flat app mascots (2026-10-09)

The Studio roster keeps the workspace coordinator first, then shows pinned Bots in a
named group and the rest under “All bots”. Search matches both groups. Pinning is saved
with the Bot and changes only its roster placement; there is no hide or pause behavior.
The operator app uses a small family of flat, solid-colour 2D silhouettes with two
white glints. The welcome view uses that Bot's same identity. The detailed original 3D
mascot on the marketing site remains separate and unchanged.

`.venv/bin/pytest -q tests/e2e/test_browser.py::test_bot_roster_pins_persist_and_simple_mascots_stay_distinct`
passed on Chromium **153.0.8010.12** / Playwright **1.63.0** with local SQLite fixtures:
pin/unpin, persistence after reload, coordinator order, search through a pinned Bot,
keyboard focus restoration, 44px phone pin targets, drawer close visibility, no
horizontal overflow, no page errors, and no request outside the local fixture host.
I inspected the application at desktop **1440×960**, tablet **900×1024**, and phone
**390×844**. The tablet/phone captures include both the open roster and the chat after
the roster closes. They are in [`artifacts/pinned-roster/`](artifacts/pinned-roster/),
along with source hashes, validation metadata, and a Playwright trace.

The API checks (`tests/test_api.py`, **36 passed**) confirm pinning leaves the Bot's
existing tools and approval mode unchanged. The anonymous marketing workflow test
(`tests/e2e/test_website.py::test_public_workflow_describes_named_recurring_tasks`,
**1 passed**) covers the new pinning statement; I inspected its updated desktop, tablet,
and phone renders at **1440×900**, **900×1024**, and **390×844**. Captures are in
[`artifacts/bot-purpose-refinement/marketing/`](artifacts/bot-purpose-refinement/marketing/).
The actual marketing hero was also captured at all three sizes. Its `hutch-agent.webp`
image loaded at its declared 560px width and retains the detailed 3D character; the
operator app does not request that asset. The anonymous site checks made no external
requests; the complete anonymous website suite passed **27 tests**. No live provider,
screen reader, or physical mobile device was used.

The scoped Impeccable detector found no primary issues in the changed JavaScript,
stylesheet, or marketing page. It reported three advisory out-of-scale radii on existing
workspace task/checkpoint/capability cards in `style.css`; those components were not
changed in this slice and remain outside its scope. The app screenshots also exposed
and verified a specificity fix that makes the mobile roster's visible close button
actually appear.

## Native form submission approval (2026-10-09)

The in-chat outward-approval card now gives native form submissions a human-readable destination, request method, submit control and
visible field labels. It hides field contents and internal fingerprints. I inspected the expanded review at desktop **1440×960**,
tablet **900×1024** and phone **390×844** in Chromium **153.0.8010.12** / Playwright **1.63.0**. The phone decision action was
also scrolled above the fixed composer and inspected separately. All captures report no horizontal overflow or browser errors.

`tests/e2e/test_browser.py::test_browser_form_submit_rechecks_the_reviewed_payload_in_chromium` uses a locally fulfilled HTTPS page:
unchanged state submits after approval; a changed recipient does not, even after the page's main-world crypto function is replaced;
selected files and an insecure page fail closed before an approval is created. The separate responsive card journey uses local
SQLite approval data and no external requests. No real website, login, provider, CAPTCHA, screen reader or physical device was
exercised. Screenshots, source hashes and metadata are in
[`artifacts/browser-form-review/`](artifacts/browser-form-review/).

## Safe checkpoint continuation (schema v34)

Chromium **153.0.8010.12** / Playwright **1.63.0** passed
`tests/e2e/test_browser.py::test_safe_checkpoint_continuation_is_reviewed_and_starts_a_new_attempt` using local SQLite and a mock runtime.
The owner-visible review names the specialist, shows the exact brief and constraints, previews the committed assistant checkpoint,
warns that the fresh model call may use more quota, and spells out excluded facts, prior results, credentials and receipts. Confirming
creates a new linked pending attempt; no provider call or action receipt is produced. I inspected the confirmation at desktop
**1440×960**, tablet **900×1024**, and phone **390×844**. The phone's decision footer remains visible at the bottom and the long
disclosure wraps without horizontal overflow. Captures and trace are in [`artifacts/safe-task-continuation/`](artifacts/safe-task-continuation/).
`tests/e2e/test_website.py::test_public_workflow_describes_named_recurring_tasks` checks the updated anonymous marketing claim at
desktop/tablet/phone with zero external requests. These fixtures do not verify live provider recovery, screen readers or a physical
phone.

## Reduced Bot-creation setup (2026-10-09)

Studio Bot creation now uses four reviewable screens. The first uses the selected latest chat request when present and shows a
local purpose-based name suggestion; model/workspace settings follow, while starters, tools, schedules, execution limits and browser
handoff remain optional disclosures. The blank setup starts with no tools and no schedule. The final screen presents the full draft
and confirms that saving creates no run. No model request was made by the setup flow.

Chromium **153.0.8010.12** / Playwright **1.63.0** passed four Bot-creation browser journeys and the anonymous marketing-copy
journey (**5 passed in 13.19s**) using local app fixtures and SQLite. I inspected the compact first screen and options screen at
desktop **1440×960**, tablet **900×1024**, and phone **390×844**, then reviewed the phone's human-handoff disclosure and complete
draft review. The anonymous marketing card was checked at **1440×900**, **900×1024**, and **390×844**; it made no external
requests and showed no overflow or page errors. Captures and trace are in [`artifacts/bot-setup/`](artifacts/bot-setup/) and
[`artifacts/bot-setup-context/site/`](artifacts/bot-setup-context/site/). These checks used a test-only credential-shaped value,
made no provider call, and do not cover a physical phone or screen reader.

## Explicit specialist-result return (schema v30, 2026-10-09)

`tests/e2e/test_browser.py::test_coordinator_specialist_dispatch_is_reviewable_at_all_viewports` now continues beyond the
specialist's completed task. The user selects the exact successful answer, sees its source Bot and bounded preview in the coordinator
composer, may remove it, and explicitly sends a follow-up. The coordinator timeline retains a collapsible source record and the next
coordinator run receives only the selected answer as untrusted context. The API test covers wrong task/message pairs, a message from
another chat, incompatible reply types, exact retries, changed-body conflicts, clipping, escaped hostile markup and exported
provenance. The fixture does not share files, memory, credentials or permissions.

Chromium **153.0.8010.12** / Playwright **1.63.0** passed the responsive handoff/result-return browser journey against local SQLite
and mock execution. I inspected desktop **1440×960**, tablet **900×1024**, and phone **390×844** screenshots, including the phone
composer attachment and expanded source record; no horizontal overflow or page errors appeared. New result captures and trace are
in [`artifacts/workspace-task-dispatch/`](artifacts/workspace-task-dispatch/). These are fixture checks, not live-provider, screen-reader,
or physical-device evidence.

## Selected coordinator facts in a specialist task (schema v32)

The handoff review shows current approved coordinator facts only inside a collapsed optional section. The owner must check each
fact; none is selected by default. The review reports the current serialized size against the eight-fact/6,000-character bounds,
shows the source scope and review revision, and warns about provider retention and the inability to recall submitted context. The
completed task card expands to show the exact snapshot and source, and says the data stays with the task rather than becoming the
specialist Bot's saved memory.

Chromium **153.0.8010.12** / Playwright **1.63.0** passed
`tests/e2e/test_browser.py::test_coordinator_specialist_dispatch_is_reviewable_at_all_viewports` and
`tests/e2e/test_website.py::test_public_workflow_describes_named_recurring_tasks`. The app review, selected fact, and stored
provenance were exercised at **1440×960**, **900×1024**, and **390×844**; the anonymous marketing workflow was checked at
**1440×900**, **900×1024**, and **390×844**. Screenshots show the phone sheet with the selected checkbox above its fixed footer
and the exact fact card at all three app widths. No page errors or horizontal overflow appeared; the public page made no external
requests. See `artifacts/workspace-task-dispatch/shared-facts-{desktop,tablet,phone}.png`, the review captures, validation JSON and
Playwright trace. Local mock/SQLite fixtures only; no provider, account, screen-reader or physical-phone check.

## Coordinator task-brief refinement (2026-10-09)

The coordinator gets drafting guidance only while selected for that role. It preserves the request, organizes provided or selected
context into a goal and expected result, and asks about material gaps rather than inventing details or authority. The review sheet
keeps the original request linked, lets the operator edit the goal and constraints or add an optional expected deliverable, shows the
specialist's saved capability settings, and requires explicit confirmation. The combined brief is bounded to 20,000 characters.

`tests/test_runtime_builtin.py::test_workspace_coordinator_gets_scoped_task_brief_guidance` and the responsive
`tests/e2e/test_browser.py::test_coordinator_specialist_dispatch_is_reviewable_at_all_viewports` pass. The latter covers the
reviewed dispatch, over-limit rejection, result return and bounded checkpoints at **1440×960**, **900×1024**, and **390×844**;
the focused runtime/conversation group passes **56 tests**. The anonymous workflow-copy check passes at **1440×900**, **900×1024**,
and **390×844**, with zero external requests, page errors or overflow. I inspected the source-and-settings view, task-edit view and
phone lower-fields view at all app sizes, and the public workflow card at all site sizes. Captures and Playwright trace are in
[`artifacts/workspace-task-dispatch/`](artifacts/workspace-task-dispatch/). Impeccable detection returned no findings for the
changed app JavaScript and marketing HTML. These checks use a mock runtime and local SQLite; they do not assess live model draft
quality, screen readers or physical devices.

The initial scoped Impeccable detector run on Studio JavaScript, the stylesheet and marketing HTML identified side-tab styling on
the coordinator request/quote blocks, plus advisory radius values; it returned no finding for the selected-fact UI or marketing
page. This follow-up replaced both side stripes with uniform 1px neutral outlines. The responsive browser test verifies matching
top/left border widths and colors and saves source-card captures at all three sizes. A CSS-only detector run after the edit reports
no side-tab findings; existing radius advisories remain outside this finding. The new task-fact option itself remains a neutral
outlined row. Chromium **153.0.8010.12** / Playwright **1.63.0** passed the responsive handoff journey in **19.01s** with no
page errors or horizontal overflow. I inspected the request card at desktop **1440×960**, tablet **900×1024** and phone **390×844**.
The first attempt hit temporary-filesystem pressure (the `/tmp` tmpfs had 444 MiB available); rerunning with a disk-backed temporary
directory passed. Captures are `artifacts/workspace-task-dispatch/review-source-{desktop,tablet,phone}.png`. Mock/SQLite fixtures
only; no provider, screen-reader or physical-phone verification.

## Reviewed coordinator-to-specialist handoff (schema v29, 2026-10-09)

`tests/e2e/test_browser.py::test_coordinator_specialist_dispatch_is_reviewable_at_all_viewports` passed against a local mock
runtime and SQLite state. Chromium **153.0.8010.12** with Playwright **1.63.0** exercised a completed coordinator turn, opened the
review sheet, displayed the specialist's saved model/tools/action policy/workspace, edited the brief and constraints, dispatched
once, and followed the durable parent task card through completion. The card changed from the active state to **Done** and showed
the latest specialist response; opening it navigated to the separate specialist chat. An exact API retry returned the same task
even when route validation was forced to fail, while a changed request under the same idempotency key conflicted. Changing the
specialist's capability snapshot before worker start produced a visible failure before process creation.

I inspected review and timeline screenshots at desktop **1440×960**, tablet **900×1024**, and phone **390×844**, including the
scrolled phone sheet with assumptions above its fixed action footer. No horizontal overflow or page errors were recorded. The
reviewed request/assumptions and direct-chat action remain readable at all sizes; the coordinator timeline scrolls independently
above the fixed phone composer. Evidence and Playwright trace are in [`artifacts/workspace-task-dispatch/`](artifacts/workspace-task-dispatch/).
The anonymous marketing workflow was inspected at **1440×900**, **900×1024**, and **390×844**; its source/hash record is in
[`artifacts/workspace-task-dispatch/site/`](artifacts/workspace-task-dispatch/site/). The site test passed, made no requests outside
the local static host, had no page errors, and measured zero horizontal overflow. The copy labels handoff experimental and states
that only the reviewed brief/constraints cross into the specialist chat.

The fixtures use a test-only mock runtime; there were no provider/model calls, paid requests, live credentials, public destinations,
physical-device tests or screen-reader checks. The scoped Impeccable scan found no actionable padding, contrast, motion, line-height
or copy-cadence defect; it reported only advisory type/radius/color mismatches in the older server-rendered stylesheet. The template
line-height warning remains a path-scoped false-positive ignore: the linked stylesheet computes body text at **14px/22.4px (1.6)**.

## Chat-sourced Bot creation and selected context (2026-10-09)

Chromium **153.0.8010.12** with Playwright **1.63.0** tested the New Bot flow from an active Studio conversation. The latest
user-authored message can seed an editable purpose; up to eight earlier user-authored messages from that exact conversation are
available as optional, unchecked selections. Assistant replies and other chats are absent from the picker. The final review shows
the exact selected text and warns that it becomes saved instructions and may be sent to the model on later runs. An older private
message was present but left unselected. The API rejects assistant/cross-chat IDs, duplicates, oversized context and legacy-route
use, persists exact source provenance, omits duplicated `original_request` fields from Bot API views, and creates no run. I inspected desktop
1440×960, tablet 900×1024, and phone 390×844 setup captures, including a scrolled phone review showing the selected context above
the fixed footer. Dialogs and review remain within the viewport without horizontal overflow. Captures, trace, browser/version and
source hashes are in [`artifacts/bot-setup-context/`](artifacts/bot-setup-context/). Fixtures made no model/provider call and do
not constitute physical-phone or screen-reader testing. The API/usage regression set passed **53 tests in 12.34s**, the focused Bot
creation browser journey passed **1 test in 6.73s**, and the anonymous marketing check passed **1 test in 2.64s**. JavaScript syntax,
Python compilation and `git diff --check` passed. Anonymous marketing wording was checked at all three sizes, with no external
requests, errors or overflow. The setup still asks the owner to review configuration and does not infer a full setup or resolve
missing details conversationally.

The model step was additionally captured at all three sizes after using a fixture Bot with route `openai/gpt-4o-mini`. Its input is
pre-filled and identified as that Bot's current route, with text explaining that it will become the new Bot's saved default and can
be changed before saving. I inspected the desktop, tablet and phone captures; each kept the model field, helper copy and footer in
view without horizontal overflow. This did not call the model. The anonymous website card now describes the same optional suggestion;
its browser test asserts the wording and recaptures the responsive card.

## Workspace model defaults for new Bots (2026-10-09)

Chromium **153.0.8010.12** / Playwright **1.63.0** exercised Preferences → Model defaults for new Bots, saved a validated
hosted-route fixture, reloaded the page, and started Bot setup. The preference persists across reload, seeds the editable model
field, and creates neither a run nor a Bot before the user completes setup. The API fixture separately verifies that existing
Bots remain unchanged, explicit route/mode choices win, invalid routes do not replace the saved preference, and clearing it
restores per-Bot route selection. I inspected the preference dialog and Bot model step at 1440×960, 900×1024, and 390×844;
the inputs and footer remained visible with no horizontal overflow. Captures, trace, validation results, and source hashes are in
[`artifacts/workspace-model-defaults/`](artifacts/workspace-model-defaults/). The anonymous marketing workflow now says that
Preferences can set a default for new Bots, a chat Bot route can still be suggested, and the choice affects new Bots only. Its
card was captured and inspected at 1440×900, 900×1024, and 390×844; there were no external requests, page errors, or overflow.
No provider/model call, physical phone, or screen-reader was used. CO-14 remains partial because coordinator/specialist routing
and actual route identity on cross-Bot runs remain unimplemented.

## One-message model overrides and saved Bot defaults (2026-10-09)

Chromium **153.0.8010.12** / Playwright **1.63.0** exercised the composer model picker with a FakeOllama route. A selected route
was applied to the next accepted message in one conversation, the run retained that `model_override`, and the composer returned to
the saved Bot route. A different conversation retained its own default; returning to the first conversation restored its unsent
selection. The browser fixture then used the separate **Save as Bot default** action, confirmed the model-only Bot update, verified
that the pending override cleared, and checked that no run was created by saving. The one-message menu and save control fit within
the viewport at 1440×960, 900×1024, and 390×844; I inspected each capture, including the phone's visible `1×` marker. Artifacts,
trace, source hashes and measurements are in [`artifacts/model-default-choice/`](artifacts/model-default-choice/). The
`test_composer_switcher_menu_check_keyboard_and_per_message_override` and
`test_model_switcher_can_explicitly_save_the_selected_route_as_bot_default` browser checks made no live model/provider call.

The anonymous marketing inference card now distinguishes a one-message route choice from saving a Bot default for later chats and
scheduled runs. Chromium **153.0.8010.12** inspected it at 1440×900, 900×1024, and 390×844; there were no external requests, page
errors, or horizontal overflow. Captures and updated source hash are in [`artifacts/bot-setup-context/site/`](artifacts/bot-setup-context/site/).

## Message-anchored replies (2026-10-09)

Chromium **153.0.8010.12** with Playwright **1.63.0** exercised selecting a specific Bot response by keyboard, checking focus moves
to the composer, retaining the unsent draft and reference across reload, removing the reference by keyboard, and sending a reply whose
message record points to the selected assistant message. The same journey passed at desktop 1440×1000, tablet 900×1024 and touch
phone 390×844; there were no page errors or horizontal overflow. On the touch phone, both the “Reply to this” and “Remove” controls
measure at least 44px high. I inspected the preview and sent-reply captures on all three sizes; the quoted source remains visually
distinct inside the user's message and the composer reference fits the narrow viewport. Screens, traces, source hashes and run records
are in [`artifacts/message-replies/`](artifacts/message-replies/). This is a synthetic local conversation with no provider call, and
does not constitute screen-reader or physical-device validation.

The reply preview now uses the Bot's human-facing display name while keeping its internal address for routing. A regression fixture
deliberately gives the Bot different values (`Project Delivery Partner` and `reply-fixture`) and checks that the preview exposes only
the display name. The same responsive reply journey verifies the linked message remains unchanged.

## Typed chat choices (2026-10-09)

The built-in conversation runtime can save a single- or multi-select question and wait for the user in the same chat. The browser
journey selected multiple options using keyboard input, submitted them through the real answer API, and confirmed the answered
labels and linked question. The pending card has a distinct “Waiting for your choice” label; it does not present the question as an
approval or an active run. Chromium **153.0.8010.12** / Playwright **1.63.0** passed at 1440×960, 900×1024 and 390×844 with no
horizontal overflow or page errors. I inspected desktop pending, tablet keyboard-selected and phone answered captures; option rows
meet touch-target sizing, focus is visible, and selected labels wrap on the phone. Captures, a Playwright trace, source hashes and
viewport records are in [`artifacts/structured-choices/`](artifacts/structured-choices/). The local SQLite fixture made no model
or provider call; its answer run stays queued because the test disables execution ticks. This does not verify external runtimes,
screen readers or a physical phone. The anonymous marketing workflow now describes this as a built-in chat capability and separates
the answer from action approval. The site suite passed **25 tests** with no external requests, page errors or overflow; I inspected
the three workflow captures in [`artifacts/scheduled-tasks/`](artifacts/scheduled-tasks/), and its JSON record contains the tested
page hash.

## Scoped conversation export (2026-10-08)

The Studio composer menu opens an export-scope dialog before downloading the JSON. The dialog explains included message provenance,
excluded stored credentials and other private records, verbatim message text, and the size limits. Chromium **153.0.8010.12** /
Playwright **1.63.0** exercised the download, parsed the resulting file, checked the exclusions, and captured the dialog at 1440×960,
900×1024 and 390×844. All three sizes had zero page errors and zero horizontal overflow. Screenshots, traces and source-hash/viewport records are
in [`artifacts/conversation-export/`](artifacts/conversation-export/); the test is
`tests/e2e/test_browser.py::test_conversation_export_shows_scope_and_downloads_json`. This is a synthetic local conversation with no
provider calls, not a screen-reader or physical-device check.

## Dashboard polish (2026-10-09)

The Studio's three working dots, legacy workflow dot, running-status dot and server-rendered live-connection mark remain still;
“Working…”, “running”, “live” and “reconnecting” carry the state. A regression check covers both the source CSS and its generated
Tailwind output so rebuilding the legacy dashboard cannot reintroduce the pulse. Studio body text computes to 14px/21.7px (1.55);
server-rendered body text computes to 14px/22.4px (1.6). Their headings use 1.3 and 1.4 line-height respectively. The browser test
checks those computed values and status animations, and places a visual-only working-indicator fixture in the Studio chat layout; it
does not claim that a run was active. Chromium **153.0.8010.12** /
Playwright **1.63.0** passed at 1440×960, 900×1024 and 390×844, with no page errors or horizontal overflow. Headings measured 30/42 px
on desktop/tablet and 24/33.6 px on phone. Screens, trace, source hashes and measurements are in
[`artifacts/dashboard-polish/`](artifacts/dashboard-polish/). I inspected the Studio and Connections captures at all three widths;
the phone layouts fit, and the status labels remain legible without an animated dot.

The same responsive dashboard pass now injects visual-only success and error banners into the real server-rendered Connections
page. Both use the same 1px neutral border; the check/alert icon carries the state color, while the text remains readable and the
existing `status`/`alert` roles remain intact. The refreshed three-size captures show no clipped content or overflow. The anonymous
marketing workflow was also shortened without removing request provenance, no-run-on-create, approval separation, checkpoint,
provider-retention or delegated-context boundaries. Its skip link now moves with `transform`; the phone keyboard check focuses it,
reveals it, and activates the `#main` target.

`uv run pytest -q tests/e2e/test_browser.py::test_dashboard_polish_keeps_work_feedback_steady_and_headings_readable tests/e2e/test_website.py::test_public_workflow_describes_named_recurring_tasks tests/e2e/test_website.py::test_public_bot_setup_copy_matches_reviewed_chat_sourced_creation tests/e2e/test_website.py::test_mobile_drawer_focus_and_ctas --no-header` passed **4 tests in 8.75s**; the final refreshed dashboard-only capture pass also passed **1 test in 4.25s** on Chromium **153.0.8010.12** / Playwright **1.63.0**. I inspected the banner and workflow captures at desktop, tablet and phone sizes; all reported zero page errors and horizontal overflow. The site test made no external requests. Fixtures only; no live provider or physical-device check.

After a final copy pass restored the visible route/fallback and safe-checkpoint conditions, both anonymous public-site journeys passed again (**2 tests in 4.27s**), and I inspected the refreshed workflow captures at all three sizes.

The base-template static detector does not resolve its linked `hutch.css` heading rule and still estimates the browser default line
height. The existing path-scoped ignore remains, with its reason updated to the new computed measurements; no new ignore was added.

## Marketing screenshot source alignment (2026-10-09)

The earlier captures named older `website/index.html` and `website/styles.css` hashes, and the stylesheet link still used the old
cache key `b614bd35` while the current CSS hash began `2c79db7e`. A browser with the old URL cached could therefore keep showing the
previous styling. I ran the site's existing asset-stamping step to update local URLs from their file hashes and added
`test_local_asset_urls_use_current_content_hashes` to prevent this mismatch. The anonymous-site browser capture was rerun against the
corrected page; its three JSON records now carry the final source hashes, no page errors, zero horizontal overflow, and no requests
to another origin. I opened the current full-page desktop (1440×1000),
tablet (900×1024), and phone (390×844) screenshots. The viewport images were also recaptured; their bytes remain unchanged because
the first fold is visually the same. Full-page screenshots and matching source records are in
[`artifacts/no-mock-setup/site/`](artifacts/no-mock-setup/site/). The hero keeps one short three-part brand line; the remaining
sections explain the workflow and limits in regular sentences. Repeated slogan-like headings about model choice, approval and stop
cleanup have been replaced with direct descriptions. The anonymous website suite passed **24 tests in 30.28s**; internal links and
CTAs work anonymously, the page requests no external origin, and the captures show no overflow or page errors. One Impeccable scan
returned no website HTML finding; it did list pre-existing advisory type, radius and color differences in the shared
server-rendered stylesheet, which was not changed in this copy update. No new detector ignore was added. The existing website padding
exception remains scoped to this file: the visible bands contain inset content, as confirmed in the opened responsive captures.

## Verified source card for clipped tool output (2026-10-08)

When tool details expand, the verified full-output download and the “Open” source card now sit outside the height-limited preview,
so the action is visible without scrolling the preview. On phones the filename occupies its own line, with size and open action
below it. Chromium **153.0.8010.12** / Playwright **1.63.0** verified the card and download at 1440×960, 768×1024 and 390×844;
the captured phone filename is one line and the card stays inside the viewport. The route rechecks the recorded SHA-256 and size,
opens content as inert `text/plain` (the fixture includes a script tag), and has no page errors or horizontal overflow. Screenshots,
source hashes and measurements are in [`artifacts/tool-source-card/`](artifacts/tool-source-card/). This is a local fixture, not a
provider or physical-phone check.

## Independent recurring tasks (2026-10-09)

The settings panel manages one to 100 named tasks on a bot. Each task has separate cron, timezone,
catch-up policy and prompt; all tasks share that bot's tools, workspace, permissions and single-run
limit. The real-browser fixture added a task, edited both tasks, reloaded the page, removed the
secondary task, then removed the primary and verified promotion of the remaining stream. Its task
prompt and timing were kept safely in the future; no model/provider request ran. The create dialog
also kept its title and create action visible while the phone prompt field was in view.

Chromium **153.0.8010.12** / Playwright **1.63.0** passed at 1440×960, 900×1024 and 390×844 with
no page errors or horizontal overflow. Both expanded task cards were inspected at every width; the
Add task target measured 44 px. The six per-task captures, trace, source hashes and viewport data
are in [`artifacts/scheduled-tasks/`](artifacts/scheduled-tasks/), with the journey in
`tests/e2e/test_browser.py::test_multiple_scheduled_tasks_can_be_managed_from_bot_settings`.
The anonymous marketing workflow test passed at the same widths, made no external requests and
reported no overflow or page errors. Its three workflow-section captures and source hash are in the
same artifact folder; I inspected each, including the stacked phone cards.

## Baseline visual validation

Captured 2026-10-07 from the `realign/platform` worktree after the shared-budget UI and marketing copy changes. The marketing site was
served from this worktree. Hutch used `/tmp/hutch-s5-visual.mbtpt6`, a disposable state directory populated by `hutch init` and one
OpenCode Go connection configured with a synthetic account ID, a 100k token allowance, and a $5 estimate limit. No API key was stored,
and no provider request was made. No personal workspace files were used. Both servers bound to loopback only.

The site/app image set below remains the 2026-10-07 checkpoint; it is not refreshed automatically when `website/` changes. For the
current marketing source, use the dated full-page and fold captures under `artifacts/marketing-top/` described at the end of this file.

## Reproduction

```bash
HUTCH_STATE_DIR=/tmp/hutch-s5-visual.mbtpt6 .venv/bin/hutch init
HUTCH_STATE_DIR=/tmp/hutch-s5-visual.mbtpt6 .venv/bin/hutch connections add opencode-go \
  --account-id shared-dev --account-daily-cap-usd 5 --allowance-tokens 100000 --allowance-window month
python3 -m http.server 18001 --bind 127.0.0.1 --directory website
HUTCH_STATE_DIR=/tmp/hutch-s5-visual.mbtpt6 .venv/bin/hutch serve --host 127.0.0.1 --port 18877
PLAYWRIGHT_BROWSERS_PATH=/tmp/hutch-playwright-browsers .venv/bin/python \
  docs/realignment/capture_visual_validation.py \
  --site http://127.0.0.1:18001/ --app http://127.0.0.1:18877/
```

Capture environment: Python 3.13.15, Playwright 1.63.0, bundled Firefox 155.0. The site, dashboard, Connections and Usage pages
returned HTTP 200 at 1440×1000 desktop, 900×1024 tablet and 390×844 phone. `capture-results.json` records dimensions, CTA targets,
errors and phone-menu behavior. Each desktop page has a Playwright trace with screenshots and DOM snapshots. Both servers were stopped
after capture.

## Inspected artifacts

The screenshots are under [artifacts/visual-validation](artifacts/visual-validation/). The complete page captures are
[site desktop](artifacts/visual-validation/site-desktop.png), [site tablet](artifacts/visual-validation/site-tablet.png),
[site phone](artifacts/visual-validation/site-phone.png), [app desktop](artifacts/visual-validation/app-desktop.png),
[app tablet](artifacts/visual-validation/app-tablet.png), [app phone](artifacts/visual-validation/app-phone.png),
[Connections desktop](artifacts/visual-validation/connections-desktop.png), [Connections tablet](artifacts/visual-validation/connections-tablet.png),
[Connections phone](artifacts/visual-validation/connections-phone.png), [Usage desktop](artifacts/visual-validation/usage-desktop.png),
[Usage tablet](artifacts/visual-validation/usage-tablet.png), and [Usage phone](artifacts/visual-validation/usage-phone.png). Fold-sized
site images are also saved for desktop, tablet and phone.

App phone state captures cover [empty](artifacts/visual-validation/app-phone-empty.png),
[loading](artifacts/visual-validation/app-phone-loading.png), [API error](artifacts/visual-validation/app-phone-error.png),
[pending approval](artifacts/visual-validation/app-phone-approvals.png), [cancelling](artifacts/visual-validation/app-phone-cancelling.png),
[reconnecting](artifacts/visual-validation/app-phone-reconnecting.png), and the [open navigation menu](artifacts/visual-validation/app-phone-menu-open.png).
Empty/loading/error used intercepted fixture responses. Cancelling is a synthetic local database row with no worker. Reconnecting used
a failed health-check route after an initial successful connection. The approval and other seeded records in this older capture
were generated by the test-only runtime fixture in an isolated state directory, not by a supported product demo command. This
capture is historical synthetic evidence and is not used as marketing proof; current marketing screenshots use the actual empty
first-run product. Deterministic runtime fixtures are excluded from packaged builds.

## Findings

All 12 site/app/Connections/Usage captures had `document.scrollWidth == innerWidth`; captured pages had no JavaScript page errors. The site CTAs all
targeted existing internal sections and worked without authentication. The quickstart section truthfully says the source repository is
private and no PyPI package is published; anonymous visitors are not shown a dead public install link.

Connections and Usage were inspected after adding account caps and reservation estimates. Their forms and disclosure text fit at all
tested widths. The Usage page's per-bot budget table becomes labelled, stacked cards on a narrow screen; measured values stay distinct
from held estimates. The connection capture has no credentials configured and shows its missing-key state.

The final site screenshot shows the illustrated run badge as **DEMO supervised run** with an accessible name that calls it a demo
preview; it no longer suggests that an example is live system activity. The pending approval card and its decision buttons remain
visible on the phone viewport. The Studio keeps the composer reachable on desktop, tablet and phone. Conversation selector, New,
Archive and Settings wrap onto a second row at phone width without clipping.
Lifecycle chips use plain-language labels; the cancelling-state browser regression checks that “Stopping” remains visible while the
run is nonterminal. The full-screen app menu now moves focus to its first link, wraps Tab within the menu, closes on Escape and
returns focus to its toggle. The focused Playwright browser regression passed. The marketing-site menu also opened/closed by keyboard
and restored focus; site tablists changed selection with arrow keys. Reduced-motion mode was used for the repeatable screenshot pass.

The Impeccable static detector was rerun over the edited website and application HTML/CSS. It returned 44 heuristic findings: 41
warnings and 3 advisories, with no error-severity finding. Most flag the existing visual language (tracking, small labels, borders,
gradients/glows and a scripted demo typing animation), not measured user defects. Decorative pulse animation was removed from the site
status dots. The machine-readable source scan is in
[`impeccable-detect-source.json`](artifacts/visual-validation/impeccable-detect-source.json). A fresh URL/browser detector pass was
attempted but unavailable because Impeccable's URL mode requires Chromium and this host only has Firefox; the earlier
[`impeccable-detect.json`](artifacts/visual-validation/impeccable-detect.json) predates the current S5 page additions. No automated
contrast calculation or screen-reader audit was performed.

These are local UI checks, not a screen-reader certification, physical phone test, or test of a real supervised browser session.
Playwright used desktop Firefox at phone/tablet viewport sizes; it did not emulate touch input. Provider, Pi, local-model, portal
and physical-device workflows remain separate verification gaps in [the continuation ledger](ledger.md).

## Local browser handoff settings (2026-10-08)

The bot settings expose an opt-in, same-session visible browser handoff. Chromium 153.0.8010.12 / Playwright 1.63.0 exercised
save-and-reload at 1440×1000, 900×1024 and 390×844. The screenshots were inspected at all three sizes. The first phone pass
found the new selector was 38px tall; it was raised to the 44px Hutch touch target and all viewport cases then passed. The helper
text stays beside the setting, the phone view has no horizontal overflow, and the selection survives a server-backed bot update.
Keyboard Tab moves from the setting to the visible Save policy control, and the setting has an associated accessible description.
No run was started, no model/provider was called, and no browser login challenge was opened. This validates the settings journey,
not a real headed browser handoff. Fixture metadata, source hashes and Playwright traces are in
[local-browser-handoff](artifacts/local-browser-handoff/): [desktop](artifacts/local-browser-handoff/desktop-enabled.png),
[tablet](artifacts/local-browser-handoff/tablet-enabled.png), and [phone](artifacts/local-browser-handoff/phone-enabled.png).
The focused test passed **3 viewport cases in 88.44s**; all report zero browser-console/page errors and zero horizontal overflow.

The installed Impeccable CLI exposes `detect` but not the documented `audit` command, so the scoped technical checklist was applied
manually. The final source detector returned `[]`. In this tested flow, accessibility has the native label/description, visible keyboard
focus and 44px phone target; contrast, screen-reader use, 320px reflow, 200% zoom and user text-spacing overrides remain untested.
The dark theme uses the existing tokens without new colors; no contrast calculation was performed. No render profiling was done.
The persisted option and live capability message come from Hutch's API, and headless runs refuse to pretend a person can take over.

### Settings capture refresh (2026-10-09)

After the setup wizard changes, I reran `.venv/bin/python -m pytest -q
tests/e2e/test_browser.py::test_local_browser_handoff_setting_is_explicit_and_persists
-W error::pytest.PytestUnhandledThreadExceptionWarning -W error::SyntaxWarning`; all **3 viewport cases
passed in 17.51s**. I reopened the current desktop (1440×1000), tablet (900×1024) and phone (390×844) screenshots.
The Linux-only limitation and experimental state are readable beside the saved setting; the form stays within each viewport,
has no page errors or horizontal overflow, and persists its selected value. The metadata source hashes match the committed
JavaScript/CSS/server/template/model files. This is a settings fixture only: no run, provider call or actual browser challenge
was started. Current captures and trace are the `*-enabled.png`, `*.json` and `*-trace.zip` files in
[`artifacts/local-browser-handoff/`](artifacts/local-browser-handoff/).
No P0–P3 defect was observed in the changed settings path; the real visible login challenge and cross-browser behavior remain open.

## Marketing source recapture (2026-10-08)

Because the older `artifacts/visual-validation/site-*.png` images predate later site edits, the marketing page was recaptured directly
from the current `website/` directory. The repeatable command is `.venv/bin/python docs/realignment/capture_marketing_top.py`.
Chromium 153.0.8010.12 / Playwright 1.63.0 captured anonymous desktop (1440×1000), tablet (900×1024) and phone (390×844)
views with reduced motion. The script also saves full-page captures for each responsive layout. Inspected fold views and full pages:
[desktop](artifacts/marketing-top/desktop.png) / [full page](artifacts/marketing-top/desktop-full.png),
[tablet](artifacts/marketing-top/tablet.png) / [full page](artifacts/marketing-top/tablet-full.png), and
[phone](artifacts/marketing-top/phone.png) / [full page](artifacts/marketing-top/phone-full.png).

All three viewports report zero horizontal overflow, no page errors and same-origin requests only. `artifacts/marketing-top/capture.json`
records the Git revision and SHA-256 values for `website/index.html`, `styles.css`, `site.js`, compiled `app.css`, token CSS, the loaded font,
the mascot and the embedded desktop/phone app screenshots. The separate first-run capture report hashes all shipped Hutch Python and
frontend sources. The anonymous website browser suite checks internal CTA targets and interaction. At desktop size the reduced-motion
preference is reflected by the visible effects control; the capture intentionally keeps that user-facing setting visible. No hosted service
or external request is needed for these captures. Local asset URLs, including product screenshots, are content-pinned to prevent browser
caches from silently keeping an older image after the file is refreshed.

After main `307ce1d`'s app styling was merged at `fdf6592`, the empty-state app images were regenerated from the built application,
re-encoded as the site's WebP proof images, and all local asset URLs were re-stamped. The app captures were opened beside the embedded
proof images; the anonymous site was recaptured at all three sizes with its full-page screenshots and opened for visual review.
`artifacts/no-mock-setup/results.json` and `artifacts/marketing-top/capture.json` pin the post-merge source hashes and image hashes.
The separate navigation contact sheet had not been regenerated and still showed an older marketing page; its independent capture utility
was rerun after correcting a wait for a hidden duplicate status label. All 39 current app/site captures and inspection sheets now pin
the post-merge sources. The integrated browser suite passed 83 checks after the latest CSS build; the site/token suite passed 27 checks
after the refreshed image URLs were built. A screenshot is a saved file, so merging a UI change alone does not update it; each capture
generator and the asset-hash build step must be run. The empty first-run image remains visually similar because it does not show the
modal, card and switcher components changed by main `307ce1d`; populated app states are available in the navigation capture set.

## Action intent review continuation

Schema v13 adds an uncertain-action card in chat and paginated older/cross-bot receipts in
Needs you. `tests/e2e/test_browser.py::test_uncertain_action_review_in_chat_preserves_history_and_recovers_lost_response`
captures uncertain, review-dialog and recorded-report views at desktop, tablet and phone sizes.
The fixture commits an operator report on the real API, drops its response and retries with the
same idempotency key. It verifies unchanged execution status/receipt/chain, retained draft and
restored focus. A second fixture checks 22 older receipts over two pages with real phone menu
and keyboard navigation. No live external effect, physical phone or screen reader is exercised.

Images, traces, timestamps and source hashes are in
[action-receipts](artifacts/action-receipts/). The app labels the recorded result a human report;
the original execution error remains inspectable under a folded report after all receipts are
reconciled. Marketing figure checks load anonymously at three widths and verify labelled fixture
copy and the responsive phone image. Inspection prompted this image-source improvement rather
than accepting a technically fitting but unreadable desktop thumbnail. Final counts/boundaries
are recorded in the continuation ledger.

## Held restoration continuation

The existing app header shows a restored-state execution hold on all routes. A read-only detail
dialog explains quarantine, revoked authority, excluded files and the source-process boundary;
there is no extra navigation page or browser activation control. Three real local-server
journeys at 1440×1000, 900×1024 and 390×844 use an actual isolated database snapshot/restore with
synthetic unfinished work. They check rejection before message admission, kept chat draft,
keyboard focus/trapping/return, state invalidation after local operator activation, 44px phone
controls, no header/content overlap and an unobscured Close button.

Inspection found and repaired a desktop header overlap and a phone error toast covering Close.
The new read-only dialog also needed an explicit hidden-button style because the shared button
reset overrode the HTML hidden attribute. Captures/traces/source hashes are in
[restoration](artifacts/restoration/). The broader navigation/site capture covers the updated
database-only website specification. These checks are isolated fixtures, not production cutover,
physical-device or screen-reader certification. Exact final counts are in the ledger.

# Design-hook triage (2026-10-08)

The `pulsing-dot` finding on `src/hutch/server/static/index.html` is a scoped false positive. The animated dot is the `.workflow .working` indicator: it is rendered only while the refreshed API status reports active runs, and disappears when no run is working. A value-specific hook ignore is persisted for this file only in `.impeccable/config.json`; the other detector rules remain active.

## Dashboard tool and meter styling review (2026-10-09)

The Impeccable stop hook reported two dashboard stylesheet findings: a left accent rail on transcript tool rows and an animated
meter width. Tool rows now keep their existing indentation, summary text and success/error colours without the rail; meter fills
update immediately without a width transition. This keeps the full amount visible without animating a layout property. The existing
website `cramped-padding`, primary-button `low-contrast` and FAQ `layout-transition` exceptions, and the live-run `pulsing-dot`
exception, remain scoped to their individual worktree files. The stop hook scanned `.worktrees/realign/...` from the repository root,
so it did not load those nested worktree exceptions; the detector run from the worktree uses them. No new site or status-dot exception
was added.

The synthetic component fixture loads the actual `/static/hutch.css` and renders a budget meter plus success, failure and ordinary
tool rows at desktop (1440×1000), tablet (900×1024) and phone (390×844). The captures and desktop trace are in
[`artifacts/ui-style-review/`](artifacts/ui-style-review/): [desktop](artifacts/ui-style-review/desktop.png),
[tablet](artifacts/ui-style-review/tablet.png), [phone](artifacts/ui-style-review/phone.png), and
[results](artifacts/ui-style-review/results.json). Firefox 155.0 reported HTTP 200 for the stylesheet, no page errors and no
horizontal overflow at all three sizes. Computed styles confirm a 0px tool-row left border, 10px text inset, no meter transition,
and an accurate 72% fill. Captures were visually inspected. The focused dashboard/view suite passed **39 tests**; the targeted
Impeccable detector returned no findings for the edited stylesheet or the configured website/dashboard/template targets, and
`git diff --check` passed.

Reproduce with an empty temporary state directory and loopback-only server:

```bash
HUTCH_STATE_DIR=/tmp/hutch-style-review .venv/bin/hutch init
HUTCH_STATE_DIR=/tmp/hutch-style-review .venv/bin/hutch serve --host 127.0.0.1 --port 18803
PLAYWRIGHT_BROWSERS_PATH=/tmp/hutch-playwright-browsers .venv/bin/python \
  docs/realignment/capture_ui_style_review.py --app http://127.0.0.1:18803/
```

The fixture is synthetic and makes no model/provider call. It validates this stylesheet in isolation, not a live transcript or device.
The same change refreshes `.impeccable/design.json` from `DESIGN.md` without rewriting the human-authored design guide.

## Provider sign-in states (2026-10-09)

Connections captures include the default disabled ChatGPT preview and the opt-in enabled state at desktop and phone sizes.
The enabled-state browser fixture obtains Hutch's authorization URL but intercepts the OpenAI authorization destination
locally; it does not contact OpenAI or complete sign-in. The test checks the dynamic-client first registration, loopback
callback, plan-use scope and PKCE method, while keeping query values and one-time state out of the saved evidence. It also
checks no horizontal overflow or page errors. Screenshots and metadata are in
[`artifacts/provider-signin/`](artifacts/provider-signin/): [enabled desktop](artifacts/provider-signin/chatgpt-preview-enabled-desktop.png),
[enabled phone](artifacts/provider-signin/chatgpt-preview-enabled-phone.png), and
[fixture results](artifacts/provider-signin/chatgpt-preview-enabled-validation.json). OpenCode Go is presented as the vendor-issued
API-key connection documented for third-party clients, not an OAuth session import. The visual captures were inspected.

## Conversation file discovery (2026-10-09)

The Studio composer menu now opens a paged list of verified files and saved tool output from the selected conversation. The browser
journey writes a fixture CSV, finds it from the chat-level file browser, downloads it with keyboard activation, and confirms focus
returns to the composer options button. A separate phone-sized empty-state journey verifies the “no files yet” message, Escape close,
focus restoration and no page overflow. The list includes only runs owned by the conversation's bot and attached to that conversation;
the download still passes through the source run's SHA-256 and size checks.

Firefox **155.0** with Playwright **1.63.0** captured the app and open file browser at desktop (1440×1000), tablet
(768×1024) and phone (390×844). All report zero page errors and zero horizontal overflow; screenshots were visually inspected.
The browser journeys passed **3 tests in 8.57s** and the API suite passed **15 tests in 3.92s**. One phone-sized browser journey loads a
51st item through the cursor control and verifies unique filenames and no overflow. Its inspected large-list state is saved with source
hash and fixture metadata in [`artifacts/generated-files/large-list-phone.png`](artifacts/generated-files/large-list-phone.png) and
[`artifacts/generated-files/cursor-list.json`](artifacts/generated-files/cursor-list.json). The API regression also inserts a newer artifact
between cursor requests and verifies the remaining older items, including a boundary between two artifact kinds from one event.
The anonymous marketing-site suite passed **22 tests**
after the public copy clarified that files remain discoverable from the conversation; a final focused feature-section recapture passed
at desktop, tablet and phone sizes. App captures and source hashes are in [`artifacts/generated-files/`](artifacts/generated-files/);
the public feature-section captures and validation metadata are in [`artifacts/provider-signin/`](artifacts/provider-signin/).
`generated-files/results.json` records fixture provenance and download hashes. No model, provider or paid call was made. This is
per-conversation discovery and is not a cross-chat artifact library, live-provider test, physical-device check or screen-reader
certification.

## Recurring-task prompt settings (original slice, 2026-10-09)

Bot creation and bot settings expose one optional task prompt for the bot's single cron schedule.
The create dialog rejects a nonempty task without cron; settings preserve the prompt after a save and
reload. The text explains that a blank prompt uses the standing bot instructions, and the schedule
removal action is labeled explicitly. At phone size, the prompt field, dialog title and fixed create
action remain visible together after scrolling the dialog body.

The earlier one-task settings form was replaced by the independently managed recurring-task list
documented below; its browser evidence remains historical for the original prompt-only slice.

## Cross-chat artifact sharing (2026-10-09)

The local Chromium fixture journey shares a verified file reference from one bot chat to another,
downloads the bytes from the recipient's Files list, then revokes access and confirms the source
download remains intact. The source Files list displays its active recipient and can revoke the
grant; the recipient can also stop access. The share action stays disabled until a destination is
explicitly chosen. The test exercises keyboard activation for opening, cancelling, sharing and
revoking from the source chat, and checks that the Files dialog's Done button remains visible at
each viewport.

Captures use Chromium **153.0.8010.12** and Playwright **1.63.0** at desktop (1440×960), tablet
(768×1024) and phone (390×844). All three report zero horizontal overflow, zero dialog overflow and
no page errors. The phone capture shows the full recipient chooser and fixed Done action; its button
is within the viewport at x=303, y=788, 70×44 px. Desktop, tablet and phone chooser, active source
grant and recipient views, source hashes, viewport bounds, result JSON and Playwright trace are saved in
[`artifacts/artifact-sharing/`](artifacts/artifact-sharing/). These are local fixture results only:
no provider calls or physical phone were used, and no screen-reader run was performed.

Chromium **153.0.8010.12** with Playwright **1.63.0** captured the create dialog at desktop
(1440×960) and phone (390×844), the scrolled phone prompt, and settings at desktop (1440×960),
tablet (900×1024) and phone (390×844). All checks reported no page errors or horizontal overflow;
the screenshots were inspected. The browser journey passed **1 test in 3.14s**. API, CLI and engine
regressions passed **34 tests in 23.04s**. Captures, trace, viewport measurements, source hashes and
fixture provenance are in [`artifacts/scheduled-task/`](artifacts/scheduled-task/). No provider or
model call was made. This was evidence for the original one-task slice; see the later independent
task-stream capture above for the current settings behavior. At this capture checkpoint bounded delegation was separate work; the current preview's responsive settings evidence is recorded in `artifacts/tool-permissions/` below.

## Inline human-resume action (2026-10-09)

Studio chat now places a 44 px minimum-height Resume action beside only the latest `human_needed`
event while its run is waiting for a person. The local browser fixture included an earlier challenge
and a newer current challenge; only the current one exposed the action. Clicking it submitted the
event sequence to the versioned Resume API with a deterministic per-run/per-event idempotency key.
The accepted state disables the button and says that Hutch is waiting for the run to continue.

Chromium **153.0.8010.12** with Playwright **1.63.0** passed **3 responsive browser journeys in
3.70s** at desktop (1440×1000), tablet (768×1024) and phone (390×844). All reported zero horizontal
overflow and no page errors; the button exceeded 44 px at each size. The three screenshots and
viewport/API/source-hash metadata are in [`artifacts/human-resume/`](artifacts/human-resume/), and
were visually inspected. Focused API/migration tests passed **34 tests in 5.01s**. No provider or
external browser call was made. The fixture verified command acceptance and persistence, but kept
the scheduler idle, so a live worker consuming the request and continuing after a real person clears
a challenge remains unverified. No screen-reader or physical-phone check was performed.

## Bounded delegation settings and public workflow copy (2026-10-08)

The bot Settings permission list exposes the explicit `delegate_task` opt-in and its Strict Offline,
extra-slot and task-text-only constraints. Visual inspection also caught a phone-header defect: the
mobile header hides action text, leaving a text-only Delete control blank. It now has a labeled trash
icon and a 44×44 touch target. The browser journey enables the permission with Space, saves with
Enter, reloads, and checks persistence. The regenerated desktop (1440×960), tablet (900×1024),
phone (390×844) and scrolled phone captures were opened and inspected; all have zero horizontal
overflow and no page errors. Viewport metrics, source hashes, trace and screenshots are in
[`artifacts/tool-permissions/`](artifacts/tool-permissions/).

The anonymous marketing workflow uses the direct heading “Keep each task reviewable from request to
result.” Desktop (1440×900), tablet (900×1024) and phone (390×844) screenshots were inspected. The
full anonymous website suite passed **23 tests in 30.41s**, including anchor/CTA resolution and a
check for external requests; this workflow made zero external requests and had no page errors.
Captures and metadata are in [`artifacts/scheduled-tasks/`](artifacts/scheduled-tasks/). The settings
journey passed **1 browser test in 3.37s** using Chromium **153.0.8010.12** and Playwright **1.63.0**.

These are local fixture and emulated-phone captures only. No live model, provider sign-in, physical
phone or screen reader was used.

## Compact bot navigation and in-chat approval recheck (2026-10-09)

The browser recheck covers the product decision to keep one bot roster in Studio for small setups
and show Fleet at ten bots, along with the separate review queue remaining useful for accumulated
requests. One-bot navigation stayed in Studio without a Fleet or Manage-all-bots destination. At ten
bots, Fleet search and paused-state filters returned the expected counts. A pending action remained
in its conversation; expanding its review details survived the transcript refresh with focus on the
Approve control, and resolving it kept the same conversation selected. A queue-discovery failure did
not hide the two bots needing attention.

Five fixture browser checks passed in **8.88s** using Chromium **153.0.8010.12** and Playwright
**1.63.0**. The inline approval was checked at 390×844; Fleet attention captures were visually
inspected at 1440×1000 and 390×844. Both report zero horizontal overflow and no page errors; the
phone attention bar does not cover the Fleet controls. The screenshots and source-hash metadata are
in [`artifacts/fleet-attention/`](artifacts/fleet-attention/). These use synthetic waits and approvals,
not a live provider, executor or device.

## Guided bot setup and human handoff (2026-10-09)

Chromium **153.0.8010.12** / Playwright **1.63.0** ran
`.venv/bin/python -m pytest -q tests/e2e/test_browser.py::test_guided_bot_creation_reviews_configuration_at_desktop_tablet_and_phone`.
The fixture passed **1 test in 5.19s** against a configured-shape provider route and a test-only dummy key; it made no model call and
verified idempotent bot creation does not start a run. Sensitive-input and same-session challenge unit regressions passed **3 tests
in 0.55s**. The browser journey captured purpose, tool/limit/handoff configuration and the full review at desktop (1440×960), tablet
(900×1024) and phone (390×844), including a phone-focused handoff disclosure and a second view scrolled to the final review row.

I inspected the purpose/configuration/review captures, the phone handoff panel, and the bottom of the review list at all three sizes.
The layouts fit their viewports; the fixed Create control remains visible while the complete review stays scrollable above it, and the
phone handoff disclosure remains readable. Playwright reported no page errors or horizontal overflow. Source hashes, trace and captures
are in [`artifacts/bot-setup/`](artifacts/bot-setup/). These are local fixture screenshots, not a live sign-in, real CAPTCHA, physical
phone, or screen-reader test. Field detection remains heuristic.

## Marketing copy for local human browser handoff (2026-10-09)

The anonymous marketing-site suite passed **24 tests in 29.03s** with warnings treated as errors.
It verified the public capability language, local assets, anonymous page loading and zero external
requests. The inspected feature-section captures were regenerated from `website/index.html`
(SHA-256 `011d718edfd980d0c7250ba07fe91c5f5987f54c034963ad5e4cb1b06248531d`) at desktop
(1440×900), tablet (900×1024) and phone (390×844); see [`artifacts/provider-signin/`](artifacts/provider-signin/). The new
copy identifies same-session password/code/CAPTCHA entry as experimental on Linux and says phone
handoff is unavailable. I inspected each capture: cards remain inset and readable, the long state
card does not cover neighboring content, the phone model-route chips wrap without horizontal page
scroll, and the handoff wording stays within its card. These are local screenshots only; no live
challenge or provider session was used.

## Purpose-derived Bot names and address review (2026-10-09)

The New Bot wizard now proposes a professional display name and local address from the purpose text using a deterministic
browser-side rule. Changing purpose refreshes the suggestion until either field is edited; the rule preserves compounds such as
“follow-up tasks,” cuts trailing clauses, and uses “Organizer” for organize/sort requests instead of assigning every one to a
generic planner role. For example, it suggests “Follow-up Task Monitor” and “Receipts Organizer.” Later edits remain visible through
the complete review. The visible chat identity uses the display name while routes continue using the unchanged local address. The
naming step made no model/provider request and creation started no run.

The Chromium **153.0.8010.12** / Playwright **1.63.0** journey passed within a three-test focused bot-setup run (**3 passed in
9.66s**) at desktop **1440×960**, tablet **900×1024**, and phone **390×844**. I inspected the identity form, review top and bottom,
and resulting chat at all sizes. The review remains scrollable above its fixed action footer; the chat header shows the human display
name; no horizontal overflow or page errors were recorded. Captures, trace, exact source hashes and validation JSON are in
[`artifacts/bot-naming/`](artifacts/bot-naming/). The API/migration set separately passed **50 tests in 8.98s**, and the anonymous
marketing/token checks passed **31 tests in 33.46s**. The browser uses a test-only provider-shaped route and submits no inference
request. No live model, provider, account, physical phone or screen reader was used.

The naming-quality follow-up passed the same focused Chromium journey (**1 passed in 4.13s**) after adding explicit checks for the
compound “Follow-up Task Monitor” and “Receipts Organizer.” It saved and I inspected the automatic suggestion card at desktop
**1440×960**, tablet **900×1024** and phone **390×844**; the reviewed name and stable address remain legible with no horizontal
overflow. The matching `automatic-name-*.png` captures and refreshed source hashes are included in `artifacts/bot-naming/`.

The naming rules now also cover reminder, alert, filing, and Bot-team coordination requests without a model call. “Remind me to
renew my passport next month” becomes “Passport Renewal Reminder”; “Alert me when an invoice is overdue” becomes “Invoice Reminder”;
“File my monthly expense receipts into folders every Friday” becomes “Expense Receipt Organizer”; and “Coordinate work across my
bots and keep me updated” becomes “Workspace Coordinator.” The naming journey confirms these names and generated addresses, then
captures the coordinator suggestion at desktop, tablet and phone sizes. I inspected each capture; the title and stable address remain
readable and the dialog remains within the viewport. The phone and tablet captures keep the suggestion visible above the fixed
action footer. The test first failed for the reminder (“Workspace Assistant”), alert (“Workspace Reminder”), and coordinator
(“Across Bots Coordinator”) prompts, then passed after the local rules were extended (**1 test in 6.56s**).

The anonymous marketing workflow copy was checked by `tests/e2e/test_website.py::test_public_workflow_describes_named_recurring_tasks`
after adding the naming claim guard (**1 passed in 3.04s**). Its captures at **1440×900**, **900×1024**, and **390×844** all
report zero overflow and no page errors, and their recorded `website/index.html` hash matches the source. I inspected the workflow
section at desktop, tablet and phone widths; the added naming explanation wraps within the first step card without shifting or
overlapping its peers. Updated captures and validation are under [`artifacts/scheduled-tasks/`](artifacts/scheduled-tasks/).

## Friendly Bot names with visible roles (2026-10-09)

The setup suggestion now pairs a deterministic, roster-unique teammate name with the purpose-derived role. Its stable local address
uses the role so the same purpose remains discoverable in CLI/API routes. The Studio header separates the personal-style name from
“AI bot · [role]”, including at phone widths; it does not describe a Bot as a human operator. The setup name and address remain
editable. Name generation makes no model request and creates no run.

The focused Chromium naming journey and anonymous website workflow check passed together (**2 passed in 9.56s**) at app sizes
**1440×960**, **900×1024**, **390×844**, and public-site sizes **1440×900**, **900×1024**, **390×844**. The generated-name browser
fixture creates an existing Bot with the deterministic candidate first, then verifies that the next Bot receives a different
identity while retaining the same role-based address. I inspected generated chat headers, the phone address field above its fixed
footer, and the public workflow card at each site size. The role remains readable on phone, with no horizontal overflow. No
provider request was made; the website test was anonymous and made no external request. Captures and metadata are in
[`artifacts/bot-naming-quality/`](artifacts/bot-naming-quality/) and
[`artifacts/bot-purpose-refinement/marketing/`](artifacts/bot-purpose-refinement/marketing/).

The exact-message **Make a bot** browser journey also passed after replacing a fixed 300 ms assertion delay with a wait for the
wizard heading (**1 passed in 5.56s**). The prior assertion ran before the wizard's local capability/preferences requests had
completed; the journey now waits for the real visible state. The separate coordinator direct-chat journey passed in the same
focused run (**1 passed in 5.14s**). No provider request was made; the journey used a synthetic local route.

## Named workspace coordinator direct chat (2026-10-09)

The selected coordinator is ordered first in the roster, labelled there and in Studio, and opens as the default chat on a fresh
Studio visit. Bot Settings can replace or clear the single workspace role without changing the Bot's model, tools, account
connections or permissions. The selected Bot continues to use its own canonical conversation; all other Bots remain directly
addressable. This slice does not yet dispatch work to specialists.

`tests/e2e/test_browser.py::test_named_workspace_coordinator_is_first_class_direct_chat_at_responsive_sizes` passed **1 test
in 6.08s** on Chromium **153.0.8010.12** / Playwright **1.63.0**. It covered default coordinator selection, role replacement,
specialist direct chat and the role badge at **1440×960**, **900×1024** and **390×844**. I inspected all three captures; the
phone uses a compact label, the chat and composer remain visible, and there is no horizontal page overflow or browser error.
Evidence, trace and source hashes are in [`artifacts/workspace-coordinator/`](artifacts/workspace-coordinator/). Fixtures use
mock route records and make no provider calls; no physical phone or screen-reader validation was performed.

## Content-free coordinator checkpoint timeline (2026-10-09)

The reviewed specialist task card now exposes its committed progress markers in a collapsible timeline. The list is ordered by
the child event cursor, returns at most the latest 16 markers while showing the total, and uses text labels for state. It also
states that the journal does not continue a task after restart. The timeline contains no event payload, prompt, hidden reasoning,
action arguments, tool output or secrets. This remains audit visibility; task execution recovery is not implemented.

`tests/e2e/test_browser.py::test_coordinator_specialist_dispatch_is_reviewable_at_all_viewports` passed **1 test in 18.16s**
on Chromium **153.0.8010.12** / Playwright **1.63.0** after verifying the final phone checkpoint clears the sticky composer.
The preceding combined app/site rerun passed both the browser flow and anonymous workflow check (**2 passed in 20.08s**).
I inspected the expanded task card at desktop (1440×960), tablet (900×1024), and phone (390×844); the state and event sequence
remain legible, the final phone marker sits above the composer, card contents wrap, and all viewports report zero horizontal overflow.
The anonymous workflow section at desktop (1440×900) and phone (390×844) accurately says the timeline cannot continue a run
after restart. Its Playwright check verified all three site sizes, zero external requests, no page errors, and zero overflow.
Screenshots, traces, viewport/source metadata, and validation output are in
[`artifacts/workspace-task-dispatch/`](artifacts/workspace-task-dispatch/). Tests use only a local mock model and SQLite; no live
provider, external browser session, physical phone or screen reader was used.

## Even outlines for checkpoints and message references (2026-10-09)

The two remaining one-sided accents in the dashboard—checkpoint rows and quoted message
references—now use the same quiet full outline as nearby surfaces. The fixture-based browser
checks passed **4 tests in 22.51s** on Chromium **153.0.8010.12** / Playwright **1.63.0**:
the coordinator handoff journey and the keyboard-accessible reply journey at desktop
(1440×1000), tablet (900×1024) and phone (390×844). The tests assert equal border widths and
colors on all sides, preserve reply focus and persisted message linkage, and verify no page
errors or horizontal overflow. I inspected the desktop and phone captures in
[`artifacts/workspace-task-dispatch/`](artifacts/workspace-task-dispatch/) and
[`artifacts/message-replies/`](artifacts/message-replies/); both layouts remain readable, and
checkpoint rows stay above the phone composer. The Impeccable detector found no remaining
side-tab findings in this stylesheet; it still reports three pre-existing advisory radius
values outside the documented token scale. No live provider, account, or physical device was
used.

## Outlook Calendar Connections states (2026-10-09)

`tests/e2e/test_browser.py::test_outlook_calendar_uses_account_consent_and_one_bot_grant_at_all_viewports` passed **1 test** using
synthetic Microsoft account/calendar responses, a real local API/store grant, and intercepted sign-in navigation. It captured the
unconnected disclosure and granted account at desktop **1440×960**, tablet **900×1024**, and phone **390×844**. All sizes reported
zero horizontal overflow, no browser errors, and no external requests. I inspected overview and granted-state captures for all sizes;
the permission explanation remains readable, the single-calendar grant fits the layout, and the phone keeps its controls reachable.
Evidence and source hashes are in [`artifacts/outlook-calendar/`](artifacts/outlook-calendar/). These fixtures do not verify a
Microsoft registration, account, consent screen, Graph response or live provider access.

## Outlook Mail Connections states (2026-10-09)

`tests/e2e/test_browser.py::test_outlook_mail_grant_and_consent_boundary_fit_all_viewports` passed with a synthetic
Microsoft account and intercepted authorization destination. The real local API persisted the Bot grant; no mailbox content or
Microsoft request was used. At desktop **1440×960**, tablet **900×1024**, and phone **390×844**, the expanded permission
disclosure and the granted-account state had zero horizontal overflow, browser errors, or external requests. I inspected both
captures at each size; the account-level `Mail.Read` notice stays readable, the per-Bot grant and revoke controls fit, and the
phone layout remains reachable. Chromium **153.0.8010.12** / Playwright **1.63.0** evidence and screenshots are in
[`artifacts/outlook-mail/`](artifacts/outlook-mail/). This does not verify a Microsoft registration, account, consent screen,
search result or live Graph request.

The anonymous marketing table test, `tests/e2e/test_website.py::test_outlook_calendar_and_mail_support_row_is_truthful_and_reachable_at_all_viewports`,
also passed at desktop **1440×900**, tablet **900×1024**, and phone **390×844**. I inspected the viewport captures and complete
table captures at all three sizes. The experimental row names Outlook Mail search previews, preserves the provider-consent and
Gmail-verification limits, has no page/table overflow, and sends no external requests. Its source hashes, screenshots and test
metadata are in [`artifacts/outlook-mail/site/`](artifacts/outlook-mail/site/). No account, provider, screen reader or physical
phone was used.

The anonymous marketing support table was shortened without dropping the consent, field-detection, or public-destination limits.
At phone width, its repeated support-status column is hidden because the first column already labels every capability; the
explanation now wraps without horizontal table scrolling. Chromium **153.0.8010.12** / Playwright **1.63.0** passed
`tests/e2e/test_website.py::test_outlook_calendar_support_row_is_truthful_and_reachable_at_all_viewports` and
`tests/e2e/test_website.py::test_provider_availability_is_readable_without_horizontal_page_scroll` (**2 passed**). Desktop
**1440×900**, tablet **900×1024**, and phone **390×844** report no page overflow, browser errors, or external requests. I inspected
the anonymous viewport captures and complete desktop/tablet/phone table captures; all five rows, including the full experimental
limitations, remain readable. Source and style hashes are recorded in
[`artifacts/outlook-calendar/site/site-validation.json`](artifacts/outlook-calendar/site/site-validation.json). No live provider,
account, screen reader or physical phone was used.


The naming-quality follow-up adds `Project Status Reporter` for “Create a weekly project status update for leadership,” including the
conversational prefix “I need a bot that…”. A test-first browser regression first observed the generic “Workspace Assistant” fallback,
then passed after the local naming rule was extended. The same Chromium journey passed in **6.68s** at desktop **1440×960**, tablet
**900×1024**, and phone **390×844**. The phone address field was scrolled fully above the fixed footer and checked for visibility; I
inspected that capture with the automatic suggestions at all three sizes. Evidence and source hashes are in
[`artifacts/bot-naming-quality/`](artifacts/bot-naming-quality/). No model/provider request, screen reader or physical phone was used.


The Connections page now names Gmail as unavailable and explains the `gmail.readonly` restricted-scope boundary, the conditional
verification/security-assessment requirements, and the fact that Google Calendar consent does not grant Gmail access. It requests no
Gmail permission and has no dead Connect button. The new fixture-only Chromium test
`tests/e2e/test_browser.py::test_gmail_unavailability_is_explicit_and_has_no_dead_connect_control` checks that notice at desktop
**1440×960**, tablet **900×1024** and phone **390×844**, with no external requests, page errors or horizontal overflow. I inspected each
responsive capture; evidence and hashes are under [`artifacts/gmail-availability/`](artifacts/gmail-availability/). No OAuth client,
Gmail account, live provider request, screen reader or physical phone was used.

## Final browser journeys and naming review (2026-10-09)

The complete `tests/e2e/test_browser.py` file passed **102 tests in 263.26s** on Chromium **153.0.8010.12** / Playwright
**1.63.0**. This includes responsive bot setup, purpose-derived names and stable editable addresses; workspace conversations and
coordinator handoff; sensitive fields revealed by clicks, typing and waits; human checkpoints; provider grants; and approval, artifact,
memory, reply, and replay journeys. The entire browser suite reported no failures or fixture teardown errors. The tests use local
SQLite, synthetic pages, and provider fixtures; no hosted model, paid provider, Microsoft account or live external request was used.

I inspected the fresh naming screenshots at desktop **1440×960**, tablet **900×1024**, and phone **390×844**, including the editable
name/address and final review. I also inspected the granted Outlook Calendar and Mail panels at each viewport after Connections began
preserving their open state across refreshes. The Bot suggestion reads as a human-facing role, the stable address remains editable,
and both permission summaries remain visible after a grant. Updated screenshots, traces and per-journey source hashes are in
[`artifacts/bot-naming-quality/`](artifacts/bot-naming-quality/), [`artifacts/outlook-calendar/`](artifacts/outlook-calendar/), and
[`artifacts/outlook-mail/`](artifacts/outlook-mail/). These are fixture-based visual checks, not live provider, screen-reader or
physical-device validation.

## Human-facing Bot names in provider access (2026-10-09)

The three fixture journeys for Google Calendar, Outlook Calendar, and Outlook Mail passed after Connections was updated to resolve
grant records to the current Bot display name. The tests check the chosen name in both the Bot selector and saved grant summary, and
the Outlook Mail disconnect dialog keeps the same name. The internal Bot address remains stable for routing. I inspected the refreshed
granted screenshots at desktop **1440×960**, tablet **900×1024**, and phone **390×844**; all three journeys reported zero horizontal
overflow, and their provider summaries show the readable Bot name without the internal slug. Evidence and current app source hashes are
under [`artifacts/google-calendar/`](artifacts/google-calendar/), [`artifacts/outlook-calendar/`](artifacts/outlook-calendar/), and
[`artifacts/outlook-mail/`](artifacts/outlook-mail/). These are fixture-only flows; no provider credentials or live provider requests
were used.

## Run-detail event-history verification (2026-10-09)

The run detail contains a keyboard-accessible “Verify event history” action and an announced status result. A local Chromium scenario
checked intact history and then confirmed that a modified stored payload raises an alert naming the failing event. I inspected screenshots
at desktop **1440×960**, tablet **900×1024**, and phone **390×844**; the control stays reachable, stacks below its status on narrow
screens, and all three document widths matched the viewport. A terminal fixture run prevented the active supervisor from starting it.
No provider call or external request was made. The captures and trace are under [`artifacts/transcript-integrity/`](artifacts/transcript-integrity/).
The matching CLI verifier reports legacy events as partial and returns a nonzero exit on tampering; its intact/legacy/tampered cases pass in `tests/test_cli.py`.

## Exact-message Bot setup from Studio chat (2026-10-09)

The browser journey `test_user_can_start_bot_setup_from_the_exact_chat_request` used a seeded conversation
with two unrelated user requests, keyboard-activated **Make a bot** on the earlier request, and confirmed
the exact text/source in the review flow while excluding the later request. No Bot or run was created.
The anonymous marketing journey checked the current setup and model-default copy, with zero external
requests, JavaScript errors, and horizontal overflow.

The focused browser/marketing batch passed **5 tests in 13.44s** on Chromium **153.0.8010.12** and
Playwright **1.63.0**. Captures were opened and inspected at app desktop **1440×960**, tablet **900×1024**,
and phone **390×844**, including a separate `is_mobile`/coarse-pointer run that tapped the action and
measured its touch target at **44px**. The anonymous marketing site was inspected at desktop **1440×900**,
tablet **900×1024**, and phone **390×844**. Node syntax validation and `git diff --check` passed.

App screenshots, trace and source hashes are in [`artifacts/bot-from-message/`](artifacts/bot-from-message/);
the anonymous marketing cards and validation are in [`artifacts/bot-from-message/marketing/`](artifacts/bot-from-message/marketing/).
Fixtures were local and no model/provider call was made. Screen-reader, physical-device and cross-browser
validation were not performed.

## Bot-purpose refinement and truthful marketing copy (2026-10-09)

The new coordinator draft was inspected before and after application at desktop **1440×960**, tablet **900×1024**, and phone
**390×844** in Chromium **153.0.8010.12** / Playwright **1.63.0**. The responsive fixture checked that the suggestion does not
replace the original purpose until **Use this draft**, carries no later user message or assistant reply, keeps the suggested
professional Bot name visible, leaves the setup review controls reachable, and produces no page errors or horizontal overflow.
I inspected all four app captures, including the applied purpose at phone width. The anonymous marketing workflow and Bot-setup
copy tests passed in the same viewport family; I inspected the final workflow screenshots after placing the experimental purpose
draft under Bot setup. No external requests or page errors occurred. App captures, trace and hashes plus anonymous marketing
captures are in [`artifacts/bot-purpose-refinement/`](artifacts/bot-purpose-refinement/). All responses were fixtures: no live
model/provider call, screen reader, or physical phone was used.

## ChatGPT background-use permission (2026-10-09)

The Bot settings permission was checked using a synthetic local ChatGPT connection. The fixture made no provider requests
and the browser reported no external requests. I inspected the permission panel at **1440×960**, **900×1024**, and
**390×844**, the phone confirmation sheet, and the saved-permission state. The browser flow checked keyboard focus trapping,
focus restoration to the refreshed control after allow/revoke, route-bound status, and no horizontal overflow. The anonymous
marketing copy was separately inspected in the Plans & keys card and expanded FAQ at desktop **1440×900**, tablet
**900×1024**, and phone **390×844**.

The focused app browser pair passed **2 tests in 10.39s** and the marketing browser batch passed **2 tests in 4.20s** on
Chromium **153.0.8010.12** / Playwright **1.63.0**. Backend consent, redaction and revocation checks passed **13 tests in
2.82s**. Captures and trace are in [`artifacts/chatgpt-background-consent/`](artifacts/chatgpt-background-consent/);
marketing captures and trace are in [`artifacts/chatgpt-background-consent/marketing/`](artifacts/chatgpt-background-consent/marketing/).
Live SIWC eligibility, user sign-in, provider limits and account behavior remain unverified.

## Professional names and Fleet state labels (2026-10-09)

The name suggestion was rerun against a purpose that includes the conversational wrapper (“I need a bot that…”). It proposed
“Project Status Reporter” and the separate stable address `project-status-reporter`; purpose changes refresh both only until
the owner edits them. This stays local and deterministic. We use clear work-based names instead of assigning an invented human
identity, so the name remains understandable in the roster and approvals. The owner can still choose any preferred name.

`uv run pytest -q tests/e2e/test_browser.py::test_purpose_derived_bot_name_is_editable_and_reviewed_at_responsive_sizes --no-header`
passed **1 test in 6.07s** on Chromium **153.0.8010.12** / Playwright **1.63.0**. I inspected the automatic-name screen at
desktop **1440×960**, tablet **900×1024**, and phone **390×844**; the name stays legible, the phone sheet scrolls above its fixed
actions, and no horizontal overflow or page error occurred. The local rule made no provider request or Bot/run creation.

The legacy Bot-card stylesheet's running/paused colored rails were removed. The active `/bots` path redirects to the responsive
Fleet, where a status chip already spells out “Needs you” or “Waiting for you.” The synthetic queue-failure journey passed at
desktop and phone (**2 tests in 2.30s**); I opened both captures and confirmed the text state stays distinct, the attention notice
does not cover Fleet content, and neither view overflows. Captures and viewport records are in
[`artifacts/bot-naming-quality/`](artifacts/bot-naming-quality/) and [`artifacts/fleet-attention/`](artifacts/fleet-attention/).
After the latest public-copy edit, the anonymous Plans & keys and expanded FAQ check passed **1 test in 2.76s**. I inspected the
refreshed phone captures; the key-based OpenCode path and ChatGPT preview/consent limits remain readable without overflow or
external requests. They are saved in [`artifacts/chatgpt-background-consent/marketing/`](artifacts/chatgpt-background-consent/marketing/).

## Explicit Bot-to-Bot reference grants (schema v38)

`tests/e2e/test_browser.py::test_explicit_cross_bot_fact_share_is_reviewable_revocable_and_responsive` exercised the real
SQLite/API/Studio path with two local Bots and one synthetic reviewed fact. The owner saw the exact fact, chose a named recipient,
and reviewed the disclosure before granting. The recipient saw source Bot, revision and the untrusted-reference boundary, then
removed the grant; new runtime recall stopped. A fresh Store connection observed the persisted grant before revocation. This
used no provider/model request, external request, generated credential or real personal fact.

Chromium **153.0.8010.12** / Playwright **1.63.0** passed at desktop **1440×960**, tablet **900×1024**, and phone **390×844**.
The share review, incoming reference, keyboard dismissal/focus return, and recipient revocation were exercised with no horizontal
overflow or page errors. I inspected the six captures and trace in [`artifacts/fact-sharing/`](artifacts/fact-sharing/); I added
spacing below the recipient selector after reviewing the initial phone capture. A separate backup/restore test verifies the grant
remains available in a held restored database. These fixtures do not verify a live provider's treatment of a previously submitted
snapshot, screen-reader behavior, or a physical phone.

The corresponding anonymous marketing workflow was refreshed at desktop **1440×900**, tablet **900×1024**, and phone
**390×844**. Inspection showed that the shared card style stretched each paragraph to fill the equal-height workflow cards, leaving
large gaps between paragraphs. The workflow cards now keep paragraphs at their natural height; the refreshed three-size captures
show a continuous reading flow with no horizontal overflow, external requests, or browser errors. The anonymous website test passed
again (**1 test in 2.78s**) after the CSS change. Screenshots and validation metadata are in
[`artifacts/bot-purpose-refinement/marketing/`](artifacts/bot-purpose-refinement/marketing/).

The focused implementation batch, including migration, held restore, API idempotency, pagination, runtime recall, and browser
review/revoke, passed **68 tests in 10.99s**. `node --check src/hutch/server/static/app.js`, Python compilation, and
`git diff --check` passed. The provider-free Chromium flow covered desktop, tablet and phone for share review, owner view and
recipient view; exact snapshots persisted across a fresh Store connection and revocation stopped subsequent recall. No live model,
provider, account or external network request was used.

## OpenCode coding-task handoff (schema v39)

`tests/e2e/test_browser.py::test_opencode_coding_handoff_is_reviewed_and_responsive` exercised the complete chat-to-review-to-durable-card path using a temporary Git project and a mocked OpenCode availability response. It also exercised the unavailable-CLI error and retry, source/authority disclosure, keyboard focus trap, command copy, card disclosure, and 320px/390px/900px/1440px layouts. The test starts no OpenCode process, calls no model/provider, and observed no request outside the local Hutch fixture.

I opened the saved review and prepared-card captures at desktop **1440×960**, tablet **900×1024**, phone **390×844** and compact phone **320×844**. At narrow widths, the modal body scrolls above its fixed actions, the brief and disclosure wrap, and the launch command stacks and wraps without page/card overflow. The modal's focus stays contained; the prepared card remains reachable above the pinned composer. The dialog displays only the project directory name, not its local path. The full trace, screenshots and machine-readable validation record are in [`artifacts/opencode-handoff/`](artifacts/opencode-handoff/); browser is Chromium **153.0.8010.12**, Playwright **1.63.0**, Python **3.13.15**. These screenshots are fixture evidence, not a live OpenCode session.

The anonymous marketing test also opened the new coding-handoff FAQ and captured desktop **1440×900**, tablet **900×1024** and phone **390×844**. I inspected the desktop and phone captures; the FAQ names the local CLI, separate OpenCode account/usage, unsandboxed approved shell commands and retained review branch. `tests/test_code_handoff.py::test_interactive_process_keeps_terminal_and_owns_a_separate_group` separately verified a PTY child can read input, receive Ctrl+C while foreground, and return foreground input to Hutch. That terminal fixture is not a screenshot, real OpenCode session or provider call.

## Workspace schedule overview and pause (schema v40)

`tests/e2e/test_browser.py::test_schedule_overview_shows_local_times_and_pauses_only_future_occurrences` covers three Bots with separate time zones and pause states, a currently running task, and a workspace pause persisted through reload. It confirms that the transaction fences a scheduler snapshot read before the pause; existing execution continues, and a Bot-specific pause remains after workspace resume. Windows missed during the pause remain subject to each task's catch-up policy after resume. The first phone render exposed an icon-only pause action with no icon because the shared phone header hides button labels. The schedule control now keeps its action text visible and stacks it beneath the status line; the browser test checks its 44px height, readable label size and width, and keyboard focus restoration after both commands. I also inspected both phone scroll positions so all three tasks are reviewable without a toast covering the list, and the empty state at all three viewports.

Chromium **153.0.8010.12** / Playwright **1.63.0** captures and trace are in [`artifacts/schedules/`](artifacts/schedules/). Desktop **1440×960**, tablet **900×1024**, and phone **390×844** showed no horizontal overflow or browser errors. The anonymous site's Scheduling card was checked at the same widths with no external requests; see `artifacts/bot-purpose-refinement/marketing/site-scheduling-*.png`. The focused browser and anonymous-site tests passed. This evidence uses local SQLite/fixture data, not real scheduled provider calls, a screen reader or a physical phone.
