# Studio redesign: validation record (2026-10-26)

Scope: the dashboard redesign requested on 2026-10-26 (tool-calling and approval UI, header, colors and WCAG, chat
bubbles, marketing site, first-run intro and fit, model picker and dialog, sidebar), and its second round the same day
(one scale for corners, type and spacing; assistant settings and the options popover rearranged; the model picker made
quicker and easier to recognise; the remaining surfaces). Work was done on branch `ui/studio-redesign` (17 focused
commits) and rebased onto `main`; it was landed by fast-forward once the checks below passed on the landing tree. Design
rules are in `DESIGN.md`; the change summary is the first `CHANGELOG.md` entry under Unreleased.

Screenshots referenced below are in `docs/realignment/artifacts/studio-redesign-2026-10-26/` (`before/` and `after/`).
All were opened and inspected; a screenshot existing is not treated as validation.

## What was built

| Area | Result |
| --- | --- |
| Thread and steps | A turn is avatar, spine, step cards, answer. Each tool call is a step with a plain-language title, subject, state word, exit code, measured duration, exact request and full output with Copy, and raw JSON on request. "Worked for" subtracts recorded approval waits. |
| Gates (approvals) | Permission requests show the exact content up front (file preview, `$ command` well, risk, scope, countdown). Decisions are unchanged: Allow once, Always allow for this bot, Deny; no single-key approve. A pending gate is brought into view when a conversation or task opens. |
| Answers and bubbles | Safe Markdown (escape-first, http/https/mailto only, no remote images, copyable code). Long requests clamp and expand; expanded state, output "Show more" and Raw/Formatted survive live updates. |
| Header | One row. The status chip, waiting/queued counts and needs-you pill are gone (each fact has one home). The coordinator chip stacks under the name on a phone. |
| Colors and type | Bundled Geist and Geist Mono; neutral graphite palette; every text token at least 5:1; 3:1 control edge for fields (WCAG 1.4.11); no side-stripe borders. |
| First-run intro | Left-aligned hero, request card, and a rail (AI service, how Hutch works). Laid out by pane width (container query); the setup action stays on screen at 320, 375, 390, 1280x720 and landscape phone. |
| Sidebar | A round Search action (opens the command palette), quiet navigation rows with distinct icons, a home card for the coordinator, 40px avatars with one-line status, an "All assistants" heading once something is pinned, soft selection with a brand marker, two pill links at the foot, a docked icon rail, and a phone sheet. There is no new-conversation button: main's ADR 0021 makes each assistant's chat persistent. |
| Model picker | Every model wears a vendor mark (bundled OpenAI and Anthropic artwork, a family monogram otherwise) with a runs-here / leaves-this-machine badge. The menu opens on Quick picks (default, in use, last four chosen for the assistant), has number keys 1-9 and `/` for the searchable list, and the command palette adds Choose a model. The dialog opens on search, shows a Recent group, filters by All / Ready now / On this machine / Hosted, and takes arrows and Enter from the search field. Roles, classes, ids and `data-spec` are unchanged. |
| Command palette | Ctrl or Cmd + K: assistants, recent chats, pages, actions (including Choose a model on a chat page); ARIA combobox, native modal dialog. |
| Assistant settings | One 10,850px accordion of a dozen panels became seven panes (Profile, Behavior, AI model, Tools and access, Schedule, Safety, Limits and memory) behind an ARIA tablist rail: vertical beside the pane from 760px of pane width, wrapped on tablets, a sticky scrolling strip on phones; arrows, Home and End; the pane survives the re-render a save triggers and a fresh visit opens on Profile. Every pane stays in the DOM so each form keeps its id and handlers. |
| Chat and assistant options | The popover is four labelled groups (This chat, Workflow, This assistant, Go to); the workflow select is a labelled row, not a card inside a menu. |
| Shared scales | One corner scale (micro 4 / control 8 / panel 12 / chat 20 / chip 100px, 50% for circles; 15 distinct radii before), six text steps (12, 13, 14, 16, 18, 24, plus 17 for reading and a display band), the 4px grid for padding and gaps (1,990 of 5,843 declarations were off it), and one control-height ladder (32, 36, 40, 44). Three browser guards fail with the selector of any violation. |
| Connections | Main's redesigned directory and focused setup pages, put on the shared scales (card padding 16, grid-snapped spacing, chips and filters that wrap at large text). |
| Marketing site | Geist, the shared graphite tokens, and first-run captures regenerated from the real empty app with the repo's own capture script (it refuses to run against a populated app). |

## Method and results

All numbers are from this branch's code, Chromium 153 (Playwright 1.63), on an isolated state directory. Fixture runs are
synthetic and are written straight to the store; no model or provider is contacted. The model-picker screenshots and axe
runs use a mocked model catalog (the real catalog needs live connections); the picker's logic is covered by the existing
e2e suite against real fixtures.

| Check | Scope | Result |
| --- | --- | --- |
| axe-core 4.14 (WCAG 2.0 to 2.2 A/AA plus best-practice rules) | 21 routes and fixtures at 1440 and 390 | 0 violations |
| axe-core, interactive states | model menu, model dialog, phone sidebar sheet, gate with details open, Needs-you drawer, at 1440 and 390 | 0 violations (after the three fixes below) |
| axe-core, first run, welcome, palette, marketing site | desktop and phone | 0 violations |
| Pixel-sampled contrast (foreground against the rendered background behind each text node) | 857 desktop and 382 phone text samples across fixtures and pages; 46 first-run and 34 welcome samples | 0 failures |
| Pixel-sampled contrast, overlays | 536 samples across menus, dialog, sheet, drawer | 0 real failures; 2 readings are the sidebar badge behind a modal's dark backdrop (the same badge passes on every page without a backdrop) |
| Token contrast pairs | all text tokens on ground, panel and raised surfaces | at least 5.0:1 (text-3 reads 4.3:1 on the raised tag surface, so gate and model tags use text-2) |
| Fit audit (document overflow, content past the viewport or cut by hidden overflow, controls clipped without an ellipsis, unintended sideways scrolling) | 21 routes at 320, 390, 768, 1024, 1440, 844x390 landscape, 390 at 200% text, 320 at 200% text; plus first run and welcome | 0 findings after fixes. The audit was self-tested: it flags an injected 700px element and a clipped button. The one intended case it reports is the landscape first-run label that is visually hidden but kept for screen readers. |
| Keyboard focus | 241 Tab stops across 5 chat fixtures; 25 sidebar stops (desktop) and 30 (phone sheet) | every stop shows a ring; the composer shows focus on its container (border and halo) |
| Reduced motion and forced colors | chat fixtures | no running animation under reduced motion; forced-colors rendering inspected |
| Large transcript | 100 rendered steps (150 recorded; the server serves the latest 200 events) | full feed re-render 258 ms; opening the step list 65 ms; expanding one step 31 ms |
| **Second iteration (shared scales, settings, model picker; rebased onto main)** | | |
| axe-core on the rebased tree | 20 routes and fixtures at 1440 and 390 | 0 violations |
| axe-core and pixel contrast, new surfaces | the seven settings panes, the options popover (and with Response style open), Apps & AI and Activity, at 1440 and 390 | 0 violations; 988 contrast samples, 0 failures (the popup's Done button had a label-in-name mismatch, fixed) |
| axe-core and contrast, model picker | menu, dialog, at 1440 and 390, mocked catalog | 0 violations; 522 overlay samples, 0 real failures (two readings are the sidebar badge behind a modal backdrop, as before; the Needs-you review label at 4.43:1 was lifted to text-2) |
| Fit audit, all routes | 20 routes at 320, 390, 768, 1024, 1440, 844x390, 390 and 320 at 200% text | 0 findings after fixes (main's connections filters could not wrap at 200% text) |
| Fit audit, settings and options | each of the seven settings panes and the options popover (with Response style open) in the same eight view configurations | 0 findings after fixes. It found overflow the closed accordion used to hide: text controls forced forms and labelled fields wider than the screen at 200% text |
| Fit audit, connection details | all 11 connection detail pages in the same eight view configurations (88 pages) | 0 findings after fixes (status chips could not wrap) |
| Scale guards | `test_radius_scale.py`, `test_type_and_spacing_scale.py` (computed style of every painted element and every stylesheet radius, on every route, every settings pane, the popover and the palette, at desktop and phone) | pass; they fail with the offending selector, verified by running them against the unfixed tree |
| Code review (twice, `/code-review high`) | the whole branch diff, then the commits added since | 10 findings in the first pass, each reproduced, fixed and pinned by a test that fails without it; see the second-pass note in the final results |

## Defects found by validation, and fixed

1. **A stale-approval click raced the page.** On the task page the thread slid in as it loaded and the gate sat below the fold, so the click outlasted the window before the card refreshed. Threads that are already present no longer animate, and a pending gate is scrolled into view. The test now passes 6 of 6 runs (it failed 2 to 4 of 4 before).
2. **The marketing site downloaded its font twice.** The preload URL carried a content hash but the `@font-face` URL did not. They match again.
3. **Roster:** the options button was hidden until hover, and the larger avatars truncated ordinary names. The button is always visible (low emphasis, in its own 28px column) and names are budgeted to stay whole at 272px.
4. **Fit:** approval gates overflowed at 200% text; the Runs filter pills were cut off; chat-library rows and KPI tiles clipped at 320px; the gate header collided at phone width; a 320px Needs-you card was too tall.
5. **Side-stripe borders** on the reply quote and Markdown blockquotes were replaced with boxed styles (project rule).
6. **Contrast:** gate tags (4.34:1) and the "leaves this machine" tag (4.43:1) now use text-2.
7. **Accessibility:** dialog titles were h3 under an h1 (now h2, with h3 group headings); Needs-you filter buttons did not contain their visible text in their accessible names; the coordinator chip put `aria-label` on a plain span.
8. **Typography regression:** I had lowered the section and reading sizes by one step. Restored to 18px and 17px (the design-system contract).
9. **Touch targets:** the "Make a bot" action and compact header actions are 44px on touch.
10. **Expanded state** (long request, step output "Show more", Raw/Formatted) used to snap shut on any live update; it is now remembered, with a regression test that fails without the fix.

Second iteration:

11. **Response style buttons rendered blank on phones.** A header rule that collapses buttons to icons leaked into the options popover ("Save conversation style" and "Use inherited" were 44px squares with `font-size: 0`). Scoped to the header's own buttons.
12. **"New conversation" threw a ReferenceError after the rebase** (found while writing a test for a review finding). Main's persistent-chat model removed conversation creation; the sidebar + and palette action are removed rather than left broken.
13. **Code review, Markdown:** list items after a shallower first item were dropped; a fenced block inside a list item lost its code block; `## Learning C#` lost its `#`; a URL beside a code span was corrupted; a prose line with a pipe above a rule became an empty table. Reproduced in Node, fixed, and pinned by seven checks that fail on the old renderer.
14. **Code review, app:** approval gates' "Show more" did nothing outside the chat stream (the Needs you queue), and a very large write gave no sign it was clipped; "Show all more characters" for short multi-line output; the palette kept a stale highlight when the query changed; the settings rail scrolled the page instead of only itself and announced the wrong orientation on phones.
15. **Text at 200%:** shared form grids and labelled fields let an input's intrinsic width push forms past the screen; long model ids in hints, connection chips and filter buttons could not wrap.
16. **Smaller:** doubled spacing between connection cards (32 instead of 16), a field beside a taller one stretching its select to 59px, a sticky rail that could hide a focused field, the model pill's monogram entering its visible text (axe, fixed by generating it with CSS), Skills headings in the muted colour, title-only phone headers off the menu button's centre line, "1 messages", a shared icon for Conversation history and Work history, Activity KPIs flush against the cards above, Apps & AI status chips wrapping in a narrow column.
17. **Popover flip-flop on phones (found by the final suite, caused by my own earlier fix):** the shared popup placed a panel as a bottom sheet or an anchored menu by measuring its current size. The sheet is capped to stay clear of its trigger, so a panel that was already a sheet measured shorter, was re-placed as anchored, grew, and was re-placed as a sheet on the next resize notification, alternating every frame (the options popover at every phone height from 560px up, with the header and content heights of the conversation-options test). Taps could land on a row that had just moved, which showed as a click timeout in `test_conversation_options_are_compact_persistent_and_recoverable`. That test passed in two earlier full runs and then failed four times in a row, so it was not treated as noise: the placement now measures the panel at its natural size, and `tests/e2e/test_popup_layout.py` samples 24 frames at every height from 560 to 992px and fails on the previous code with the two alternating states.

## Tests changed, and why

Updated because the design they encoded was replaced on purpose:

| Test | Change |
| --- | --- |
| `test_delegated_wait_status_is_responsive_and_reviewable` | The header no longer repeats waiting and queued counts; it asserts the header is quiet and the wait is stated once on the task. |
| `test_workflow_pill_meets_target_minimum` (now `test_reminder_review_action_meets_target_minimum`) | The needs-you pill is gone; the reminder's Review action keeps the 24px target and the header must not repeat the count. |
| `test_untrusted_run_content_is_text_not_executable_html` | Answers are Markdown, so a paragraph wrapper is expected; nothing the payload says may become an element. |
| `test_queued_chat_keeps_earlier_approval_and_live_status_fresh` | Scoped "Done" to the turn header (each step also carries a visually hidden state word). |
| `test_shared_design_tokens_render_consistently_across_all_surfaces` | Pinned values moved to the new graphite tokens. |
| `test_popup_edges_and_surfaces_match_design_tokens` | Form fields use the 3:1 edge token; menus keep the strong border token. |
| `test_open_phone_sheet_reaches_every_destination_and_wraps` | Needs you is reached within six Tab stops (the Search action now precedes the navigation), not the fourth. |
| `test_every_workspace_route_renders_independently_at_responsive_sizes` | The long fixture name is longer (Geist is narrower, so the old name no longer needed an ellipsis); the phone "New" button must be a labelled button wider than the 44px icon form. |
| `test_approval_triage_marketing_evidence_is_complete` (now `test_archived_approval_triage_marketing_evidence_is_complete`) | `main` turned `docs/realignment/approval-triage-2026-10-22/marketing` into a frozen archive that is checked against its own snapshot of the page, and its producer test now writes elsewhere. My earlier regeneration of those eleven files made the archive inconsistent, so it was dropped and the archive restored to `main`'s version. |

Second iteration, updated because the structure they encoded was replaced on purpose:

| Test | Change |
| --- | --- |
| `test_assistant_settings_keep_everyday_edits_up_front` | Was "closed by default, opens with Space". It now asserts the rail (ARIA tablist with seven named tabs), Profile first, only the selected pane exposed, the rail beside the pane on desktop and above it on phones, arrow/Home/End movement that selects the pane, the selected tab fully inside the rail, and no overflow in any pane. |
| `test_connection_and_assistant_settings_share_disclosure_axes` | The "Customize how it works" summary no longer exists; the in-card disclosure alignment check keeps the usage-limits summary. |
| Persona, mascot-picker and 32 settings call sites across eight files | The four copy-pasted `open_assistant_customization(page)` helpers became one `tests/e2e/settings_pane.py`; each call names the pane that owns the field it touches (`"behavior"`, `"model"`, `"tools"`, `"schedule"`, `"safety"`, `"limits"`, `"profile"`). |
| `test_studio_palette.py` | Asserts New assistant and the absence of a New conversation action and button (main made each assistant's chat persistent). |

Added in the second iteration: `test_radius_scale.py`, `test_type_and_spacing_scale.py` (the shared-scale guards), `test_settings_rail.py` (the rail moves, not the page; orientation follows layout; a save keeps the pane), `test_model_picker.py` (marks, quick picks and recents, number keys and `/`, the dialog's filters, arrows and Enter with one radio per route, the palette action, no remote request), two cases in `test_studio_transcript.py` (clipped output label, the Needs-you "Show more"), two in `test_studio_palette.py`, and seven Markdown checks in `markdown_check.mjs` that fail on the previous renderer.

Hardened (same assertions, retrying wait instead of an instant check on a popup that opens asynchronously):
`test_inline_chat_approval_is_one_click_and_preserves_conversation`,
`test_chat_header_uses_available_title_space_and_groups_assistant_settings` and
`test_fleet_appears_at_ten_bots_with_search_and_state_filters`. `test_conversation_options_are_compact_persistent_and_recoverable` now waits for each
conversation switch to replace the view (a new `switch_conversation` helper) and for the asynchronous task-template import
to fill the composer. It used to wait for text that the old view also contained and then click Options on a view that was
about to be rebuilt; it passed 8 of 8 on clean `main` and failed 2 of 8 here, because the redesigned view is rebuilt a
little later (a conversation switch takes about 79 and 127ms against 67 and 95ms on `main` in two interleaved runs). The
generation guards in `renderChatStudio` were checked and are doing their job: the superseded render returns without
painting, and the render that landed after the click was the current one. It passes 12 of 12 under a load average of 11. `test_scoped_fact_review_revision_conflict_and_memory_off` had the same shape (switch conversation, then click the fact panel's summary in the old view) and failed 1 of 6 on clean `main` and once in a full run here; it now uses the same helper.

Added: `tests/e2e/test_studio_transcript.py` (Markdown inertness and Copy, step cards, gate content and decisions, long-request clamp and labels, header facts once, persistence across live updates), `tests/e2e/test_studio_palette.py`, `tests/test_studio_markdown.py` with `tests/support/markdown_check.mjs` (36 checks, mutation-verified), and updated `tests/test_studio_shell.py` and `tests/test_site_tokens.py`.

## Failures not caused by this work

At the start of the second round, a full browser run on a clean checkout of `main` (`1b95633a`) had 14 failures (13 failed,
1 teardown error), mostly in `test_design_system.py`, the typed-output widget test, the approval-triage evidence consumer and
four in `test_browser.py`. `main` has since changed that picture (the design-system failures pass on the final tree), so the
final comparison below is against the tree itself, not that list.

`test_design_system.py::test_assistant_first_run_and_app_catalog_use_familiar_visual_language` pinned eleven connection tiles and failed on `main`'s own tip after its Telegram commit made it twelve. I updated its expectations here; `main` then fixed the same test in a later commit, my identical change became empty on the next rebase, and I dropped it.

`test_website.py::test_dynamic_workflow_marketing_is_truthful_and_responsive` fails deterministically on `main`'s tip (`assert 2 == 1`: the availability table now has two rows whose text contains "Workflows") and fails the same way on this branch. I did not touch it; whichever row is right is a marketing-copy decision for whoever changed that table.

Intermittent failures that are not from this work, each checked against a clean checkout of `main`'s tip (`05aa6489`) rather than assumed:

- `test_paired_phone_keeps_mixed_question_and_approval_pending_in_either_order[decision_order1]` fails now and then waiting 30 seconds for the answer response: 1 of 6 runs on clean `main`, 1 of 5 here, and once in each of the last two runs. I did not change it and did not find its cause.
- `tests/test_store_events.py::test_batched_writer_sustains_over_1000_events_per_second` is a throughput test; it fails in isolation on clean `main` and here when the machine is loaded (load average 4.7 to 11 from other agents' work).
- `tests/test_workspace_protocol.py::test_single_line_spin_deadline_is_bounded_by_an_outer_process[signal]` and `tests/test_offline_mode.py::test_loopback_broker_refuses_a_request_after_close_starts` are timing and signal tests that failed in one full run each and pass in isolation on both trees. This branch changes no backend code.

I report them as load-sensitive and did not re-run until green.

## Not tested, or limited

- No screen reader (NVDA, VoiceOver, TalkBack) was run; accessibility claims rest on axe, the accessibility tree, keyboard walks and the measurements above.
- Chromium only; Firefox and WebKit were not run. The customizable select (`appearance: base-select`) degrades to the native picker elsewhere by design.
- No physical phone or tablet; narrow sizes use emulation and 200% text size, which is stricter on text and looser on pixel scaling than 400% browser zoom.
- No user research or independent design review. The scores below are my own judgment from the evidence; the two `/code-review` passes were by a model, not a person.
- The model picker was exercised with a synthetic catalog for screenshots, audits and tests; live provider catalogs were not contacted.
- The vendor marks use artwork already bundled for connections; no new brand asset was added, and none is fetched at runtime.
- `main` moved throughout the work (it gained dozens of commits, including a redesign of the connections flow and a persistent-chat model). The branch was rebased repeatedly, resolving real conflicts in `app.js`, `input.css`, `test_browser.py` and the site index. One of those resolutions was wrong and caught before landing: `git checkout --theirs` on the site index discarded `main`'s other edits to that file. The final tree was verified against `main` line by line (the index differs only in the graphite `theme-color`, the Geist preload and cache stamps). (No test pins that; it was checked by diffing against `main`.)
- The full browser and backend suites ran on the landing tree before `main` moved a last time (ten more commits). After that rebase I ran the targeted set above, landed, and then ran the full browser suite once more on the landed commit (`16f72083`, below). The backend suite was not re-run after the last rebase; this branch changes no backend code, and `main`'s ten newest commits were validated by their own authors.

## Self-assessment against the PRODUCT.md gates

| Gate | Score | Basis |
| --- | --- | --- |
| Aesthetic (at least 90) | about 91 | One shape, type and spacing language enforced by guards rather than by hand; the thread, gates, bubbles, sidebar, settings, popover, picker, intro and connections read as one product in opened screenshots at 320 to 1440. At the gate, not far above it: no external review, and the sidebar still carries a list of destinations that the Muse reference does not. |
| Functionality (at least 95) | about 95 | Every role, id and decision semantic is preserved; the suites exercise them; validation found and fixed the defects listed above. At the gate, not above it: the environments under "Not tested" were not covered, and one phone test is intermittently red on `main` as well as here. |

Both are unreviewed estimates, and the overall score is the lower of the two. Whether this matches the quality of the Grok and Muse references is your call; the screenshots are the thing to compare.

## Final suite results

Temp, basetemp and artifact paths were on the disk volume; the Chromium revision is the one the locked Playwright expects.

| Run | Command | Result |
| --- | --- | --- |
| Browser, full, first pass on the rebased tree | `pytest -q tests/e2e` | 445 passed, 1 skipped, 6 failed (26 min). Causes: three tests in `test_learning.py` and one in `test_browser_budget_controls.py` used the old accordion or never selected the pane that owns the field (Memory and learning and the usage limits are in Limits and memory); `test_tool_compatibility.py` raced a page transition (the shared helper now retries its click); and `test_archived_approval_triage_marketing_evidence_is_complete`, because `main` had turned that directory into a frozen archive and my earlier regeneration of its eleven files made it inconsistent (restored to `main`'s version). All six were fixed in the test layer or by restoring the archive, with no assertion weakened. |
| Browser, full, on the landing tree (`0989a590`, rebased onto `main`'s Telegram commit) | `pytest -q tests/e2e` | 452 passed, 1 skipped, 2 failed (32 min). The options test: a test race, fixed in the test layer (see "Hardened"), then 12 of 12. The paired-phone test: the inherited intermittent failure described above. This run also found the popover flip-flop (defect 17), fixed in `controls.js` with a regression test,. |
| Backend, full, on the landing tree | `pytest -q --ignore=tests/e2e` | 3673 passed, 20 skipped, 6 xfailed, 2 failed (25 min); both failures are the load-sensitive tests described above. |
| Browser, full, on the landed commit (`16f72083`, after the merge) | `pytest -q tests/e2e` | 460 passed, 1 skipped, 2 failed (30 min). `test_dynamic_workflow_marketing_is_truthful_and_responsive` fails identically on clean `main` (see above). `test_design_system.py::test_answer_feedback_stays_local_revisioned_and_accessible` failed once, waiting for the feedback controls to reach a revision; it passed in both earlier full runs, passed 6 of 6 on `main`'s pre-merge tip and 6 of 6 on the landed commit, and 8 of 8 on each under parallel stress. I could not reproduce it and have no cause to report. |
| Landing tree after the last rebase onto `main` (`f6bda0e5`, ten more commits including a campaign-report dialog and a navigation fence) | the three scale guards, popup layout, campaign report, conversation navigation, channels, the picker, settings rail, palette, transcript, the whole of `test_design_system`, `test_learning`, `test_browser_budget_controls`, `test_tool_compatibility`, `test_website`, the delegation, workflow-card and spending tests, all of `test_browser`, and the Markdown, site-token, emoji-audit and shell tests | 311 passed, 3 failed (27 min): the paired-phone test and the fact-card test (both intermittent on clean `main`, see above) and the workflow availability row (fails identically on clean `main`). The fact-card test was then hardened and passed 4 of 4 with the options test. |
| Lab audits on the rebased tree | axe on 20 routes at 1440 and 390; the new surfaces; the picker states; fit on all routes, on every settings pane and the popover, on all 88 connection detail pages and on `main`'s new Telegram setup page, in eight view configurations (axe on Telegram at 1440, 390 and 320 only) | 0 axe violations; 988 contrast samples with 0 failures (and 522 overlay samples where the only two readings are the sidebar badge behind a modal backdrop); 0 fit findings |

An earlier full browser run on the same tree had 13 failures that were real and are fixed: three tests waited for the Profile
pane's heading after switching panes; the regrouped options popover, taller than the old list, became a bottom sheet that
covered its own trigger on small screens (a sheet is now capped to leave the header uncovered); and the settings page
remembered the last pane for the whole session, so navigating away and back reopened it on Behavior (only a save's re-render
keeps the pane now, and a fresh visit opens on Profile).
