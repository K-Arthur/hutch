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
| Sidebar | Round Search (opens the command palette) and New actions, quiet navigation rows, a home card for the coordinator, 40px avatars with one-line status, soft selection with a brand marker, two pill links at the foot, a docked icon rail, and a phone sheet. |
| Model picker | Pill trigger; menu grouped by where each model runs ("On this machine", "Hosted - leaves this machine") with icon tiles; "Choose a model" dialog with card rows and the selection control at the far edge. Roles, classes and wording are unchanged. |
| Command palette | Ctrl or Cmd + K: assistants, recent chats, pages, actions; ARIA combobox, native modal dialog. |
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
