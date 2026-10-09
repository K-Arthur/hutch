# Visual validation record

## Scoped conversation export (2026-10-08)

The Studio composer menu opens an export-scope dialog before downloading the JSON. The dialog explains included message provenance,
excluded stored credentials and other private records, verbatim message text, and the size limits. Chromium **153.0.8010.12** /
Playwright **1.63.0** exercised the download, parsed the resulting file, checked the exclusions, and captured the dialog at 1440×960,
900×1024 and 390×844. All three sizes had zero page errors and zero horizontal overflow. Screenshots, traces and source-hash/viewport records are
in [`artifacts/conversation-export/`](artifacts/conversation-export/); the test is
`tests/e2e/test_browser.py::test_conversation_export_shows_scope_and_downloads_json`. This is a synthetic local conversation with no
provider calls, not a screen-reader or physical-device check.

## Dashboard polish (2026-10-09)

The Studio's three working dots and the server-rendered live-connection mark remain still; “Working…”, “live” and “reconnecting” carry
the state. Shared server-rendered headings use a 1.4 line-height. The browser test checks the computed heading and status animation,
and places a visual-only working-indicator fixture in the actual Studio chat layout; it does not claim that a run was active. Chromium
**153.0.8010.12** / Playwright **1.63.0**
passed at 1440×960, 900×1024 and 390×844, with no page errors or horizontal overflow. The heading measured 30/42 px on desktop/tablet
and 24/33.6 px on phone. Screens, trace, source hashes and measurements are in
[`artifacts/dashboard-polish/`](artifacts/dashboard-polish/). I inspected the Studio phone capture with the steady dots visible and
the Connections phone capture with its heading and controls fitting the viewport.

The base-template static detector does not resolve its linked `hutch.css` heading rule and still estimates the browser default line
height. The existing path-scoped ignore remains, with its reason updated to the new computed measurements; no new ignore was added.

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
task-stream capture above for the current settings behavior. Bounded delegation remains separate work.

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
