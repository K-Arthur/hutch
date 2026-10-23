# Holistic experience — rendered review, 2026-10-23

Authority: [approved task-first route](../research/holistic-experience-2026-10-23.md),
[`DESIGN.md`](../../DESIGN.md). Current test/integration status lives in the
[task checkpoint](holistic-experience-progress.md); this record does not imply a
whole-suite pass or accessibility certification.

## Inspection coverage

Screenshots were opened individually, not judged only from a contact sheet. The
fixture viewports are Chromium CSS viewports, not physical-device tests. Tablet
and compact-phone geometry is additionally covered by the named regressions.

| Family | Opened evidence / representative states | Result |
|---|---|---|
| Chats and roster | `ui-audit-2026-10-20/app-surfaces/studio-{desktop,phone}.png`; expanded helper gallery, long assistant names, fleet menus | Shared shell, readable conversation, bounded menus; all gallery choices remain reachable above the composer |
| Activity | `app-surfaces/activity-{desktop,phone}.png`; clear state plus recent work | One aligned rail; no unrelated widths or empty activity columns |
| History and chat library | `app-surfaces/{runs,chat-library}-{desktop,phone}.png` | Filters stack without page overflow; result names wrap; technical data remains secondary |
| Schedules | `app-surfaces/schedules-{desktop,phone}.png`; open assistant chooser | Task-first empty state, 44px action, keyboard-reachable choices |
| Apps & AI | `app-surfaces/connections-{desktop,phone}.png`; `model-provider-quick-connect-2026-10-10/connect-phone.png` | Named service marks and states; focused key-entry dialog retains reachable actions and permission/billing copy |
| Assistant settings | `holistic-experience-2026-10-23/settings/controls-{1440,1280,320}.png`; assistant options menu | Fixed squeezed desktop fields; full inheritance labels, slider/value containment, editable basics remain first |
| Workspace settings | `app-surfaces/workspace-settings-{desktop,phone}.png`; actual opened native select | Dark native options, readable selection/focus, system-sans fields. Native popup was captured and inspected, not inferred from its closed control |
| Setup | Guided/import/source/duplicate captures plus `test_task_pages.py` | Page rather than long modal; independent heading/action access; reload, discard, replacement and delayed-create checks; no run on create |
| Skills and Runtime | `holistic-experience-2026-10-23/headers/` at 1440, 900, 390 and 320 | Fixed blank phone Refresh buttons; SVG, accessible name, focus and 44px target survive narrow headers |
| Run details and approvals | `app-surfaces/{run-detail,approvals}-{desktop,phone}.png`; interaction regressions | Human outcome first; technical transcript details optional; approval queue loading/focus failure paths checked |
| Phone supervision | `holistic-experience-2026-10-23/phone/` | Monitor-only boundary and revocation checked; ordinary messages now use body sans, raw technical events retain mono |
| Computer panel | `holistic-experience-2026-10-23/computer/` | Desktop/phone containment, human control, missing/stale frame states; synthetic frames explicitly are not real desktop/provider proof |
| Typed output widgets | `holistic-experience-2026-10-23/widgets/` | Real transcript renderer with golden fixture blocks: table, chart, comparison, flowchart, status, timeline, text, code receipt. Necessary table/code scrolling stays local |
| Server-rendered pages | `holistic-experience-2026-10-23/server-pages/` | Models, Usage, direct assistant page, compatibility Connections, login, pair and error at 1440/900/390/320. Fixed narrow 22px title override, long endpoint overflow and squeezed estimate label |
| Marketing | `holistic-experience-2026-10-23/marketing/`; refreshed approval-triage evidence | Short overview no longer stretches with explanations. Technical prose uses body-sized shared-width rows. Real proof assets load at their truthful dimensions; no composed/fabricated UI |

Paths in the table are relative to `artifacts/`; `app-surfaces/` abbreviates
`ui-audit-2026-10-20/app-surfaces/`. Provider-connect, native-select and menu
captures are retained in `holistic-experience-2026-10-23/controls/`.
`manifest.json` records retained evidence
hashes and the source checkpoint; captures from different tests are not an atomic
whole-product snapshot.

## Findings fixed during review

- Unsaved setup could be silently replaced; pending persistence could resurrect a
  discarded draft; late async results could seize the next page. Explicit
  replacement confirmation, lifecycle guards, timer cancellation and scoped
  completion now have regression coverage.
- Returning while creation is pending must preserve the submitted configuration:
  the setup fieldset and action remain disabled and say **Creating assistant…**.
- Desktop assistant settings inherited a fixed 340px side column inside a 760px
  page, squeezing the main form. The shared rail plus panel-width-aware tracks
  correct the cause, rather than shrinking text or hiding fields.
- Phone header text hiding produced empty Refresh controls. Named SVG actions
  now use the same compact-header grammar and a 44px target.
- Long technical/approval explanations were metadata-sized and confined to narrow
  columns. They now use the site's existing 17px body token; app prose stays on its
  existing 16px body token. The boundary badge now counts the six actual items.
- Transcript avatars incorrectly used editable display names rather than the
  roster's canonical assistant address. The regression compares the saved avatar
  SVGs on desktop and phone; opened captures are retained in `identity/`.
- Marketing proof captions/chrome use body sans; mono remains reserved for code
  and measured values. The explicitly labelled extended phone viewport remains a
  real capture, not a composite or ordinary-phone viewport claim.

## Review and limits

Requirements and standards self-review covered the committed branch delta from
`f29b299b` plus relevant uncommitted/untracked work. No framework, dependency,
provider access, tool authority, API endpoint or production data operation was
added. Blank assistant setup no longer grants OpenCode tools implicitly; explicit
reviewed templates remain explicit selections.

This is a two-pass **self-review**, not an independent reviewer certification.
The final delta includes identity, measured duplicate-test overflow, caption type,
and genuine refreshed evidence; no further actionable finding remains in that
review scope. Broad execution status is recorded separately in the checkpoint.
Earlier computer-phone “baseline” comparisons were contaminated by child imports
from another editable checkout. A fresh isolated comparison now reproduces both
failure classes on `f29b299b`: controlled-session fixture setup fails and the
process worker finishes before the expected human wait (1 failed, 1 error).
The changed-tree suite has 1 failure and 4 instances of that fixture error. This
establishes pre-existing failure in this environment, not the deeper cause or a
working control path. Test-environment fixes affect only the external runner,
not Hutch's approval or sandbox controls. The separate synthetic computer-panel
suite passed all 10 tests; that is not a substitute for successful input handback.

The disk-backed writer-throughput test also fails before this work (577 events/s
versus 530 events/s in the task tree under shared host load). Writer and test bytes
are unchanged. The test's supported RAM-backed option passes its unchanged >1000/s
gate. This supports a storage/load-sensitive environment limitation, not a claim
that on-disk production throughput was improved. All four remaining subprocess
durability probes pass after correcting child import isolation; no safety code,
threshold or assertion was relaxed.

## Completed broad validation

The interrupted isolated run plus restart-safe serial batches covered all **3278
runnable fast-test nodes**: **3260 passed, 7 skipped, 6 xfailed, 5 failed nodes**.
The original aggregate is retained in `fast-validation.json` with its source
fingerprint. Per-phase journals and batch JUnit/logs are under
`/home/kevina/.local/share/opencode/holistic-fast-validation/`. This is combined
coverage, not one uninterrupted green invocation; teardown errors are folded into
the associated node outcome in that aggregate.

Besides the storage benchmark, four workflow API nodes timed out or failed thread
shutdown in batch 28 (3 test-call failures and 2 teardown errors). A bounded
focused rerun passed all four on the pre-overhaul archive and all four on the task
tree. Tests, workflow engine, supervisor and API bytes are unchanged. The original
failures remain recorded; their batch/timing cause is **not diagnosed**, and no
timeout, assertion, safety boundary or product code was changed to hide them.

## Integration and cleanup

Fast-forwarded `main` from `f29b299b` to `9fe75af9`. In the original checkout,
**62 post-merge tests passed** (170.16s): dashboard/server and model contracts,
site tokens, all setup/task-page and experience-surface browser regressions,
marketing evidence completeness and the emoji audit. JavaScript syntax passed.
Opened the post-merge phone identity and desktop expanded-settings captures.
Genuine output, captures, preservation hashes and cleanup checks are retained in
`artifacts/holistic-experience-2026-10-23/integration/`.

All **12 unrelated modified tracked files** match their pre-merge hashes after
integration testing and cleanup; unrelated untracked files were not removed.
Archived only this task's duplicate research note, then let Git install its more
complete tracked version. Removed the task worktree and merged feature branch,
unlinked only its node_modules symlink, and removed the task-owned temporary
baseline archive. Shared dependencies and other worktrees remain. No push.
This integration pass includes the user's existing uncommitted backend work;
it is not a claim that those edits were reviewed or committed by this task.

The mechanical detector reported eight advisory items, not proof of visual
quality. Provider sign-in artwork radius and neutral provider-artwork backgrounds
are documented brand exceptions; 11px marketing table headings are an existing
explicit token exception. Off-ramp Skills/server type and the legacy success
border were normalized. The detector's stale sidecar notice is not a reason to
rewrite the approved design system.

Keyboard, native-select focus, text-spacing overrides, narrow reflow and
supplementary doubled-root/effective-viewport probes have evidence in the focused
tests. Native browser zoom, a screen reader, physical phones, other browser
engines and live provider inference were **not** verified. No numerical aesthetic
score, usability success rate or whole-product conformance is asserted.
