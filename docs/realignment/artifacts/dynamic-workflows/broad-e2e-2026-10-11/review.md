# Full E2E suite review

The complete browser suite ran on the committed `bef3b2b2` snapshot in a disposable worktree. It completed with 177 passed, 29 failed, and 8 teardown errors over 19m53s. The unmodified log and machine-readable test list are retained beside this review.

Two failures were in this workflow task. The workflow-card check exposed focus restoration and a compact-phone scroll-clearance gap; its focused rerun now passes with 44px actions at 1440, 768, 360 and 320 CSS pixels, plus text-spacing and forced-colors checks. The specialist-question check tried to execute through `mock/demo`, which Hutch intentionally refuses; the fixture now uses a scripted loopback Ollama-compatible server and the real UI/API/answer-run path, and the focused rerun passes.

The other broad failures span schedules, OpenCode, artifact sharing, navigation, settings, workspace rosters, drafts, composer controls and facts. Eight fixture teardowns report that the Uvicorn thread did not stop within its join timeout. These failures were not isolated or closed during this task and remain open; they are not described as harmless baseline issues.

This broad run is not a green-suite claim. It is a regression snapshot, and the updated focused tests should be rerun as part of the next full-suite triage.
