# Studio redesign: validation record (2026-10-26)

Scope: the dashboard redesign requested on 2026-10-26 (tool-calling and approval UI, header, colors and WCAG, chat
bubbles, marketing site, first-run intro and fit, model picker and dialog, sidebar). Work lives on branch
`ui/studio-redesign`, based on `main` at `b8bb7310`. Nothing is committed or pushed. Design rules are in `DESIGN.md`;
the change summary is the first `CHANGELOG.md` entries under Unreleased.

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
| Assistant settings | One 10,850px accordion of a dozen panels became seven panes (Profile, Behavior, AI model, Tools and access, Schedule, Safety, Limits and memory) behind an ARIA tablist rail: vertical beside the pane from 760px of pane width, wrapped on tablets, a sticky scrolling strip on phones; arrows, Home and End; remembered per assistant. Every pane stays in the DOM so each form keeps its id and handlers. |
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
| `test_approval_triage_marketing_evidence_is_complete` | Evidence regenerated from the current site with the producer test (see below). It already failed on `main` at `b8bb7310` because that commit changed `index.html` after the evidence was captured. |

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
`test_fleet_appears_at_ten_bots_with_search_and_state_filters`.

Added: `tests/e2e/test_studio_transcript.py` (Markdown inertness and Copy, step cards, gate content and decisions, long-request clamp and labels, header facts once, persistence across live updates), `tests/e2e/test_studio_palette.py`, `tests/test_studio_markdown.py` with `tests/support/markdown_check.mjs` (36 checks, mutation-verified), and updated `tests/test_studio_shell.py` and `tests/test_site_tokens.py`.

## Failures not caused by this work

- `tests/e2e/test_experience_surfaces.py::test_typed_output_widgets_fit_the_run_transcript_at_responsive_sizes` fails the same way at the base commit (the element-screenshot wait never sees the card as visible).
- Six backend tests fail identically on a clean checkout of `main` at `b8bb7310` (checked in a temporary worktree): `test_runtime_builtin.py` (2), `test_toolcalling_validation.py` (2), `test_workflow_csv_acceptance.py` (1), `test_workflow_engine.py` (1).

## Not tested, or limited

- No screen reader (NVDA, VoiceOver, TalkBack) was run; accessibility claims rest on axe, the accessibility tree, keyboard walks and the measurements above.
- Chromium only; Firefox and WebKit were not run. The customizable select (`appearance: base-select`) degrades to the native picker elsewhere by design.
- No physical phone or tablet; narrow sizes use emulation and 200% text size, which is stricter on text and looser on pixel scaling than 400% browser zoom.
- No user research or independent design review. The scores below are my own judgment from the evidence.
- The model picker was exercised with a mocked catalog for screenshots and audits; live provider catalogs were not contacted.
- The other agent's work is in flight on the same surfaces (ADR 0021 and P13 in `desktop-production-2026-10-26.md`: a "Chat with Hutch" and Tasks daily path). This branch keeps every route, id and role and restyles around them, but the two will need reconciling.

## Self-assessment against the PRODUCT.md gates

| Gate | Score | Basis |
| --- | --- | --- |
| Aesthetic (at least 90) | about 90 | One shape language across thread, gates, bubbles, sidebar, picker and intro; checked in opened screenshots at 320, 375, 390, 768, 1024, 1280x720, 1440 and landscape phone. At the gate, not above it: no external review, and the sidebar still carries a list of destinations that the Muse reference does not. |
| Functionality (at least 95) | about 95 | Existing behavior and every role, id and decision semantic are preserved; the e2e suite exercises them; the validation above found and fixed ten defects. At the gate, not above it: the pre-existing failures listed above (one e2e, six backend) remain open, and the environments listed under "Not tested" were not covered. |

Both are unreviewed estimates, and the overall score is the lower of the two. Whether this matches the quality of the Grok and Muse references is your call; the screenshots are the thing to compare.

## Final suite results

Both runs were on the final tree (after the last code, test and doc edits), with temp, basetemp and artifact paths on the
disk volume. The Chromium revision is the one the locked Playwright expects.

| Suite | Command | Result |
| --- | --- | --- |
| Browser | `pytest -q tests/e2e` | 394 passed, 1 skipped, 1 failed (23 min). The failure is `test_typed_output_widgets_fit_the_run_transcript_at_responsive_sizes`, which fails the same way at the base commit. |
| Everything else | `pytest -q --ignore=tests/e2e` | 3384 passed, 15 skipped, 6 xfailed, 6 failed (19 min). The six failures are the backend tests listed above, which also fail on a clean checkout of `main` at `b8bb7310`. |

For comparison, the first full browser run after the redesign had 24 failures and 1 teardown error; triage of those produced
the fixes and test updates above. The baseline (before any change) had 5 browser failures: the typed-output test above;
two popup-visibility races, which the hardened tests now cover; and two others (a generated-file download test and a
computer-use login test) that pass on the final tree. I did not investigate why those two failed at the baseline, so I
cannot say whether they were load-dependent.
