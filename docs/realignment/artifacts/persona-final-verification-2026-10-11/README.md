# Persona verification checkpoint

These files record the local pre-integration checkpoint on `persona/adaptive`, before importing the latest local
`main` commit `63b2712`.

- `offline-suite.log` is the full offline run: **2,048 passed**.
- `browser-suite-pre-main.log` is the complete `tests/e2e` run. It records **29 failed, 181 passed, 8 teardown
  errors**. The failure list includes a stale inspector-role assertion that was corrected afterward; do not treat this
  historical full-suite result as the final integrated run.
- `persona-focused-browser.log` is the focused live-preview and answer-rewrite run after updating that assertion:
  **2 passed**.

The task plan records how the pre-integration failures compare with the earlier clean-base run and which isolated checks
passed on `63b2712`. No assertions were removed or weakened.

After merge commit `15e1649`, the complete offline suite passed (**2,116 passed**); see `offline-suite-integrated.log`.
The dedicated migration suite was rerun after the final test additions and passed (**32 passed**); see
`migration-suite-integrated.log`.
The complete integrated browser run is recorded in `browser-suite-integrated-stalled.log`: it remained inside the
known responsive workspace-settings case at 33% for over seven minutes, then was interrupted at 20 minutes. The focused
integrated browser retry in `browser-focused-integrated-enospc.log` ran while `/tmp` was full and failed creating
Chromium/trace state (`ENOSPC`); those failures are environment-contaminated. The focused rerun with temporary files
moved to `/var/tmp`, recorded in `browser-focused-integrated.log`, passed **6 tests**: live preview, answer rewrite,
specialist clarification, workflow-pill dimensions, and the Runtime page. These task-specific Chromium runs did not use a
provider. `persona-live-preview-2026-10-11/validation.json` records zero horizontal overflow from 320 to 1440 CSS pixels,
including the 720×480 effective-width check.

After fast-forwarding integrated commit `a111ffb` into local `main`, a final clean-worktree smoke run passed **38 tests**
(32 migration tests and 6 focused browser tests in 22.21 s). The captured output is `post-merge-smoke.log`. This
targeted post-merge check does not change the full browser-suite status above.

After the final benchmark and design-triage commits were fast-forwarded, the same 38-test post-merge smoke passed again
in **22.15 s** using `TMPDIR=/var/tmp`; see `post-merge-final-smoke.log`. The run refreshed the live-preview and
answer-rewrite fixture screenshots, validation records and traces. Their desktop/phone and tablet/compact-phone
captures were inspected; the records show zero horizontal overflow across their 320, 360, 720, 768 and 1440 CSS-pixel
checks, no page or console errors, no external requests, and no provider calls. The regenerated persona evidence was
retained; unrelated delegation captures were restored to their committed state.

The stalled full run's workspace-mode settings case was isolated with `TMPDIR=/var/tmp`. On the integrated tree, all four
viewport variants failed after 30 seconds at the same wait for the “Workspace Helper settings” heading (4 failed in
128.38 s). At integration-base commit `63b2712`, the desktop variant failed at that same locator (1 failed, 3 deselected
in 35.11 s). This confirms the reproduced desktop failure is inherited; the full integrated browser suite remains
unverified. The comparison used an existing runtime worktree with unrelated documentation changes, which were preserved.
