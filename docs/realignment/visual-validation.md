# Visual validation record

## Shared design system across Studio, Connections, and marketing (2026-10-09)

The shared semantic tokens now feed the operator UI and static marketing build from
`website/tokens.json`. Studio and Connections use the same workspace sidebar,
contextual header, system body font, emerald action color, azure focus ring, and
8px control / 12px panel geometry. Marketing keeps its editorial layout, Archivo
display headings, and detailed 3D mascot while using the same body type and
semantic palette. The app's 2D Bot silhouettes remain product identity, not status.

I inspected the actual user-facing Studio and Connections SPA routes at desktop
**1440×960**, tablet **900×1024**, and phone **390×844**, plus the marketing site
at those sizes. The Connections capture uses `/#/connections` inside the shared
workspace shell. Marketing was captured as both a readable viewport and a full-page
overview at each size. An earlier exploratory capture used the compatibility route at
`/connections`; it showed an older server-rendered page and was not used as visual
evidence for the current Connections screen. The twelve current screenshots have been
opened and reviewed. The operator layouts keep their shared shell at tablet and
phone widths; the website preserves its distinct editorial composition. A 320px
reflow check reports no horizontal overflow on any of the three surfaces.

`tests/e2e/test_design_system.py::test_shared_design_tokens_render_consistently_across_all_surfaces`
and `tests/test_site_tokens.py` passed together (**8 passed**). The rendered
checks compare body font, background/surface colors, primary action, focus ring,
panel/control geometry, and the Studio/Connections shell. Chromium
**153.0.8010.12** / Playwright **1.63.0** generated screenshots, validation JSON,
and a trace in [`artifacts/design-system/`](artifacts/design-system/). The browser
made no external requests and no provider calls. This is local fixture evidence;
no screen reader or physical mobile device was used. The anonymous marketing suite
`tests/e2e/test_website.py` passed separately (**27 passed**).

## Assistant usage settings disclosure (2026-10-10)

The advanced assistant settings view summarizes the work-step and time limits
without immediately exposing token and currency fields. I inspected the
collapsed and expanded states separately at desktop **1440×960**, tablet
**900×1024**, and phone **390×844**. The phone version stacks each setting in a
single column and keeps keyboard focus visible while the disclosure is open.

`tests/e2e/test_browser.py::test_bot_usage_limits_are_optional_clear_and_use_everyday_time_units`
passed (**1 passed**) on Chromium **153.0.8010.12** / Playwright **1.63.0** at
desktop **1440×960**, tablet **900×1024**, phone **390×844**, and compact phone
**320×740**. It verifies the summary at all four sizes, keyboard operation on
phone, no horizontal overflow, 15-minute display for the stored 900-second
default, and conversion of 2.5 minutes back to 150 seconds. No provider or
external requests were made. Captures, source hashes, `validation.json`, and a
trace are in [`artifacts/assistant-usage-details-2026-10-10/`](artifacts/assistant-usage-details-2026-10-10/).

## Marketing icons and legibility refinement (2026-10-10)

The website's choice and approval cards now align each illustration icon with
its heading, reducing repeated tile chrome and keeping the cards easy to scan.
Small hero and example labels are at least 12px. The main scene retains the
detailed 3D Hutch character while using a restrained surface and neutral shadow
rather than a blue glow with orbit rings. Benefit and example illustrations use
simpler color fields.

The responsive check covers **1440×960**, **900×1024**, **390×844**, and
**320×740**, verifying icon/title alignment, readable label size and leading,
and no horizontal overflow. The anonymous website suite passed **28 tests in
43.56s** on Chromium **153.0.8010.12** / Playwright **1.63.0**. I viewed the
hero at desktop, tablet, and phone sizes, then opened the choice cards, approval
flow, benefit cards, and example cards separately at desktop and phone sizes.
There were no page errors, external requests, or provider calls. Screenshots,
source hashes, and validation records are in
[`artifacts/marketing-card-hierarchy-2026-10-10/`](artifacts/marketing-card-hierarchy-2026-10-10/).
No screen reader or physical phone was used. The full marketing page still needs
a broader content and surface review.

## Guided Bot setup YAML import (2026-10-09)

I inspected the first-step import panel and final imported review at desktop **1440×960**, tablet
**900×1024**, and phone **390×844**. The file chooser is keyboard-operable, the import status is
announced, long review content scrolls inside the modal, and its action footer remains visible. The
phone review intentionally scrolls through the full configuration while keeping Cancel/Create visible.
All three sizes have no horizontal page overflow.

Chromium **153.0.8010.12** / Playwright **1.63.0** passed
`tests/e2e/test_browser.py::test_bot_setup_yaml_import_fills_reviewed_draft_without_saving_until_confirmation`.
The fixture imports only into an unsaved draft, walks each step, and verifies no Bot or run exists until
the user confirms **Create bot**. A file over 64 KiB is rejected in the browser before it sends an import request. API cases
reject wrong versions, unknown/authority-bearing fields, unsafe Python tags, aliases, duplicate keys and oversized content;
another API case confirms that a missing local provider key does not block draft review, while Bot creation still requires it.
The local browser made no model or
external request; the run used local fixtures. Screenshots, trace and metadata are in
[`artifacts/bot-setup-import/`](artifacts/bot-setup-import/). No screen reader or physical phone was used.

## Bot setup YAML review and download (2026-10-09)

The final guided setup review now has a keyboard-operable YAML preview and download action. The
preview fits inside the modal at desktop **1440×960**, tablet **900×1024**, and phone **390×844**;
the YAML block scrolls within its own boundary, the modal footer stays visible, and the page has no
horizontal overflow. I inspected all three rendered captures. Pressing Enter builds the preview and
downloads the same text. The setup remains unsaved until **Create bot** is confirmed.

Chromium **153.0.8010.12** / Playwright **1.63.0** passed
`tests/e2e/test_browser.py::test_guided_bot_creation_reviews_configuration_at_desktop_tablet_and_phone`.
The API test validates parseable YAML and checks that endpoint URLs, local paths and chat-source
references are omitted, the response is not cached, and no Bot/run is saved. The browser used a
synthetic route and test-only credential marker; no model call or external request occurred. Screenshots,
the downloaded YAML sample, validation metadata and trace are in
[`artifacts/bot-setup/`](artifacts/bot-setup/). No screen reader or physical phone was used.

## Searchable pinned Bot roster and flat app mascots (2026-10-09)

The Studio roster keeps the workspace coordinator first, then shows pinned Bots in a
named group and the rest under “All bots”. Search matches both groups. Pinning is saved
with the Bot and changes only its roster placement. Hiding is reversible from a disclosed
Hidden bots group and does not pause work or schedules. One Bot overflow control contains
pin, named section, hide/show, template download, safe duplicate and settings actions.
At this validation point, the operator app used flat, solid-colour 2D silhouettes with
two white glints. The welcome view used that Bot's same identity. The eye treatment was
refined in the follow-up below; the detailed original 3D mascot on the marketing site
remains separate and unchanged.

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

## Shape-aware flat Bot faces (2026-10-10)

I reviewed the eight mascot silhouettes separately at a magnified **128px** preview size.
The earlier diagonal slits read as repeated eyebrow-like marks, especially on pointed
heads. The product now uses softer upright ink ovals, with a per-shape centerline, spacing,
proportion, height and subtle tilt. The drop and triangle sit lower in their wider body;
the shield keeps a compact pair below its taper. The picker preview remains the same SVG
geometry used by the selected Bot throughout Studio.

Chromium **153.0.8010.12** / Playwright **1.63.0** passed
`tests/e2e/test_design_system.py::test_flat_mascot_eyes_stay_inside_every_silhouette`.
The test measures each rotated ellipse against its actual vector path, checks shape-specific
face layouts and picker/preview parity, and verifies minimum **3:1** eye-to-body contrast.
I opened the eight individual face captures, plus the picker and roster at desktop
**1440×960**, tablet **900×1024**, phone **390×844**, and compact phone **320×740**. Phone
pickers keep a balanced two-row layout without horizontal overflow. Captures, source hashes,
metadata and a Playwright trace are in [`artifacts/mascot-eye-review/`](artifacts/mascot-eye-review/).
This used local SQLite fixtures only; no provider call, screen reader or physical phone was tested.

## Simpler 2D mascot eyes after owner review (2026-10-10)

The earlier fitted visor and pale slits still read as a mask. The app now uses
two near-round dark eyes directly on each colored silhouette, with matched
proportions and subtle inward tilt. Their positions and sizes adapt to the orb,
capsule, bean, drop, pebble, shield, triangle, and hex heads. The face stays
flat and restrained; the more detailed 3D character remains on the marketing
site.

Chromium **153.0.8010.12** / Playwright **1.63.0** passed
`tests/e2e/test_design_system.py::test_flat_mascot_eyes_stay_inside_every_silhouette`
in **7.84s**. The browser measures every eye path within its colored head,
checks at least **3:1** eye-to-body contrast and balanced placement, and compares
all eight identity-picker faces with their selected previews. I opened the eight
enlarged shape captures, picker, phone settings and roster individually. The
44px picker controls remain usable, the phone layout fits without horizontal
overflow, and no page errors occurred. Captures, source hashes and trace are in
[`artifacts/mascot-eye-review-2026-10-10/`](artifacts/mascot-eye-review-2026-10-10/).
This fixture did not use providers, a screen reader, or a physical phone.

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

### Current app typography pass (2026-10-10)

The app and its supporting server pages now share locally bundled Archivo
headings, a 24px/1.25 desktop page title (22px on phones), and 16px/1.55 system
sans interface copy. The first responsive check measured computed font family,
font readiness, title size/leading, body size/leading, and still status marks.
Working/status and notice/error style assertions use offscreen or temporary
fixtures; the screenshots contain no synthetic active run or simultaneous
success and failure banners. The test batch passed **9 tests in 11.85s** on
Chromium **153.0.8010.12** / Playwright **1.63.0**. I inspected Studio and the
legacy server Connections route independently at desktop **1440×960**, tablet
**900×1024**, and phone **390×844**. No page errors or horizontal overflow were
recorded. The Connections captures are compatibility-page typography evidence;
their technical setup content remains a separate redesign issue. These local
fixtures made no provider calls and do not verify packaged-install font loading,
a screen reader, or a physical phone.

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

The anonymous marketing test opened the coding-handoff FAQ and captured desktop **1440×900**, tablet **900×1024** and phone **390×844**. I inspected each phone page individually. A two-line FAQ title initially ran under its disclosure arrow; the browser regression reproduced it, then passed after the shared spacing token restored reserved space. The final capture shows the title and arrow clearly separated. The shorter answer explains the private OpenCode profile, local terminal launch, separate worktree, usage, and command-authority boundary. Screenshots, trace and source hashes are in [`artifacts/chatgpt-background-consent/marketing/`](artifacts/chatgpt-background-consent/marketing/). `tests/test_code_handoff.py::test_interactive_process_keeps_terminal_and_owns_a_separate_group` separately verified a PTY child can read input, receive Ctrl+C while foreground, and return foreground input to Hutch. That terminal fixture is not a screenshot, real OpenCode session or provider call.

## Workspace schedule overview and pause (schema v40)

`tests/e2e/test_browser.py::test_schedule_overview_shows_local_times_and_pauses_only_future_occurrences` covers three Bots with separate time zones and pause states, a currently running task, and a workspace pause persisted through reload. It confirms that the transaction fences a scheduler snapshot read before the pause; existing execution continues, and a Bot-specific pause remains after workspace resume. Windows missed during the pause remain subject to each task's catch-up policy after resume. The first phone render exposed an icon-only pause action with no icon because the shared phone header hides button labels. The schedule control now keeps its action text visible and stacks it beneath the status line; the browser test checks its 44px height, readable label size and width, and keyboard focus restoration after both commands. I also inspected both phone scroll positions so all three tasks are reviewable without a toast covering the list, and the empty state at all three viewports.

Chromium **153.0.8010.12** / Playwright **1.63.0** captures and trace are in [`artifacts/schedules/`](artifacts/schedules/). Desktop **1440×960**, tablet **900×1024**, and phone **390×844** showed no horizontal overflow or browser errors. The anonymous site's Scheduling card was checked at the same widths with no external requests; see `artifacts/bot-purpose-refinement/marketing/site-scheduling-*.png`. The focused browser and anonymous-site tests passed. This evidence uses local SQLite/fixture data, not real scheduled provider calls, a screen reader or a physical phone.

## Bot memory export (2026-10-09)

`tests/e2e/test_browser.py::test_bot_memory_export_explains_scope_and_downloads_complete_json` passed at desktop
**1440×960**, tablet **900×1024**, and phone **390×844** in Chromium **153.0.8010.12** / Playwright **1.63.0**.
The scenario downloads the real local API response, parses the JSON, checks active and archived fact revisions and their
archive decision, verifies the download action remains within the phone viewport, and returns keyboard focus to the settings control. The confirmation explicitly says the file is
plaintext, notes that fact values and review notes may be sensitive, and lists included and excluded data. The phone action and confirmation controls meet the 44px target; no horizontal
overflow or browser errors occurred. I inspected each saved dialog screenshot; text wraps cleanly and the dialog footer remains
visible at phone width. Screenshots, traces and source hashes are in [`artifacts/bot-memory-export/`](artifacts/bot-memory-export/).

The final affected API/store/browser batch passed **61 tests in 15.99s**, including the three responsive download cases. JavaScript
syntax, Python compilation and `git diff --check` passed. This uses synthetic SQLite facts and no provider/model call. It verifies browser
download handling and server scope/size behavior, not the contents of a user's real memory, password-manager protection,
screen-reader behavior or physical-phone behavior.

## Owner-approved coordinator specialist roster (schema v41)

`tests/e2e/test_browser.py::test_named_workspace_coordinator_is_first_class_direct_chat_at_responsive_sizes` exercises the real
settings UI with ten eligible Bots. Search narrows the list to a single choice, Space toggles its focused checkbox, and Save
persists the owner selection. Promoting that specialist to coordinator removes it from the roster and does not approve the prior
coordinator. The API/store tests also remove a specialist after dispatch and confirm the existing task and child conversation stay
available. The separate coordinator-task browser journey confirms the selector offers only approved Bots; an unlisted direct API
submission is rejected before a task row is created.

The settings card now stays compact by default and shows the current approved count; its search and roster open only after the owner
chooses **Manage**. The owner can expand/collapse the native disclosure with Enter, then search a ten-Bot roster, toggle a checkbox
with Space, and save. The count updates after save. Load failures open the details automatically and disable saving, so the error is
not hidden behind the collapsed state. Promoting a specialist removes it from the roster without approving the former coordinator.

I inspected both collapsed and expanded app captures at desktop **1440×960**, tablet **900×1024**, phone **390×844**, and compact
phone **320×844**. Each captured viewport had no horizontal overflow; the compact summary preserves the full title over two lines when
needed, while the count and **Manage**/**Close** control remain visible. Expanded search and selection controls fit all sizes. The
anonymous marketing test inspected its coordinator-handoff copy at desktop **1440×900**, tablet **900×1024**, and phone **390×844**;
the screenshots show the approved-roster rule and the existing-work boundary without clipping. Chromium **153.0.8010.12** and
Playwright **1.63.0** were used. Both browser flows reported no page errors or external requests; they made no provider/model calls.
The focused browser test passed **1 test in 6.30s** after a test-first failure on the previously absent disclosure. Screenshots, traces,
source hashes, commands and validation JSON are in [`artifacts/workspace-specialists/`](artifacts/workspace-specialists/).
Fixtures use isolated local state. No screen reader or physical phone was tested.

## Bot and conversation overflow actions (2026-10-09)

The Bot overflow menu now includes recoverable hide/show, pinning, named sections,
review-before-download of a local sanitized template, a safe Duplicate bot setup, and
settings. The conversation menu includes New, Rename, Pin, Mark unread, section,
scope-reviewed local export, and Archive/Restore. Conversation lists group pinned,
named-section, recent and archived chats; selecting a chat clears its unread marker,
and a new reply can mark it unread again.

`tests/e2e/test_browser.py::test_conversation_options_are_compact_persistent_and_recoverable`,
`test_bot_menu_downloads_a_reviewable_local_setup_template`,
`test_duplicate_bot_starts_from_safe_editable_setup_without_copying_authority`, and
`test_bot_sidebar_menu_supports_recoverable_hide_and_named_sections` exercise these
flows against local fixtures. The conversation and duplicate flows generate desktop
**1440×960**, tablet **900×1024**, and phone **390×844** captures and Playwright traces
under [`artifacts/conversation-options/`](artifacts/conversation-options/) and
[`artifacts/bot-chat-options/`](artifacts/bot-chat-options/). Visual review checks menu
placement, modal footers, keyboard Escape/focus return, persistent state, no horizontal
overflow, and review before any export or creation. No provider, external site, paid call,
screen reader, or physical phone is used by these tests.

The chat options menu also has a **320×844** compact-phone capture. The focused
conversation/template/duplicate/roster/quick-setup batch passed **42 tests**. Rename
updates the open picker immediately and survives reload. Duplicate setup carries only
standing instructions, model route, inference mode, workspace type and limits; its review
excludes tools, connected accounts, provider URLs, local folders, schedules, memory values,
browser handoff and history. All menu and duplicate setup/review captures were inspected
after the final CSS changes.

The chat menu now keeps New, Rename, Pin, Unread and Section visible, with template,
export and archive actions grouped under **More**. Its task-template review copies only
the first user request into an editable name/prompt pair; the local JSON download excludes
assistant replies and all other conversation context. Import validates the version and
bounds, fills the draft, and does not start a run. The conversation-options browser test
passed **1** and checks the More disclosure's Escape/focus behavior, task-template download
and import, and that run count stays unchanged. Phone review captures at desktop
**1440×960**, tablet **900×1024**, and phone **390×844**; More is also inspected at compact
phone **320×844**. The template dialog keeps both fields and its download action inside the
phone viewport with no horizontal overflow. Updated artifacts include
[`task-template-review-desktop.png`](artifacts/conversation-options/task-template-review-desktop.png),
[`task-template-review-phone.png`](artifacts/conversation-options/task-template-review-phone.png),
[`more-phone.png`](artifacts/conversation-options/more-phone.png), and
[`more-compact-phone.png`](artifacts/conversation-options/more-compact-phone.png). This is a
local Chromium fixture; no provider call or network share occurs. No physical-device or
screen-reader validation was run.

A later full diagnostic run completed with **1,689 passed, 4 failed, and 1 teardown error in
872.90s**. It exposed three older-schema fixtures that retained the v44 task-template table,
and one archive browser test that did not open the new **More** disclosure before clicking
Archive. The fixtures now remove the table before lowering `user_version`; the browser test
opens the disclosure and closes its context in `finally`. Those four failed cases passed in
targeted reruns (**3 migration tests and 1 browser test**). The full suite has not been rerun
after these test-fixture corrections and is not a release-suite pass. The earlier schedule
focus, status indicator, heading-leading and roster-menu fixes remain covered by focused
regressions.
Chromium **153.0.8010.12** / Playwright **1.63.0**; all captured local fixtures had no page
errors or horizontal overflow. No live provider, paid call, external account, screen reader,
or physical phone was used.

The user-provided Bobo Figma preview rendered its full canvas at 1400×881 (natural canvas 32128×20200); it was too zoomed out to
inspect individual components. The compact summary follows Hutch's committed design tokens and uses that preview only as high-level
mobile-chat context. No external assets or token values were copied.

## Local saved-request library (2026-10-10)

The conversation's **More** menu can save the first user request to a local library after review. A searchable composer menu opens
the library; **Use request** fills the draft and leaves sending as a separate user action. Owners can edit with revision checks or
delete after confirmation. The local JSON import/export path remains available for portability and does not include replies, files,
tool activity, credentials, or chat identifiers. Marketing copy describes the draft-only behavior and local storage without implying
cloud sharing.

The saved-request API tests passed **2 tests** (within a combined **23-test** template and migration run) for bounded fields,
idempotent create/update/delete, conflict detection, and persistence.
An added regression verifies retries return the original response snapshot after later edits and deletion; this prevents retries from
turning into errors or silently returning newer content. The browser journey passed **1 test** across review, persistence, search,
draft-only use, edit, confirmed delete, run-count invariance, and no external requests or provider calls. The anonymous marketing
suite passed **27 tests** and separately asserts this feature's claims. Chromium **153.0.8010.12** / Playwright **1.63.0** captures
were inspected at desktop **1440×960**, tablet **900×1024**, phone **390×844**, and compact phone **320×844**. Dialogs fit the tested
viewport; library controls stack into full-width buttons on phone. Marketing screenshots show the repeat-work copy at desktop
**1440×900**, tablet **900×1024**, and phone **390×844**. Evidence is under
[`artifacts/saved-requests/`](artifacts/saved-requests/), including `validation.json` and the Playwright trace. No screen reader or
physical device was tested.

## Quick Bot creation and compact roster controls (2026-10-09)

The default Bot setup starts with the request the user already selected in chat, makes editing its standing instructions optional,
suggests an editable role-based display name, and keeps identity details and advanced controls available on demand. Creation
saves the Bot only; it does not start a run, grant tools or schedule work. The roster keeps one options control per Bot; pinning
and settings live in that menu. For ten or more Bots, idle entries collapse under a searchable, keyboard-operable **All bots**
group, while the coordinator, attention-needed Bots and active Bots remain visible. Display names wrap to two lines before the
clamp, preserving more of a long role name without letting one Bot row dominate the sidebar.

The focused browser batch passed **5 tests in 17.08s**: quick setup with workspace defaults and no run, role-based name editing,
creation from the exact selected request without retyping, persistent pinning with the combined options menu, and a ten-Bot compact
roster with search and keyboard expansion. A separate small-workspace browser regression exercised Bot settings through the
options menu (**1 passed in 5.17s**). I inspected the quick-setup captures at desktop **1440×960**, tablet **900×1024**, and phone
**390×844**, plus desktop/tablet/phone captures of the Bot menu and collapsed large roster. The suggested Bot name has a clear
editable field border; the phone footer and fields stay visible; menu targets fit the phone drawer; and no inspected viewport has
horizontal overflow. Chromium **153.0.8010.12** / Playwright **1.63.0** made no external requests or provider calls. Captures,
visual-review notes, source hashes and traces are in [`artifacts/simple-bot-setup/`](artifacts/simple-bot-setup/),
[`artifacts/pinned-roster/`](artifacts/pinned-roster/), and [`artifacts/compact-roster/`](artifacts/compact-roster/). These
fixture checks do not replace screen-reader or physical-device validation.

## Shape-aware 2D mascot faces and Studio search states (2026-10-10)

App mascots remain simple 2D forms. The eight silhouettes now use their own eye spacing, height, and tilt so the same face is not pasted
onto an orb, capsule, bean, drop, pebble, shield, triangle, and hex. The browser test checks each pair's sampled edge stays within the
corresponding SVG silhouette and that all eight face proportions are distinct. I inspected the updated individual desktop and phone
captures in [`artifacts/mascot-eye-review/`](artifacts/mascot-eye-review/); the marketing site's more detailed mascot remains separate.

Studio conversation search was also rechecked with a no-results query, a simulated service error, and HTML-like content in an excerpt.
The latter is displayed as text and creates no image element. I inspected the desktop, tablet, phone, compact-phone, empty-result, and
error-state screenshots separately in [`artifacts/conversation-search/`](artifacts/conversation-search/). None has horizontal overflow;
the touch search control measures 44×44 CSS pixels. These checks used local Chromium **153.0.8010.12** fixtures and made no provider or
external requests. The full offline non-E2E suite passed **1,532 tests** with thread and syntax warnings treated as errors. Physical phone,
screen-reader, and live-provider checks remain outstanding.

## Shape picker face fidelity (2026-10-10)

Owner review called out that mascot design must account for the different head shapes. The shape picker exposed a real mismatch: its
eight silhouettes all used the orb's eye coordinates because the renderer was given a color token where it expected a shape index. A
browser regression failed on that exact mismatch before the selector began using each shape's own face geometry. Selecting any shape
now updates the large preview with the same geometry used by the corresponding roster avatar.

Both colour and shape choices now use 44×44px targets. Each eight-option row stays on one line on desktop and tablet and becomes a
balanced four-by-two grid on 390px and 320px phones; the colour remains a 26px swatch inside its larger button. The final focused
journey passed **1 test in 3.74s** on Chromium **153.0.8010.12** / Playwright **1.63.0**, checking every selector face against all eight
rendered avatars, selected-state updates, target size, both phone layouts, no overflow, and no browser errors. I opened and inspected the
desktop, tablet, phone, and compact-phone selector captures individually in [`artifacts/mascot-eye-review/`](artifacts/mascot-eye-review/).
No provider calls or external requests occurred. The Figma Community shape library was reviewed for variety of base forms only; no
artwork was reused. Physical-device and screen-reader checks remain open.

## Independent route review and responsive control-density fixes (2026-10-10)

I reviewed Studio, Activity, Schedules, Fleet, Run history, Needs you/approvals, Connections, Bot settings, Run detail, Preferences,
and the marketing page as separate rendered surfaces. Desktop **1440×960**, tablet **900×1024**, phone **390×844**, and compact phone
**320×740** were checked in Chromium **153.0.8010.12** / Playwright **1.63.0**. Each desktop, tablet and phone image was opened
individually; the compact-phone sweep asserts the page width instead of relying on a collage. The route fixture uses 11 synthetic Bots
and one completed run, so these captures are layout evidence, not live workspace or provider evidence.

The review found three worthwhile density/readability fixes. Fleet cards now show **Open** and one 44×44 options control; pause/resume
and settings sit inside that menu. The empty Schedules state offers a single **Choose an assistant** disclosure, with its assistant links revealed on
demand. Run history uses professional Bot display names and switches to linked cards at widths up to 900px, where the previous table
wrapped Bot names, timestamps and columns awkwardly. The chooser includes a downward indicator, and the menu action journey verifies
pause and resume against the local API.

The final focused command passed **3 tests in 14.13s**, with thread and syntax warnings treated as errors:

```text
.venv/bin/python -m pytest -q -W error::pytest.PytestUnhandledThreadExceptionWarning -W error::SyntaxWarning tests/e2e/test_design_system.py::test_every_workspace_route_renders_independently_at_responsive_sizes tests/e2e/test_browser.py::test_schedule_overview_shows_local_times_and_pauses_only_future_occurrences tests/e2e/test_browser.py::test_fleet_appears_at_ten_bots_with_search_and_state_filters
```

`test_every_workspace_route_renders_independently_at_responsive_sizes` checks all primary routes, 320px overflow, no browser errors
and no request outside the local fixture; `test_schedule_overview_shows_local_times_and_pauses_only_future_occurrences` checks
the compact chooser; `test_fleet_appears_at_ten_bots_with_search_and_state_filters` checks the combined menu actions. `node --check`,
`git diff --check`, and the Impeccable detector (`[]`) passed. Validation metadata and individual screenshots are in
[`artifacts/ui-surface-review/`](artifacts/ui-surface-review/). No external requests or provider calls occurred. The shared app
design tokens remain consistent across the workspace routes, while marketing keeps its
editorial layout and detailed 3D character. The eight 2D app silhouettes retain their own face geometry, as separately verified in
[`artifacts/mascot-eye-review/`](artifacts/mascot-eye-review/).

This is local fixture validation, not screen-reader or physical-device testing. Figma node-level retrieval was blocked by the current
Starter-plan tool limit; the current visual-validation entry records that boundary.


## Intent-preserving chat-led Bot setup (2026-10-10)

The optional missing-detail check starts from the exact user message selected in chat. It asks one work question at a time, offers
2–5 choices plus free text, and carries the original request and selected earlier context forward without asking the owner to repeat
the task. The same browser can restore an unsent choice/free-text answer and the editable proposal for up to seven days; setup warns
owners not to enter passwords, codes or account credentials. The proposal remains review-only and cannot change Bot settings or
create a Bot before the explicit setup confirmation.

I opened the individual question screen at desktop **1440×960** and the restored question at phone **390×844**, then inspected the
editable draft separately at desktop **1440×960**, tablet **900×1024**, and phone **390×844**. The mobile sheet keeps its action footer
visible; the restored choice and typed text remain available after reload. Each capture is in
[`artifacts/bot-setup-clarification/`](artifacts/bot-setup-clarification/), with Chromium **153.0.8010.12** / Playwright **1.63.0**
metadata and trace. The browser journey verifies exact request/context scope, the submitted answer history, no Bot/run before creation,
no page errors, and no external/provider calls. This is same-browser fixture evidence; it does not verify live model question quality,
screen readers, or a physical phone.

The focused clarification/refinement/API command passed **3 tests in 6.66s**; the full conversation module passed **19 tests in 6.30s**;
the tool-free runtime guard passed **1 test in 1.17s**. `node --check`, Python compilation, and `git diff --check` passed. The eight
distinct 2D app mascot silhouettes and their per-shape face geometry remain covered separately in
[`artifacts/mascot-eye-review/`](artifacts/mascot-eye-review/).

The implementation and focused screenshots are committed locally on `main` as `160af58`. No provider call, external request, push,
or publication occurred.

## Google Calendar event-creation approval (2026-10-10)

I inspected the Connection surface and grant confirmation separately at desktop **1440×960**, tablet **900×1024**, phone **390×844**,
and compact phone **320×740**. The exact event-creation grant copy was also opened individually at desktop and phone sizes. The
mobile form wraps within the viewport, preserves the full permission disclosure, and keeps actions reachable; all sizes report zero
horizontal overflow. Evidence and trace are in [`artifacts/google-calendar-event-creation/`](artifacts/google-calendar-event-creation/),
and the read-only connection journey remains in [`artifacts/google-calendar/`](artifacts/google-calendar/). The journey uses synthetic
account/calendar fixtures and made no Google calls or external requests. Chromium **153.0.8010.12** / Playwright **1.63.0**.

The focused provider/API/migration and two responsive browser journeys passed **56 tests**. Python compilation, JavaScript syntax,
`git diff --check`, and scoped Impeccable detection (`[]`) passed. Live Google sign-in, consent, provider behavior, screen-reader and
physical-device validation remain open. The page follows Hutch's existing visual system; individual Figma node inspection was limited
by the connected Starter plan.

## Personal-assistant entry, roster, app choices, and mascot faces (2026-10-10)

The empty chat now leads with a real request field, Hutch's locally drawn calendar, mail, and AI-category glyphs, and the simple 2D Hutch face.
Submitting carries the exact request into setup; the dialog calls it the person's starting request, suggests an editable assistant name,
and says there is no need to repeat it. The quick summary describes the actual safe defaults without leading with workspace, tool, or
schedule terminology. The next steps keep model choice and abilities explicit, with deeper controls available on request.

The former Connections page is presented as **Apps & AI**. Its first layer uses concise cards with a service mark, plain-language
description, honest state, and one next action. Account scopes, OAuth setup, and detailed integration controls sit under **More account
settings**. The service cards use original Hutch-colored category glyphs beside exact text labels. The marketing illustration uses the
same icon family. The AI choice uses Hutch's generic sparkle mark; it does not imitate or recolor the OpenAI Blossom. The main app's
faces use shape-specific, slightly asymmetric solid ink eyes with no highlights, keeping the 2D identity
readable on each bright silhouette; the marketing site retains its richer 3D art.

The larger Fleet view now shows a human role, truthful status, run cadence, and action expectation first. Exact model routes, schedules,
activity, estimated tokens and saved-note counts stay together under **More details**; pause/resume and settings share one menu. The
chat's empty-conversation gallery leads with common tasks and short names such as **File organizer** and **Meeting follow-up** rather
than storage IDs. The first six are reordered for personal-assistant use while stored IDs and template behavior remain unchanged.

The design uses the user's supplied mobile references for the recognizable chat list, direct assistant conversation, and grouped per-assistant actions. A node-level request for the connected Figma preview was attempted, but the account's Starter-plan tool limit blocked retrieval. Hutch's checked-in `DESIGN.md` remains the visual authority; no Bobo artwork or palette was copied.

The current Hutch welcome and app-catalog captures under [`artifacts/assistant-first-ui/everyday-start/`](artifacts/assistant-first-ui/everyday-start/) show each surface separately at desktop **1440×960**, tablet **900×1024**, phone **390×844**, and compact phone **320×740**, plus the prefilled setup at desktop and phone and Calendar access expanded at desktop. Updated individual route captures, including Fleet's collapsed and expanded card, are in [`artifacts/ui-surface-review/`](artifacts/ui-surface-review/); the Studio gallery was separately inspected at desktop and phone before and after scrolling to its final choice, where every card stays above the composer. The separate 3D marketing hero captures are in [`artifacts/assistant-first-ui/marketing/`](artifacts/assistant-first-ui/marketing/), and current public-site product images are at `website/assets/captures/setup-{desktop,phone}.webp`. Mascot face previews under [`artifacts/mascot-eye-review-2026-10-10/`](artifacts/mascot-eye-review-2026-10-10/) were opened individually, including the drop, triangle, and hex, then the picker at desktop, tablet, phone, and compact phone. All screenshot checks use reduced motion and local fixtures.

Chromium **153.0.8010.12** / Playwright **1.63.0** passed the **5-test** design-system browser file after the Fleet and gallery changes, plus the updated all-routes test that checks the composer overlap at desktop and phone scroll positions. The anonymous website suite passed **27 tests** after replacing its stale screenshot captures; no external requests or provider calls occurred. The first-run test verifies the original request remains exact, keyboard focus reaches the setup action, and all four sizes avoid horizontal overflow; the mascot test verifies eight distinct silhouettes, per-shape faces, picker parity, in-boundary eyes, and at least **3:1** eye/body contrast. Visual review also caught and fixed a reveal-animation issue: content nested in closed technical disclosures now stays out of the hidden reveal state and remains visible when opened. These fixture checks do not verify live account consent, screen readers, or physical devices.

## Everyday-first UI and screenshot provenance (2026-10-10)

The app now opens assistant settings on only the editable name and short role. Standing directions, model/runtime, permissions, schedules,
memory and workspace controls remain available inside one optional disclosure. The first-run composer carries the exact request into
setup and suggests an editable, request-based name; it does not ask the person to repeat their goal. Apps & AI uses familiar local
calendar, mail and model marks with names, honest states and one next step. The everyday path uses plain language; the optional layer
retains the technical controls for people who want them. App assistants stay simple, shape-aware 2D characters, while the public site
keeps the detailed 3D mascot.

The earlier screenshots looked behind the UI because saved image files were not tied to the exact app and website source that produced
them. I added SHA-256 source fingerprints for the app shell, app JavaScript/CSS, marketing HTML/CSS/JavaScript and visual test to the
responsive evidence, then regenerated the current individual route and assistant-settings captures. The route evidence covers Studio,
Activity, Scheduled work, Manage assistants, Work history, Needs you, Apps & AI, assistant settings, run detail, preferences and the
marketing site at **1440×960**, **900×1024** and **390×844**, plus 320px overflow checks. Each page is saved separately rather than as a
collage. The screenshots and matching fingerprints are in [`artifacts/ui-surface-review/`](artifacts/ui-surface-review/) and
[`artifacts/assistant-settings-everyday/`](artifacts/assistant-settings-everyday/); request-first and app-mark screenshots are in
[`artifacts/assistant-first-ui/everyday-start/`](artifacts/assistant-first-ui/everyday-start/).

I opened individual desktop and phone renders for settings, Studio, Fleet, Apps & AI, first run, request-carryover setup, Needs you and
the 3D marketing hero. Chromium **153.0.8010.12** / Playwright **1.63.0** passed **13 design-system and site-token tests** and **20
focused settings/provider journeys**, with thread and syntax warnings treated as errors. These fixture journeys made no external
requests or provider calls. The supplied Figma screen was requested individually, but Figma's current Starter-plan tool-call limit
prevented node-level retrieval; implementation follows the main-branch `DESIGN.md` and the user's supplied screens. Physical-device,
live provider and screen-reader validation remain separate gaps.

## App type roles, service glyphs, and full-row selection (2026-10-10)

The app now has named system-sans roles for display, page and section titles,
body, reading, labels, captions, and measured values. Rem-based app sizes follow
browser text settings; the marketing site retains its locally bundled Archivo
display face. Ordinary navigation, state, and action labels use the app family;
mono stays on identifiers, timestamps, code, and numeric measurements. App
icons share local 24×24 outline geometry, 16/20/24px size roles, and a 1.75px
current-color stroke. Apps & AI uses functional calendar, mail, inbox, sparkle,
and cloud glyphs with exact service names as text; these are not provider logos.

The active assistant highlight now belongs to the full roster row and reaches
the trailing options target. Selection remains available as `aria-current` on
the assistant button, and the full display name remains available in its title
while the visible label stays on one line with an ellipsis for long names. The phone first-run screen also
keeps **Set up my assistant** fully in the initial 390×844 viewport.

I inspected the individual Studio and Apps & AI desktop, tablet, and phone
renders, the request-first setup at all three sizes, the service catalogue at
desktop and phone, and the active-row capture at desktop, tablet, and phone.
The selection row's right edge matches the options target at all sizes and the
browser reports no horizontal overflow. At 200% root text sizing, a 0.9375rem
body role renders at 30px and a 1.5rem page-title role at 48px. The page checks
also exercise 320px reflow for Studio, Apps & AI, and the marketing site.

The final command
`.venv/bin/pytest -q -W error::pytest.PytestUnhandledThreadExceptionWarning -W error::SyntaxWarning tests/e2e/test_design_system.py tests/e2e/test_browser.py::test_bot_roster_pins_persist_and_simple_mascots_stay_distinct`
passed **7 tests in 36.60s** on Chromium **153.0.8010.12** / Playwright
**1.63.0**. No external requests or provider calls occurred. Impeccable's scoped
type/layout scan returned no findings. Individual images and source fingerprints
are in [`artifacts/assistant-first-ui/everyday-start/`](artifacts/assistant-first-ui/everyday-start/),
[`artifacts/design-system/`](artifacts/design-system/), and
[`artifacts/pinned-roster/`](artifacts/pinned-roster/); the detailed Figma and
Lucide reference review is in
[`docs/research/icon-and-chat-interface-references-2026-10-10.md`](../research/icon-and-chat-interface-references-2026-10-10.md).
No screen reader or physical mobile device was used.


## Provider icon review and supplied customization references (2026-10-10)

The first visual pass bundled Google Calendar and Gmail SVGs locally. A later
brand-permission review found that those files were from an older icon generation
and that Hutch has no documented permission to ship Google or Microsoft product
marks in the app or marketing site. That trial was removed. Current surfaces use
Hutch-colored category glyphs beside exact service names; these glyphs are not
provider logos. The official, unaltered white OpenAI Blossom is used only beside
the explicitly named ChatGPT service in its directly related app context, under
OpenAI's published use terms. Relevant primary guidance: [Google
product-icon usage](https://partnermarketinghub.withgoogle.com/brands/google/branding-guidelines/how-to-show-googles-brand/),
[Microsoft Trademark and Brand Guidelines](https://www.microsoft.com/en-us/legal/intellectualproperty/trademarks) and [Microsoft Copyright Permissions](https://www.microsoft.com/en-us/legal/intellectualproperty/copyright/permissions),
and [OpenAI Brand Guidelines](https://openai.com/brand/).

The current desktop, tablet, and phone visual checks capture the individual Studio, Apps & AI, and marketing surfaces at
1440×960, 900×1024, and 390×844, plus compact-phone checks where recorded. The supplied assistant-customization reference was
reviewed for its separate color and character choices, prominent editable name/preview, and single save action. The supplied
device-access reference was reviewed for device state, recent activity, and outputs grouped separately. These are design inputs, not
claims that device pairing or live activity is implemented in this UI slice. Mobbin retrieval was blocked by its paid-plan requirement;
Figma node retrieval was blocked by the connected account's plan limit. No Mobbin screen was independently inspected in this pass.

The corrected category glyphs were captured and inspected individually at desktop, tablet, and phone sizes. The assistant roster now
keeps each name to one line, shows an ellipsis when the available width is not enough, and retains the complete name on the row for
discovery. Final evidence is in [`artifacts/design-system/`](artifacts/design-system/) and [`artifacts/pinned-roster/`](artifacts/pinned-roster/).
The focused checks passed: the design-system browser file (**6 tests, 44.79s**), anonymous website checks (**27 tests, 48.79s**), and
the pinned-roster interaction (**1 test, 8.09s**), on Chromium **153.0.8010.12** / Playwright **1.63.0**. The pages report no
unexpected external requests or provider calls. The first website rerun caught a stale stylesheet cache key; the key was corrected,
then all 27 checks passed. These fixture checks do not establish live provider consent or brand permission.

## Assistant face, service-tile, and phone-header refinement (2026-10-10)

The app mascot now uses paired tapered light eyes with a fine dark edge. All
eight silhouettes have individually fitted eye paths, and the shape picker uses
the same face geometry. Apps & AI now places the service glyph, full product
name, and connection state on a shared row; the local color tiles are original
function cues, not provider logos. A compact mobile Fleet action keeps the full
page title on one line and retains the accessible label **New assistant**.
Short desktop welcome spacing keeps its primary setup action visible at 1280×720.

I ran the first-run/app-catalog, mascot-containment, all-route responsive, and
roster-selection browser journeys together: **4 passed in 26.85s**. The all-route
journey covers Studio, Activity, Schedules, Fleet, Runs, Approvals, Apps & AI,
assistant settings, run detail, and the marketing site at **1440×960**,
**900×1024**, **390×844**, and **320×740**. It checks 320px horizontal overflow;
the Fleet title/action alignment is also asserted at both phone widths. I opened
the 30 route screenshots individually at desktop, tablet, and phone sizes, then
opened each of the eight mascot-face crops individually. The short-desktop
welcome and service catalog have their own captures. The roster journey checks
one-line long-name truncation, full title access, and the selected row reaching
the trailing options control.

Evidence and current-source fingerprints are in
[`artifacts/ui-surface-review/`](artifacts/ui-surface-review/),
[`artifacts/assistant-first-ui/everyday-start/`](artifacts/assistant-first-ui/everyday-start/),
[`artifacts/mascot-eye-review-2026-10-10/`](artifacts/mascot-eye-review-2026-10-10/),
and [`artifacts/pinned-roster/`](artifacts/pinned-roster/). The marketing
approval illustration's local check icon was also inspected separately at
desktop, tablet, and phone in
[`artifacts/website-checkmark-2026-10-10/`](artifacts/website-checkmark-2026-10-10/).
Checks used Python **3.13.15**, Chromium **153.0.8010.12**, and Playwright
**1.63.0** with local fixtures: **zero external requests and zero provider calls**.
No live provider, physical device, or screen reader was used. Mobbin remained
behind its paid-plan gate and Figma node-level retrieval was blocked by the
connected account's Starter-plan tool limit, so neither is claimed as a source
for this pass.

## Studio welcome and service-tile refinement (2026-10-10)

Independent Studio and Apps & AI captures showed two avoidable rough edges: a
blank assistant description appeared as the literal “No description yet,” and
the long assistant-specific composer placeholder wrapped on phone. Studio now
omits that empty description and uses a short “Message…” placeholder while its
accessible label continues to name the assistant. The ChatGPT mark remains the
exact white OpenAI asset; generic mail and calendar cues are slightly larger and
more legible, with Outlook still using a neutral blue mail symbol rather than an
unlicensed Microsoft product icon.

The responsive route test checked Studio and Apps & AI, along with the other
workspace routes and marketing, at **1440×960**, **900×1024**, **390×844**, and
**320×740**. I opened the updated Studio and Apps & AI screens separately at
desktop, tablet, and phone sizes. The test also verifies that blank description
copy stays absent, the phone composer remains concise, ChatGPT loads the exact
local Blossom asset, Outlook has a distinct blue mail cue beside its full name,
and long sidebar assistant names keep their one-line/ellipsis behavior.

The same rerun exposed an async gallery race: the four-second conversation
refresh compared its server snapshot with live DOM after `wireWelcome()` had
inserted template cards, so it replaced the gallery and detached its cards.
Studio now compares the last canonical server snapshot held for that feed, so
the asynchronous enhancement does not trigger a redundant rerender. A browser
regression check retains the same template card through a full background
refresh. The focused route, refresh, and roster run passed **3 tests in 23.02s**
on Chromium **153.0.8010.12** / Playwright **1.63.0** with no external requests
or provider calls. See the individually inspected Studio and Apps & AI captures
in [`artifacts/studio-service-refinement/`](artifacts/studio-service-refinement/).

## Follow-up: mascot face correction and final roster check (2026-10-10)

The tapered light marks in the prior capture still read like slashes. The app
mascots and shape picker were changed to dark oval eyes, with per-shape spacing,
height, scale, and a slight tilt. The later refinement keeps those dark eyes
and softens their curved contours, with no pupils or highlights. All eight
silhouettes use shape-aware geometry shared with the
identity picker; details and current screenshots appear in the final review
below.

The latest roster capture also confirms each assistant name remains on one line
and truncates with an ellipsis only when the available width requires it. The
selection color reaches the row's single options control. The official white
OpenAI Blossom is used next to ChatGPT. Outlook's icon decision was checked
against Microsoft's current guideline: product icons require an express license,
which is not recorded for Hutch. The account tile therefore uses Hutch's own
blue-toned inbox glyph beside the full product name. Gmail and Google Calendar
retain category artwork pending Google's approval process. Current icon and
visual evidence follows below.

## Final provider-icon and one-line roster review (2026-10-10)

Apps & AI displays the exact local OpenAI Blossom beside **ChatGPT**. Microsoft
Outlook, Gmail, and Google Calendar each have a 48px service tile with Hutch's
original category art and the full provider name. I opened the Connections
screenshots independently at desktop, tablet, and phone. Gmail and Google
Calendar continue to use Hutch's mail and calendar glyphs because Google's
current product-icon rules require approval; Microsoft bars product-icon use
without an express license.

Assistant names remain single-line in the expanded desktop and phone roster.
Long names end in an ellipsis, retain the complete name for assistive discovery,
and never push the shared options button out of the selected row. The mascot
follow-up replaces ring-like pale eyes with broad, softly curved solid ink eyes
without pupils or highlights; all eight silhouettes
and the shape picker were inspected after the change. The focused 4-test
verification and refreshed screenshots are recorded in the current ledger
checkpoint. The cross-product visual overhaul remains open.

## Provider artwork correction and simplified mascot faces (2026-10-10)

The official ChatGPT Blossom remains next to the named ChatGPT service. I found
the Outlook product icon, but Microsoft's current [trademark rules](https://www.microsoft.com/en-us/legal/intellectualproperty/trademarks)
require an express license for app and product icons; Hutch has no recorded
license, so the Outlook connection now uses an original blue-toned inbox glyph
beside the full provider name. Gmail and Google Calendar also use Hutch's own
category glyphs pending Google's approval process.

The last eye revision removed the tiny white dots that made the characters look
like they had pupils. Each of the eight app silhouettes now has two softly
curved, solid ink eyes, placed and sized for its face; the identity picker uses
the same paths. The result keeps the small 2D characters simple and leaves the
marketing site's detailed 3D mascot separate. I opened the updated Studio at
desktop and phone widths, Connections at desktop and phone widths, the selected
desktop and phone roster, and individual orb, drop, and shield faces. The
broader route suite had already been inspected page by page and was recaptured
at desktop **1440×960**, tablet **900×1024**, phone **390×844**, and compact phone
**320×740**.

The focused browser batch passed **4 tests in 32.06s**:
`test_shared_design_tokens_render_consistently_across_all_surfaces`,
`test_every_workspace_route_renders_independently_at_responsive_sizes`,
`test_flat_mascot_eyes_stay_inside_every_silhouette`, and
`test_bot_roster_pins_persist_and_simple_mascots_stay_distinct`. It checks the
ChatGPT asset, original Outlook inbox glyph, one-line ellipsis names, selected
row coverage through its one options button, pin persistence, all eight
shape-specific faces, picker parity, and responsive routes. Chromium
**153.0.8010.12** / Playwright **1.63.0** used local fixtures; there were **zero
provider calls and zero external requests**. `node --check`, sidecar JSON
validation, `git diff --check`, and the Impeccable detector passed with zero
anti-patterns. No live provider, screen reader, or physical device was used.
Screenshots, source hashes, and traces are in
[`artifacts/ui-surface-review/`](artifacts/ui-surface-review/),
[`artifacts/mascot-eye-review-2026-10-10/`](artifacts/mascot-eye-review-2026-10-10/),
and [`artifacts/pinned-roster/`](artifacts/pinned-roster/). The all-surface
redesign remains open.

## Chat toolbar, approval access, and icon distinction (2026-10-10)

Assistant settings now live in the conversation options menu, leaving the chat
toolbar for the conversation selector, search, action menu, approval review,
and stop. The desktop title receives available width. The phone approval card
stays above the floating jump-to-latest control, so its details and decision
buttons remain usable. Apps & AI uses different original category shapes for
Gmail mail and Outlook inbox, with exact service names adjacent.

I reviewed the tablet and phone approval captures and desktop and phone selected
roster captures individually. Assistant names remain single-line; long names
truncate with an ellipsis, and the selection treatment reaches the shared options
control. The chat header test saves desktop, open-menu, and phone captures at
[`artifacts/chat-header-options/`](artifacts/chat-header-options/).

The final focused browser batch passed **7 tests in 46.98s**. It covers approval
resolution and disclosure persistence through feed refresh, chat action grouping,
a one-line long-name assistant row, distinct provider category artwork, the shared
design tokens, and independent responsive route rendering. The chat-header fixture
uses Chromium **153.0.8010.12** / Playwright **1.63.0**, with no page errors,
external requests, or provider calls. Desktop, tablet, phone, and compact-phone
route captures are in [`artifacts/ui-surface-review/`](artifacts/ui-surface-review/);
the focused toolbar images and measurements are in
[`artifacts/chat-header-options/`](artifacts/chat-header-options/). These are local
fixtures; live integrations, screen-reader operation, and physical devices were
not tested.

**Provider-art guidance correction:** earlier notes described Google's product
icons as requiring approval in all cases. Google's product list links Gmail and
Calendar to general icon guidelines, and its brand guidance points product-icon
requests to Partner Marketing Hub; the detailed icon rules did not load during
this review. Hutch has no permission recorded, so it keeps original category
art until the applicable terms are confirmed. This does not establish that every
in-app usage requires approval. Microsoft's current guidance separately states
that Outlook product icons require an express license. OpenAI's current guide
says not to recolor Blossom, so its local exact white mark remains unmodified.

## Gmail send-only setup (2026-10-10)

The Connections page now offers a separate Gmail send-only setup, account list,
per-assistant grant, revocation, and disconnect path. A Chromium fixture test
opened the path and captured desktop (1440×960), tablet (900×1024), phone
(390×844), and compact phone (320×740). I inspected the desktop, phone, and
compact-phone screenshots individually. The form reflows to one column on
phones; each viewport reports zero horizontal overflow, no page errors, and no
external requests. The browser version was **153.0.8010.12** with Playwright
**1.63.0**. Google credentials and provider calls: none.

Screenshots, source hashes, and the trace are in
[`artifacts/google-mail-send/`](artifacts/google-mail-send/). The rendered
surface distinguishes sensitive `gmail.send` from restricted search access,
shows the account's sender address and exact approval boundary, and keeps
revocation and disconnect visible. This fixture review covers the new
send-only journey only; the wider Connections redesign and all-surface UI
overhaul remain open. No live sign-in, screen-reader, or physical-device check
was performed.

## Mascot face correction after owner review (2026-10-10)

The earlier visor and pale slits still read as a mask. Each flat app mascot now
has two balanced, near-round ink eyes directly on its colored silhouette. Their
position and size follow the orb, capsule, bean, drop, pebble, shield, triangle,
and hex shapes. The face uses no panel, pupils or detached marks; the website's
detailed 3D mascot remains separate. Tests compare the picker with the matching
live-avatar geometry and verify each eye stays inside its head with at least
3:1 contrast against the body.

The focused browser check passed:
`.venv/bin/python -m pytest -q tests/e2e/test_design_system.py::test_flat_mascot_eyes_stay_inside_every_silhouette`
(**1 passed in 7.84s**, Chromium **153.0.8010.12** / Playwright **1.63.0**). It
also checks all eight shapes and colors, 44px picker targets, two-row choices
at phone and compact-phone widths, and no horizontal overflow. I opened all
eight enlarged faces one by one, then reviewed the desktop Studio/roster and
the desktop, tablet, phone, and compact-phone picker captures. They use local
fixtures with no provider calls. Exact captures, source hashes and trace are in
[`artifacts/mascot-eye-review-2026-10-10/`](artifacts/mascot-eye-review-2026-10-10/).
This mascot correction does not complete the broader app or marketing UI
overhaul; the surface inventory above remains open for independent review.

## Larger assistant roster and long-name reflow (2026-10-10)

The larger-roster view no longer repeats schedule cadence and action-access
chips on every assistant. Each card leads with its one-line name, status, short
description and **Open** action; service, schedule, action access, recent work
and usage are grouped under **Details**. Pause/resume and settings remain in a
single ellipsis menu. Long names use an ellipsis while their full text remains
available.

The responsive test found that one long-name card could be 617px wide inside a
390px phone viewport; the application scroll container clipped it, so the old
document-width-only assertion did not detect it. The card, grid and header now
permit shrinking, and the browser asserts each card stays inside the viewport
at 1440px, 900px, 390px and 320px. Long-name phone and compact-phone crops are
saved as `fleet-long-name-phone.png` and `fleet-long-name-compact-phone.png` in
[`artifacts/ui-surface-review/`](artifacts/ui-surface-review/).

`tests/e2e/test_design_system.py::test_every_workspace_route_renders_independently_at_responsive_sizes`
passed **1 test in 16.65s** with Chromium **153.0.8010.12** / Playwright
**1.63.0**. I inspected desktop, tablet, phone, and the two long-name crops
individually. Every route and assistant card fit; the browser reported no
external requests, provider calls, or page errors. Current source hashes,
responsive captures, and the trace are in the same artifact directory. This is
fixture evidence; no screen reader or physical phone was tested.

The task-details capture now includes a saved assistant response beside the
completed user request. I inspected the populated completion on desktop, tablet,
and phone separately. This response is synthetic fixture content; the browser
test reads it back from the saved event transcript, and no model or provider is
called.

The separate Fleet search, pause/resume, and attention-with-approval tests also
passed **3 cases in 5.92s**. Desktop and phone screenshots show the open and
human-wait states after the compact-card change; I reviewed both independently.
Their sanitized fixture metadata and images are in
[`artifacts/fleet-attention/`](artifacts/fleet-attention/). No live approval or
provider was used.

## Quick assistant setup and single-line roster (2026-10-10)

The simple setup summary now hides internal model IDs and routing-mode names.
It tells the user that Hutch will use the saved AI choice, has no apps or
recurring work connected, and checks with them before important actions. The
fine-tuning step still exposes the actual model route and inference mode, and
the test verifies that those selections persist. Saving the assistant starts no
run. This copy does not imply that any app permission was granted.

`tests/e2e/test_browser.py::test_quick_bot_creation_uses_the_workspace_default_without_starting_work`
and `tests/e2e/test_browser.py::test_bot_roster_pins_persist_and_simple_mascots_stay_distinct`
passed **2 tests in 11.06s** with Chromium **153.0.8010.12** and Playwright
**1.63.0**. I inspected the quick-setup desktop (1440×960), tablet (900×1024),
and phone (390×844) captures individually. The desktop and phone roster captures
were also reviewed individually: long assistant names remain on one line with
an ellipsis, while the selected background reaches the single options control.
All tested viewports had no horizontal overflow; the run made no provider calls
or external requests and reported no page errors. Evidence is in
[`artifacts/quick-setup-language-2026-10-10/`](artifacts/quick-setup-language-2026-10-10/)
and [`artifacts/pinned-roster/`](artifacts/pinned-roster/). These are local
browser fixtures, not a screen-reader or physical-phone test. The all-surface
UI overhaul remains open.

After simplifying the mascot eyes, the pinned-roster check was updated to
assert two balanced dark eyes and rerun. It passed **1 test in 7.75s**; the
refreshed desktop, tablet and phone captures retain the one-line long name and
selected-row coverage. Metadata records matching current source hashes, zero
external requests, and zero page errors.

## Chat details affordance (2026-10-10)

The normal transcript now replaces a shortened execution ID with an icon button
named **View work details**. The link targets the existing run detail page, while
the raw ID is absent from the visible thread text. The keyboard-accessible reply
journey also verifies focus return, draft recovery after reload, persisted reply
anchoring and successful send. All three responsive browser cases passed with
Chromium **153.0.8010.12** and Playwright **1.63.0**. Each viewport reported
zero horizontal overflow and no page errors; no model or provider was called.

I inspected the desktop (1440×1000), tablet (900×1024), and phone (390×844)
screenshots independently. The detail control remains aligned with the reply,
wraps to its own row on phone rather than squeezing the assistant label or stop
control, and exposes a 44px phone touch target. Images, JSON, and traces are in
[`artifacts/message-replies-clean-chat-2026-10-10/`](artifacts/message-replies-clean-chat-2026-10-10/).
This is a focused transcript polish check, not acceptance of the populated chat
surface or the all-surface redesign.

## Source-aligned Apps & AI review (2026-10-10)

The older Apps & AI captures showed a short **Outlook** label and colorful
product-like marks, while the current implementation uses **Microsoft Outlook**
and different, original category glyphs. Those older screenshots had no source
hashes, so they could not establish which code revision they represented. I
captured the current source to
[`artifacts/app-catalog-source-aligned-2026-10-10/`](artifacts/app-catalog-source-aligned-2026-10-10/)
and inspected desktop (1440×960), short desktop (1280×720), tablet (900×1024),
phone (390×844), and compact phone (320×740) individually.

The first attempt at the compact-phone welcome capture began midway down the
page because this app scrolls inside its content pane. The fixture now resets and
asserts the app's scroll position before each capture; the replacement image
shows the complete first-use screen from its true top.

The phone cards are shorter and retain the full label, state, description, and
44px action. Each is at most 190px high in the mobile fixture; no viewport had
horizontal overflow. The provider and seed content stayed local: the browser
made no external requests or model/provider calls. The focused test passed **1
case in 8.83s** with Chromium **153.0.8010.12** and Playwright **1.63.0**. It checks that
the ChatGPT tile uses OpenAI's unchanged local white mark and that Gmail and
Outlook category illustrations stay separate from any claimed provider logo.

## Approval queue priority and optional notifications (2026-10-10)

The **Needs you** drawer now places pending decisions and uncertain action
outcomes before optional browser-notification settings. Notifications live in a
collapsed disclosure; its summary shows **On**, **Off**, **Blocked**, or
**Unavailable**, while the open panel retains the full privacy and tab-open
explanation.

The focused approval and route batch passed **4 tests in 30.46s** with Chromium
**153.0.8010.12** / Playwright **1.63.0**. It verifies the closed default, the
On/Off/Blocked/Unavailable states, notification click-through, preserved review
focus, in-chat approval, and independent responsive route rendering. The
approval screenshots have zero horizontal overflow at desktop **1440×1000**,
tablet **768×1024**, and phone **390×844**. I inspected the expanded desktop and
phone notification settings and desktop and phone pending-approval screenshots
individually. These fixtures use local approval data and a stubbed notification
API; no OS prompt, provider call, or real notification was used. Screenshots
and source hashes are in [`artifacts/browser-alerts/`](artifacts/browser-alerts/).

## Empty Studio helper gallery hierarchy (2026-10-10)

The empty chat now places the optional **Create a helper from an example**
disclosure below its direct message invitation. It starts collapsed. Opening it
shows six compact helper rows with distinct 2D shapes; selecting a row enters
setup without creating a helper or starting a task. The phone list scrolls above
the fixed composer so the last choice remains reachable.

The focused Playwright test passed **1 case in 10.76s** with Chromium
**153.0.8010.12** / Playwright **1.63.0**. It covered desktop **1440×960**,
tablet **900×1024**, phone **390×844**, and compact phone **320×740**, tested
keyboard expansion, and checked a simultaneous line/paragraph/letter/word
spacing override at 320px. No horizontal overflow or composer overlap occurred.
I opened the collapsed and expanded screenshots separately at each size and
inspected the helper setup dialog; the source fingerprints and trace are in
[`artifacts/studio-helper-gallery-2026-10-10/`](artifacts/studio-helper-gallery-2026-10-10/).
These are local fixture checks only: no provider, external site, screen reader,
or physical phone was used.

## Assistant settings action hierarchy (2026-10-10)

The assistant settings header now shows the assistant name on one line with a
single **Assistant options** control. **Open chat** and **Delete assistant** are
inside the menu; the destructive action no longer sits beside routine
navigation. The menu is 44px square, opens below its trigger, closes on outside
click or Escape, and returns keyboard focus to the trigger.

`uv run --frozen pytest -q tests/e2e/test_design_system.py::test_assistant_settings_header_groups_secondary_actions`
passed **1 test** in **6.08s** on Chromium **153.0.8010.12** /
Playwright **1.63.0**. It covers desktop **1440×960**, phone **390×844**, and
compact phone **320×740**, checks one-line title geometry and zero horizontal
overflow, and confirms the menu items and focus behavior. I inspected the
settings page and open menu screenshots individually at desktop and phone
sizes. The test recorded no external requests or page errors. Captures, source
fingerprints, and trace are in
[`artifacts/assistant-settings-actions-2026-10-10/`](artifacts/assistant-settings-actions-2026-10-10/).
This validates one settings-page change; the all-surface redesign remains open.

## Independent app-route baseline (2026-10-10)

Refreshed source-bound screenshots for Studio, Activity, Scheduled work, Manage
assistants, Past work, Needs you, Apps & AI, Assistant settings, Task details,
Preferences, and the marketing page. The Playwright route check passed **1 case
in 17.56s** at desktop **1440×960**, tablet **900×1024**, phone **390×844**,
and compact phone **320×740**. It checks each route separately, resets the
mobile navigation drawer between captures, asserts no page overflow, and
reports no browser errors or external requests.

I opened the current desktop and phone screenshots independently for each app
route and the marketing page. This baseline review identified the assistant
settings header action crowding and a low-emphasis **Choose an assistant** action
in the empty schedule state; the settings header and empty-state action have
since been fixed. The responsive captures, trace, and source hashes are in
[`artifacts/ui-surface-review/`](artifacts/ui-surface-review/). The remaining
account, pairing, legacy server-page, expanded-state, and full marketing reviews
are still open; this route batch does not mark the redesign complete.

## Shared button variants and schedule assistant chooser (2026-10-10)

The empty schedule's **Choose an assistant** action now renders with the shared
emerald primary fill; generated utility CSS had previously flattened named
button variants to the neutral fill. Ghost choices retain a transparent fill.
With eleven fixture assistants, each choice is a 44px, one-line row. Long labels
show a rendered ellipsis while `aria-label` and `title` retain the full assistant
name. On phone and compact phone widths, the expanded roster stays within a
bounded scroll area, and keyboard focus brings the final row into view.

`uv run --frozen pytest -q tests/e2e/test_design_system.py::test_every_workspace_route_renders_independently_at_responsive_sizes`
passed **1 test in 22.25s** on Chromium **153.0.8010.12** / Playwright
**1.63.0**. It checked desktop **1440×960**, tablet **900×1024**, phone
**390×844**, and compact phone **320×740** for Studio, Activity, Scheduled work,
Manage assistants, Past work, Needs you, Apps & AI, Assistant settings, Task
details, Preferences, and marketing. There were no browser errors, external
requests, or provider calls. I inspected the empty schedule on desktop, tablet,
and phone, and the opened assistant choices separately on desktop and phone.
Evidence is in [`artifacts/ui-surface-review/`](artifacts/ui-surface-review/).
This is a focused route refinement; it does not complete the all-surface UI
overhaul.

## Assistant naming, role separation, and roster truncation (2026-10-10)

The request-based setup now suggests a short first-and-last assistant name and
keeps its task role in a separate editable note. The task-based local address
updates with the request but stays independent from a custom display name. The
selected-request flow still saves the user's original message as instructions
without asking them to enter it a second time. Legacy combined `Name · Role`
values keep rendering as a short name with the role below it.

The focused setup, YAML-import, settings-header, and all-route browser check
passed **7 tests in 45.63s**. It covered purpose-derived names, user edits, chat
and settings headers, sidebar rows, and the ten-assistant management view at
**1440×960**, **900×1024**, and **390×844** with Chromium **153.0.8010.12** and
Playwright **1.63.0**; selected-request setup also passed at those sizes.
I inspected the chat welcome, setup dialog, settings page, and larger roster
individually on desktop and phone, with tablet captures checked for overflow.
The name stays on one line, the task remains visible as secondary text, and
long management names retain their full accessible title when ellipsized. The
roster uses the idle row for the task role and keeps status in its accessible
title; active and attention states remain visible. No model/provider requests
were made. Screenshots, trace, browser details, and
source hashes are in
[`artifacts/bot-naming-quality/`](artifacts/bot-naming-quality/) and
[`artifacts/bot-from-message/`](artifacts/bot-from-message/). The broader
all-surface UI review remains open.

## Populated chat reply references (2026-10-10)

The independently reviewed same-chat reply flow showed a short quoted message
with a large empty area caused by preserved indentation in the markup. The
quote now collapses template whitespace and preserves line breaks in actual
message text. A normal send also no longer raises a transient **Sent** toast
over the phone composer; the new message and timestamp supply the confirmation.
Special rehearsal and queued-work notices are retained.

The browser regression passed **3 cases** at desktop **1440×1000**, tablet
**900×1024**, and phone **390×844** in Chromium **153.0.8010.12** / Playwright
**1.63.0**. The local fixture verifies the anchored reply survives reload,
keyboard focus returns to the composer, the short quote stays under **140px**,
and the viewport does not overflow. It recorded no page errors, provider calls,
or external requests. The sent-message screenshots were opened separately at
desktop, tablet, and phone sizes. Per-size JSON, source hashes, and traces are
in [`artifacts/reply-quote-polish-2026-10-10/`](artifacts/reply-quote-polish-2026-10-10/).
Attachments, long histories, human waits, and other open surfaces remain in
the broader review queue.
